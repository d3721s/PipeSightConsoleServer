from __future__ import annotations

import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.services.osd_service import build_ffmpeg_osd_filter, osd_text


settings = get_settings()


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
            fh.write(osd_text(project_name, project_location))
        vf = build_ffmpeg_osd_filter(osd_name, reload=False)
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


def save_png_snapshot(png_data_url: str, *, prefix: str = "PipeSight_3d") -> str:
    """Save a client-supplied PNG (e.g. a 3D canvas capture) to the snapshots dir.

    The 3D point-cloud view is rendered in the browser, so unlike camera
    snapshots the image can only come from the frontend as a base64 data URL.
    Returns the absolute file path.
    """
    from app.services.annotation_service import _decode_data_url

    snapshot_dir = settings.active_storage_dir / "snapshots"
    snapshot_dir.mkdir(parents=True, exist_ok=True)
    name = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S_%f')[:-3]}.png"
    path = snapshot_dir / name
    path.write_bytes(_decode_data_url(png_data_url))
    return str(path)


def save_depth_raw(png_path: str, depth_raw_base64: str) -> str:
    """Save a base64 raw-depth blob next to its PNG snapshot (same name, .depthbin).

    Lets the annotate page measure real surface area from the saved snapshot.
    Returns the absolute file path of the written blob.
    """
    import base64

    path = Path(png_path).with_suffix(".depthbin")
    path.write_bytes(base64.b64decode(depth_raw_base64))
    return str(path)
