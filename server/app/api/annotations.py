from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.models import Annotation, Marker, MediaAsset
from app.schemas import AnnotationCreate, MarkerCreate, MarkerOut


router = APIRouter(prefix="/api", tags=["annotations"])


@router.post("/annotations")
def create_annotation(payload: AnnotationCreate, db: Session = Depends(get_db)) -> dict:
    if db.get(MediaAsset, payload.media_asset_id) is None:
        raise HTTPException(status_code=404, detail="media asset not found")
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
        distance_m=payload.distance_m,
    )
    db.add(marker)
    db.commit()
    db.refresh(marker)
    return marker


@router.get("/media/{media_id}/markers", response_model=list[MarkerOut])
def list_markers(media_id: int, db: Session = Depends(get_db)) -> list[Marker]:
    return list(
        db.scalars(
            select(Marker).where(Marker.media_asset_id == media_id).order_by(Marker.distance_m, Marker.id)
        ).all()
    )


@router.put("/markers/{marker_id}", response_model=MarkerOut)
def update_marker(marker_id: int, payload: MarkerCreate, db: Session = Depends(get_db)) -> Marker:
    marker = db.get(Marker, marker_id)
    if not marker:
        raise HTTPException(status_code=404, detail="marker not found")
    for key, value in payload.model_dump(by_alias=False).items():
        setattr(marker, key, value)
    db.commit()
    db.refresh(marker)
    return marker


@router.delete("/markers/{marker_id}")
def delete_marker(marker_id: int, db: Session = Depends(get_db)) -> dict:
    marker = db.get(Marker, marker_id)
    if not marker:
        raise HTTPException(status_code=404, detail="marker not found")
    db.delete(marker)
    db.commit()
    return {"ok": True}

