from __future__ import annotations

import subprocess
import threading
from dataclasses import dataclass

from app.config import get_settings
from app.db import SessionLocal
from app.services.media_service import write_mediamtx_config


settings = get_settings()


@dataclass
class MediaMtxState:
    running: bool = False
    pid: int | None = None
    exe: str | None = None
    config: str | None = None
    error: str | None = None


class MediaMtxService:
    """Owns the lifecycle of the bundled MediaMTX process.

    MediaMTX is what bridges the camera RTSP stream to the browser over WebRTC
    (WHEP). Nothing else in the project starts it, so the web preview stays black
    unless this service launches it on server startup.
    """

    def __init__(self) -> None:
        self._process: subprocess.Popen | None = None
        self._lock = threading.Lock()
        self._state = MediaMtxState()

    @property
    def state(self) -> MediaMtxState:
        with self._lock:
            if self._process and self._process.poll() is not None:
                self._state.running = False
                self._state.error = f"mediamtx exited with {self._process.returncode}"
                self._process = None
            return self._state

    def start(self) -> MediaMtxState:
        with self._lock:
            if self._process and self._process.poll() is None:
                return self._state

            exe = settings.resolved_mediamtx_exe
            if exe is None:
                self._state = MediaMtxState(
                    running=False,
                    error="mediamtx executable not found (set PIPESIGHT_MEDIAMTX_EXE)",
                )
                return self._state

            # Always (re)generate the config so the camera paths exist even if the
            # operator never saved a camera through the API.
            with SessionLocal() as db:
                config_path = write_mediamtx_config(db)

            try:
                # Inherit the server's stdout/stderr so MediaMTX logs (including
                # why it rejects a WHEP request) show up in the run.sh terminal.
                self._process = subprocess.Popen([str(exe), str(config_path)])
            except OSError as exc:
                self._process = None
                self._state = MediaMtxState(
                    running=False,
                    exe=str(exe),
                    config=str(config_path),
                    error=f"failed to launch mediamtx: {exc}",
                )
                return self._state

            self._state = MediaMtxState(
                running=True,
                pid=self._process.pid,
                exe=str(exe),
                config=str(config_path),
                error=None,
            )
            return self._state

    def stop(self) -> None:
        with self._lock:
            process = self._process
            self._process = None
            self._state.running = False
            if process and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    process.kill()

    def reload(self) -> MediaMtxState:
        """Rewrite the config and restart so new camera settings take effect."""
        self.stop()
        return self.start()


mediamtx_service = MediaMtxService()
