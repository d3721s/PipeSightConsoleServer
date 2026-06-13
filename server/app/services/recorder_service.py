from __future__ import annotations

import json
import os
import subprocess
import threading
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from app.config import get_settings
from app.services.odometer_service import odometer_service
from app.services.settings_service import get_recording_segment_minutes


settings = get_settings()

# OSD font. Install on the cart with: sudo apt install -y fonts-wqy-zenhei
OSD_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OSD_TEXT_REFRESH_S = 0.2  # how often the dynamic OSD textfile is rewritten
TRACK_SAMPLE_S = 1.0      # how often a mileage sample is buffered (one row/sec)


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

        # Mileage history captured during the recording, used to write a per-
        # segment .json (videoTime -> raw odometer JSON) for the annotation page.
        self._track_lock = threading.Lock()
        self._track: list[tuple[float, dict]] = []  # (wall_epoch, raw_json)
        self._track_thread: threading.Thread | None = None
        self._t0: float = 0.0

        # Segment-list watcher: ffmpeg writes the actual segment files it cuts to
        # a CSV; we tail it to slice the mileage and to register each segment.
        self._segment_list: Path | None = None
        self._watch_thread: threading.Thread | None = None
        self._project_id: int | None = None
        self._session_id: int | None = None
        self._processed_segments: set[str] = set()

    @property
    def state(self) -> RecordingState:
        if self._process and self._process.poll() is not None:
            self._finish()
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
        project_id: int | None = None,
        session_id: int | None = None,
    ) -> RecordingState:
        if self.state.active:
            raise RuntimeError("recording already active")

        recording_dir = settings.active_storage_dir / "recordings"
        recording_dir.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        pattern = recording_dir / f"PipeSight_{stamp}_%03d.mp4"
        # Segment length: explicit arg wins, else the persisted setting, else default.
        if segment_minutes and segment_minutes > 0:
            minutes = segment_minutes
        else:
            minutes = get_recording_segment_minutes(settings.recording_segment_minutes)
        segment_seconds = max(1, minutes) * 60

        self._osd_textfile = recording_dir / f".osd_{stamp}.txt"
        self._segment_list = recording_dir / f".segments_{stamp}.csv"
        self._project_id = project_id
        self._session_id = session_id
        self._processed_segments = set()
        self._track = []
        self._t0 = time.time()

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
        self._write_osd_text()  # ensure the OSD file exists before ffmpeg starts
        self._start_workers()

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
            "-segment_list",
            self._segment_list.as_posix(),
            "-segment_list_type",
            "csv",
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
            self._stop_workers()
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
        self._finish()
        return self._state

    def _finish(self) -> None:
        """Tear down workers, drain any final segment, and clear state once."""
        if not self._state.active and self._process is None:
            return
        if self._process is not None and self._process.poll() is not None and self._state.error is None:
            rc = self._process.returncode
            if rc not in (0, 255):  # 255 == graceful 'q' quit
                self._state.error = f"ffmpeg exited with {rc}"
        self._process = None
        self._state.active = False
        self._stop_workers()
        # Final drain: the last segment's CSV line is written when ffmpeg closes.
        try:
            self._drain_segments()
        except Exception:
            pass
        self._cleanup_temp()

    # --- background workers -------------------------------------------------

    def _start_workers(self) -> None:
        self._osd_stop.clear()
        self._osd_thread = threading.Thread(target=self._osd_loop, name="osd-writer", daemon=True)
        self._track_thread = threading.Thread(target=self._track_loop, name="track-sampler", daemon=True)
        self._watch_thread = threading.Thread(target=self._watch_loop, name="segment-watch", daemon=True)
        self._osd_thread.start()
        self._track_thread.start()
        self._watch_thread.start()

    def _stop_workers(self) -> None:
        self._osd_stop.set()
        for thread in (self._osd_thread, self._track_thread, self._watch_thread):
            if thread and thread.is_alive():
                thread.join(timeout=2)
        self._osd_thread = None
        self._track_thread = None
        self._watch_thread = None

    def _osd_loop(self) -> None:
        while not self._osd_stop.is_set():
            try:
                self._write_osd_text()
            except OSError:
                pass
            time.sleep(OSD_TEXT_REFRESH_S)

    def _track_loop(self) -> None:
        # One mileage sample per second, storing the cart's whole JSON verbatim.
        next_t = time.time()
        while not self._osd_stop.is_set():
            raw = odometer_service.get_current_raw()
            if raw is not None:
                with self._track_lock:
                    self._track.append((time.time(), raw))
            next_t += TRACK_SAMPLE_S
            time.sleep(max(0.0, next_t - time.time()))

    def _watch_loop(self) -> None:
        while not self._osd_stop.is_set():
            try:
                self._drain_segments()
            except Exception:
                pass
            time.sleep(1.0)

    # --- segment list -> per-segment json + DB asset ------------------------

    def _drain_segments(self) -> None:
        seg_list = self._segment_list
        if seg_list is None or not seg_list.exists():
            return
        try:
            lines = seg_list.read_text(encoding="utf-8").splitlines()
        except OSError:
            return
        for line in lines:
            parts = line.split(",")
            if len(parts) < 3:
                continue
            name = parts[0].strip()
            if not name or name in self._processed_segments:
                continue
            try:
                start_s = float(parts[1])
                end_s = float(parts[2])
            except ValueError:
                continue
            self._processed_segments.add(name)
            mp4_path = seg_list.parent / name
            self._write_segment_track(mp4_path, start_s, end_s)
            self._register_segment(mp4_path)

    def _write_segment_track(self, mp4_path: Path, start_s: float, end_s: float) -> None:
        seg_t0 = self._t0 + start_s
        seg_t1 = self._t0 + end_s
        with self._track_lock:
            rows = [
                {"videoTime": round(wall - seg_t0, 2), "raw": raw}
                for wall, raw in self._track
                if seg_t0 - 0.5 <= wall <= seg_t1 + 0.5
            ]
        payload = {
            "video": mp4_path.name,
            "startedAt": datetime.fromtimestamp(seg_t0).isoformat(timespec="seconds"),
            "durationS": round(end_s - start_s, 2),
            "samples": rows,
        }
        track_path = mp4_path.with_suffix(".json")
        try:
            tmp = track_path.with_suffix(".json.tmp")
            tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
            os.replace(tmp, track_path)
        except OSError:
            pass

    def _register_segment(self, mp4_path: Path) -> None:
        # Insert a MediaAsset row so the annotation page can list this recording.
        try:
            from app.db import SessionLocal
            from app.models import MediaAsset
        except Exception:
            return
        try:
            with SessionLocal() as db:
                exists = db.query(MediaAsset).filter(MediaAsset.file_path == str(mp4_path)).first()
                if exists:
                    return
                asset = MediaAsset(
                    project_id=self._project_id,
                    session_id=self._session_id,
                    camera_device=self._state.device or "front",
                    camera_channel=self._state.channel or 1,
                    type="video",
                    file_path=str(mp4_path),
                )
                db.add(asset)
                db.commit()
        except Exception:
            pass

    def _cleanup_temp(self) -> None:
        for path in (self._osd_textfile, self._segment_list):
            if path is None:
                continue
            for candidate in (path, path.with_suffix(path.suffix + ".tmp"), path.with_suffix(".tmp")):
                try:
                    candidate.unlink(missing_ok=True)
                except OSError:
                    pass
        self._osd_textfile = None
        self._segment_list = None

    # --- OSD rendering -----------------------------------------------------

    def _build_drawtext_filter(self, textfile: Path) -> str:
        font = _ff_escape_path(OSD_FONT)
        # Match the live preview overlay (OsdOverlay.vue): white text on a
        # translucent black block with a soft shadow.
        common = (
            f"fontfile={font}:fontsize=46:fontcolor=white:"
            "box=1:boxcolor=black@0.45:boxborderw=10:line_spacing=12:"
            "shadowcolor=black@0.8:shadowx=1:shadowy=2"
        )
        time_text = "时间\\: %{localtime\\:%Y-%m-%d %H\\\\\\:%M\\\\\\:%S}"
        time_layer = f"drawtext={common}:x=30:y=20:text='{time_text}'"
        body_file = _ff_escape_path(str(textfile))
        body_layer = f"drawtext={common}:x=30:y=90:textfile={body_file}:reload=1"
        return f"{time_layer},{body_layer}"

    def _osd_body_text(self) -> str:
        mileage_m = odometer_service.get_current_mileage_m()
        distance = "距离: --" if mileage_m is None else f"距离: {mileage_m:.2f}m"
        name = self._state.project_name or "-"
        location = self._state.project_location or "-"
        return f"{distance}\n项目名称: {name}\n项目地点: {location}\n"

    def _write_osd_text(self) -> None:
        textfile = self._osd_textfile
        if textfile is None:
            return
        tmp = textfile.with_suffix(".tmp")
        tmp.write_text(self._osd_body_text(), encoding="utf-8")
        os.replace(tmp, textfile)


recorder_service = RecorderService()
