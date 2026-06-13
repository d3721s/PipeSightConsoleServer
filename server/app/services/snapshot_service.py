from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime

from app.config import get_settings
from app.services.odometer_service import odometer_service
from app.services.recorder_service import OSD_FONT, _ff_escape_path


settings = get_settings()


def _osd_text(distance_m: float | None, project_name: str, project_location: str) -> str:
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    distance = "--" if distance_m is None else f"{distance_m:.2f}m"
    return (
        f"时间: {now}\n"
        f"距离: {distance}\n"
        f"项目名称: {project_name or '-'}\n"
        f"项目地点: {project_location or '-'}\n"
    )


def take_snapshot(
    rtsp_url: str,
    *,
    project_name: str = "",
    project_location: str = "",
) -> str:
    snapshot_dir = settings.active_storage_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    name = f"PipeSight_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
    path = snapshot_dir / name

    # Render the OSD from a textfile (same approach as recording) to avoid
    # drawtext inline-text escaping pitfalls with ':' and Chinese characters.
    osd_fd, osd_name = tempfile.mkstemp(suffix=".txt", dir=str(snapshot_dir))
    try:
        with os.fdopen(osd_fd, "w", encoding="utf-8") as fh:
            fh.write(_osd_text(odometer_service.get_current_mileage_m(), project_name, project_location))
        font = _ff_escape_path(OSD_FONT)
        textfile = _ff_escape_path(osd_name)
        # Match the live preview overlay (OsdOverlay.vue): white text on a
        # translucent black block with a soft shadow. Kept consistent with
        # recorder_service._build_drawtext_filter.
        vf = (
            f"drawtext=fontfile={font}:textfile={textfile}:"
            "x=30:y=20:fontsize=46:fontcolor=white:"
            "box=1:boxcolor=black@0.45:boxborderw=10:line_spacing=12:"
            "shadowcolor=black@0.8:shadowx=1:shadowy=2"
        )
        command = [
            settings.ffmpeg_exe,
            "-hide_banner",
            "-y",
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-frames:v",
            "1",
            "-vf",
            vf,
            str(path),
        ]
        result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
    finally:
        try:
            os.unlink(osd_name)
        except OSError:
            pass
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "snapshot failed")
    return str(path)
