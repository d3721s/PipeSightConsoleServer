from __future__ import annotations

from pathlib import Path

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.drivers.rtsp import build_rtsp_url, media_path, recording_media_path
from app.models import CameraDevice


settings = get_settings()


def public_base(request: Request, port: int) -> str:
    host = request.url.hostname or "127.0.0.1"
    return f"http://{host}:{port}"


def whep_url(request: Request, path: str) -> str:
    return f"{public_base(request, settings.mediamtx_webrtc_port)}/{path}/whep"


def stream_payload(
    request: Request,
    camera: CameraDevice,
    channel: int,
    use_recording_relay: bool = False,
) -> dict:
    path = recording_media_path(camera.code, channel) if use_recording_relay else media_path(camera.code, channel)
    return {
        "device": camera.code,
        "channel": channel,
        "path": path,
        "rtspUrl": build_rtsp_url(camera, channel),
        "whepUrl": whep_url(request, path),
        "recordingRelay": use_recording_relay,
    }


def write_mediamtx_config(db: Session) -> Path:
    cameras = db.scalars(select(CameraDevice)).all()
    lines = [
        "rtspAddress: :8554",
        "webrtcAddress: :8889",
        "paths:",
    ]
    for camera in cameras:
        if not camera.ip:
            continue
        for channel in (1, 2):
            lines.extend(
                [
                    f"  {media_path(camera.code, channel)}:",
                    f"    source: {build_rtsp_url(camera, channel)}",
                    f"  {recording_media_path(camera.code, channel)}:",
                    "    source: publisher",
                ]
            )
    settings.mediamtx_config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return settings.mediamtx_config

