from __future__ import annotations

import subprocess
from datetime import datetime

from app.config import get_settings


settings = get_settings()


def take_snapshot(rtsp_url: str) -> str:
    snapshot_dir = settings.active_storage_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    name = f"PipeSight_snapshot_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
    path = snapshot_dir / name
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
        str(path),
    ]
    result = subprocess.run(command, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE, text=True, timeout=15)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "snapshot failed")
    return str(path)

