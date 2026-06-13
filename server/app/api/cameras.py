from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.drivers.onvif_client import OnvifError
from app.drivers.onvif_ptz import ptz_driver
from app.models import CameraDevice
from app.schemas import ActiveCameraIn, CameraChannelOut, CameraConfigIn, CameraOut, StreamOut
from app.services.media_service import stream_payload, write_mediamtx_config
from app.services.mediamtx_service import mediamtx_service
from app.services.recorder_service import recorder_service
from app.services.settings_service import get_setting, set_setting


router = APIRouter(prefix="/api/cameras", tags=["cameras"])


def get_camera(db: Session, code: str) -> CameraDevice:
    camera = db.scalar(select(CameraDevice).where(CameraDevice.code == code))
    if not camera:
        raise HTTPException(status_code=404, detail="camera not found")
    return camera


@router.get("", response_model=list[CameraOut])
def list_cameras(db: Session = Depends(get_db)) -> list[CameraDevice]:
    return list(db.scalars(select(CameraDevice).order_by(CameraDevice.id)).all())


@router.get("/{device}/config", response_model=CameraOut)
def read_camera_config(device: str, db: Session = Depends(get_db)) -> CameraDevice:
    return get_camera(db, device)


@router.put("/{device}/config", response_model=CameraOut)
def update_camera_config(device: str, payload: CameraConfigIn, db: Session = Depends(get_db)) -> CameraDevice:
    camera = get_camera(db, device)
    camera.ip = payload.ip.strip()
    camera.username = payload.username.strip()
    camera.password = payload.password
    camera.onvif_port = 80
    camera.rtsp_port = payload.rtsp_port or 554
    camera.status = "connecting" if camera.ip else "disconnected"
    ptz_driver.invalidate(camera)
    db.commit()
    db.refresh(camera)
    write_mediamtx_config(db)
    mediamtx_service.reload()
    return camera


@router.post("/{device}/probe-onvif")
async def probe_onvif(device: str, db: Session = Depends(get_db)) -> dict:
    camera = get_camera(db, device)
    try:
        session = await ptz_driver.probe(camera)
    except OnvifError as exc:
        camera.status = "disconnected"
        db.commit()
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    camera.status = "connected"
    db.commit()
    return {
        "ok": True,
        "device": device,
        "profileToken": session.profile_token,
        "ptzUrl": session.ptz_url,
        "media2Url": session.media2_url,
    }


@router.get("/{device}/channels", response_model=list[CameraChannelOut])
def camera_channels(device: str, db: Session = Depends(get_db)) -> list[dict]:
    get_camera(db, device)
    return [
        {"channel": 1, "type": "ptz", "name": "云台", "ptzEnabled": True},
        {"channel": 2, "type": "fixed", "name": "固定", "ptzEnabled": False},
    ]


@router.post("/active")
def set_active_camera(payload: ActiveCameraIn, db: Session = Depends(get_db)) -> dict:
    get_camera(db, payload.device)
    value = {"device": payload.device, "channel": payload.channel}
    set_setting(db, "active_camera", value)
    return value


@router.get("/active")
def get_active_camera(db: Session = Depends(get_db)) -> dict:
    return get_setting(db, "active_camera", {"device": "front", "channel": 1})


@router.get("/active/stream", response_model=StreamOut)
def get_active_stream(request: Request, db: Session = Depends(get_db)) -> dict:
    active = get_setting(db, "active_camera", {"device": "front", "channel": 1})
    device = active.get("device", "front")
    channel = int(active.get("channel", 1))
    camera = get_camera(db, device)
    if not camera.ip:
        raise HTTPException(status_code=400, detail="camera IP is empty")
    use_relay = recorder_service.active_for(device, channel)
    return stream_payload(request, camera, channel, use_relay)

