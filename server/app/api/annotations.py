from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.models import Annotation, Marker, MediaAsset
from app.schemas import AnnotationCreate, GraphicAnnotationIn, MarkerCreate, MarkerOut
from app.services import annotation_service


router = APIRouter(prefix="/api", tags=["annotations"])
settings = get_settings()


def _storage_url(absolute_path: str) -> str | None:
    try:
        rel = Path(absolute_path).resolve().relative_to(settings.active_storage_dir.resolve())
    except (ValueError, OSError):
        return None
    return "/storage/" + rel.as_posix()


@router.post("/annotations")
def create_annotation(payload: AnnotationCreate, db: Session = Depends(get_db)) -> dict:
    if db.get(MediaAsset, payload.media_asset_id) is None:
        raise HTTPException(status_code=404, detail="未找到该文件")
    annotation = Annotation(
        media_asset_id=payload.media_asset_id,
        annotation_json=payload.annotation_json,
        rendered_path=payload.rendered_path,
    )
    db.add(annotation)
    db.commit()
    db.refresh(annotation)
    return {"id": annotation.id}


@router.get("/media/{media_id}/annotations")
def list_annotations(media_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(select(Annotation).where(Annotation.media_asset_id == media_id)).all()
    return [
        {
            "id": row.id,
            "mediaAssetId": row.media_asset_id,
            "annotationJson": row.annotation_json,
            "renderedPath": row.rendered_path,
            "createdAt": row.created_at,
        }
        for row in rows
    ]


@router.post("/markers", response_model=MarkerOut)
def create_marker(payload: MarkerCreate, db: Session = Depends(get_db)) -> Marker:
    marker = Marker(
        project_id=payload.project_id,
        session_id=payload.session_id,
        media_asset_id=payload.media_asset_id,
        defect_type=payload.defect_type,
        defect_code=payload.defect_code,
        severity=payload.severity,
        direction=payload.direction,
        position=payload.position,
        note=payload.note,
        left_mileage=payload.left_mileage,
        right_mileage=payload.right_mileage,
    )
    db.add(marker)
    db.commit()
    db.refresh(marker)
    return marker


@router.get("/media/{media_id}/markers", response_model=list[MarkerOut])
def list_markers(media_id: int, db: Session = Depends(get_db)) -> list[Marker]:
    return list(
        db.scalars(
            select(Marker).where(Marker.media_asset_id == media_id).order_by(Marker.left_mileage, Marker.id)
        ).all()
    )


@router.put("/markers/{marker_id}", response_model=MarkerOut)
def update_marker(marker_id: int, payload: MarkerCreate, db: Session = Depends(get_db)) -> Marker:
    marker = db.get(Marker, marker_id)
    if not marker:
        raise HTTPException(status_code=404, detail="未找到该标记")
    for key, value in payload.model_dump(by_alias=False).items():
        setattr(marker, key, value)
    db.commit()
    db.refresh(marker)
    return marker


@router.delete("/markers/{marker_id}")
def delete_marker(marker_id: int, db: Session = Depends(get_db)) -> dict:
    marker = db.get(Marker, marker_id)
    if not marker:
        raise HTTPException(status_code=404, detail="未找到该标记")
    db.delete(marker)
    db.commit()
    return {"ok": True}


# --- graphical annotations (image / video frame) ---------------------------


def _annotation_out(ann: Annotation) -> dict:
    data = ann.annotation_json or {}
    return {
        "id": ann.id,
        "mediaAssetId": ann.media_asset_id,
        "renderedUrl": _storage_url(ann.rendered_path) if ann.rendered_path else None,
        "sourceType": data.get("sourceType"),
        "videoTime": data.get("videoTime"),
        "defect": data.get("defect", {}),
        "shapes": data.get("shapes", []),
        "baseSize": data.get("baseSize", {}),
        "createdAt": ann.created_at.isoformat(timespec="seconds"),
    }


@router.post("/graphic-annotations")
def create_graphic_annotation(payload: GraphicAnnotationIn, db: Session = Depends(get_db)) -> dict:
    if payload.media_asset_id is not None and db.get(MediaAsset, payload.media_asset_id) is None:
        raise HTTPException(status_code=404, detail="未找到该文件")

    defect = {
        "type": payload.defect_type,
        "code": payload.defect_code,
        "severity": payload.severity,
        "direction": payload.direction,
        "position": payload.position,
        "note": payload.note,
        "leftMileage": payload.left_mileage,
        "rightMileage": payload.right_mileage,
    }
    annotation_json = {
        "sourceType": payload.source_type,
        "mediaAssetId": payload.media_asset_id,
        "videoTime": payload.video_time,
        "shapes": payload.shapes,
        "baseSize": payload.base_size,
        "defect": defect,
    }

    try:
        rendered_path, _json_path, stored = annotation_service.save_annotation(
            annotation_json=annotation_json,
            rendered_png_data_url=payload.rendered_png,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    annotation = Annotation(
        media_asset_id=payload.media_asset_id or 0,
        session_id=payload.session_id,
        annotation_json=stored,
        rendered_path=str(rendered_path) if rendered_path else "",
    )
    db.add(annotation)

    # Mirror the defect into a Marker row for reporting/listing.
    marker = Marker(
        project_id=payload.project_id,
        session_id=payload.session_id,
        media_asset_id=payload.media_asset_id,
        defect_type=payload.defect_type,
        defect_code=payload.defect_code,
        severity=payload.severity,
        direction=payload.direction,
        position=payload.position,
        note=payload.note,
        left_mileage=payload.left_mileage,
        right_mileage=payload.right_mileage,
    )
    db.add(marker)
    db.commit()
    db.refresh(annotation)
    return _annotation_out(annotation)


@router.get("/media/{media_id}/graphic-annotations")
def list_graphic_annotations(media_id: int, db: Session = Depends(get_db)) -> list[dict]:
    rows = db.scalars(
        select(Annotation).where(Annotation.media_asset_id == media_id).order_by(Annotation.id.desc())
    ).all()
    return [_annotation_out(row) for row in rows]


@router.delete("/graphic-annotations/{annotation_id}")
def delete_graphic_annotation(annotation_id: int, db: Session = Depends(get_db)) -> dict:
    ann = db.get(Annotation, annotation_id)
    if not ann:
        raise HTTPException(status_code=404, detail="未找到该标注")
    # Best-effort cleanup of the rendered file.
    if ann.rendered_path:
        try:
            Path(ann.rendered_path).unlink(missing_ok=True)
        except OSError:
            pass
    db.delete(ann)
    db.commit()
    return {"ok": True}

