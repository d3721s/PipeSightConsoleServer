from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from app.db import get_db
from app.drivers.rtsp import build_rtsp_url
from app.models import CameraDevice, MediaAsset, Project
from app.schemas import MediaAssetOut, RecordingStartIn, RecordingStatusOut, SnapshotIn
from app.services.recorder_service import recorder_service
from app.services.odometer_service import odometer_service
from app.services.settings_service import get_setting
from app.services.snapshot_service import take_snapshot


router = APIRouter(prefix="/api", tags=["media"])


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
    try:
        path = take_snapshot(build_rtsp_url(camera, channel))
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

