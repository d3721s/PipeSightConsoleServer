from __future__ import annotations

from pathlib import Path

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import get_settings
from app.drivers.rtsp import build_rtsp_url, media_path, recording_media_path
from app.models import CameraDevice


settings = get_settings()


def whep_url(path: str) -> str:
    # Relative path on purpose: the browser may sit on a different machine than
    # the server (tablet over LAN), so a hard-coded host/IP here would point the
    # client at its own machine. The dev server (Vite) and FastAPI both proxy
    # "/whep/*" to MediaMTX, so a relative URL resolves to whatever origin the
    # page was loaded from.
    return f"/whep/{path}/whep"


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
        "rtspUrl": build_rtsp_url(camera, channel, subtype=settings.preview_rtsp_subtype),
        "whepUrl": whep_url(path),
        "recordingRelay": use_recording_relay,
    }


def write_mediamtx_config(db: Session) -> Path:
    cameras = db.scalars(select(CameraDevice)).all()
    lines = [
        f"rtspAddress: :{settings.mediamtx_rtsp_port}",
        "webrtc: yes",
        f"webrtcAddress: :{settings.mediamtx_webrtc_port}",
        # Media flows by UDP straight from the browser to MediaMTX (the WHEP
        # proxy only carries signaling), so this port must be reachable on the
        # server's LAN IP.
        "webrtcLocalUDPAddress: :8189",
    ]
    if settings.mediamtx_webrtc_additional_hosts:
        hosts = ", ".join(settings.mediamtx_webrtc_additional_hosts)
        lines.append(f"webrtcAdditionalHosts: [{hosts}]")
    lines.append("paths:")
    for camera in cameras:
        if not camera.ip:
            continue
        for channel in (1, 2):
            lines.extend(
                [
                    f"  {media_path(camera.code, channel)}:",
                    f"    source: {build_rtsp_url(camera, channel, subtype=settings.preview_rtsp_subtype)}",
                    f"    rtspTransport: {settings.mediamtx_rtsp_transport}",
                    "    sourceOnDemand: yes",
                    # Stop pulling a stream ~1s after the last viewer leaves, so
                    # only the currently-viewed camera+channel is ever decoded
                    # (default is 10s, which made a just-switched-away channel
                    # keep streaming alongside the new one).
                    "    sourceOnDemandCloseAfter: 1s",
                    f"  {recording_media_path(camera.code, channel)}:",
                    "    source: publisher",
                ]
            )
    settings.mediamtx_config.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return settings.mediamtx_config

