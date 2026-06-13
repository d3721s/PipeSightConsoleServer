from __future__ import annotations

from urllib.parse import quote

from app.models import CameraDevice


def build_rtsp_url(camera: CameraDevice, channel: int) -> str:
    username = quote(camera.username or "")
    password = quote(camera.password or "")
    auth = f"{username}:{password}@" if username or password else ""
    port = camera.rtsp_port or 554
    return (
        f"rtsp://{auth}{camera.ip}:{port}/cam/realmonitor"
        f"?channel={channel}&subtype=0&unicast=true&proto=Onvif"
    )


def media_path(device: str, channel: int) -> str:
    return f"{device}_{channel}"


def recording_media_path(device: str, channel: int) -> str:
    return f"recording_{device}_{channel}"

