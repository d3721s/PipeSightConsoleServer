from __future__ import annotations

import json
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db import get_db
from app.drivers.rtsp import build_rtsp_url
from app.models import Annotation, CameraDevice, Marker, MediaAsset, Project
from app.schemas import MediaAssetOut, RecordingStartIn, RecordingStatusOut, SnapshotIn
from app.services.recorder_service import recorder_service
from app.services.odometer_service import odometer_service
from app.services.settings_service import get_setting
from app.services.snapshot_service import take_snapshot


router = APIRouter(prefix="/api", tags=["media"])
settings = get_settings()


def _storage_url(absolute_path: str) -> str | None:
    """Map an absolute file under the active storage dir to its /storage URL."""
    try:
        rel = Path(absolute_path).resolve().relative_to(settings.active_storage_dir.resolve())
    except (ValueError, OSError):
        return None
    return "/storage/" + rel.as_posix()


def _camera_for_request(db: Session, device: str | None, channel: int | None) -> tuple[CameraDevice, int]:
    if device is None or channel is None:
        active = get_setting(db, "active_camera", {"device": "front", "channel": 1})
        device = device or active.get("device", "front")
        channel = channel or int(active.get("channel", 1))
    camera = db.query(CameraDevice).filter(CameraDevice.code == device).one_or_none()
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")
    if not camera.ip:
        raise HTTPException(status_code=400, detail="camera IP is empty")
    return camera, int(channel)


@router.post("/snapshots", response_model=MediaAssetOut)
def create_snapshot(payload: SnapshotIn, db: Session = Depends(get_db)) -> MediaAsset:
    camera, channel = _camera_for_request(db, payload.device, payload.channel)

    project_name = payload.project_name
    project_location = payload.project_location
    if (not project_name or not project_location) and payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is not None:
            project_name = project_name or project.name
            project_location = project_location or project.location

    try:
        path = take_snapshot(
            build_rtsp_url(camera, channel),
            project_name=project_name,
            project_location=project_location,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    asset = MediaAsset(
        project_id=payload.project_id,
        session_id=payload.session_id,
        camera_device=camera.code,
        camera_channel=channel,
        type="photo",
        file_path=path,
        distance_m=payload.distance_m,
    )
    db.add(asset)
    db.commit()
    db.refresh(asset)
    return asset


@router.post("/recordings/start", response_model=RecordingStatusOut)
def start_recording(payload: RecordingStartIn, db: Session = Depends(get_db)) -> dict:
    camera, channel = _camera_for_request(db, payload.device, payload.channel)

    # OSD project lines: prefer values sent by the client, else fall back to the
    # bound project record so the burned-in OSD matches the report.
    project_name = payload.project_name
    project_location = payload.project_location
    if (not project_name or not project_location) and payload.project_id is not None:
        project = db.get(Project, payload.project_id)
        if project is not None:
            project_name = project_name or project.name
            project_location = project_location or project.location

    try:
        state = recorder_service.start(
            build_rtsp_url(camera, channel),
            camera.code,
            channel,
            project_name=project_name,
            project_location=project_location,
            segment_minutes=payload.segment_minutes,
            project_id=payload.project_id,
            session_id=payload.session_id,
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return state.__dict__


@router.post("/recordings/stop", response_model=RecordingStatusOut)
def stop_recording() -> dict:
    return recorder_service.stop().__dict__


@router.get("/recordings/status", response_model=RecordingStatusOut)
def recording_status() -> dict:
    return recorder_service.state.__dict__


@router.get("/odometer")
def odometer() -> dict:
    # Live mileage from the cart's TCP odometer service. The frontend polls this
    # to render the same distance in its OSD overlay as the burned-in recording.
    cm = odometer_service.get_current_mileage_cm()
    return {
        "connected": odometer_service.connected,
        "mileageCm": cm,
        "mileageM": None if cm is None else cm / 100.0,
    }


@router.get("/photos")
def list_photos(db: Session = Depends(get_db)) -> list[dict]:
    # Snapshots, for the image annotation tab.
    assets = db.scalars(
        select(MediaAsset).where(MediaAsset.type == "photo").order_by(MediaAsset.id.desc())
    ).all()
    out: list[dict] = []
    for asset in assets:
        url = _storage_url(asset.file_path)
        out.append(
            {
                "id": asset.id,
                "projectId": asset.project_id,
                "sessionId": asset.session_id,
                "name": Path(asset.file_path).name,
                "capturedAt": asset.captured_at.isoformat(timespec="seconds"),
                "distanceM": asset.distance_m,
                "imageUrl": url,
                "available": url is not None and Path(asset.file_path).exists(),
            }
        )
    return out


@router.get("/recordings")
def list_recordings(db: Session = Depends(get_db)) -> list[dict]:
    # Recorded segments (one MediaAsset per .mp4) for the annotation page to pick.
    assets = db.scalars(
        select(MediaAsset).where(MediaAsset.type == "video").order_by(MediaAsset.id.desc())
    ).all()
    out: list[dict] = []
    for asset in assets:
        video_url = _storage_url(asset.file_path)
        track_path = Path(asset.file_path).with_suffix(".json")
        track_url = _storage_url(str(track_path)) if track_path.exists() else None
        out.append(
            {
                "id": asset.id,
                "projectId": asset.project_id,
                "sessionId": asset.session_id,
                "name": Path(asset.file_path).name,
                "capturedAt": asset.captured_at.isoformat(timespec="seconds"),
                "videoUrl": video_url,
                "trackUrl": track_url,
                "available": video_url is not None and Path(asset.file_path).exists(),
            }
        )
    return out


@router.get("/recordings/{asset_id}/track")
def recording_track(asset_id: int, db: Session = Depends(get_db)) -> dict:
    asset = db.get(MediaAsset, asset_id)
    if asset is None or asset.type != "video":
        raise HTTPException(status_code=404, detail="recording not found")
    track_path = Path(asset.file_path).with_suffix(".json")
    if not track_path.exists():
        return {"video": Path(asset.file_path).name, "samples": []}
    try:
        return json.loads(track_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {"video": Path(asset.file_path).name, "samples": []}


def _unlink(path: str | Path) -> None:
    try:
        Path(path).unlink(missing_ok=True)
    except OSError:
        pass


@router.delete("/media/{asset_id}")
def delete_media(asset_id: int, db: Session = Depends(get_db)) -> dict:
    """Delete a photo/recording: its file (+ video track sidecar), its graphic
    annotations (rows + rendered PNGs) and its marker rows."""
    asset = db.get(MediaAsset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="media not found")

    # Remove the media file itself, and the per-segment track json for videos.
    if asset.file_path:
        _unlink(asset.file_path)
        if asset.type == "video":
            _unlink(Path(asset.file_path).with_suffix(".json"))

    # Remove linked annotations (and their rendered images) + marker mirrors.
    annotations = db.scalars(
        select(Annotation).where(Annotation.media_asset_id == asset_id)
    ).all()
    for annotation in annotations:
        if annotation.rendered_path:
            _unlink(annotation.rendered_path)
        db.delete(annotation)
    markers = db.scalars(select(Marker).where(Marker.media_asset_id == asset_id)).all()
    for marker in markers:
        db.delete(marker)

    db.delete(asset)
    db.commit()
    return {"ok": True}

