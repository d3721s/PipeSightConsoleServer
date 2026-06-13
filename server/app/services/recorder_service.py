from __future__ import annotations

import subprocess
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.drivers.rtsp import recording_media_path


settings = get_settings()


@dataclass
class RecordingState:
    active: bool = False
    device: str | None = None
    channel: int | None = None
    started_at: datetime | None = None
    output_pattern: str | None = None
    relay_path: str | None = None
    error: str | None = None


class RecorderService:
    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._state = RecordingState()

    @property
    def state(self) -> RecordingState:
        if self._process and self._process.poll() is not None:
            self._state.active = False
            self._state.error = f"ffmpeg exited with {self._process.returncode}"
            self._process = None
        return self._state

    def active_for(self, device: str, channel: int) -> bool:
        state = self.state
        return state.active and state.device == device and state.channel == channel

    def start(self, rtsp_url: str, device: str, channel: int) -> RecordingState:
        if self.state.active:
            raise RuntimeError("recording already active")

        recording_dir = settings.storage_dir / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pattern = recording_dir / f"PipeSight_{stamp}_%03d.mp4"
        relay_path = recording_media_path(device, channel)
        relay_url = f"rtsp://127.0.0.1:{settings.mediamtx_rtsp_port}/{relay_path}"
        segment_seconds = max(1, settings.recording_segment_minutes) * 60

        tee = (
            f"[f=segment:segment_time={segment_seconds}:reset_timestamps=1]"
            f"{pattern.as_posix()}|[f=rtsp:rtsp_transport=tcp]{relay_url}"
        )
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
            "-c:v",
            "copy",
            "-an",
            "-f",
            "tee",
            tee,
        ]

        self._process = subprocess.Popen(
            command,
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._state = RecordingState(
            active=True,
            device=device,
            channel=channel,
            started_at=datetime.now(),
            output_pattern=str(pattern),
            relay_path=relay_path,
            error=None,
        )
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
        return self._state


recorder_service = RecorderService()

