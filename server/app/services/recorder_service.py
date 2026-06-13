from __future__ import annotations

import os
import subprocess
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.services.odometer_service import odometer_service


settings = get_settings()

# OSD font. Install on the cart with: sudo apt install -y fonts-wqy-zenhei
OSD_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OSD_TEXT_REFRESH_S = 0.2  # how often the dynamic OSD textfile is rewritten


@dataclass
class RecordingState:
    active: bool = False
    device: str | None = None
    channel: int | None = None
    started_at: datetime | None = None
    output_pattern: str | None = None
    error: str | None = None
    project_name: str = ""
    project_location: str = ""


def _ff_escape_path(path: str) -> str:
    # Inside an ffmpeg filter argument, ':' and '\' must be escaped.
    return path.replace("\\", "\\\\").replace(":", "\\:")


class RecorderService:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._state = RecordingState()
        self._osd_textfile: Path | None = None
        self._osd_stop = threading.Event()
        self._osd_thread: threading.Thread | None = None

    @property
    def state(self) -> RecordingState:
        if self._process and self._process.poll() is not None:
            self._state.active = False
            self._state.error = f"ffmpeg exited with {self._process.returncode}"
            self._process = None
            self._stop_osd_writer()
        return self._state

    def active_for(self, device: str, channel: int) -> bool:
        state = self.state
        return state.active and state.device == device and state.channel == channel

    def start(
        self,
        rtsp_url: str,
        device: str,
        channel: int,
        *,
        project_name: str = "",
        project_location: str = "",
        segment_minutes: int | None = None,
    ) -> RecordingState:
        if self.state.active:
            raise RuntimeError("recording already active")

        recording_dir = settings.storage_dir / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pattern = recording_dir / f"PipeSight_{stamp}_%03d.mp4"
        minutes = segment_minutes if segment_minutes and segment_minutes > 0 else settings.recording_segment_minutes
        segment_seconds = max(1, minutes) * 60

        # Dynamic OSD lines (distance + project) are rendered from a textfile that
        # a background thread rewrites with the live odometer value. The time line
        # uses ffmpeg's built-in localtime so it ticks every second regardless.
        self._osd_textfile = recording_dir / f".osd_{stamp}.txt"
        self._state = RecordingState(
            active=True,
            device=device,
            channel=channel,
            started_at=datetime.now(),
            output_pattern=str(pattern),
            error=None,
            project_name=project_name,
            project_location=project_location,
        )
        self._write_osd_text()  # ensure the file exists before ffmpeg starts
        self._start_osd_writer()

        vf = self._build_drawtext_filter(self._osd_textfile)
        command = [
            settings.ffmpeg_exe,
            "-hide_banner",
            "-y",
            "-rtsp_transport",
            "tcp",
            "-i",
            rtsp_url,
            "-map",
            "0:v:0",
            "-vf",
            vf,
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "23",
            "-an",
            "-f",
            "segment",
            "-segment_time",
            str(segment_seconds),
            "-reset_timestamps",
            "1",
            pattern.as_posix(),
        ]

        try:
            self._process = subprocess.Popen(
                command,
                stdin=subprocess.PIPE,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.PIPE,
                text=True,
            )
        except OSError:
            self._stop_osd_writer()
            self._state.active = False
            raise
        return self._state

    def stop(self) -> RecordingState:
        process = self._process
        if process and process.poll() is None:
            try:
                if process.stdin:
                    process.stdin.write("q")
                    process.stdin.flush()
            except OSError:
                pass
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.terminate()
                try:
                    process.wait(timeout=2)
                except subprocess.TimeoutExpired:
                    process.kill()
        self._process = None
        self._state.active = False
        self._stop_osd_writer()
        return self._state

    # --- OSD rendering -----------------------------------------------------

    def _build_drawtext_filter(self, textfile: Path) -> str:
        font = _ff_escape_path(OSD_FONT)
        common = (
            f"fontfile={font}:fontsize=40:fontcolor=yellow:"
            "box=1:boxcolor=black@0.4:boxborderw=8"
        )
        # Line 1: live clock (built-in). Lines 2-4: distance/project/location from
        # the textfile (reload=1 re-reads it every frame). x=20 keeps it top-left.
        time_text = "时间\\: %{localtime\\:%Y-%m-%d %H\\\\\\:%M\\\\\\:%S}"
        time_layer = f"drawtext={common}:x=20:y=20:text='{time_text}'"
        body_file = _ff_escape_path(str(textfile))
        body_layer = f"drawtext={common}:x=20:y=75:textfile={body_file}:reload=1"
        return f"{time_layer},{body_layer}"

    def _osd_body_text(self) -> str:
        mileage_m = odometer_service.get_current_mileage_m()
        distance = "距离: --" if mileage_m is None else f"距离: {mileage_m:.2f}m"
        name = self._state.project_name or "-"
        location = self._state.project_location or "-"
        # textfile content is rendered literally by ffmpeg; newlines => new lines.
        return f"{distance}\n项目名称: {name}\n项目地点: {location}\n"

    def _write_osd_text(self) -> None:
        textfile = self._osd_textfile
        if textfile is None:
            return
        # Atomic replace so ffmpeg never reads a half-written file (avoids flicker).
        tmp = textfile.with_suffix(".tmp")
        tmp.write_text(self._osd_body_text(), encoding="utf-8")
        os.replace(tmp, textfile)

    def _start_osd_writer(self) -> None:
        self._osd_stop.clear()
        self._osd_thread = threading.Thread(target=self._osd_loop, name="osd-writer", daemon=True)
        self._osd_thread.start()

    def _osd_loop(self) -> None:
        while not self._osd_stop.is_set():
            try:
                self._write_osd_text()
            except OSError:
                pass
            time.sleep(OSD_TEXT_REFRESH_S)

    def _stop_osd_writer(self) -> None:
        self._osd_stop.set()
        textfile = self._osd_textfile
        if textfile is not None:
            for path in (textfile, textfile.with_suffix(".tmp")):
                try:
                    path.unlink(missing_ok=True)
                except OSError:
                    pass
        self._osd_textfile = None


recorder_service = RecorderService()
