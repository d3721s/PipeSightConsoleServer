from __future__ import annotations

import shutil
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PipeSight"
    host: str = "0.0.0.0"
    port: int = 8000

    data_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[1] / "data"
    )
    storage_dir: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[1] / "storage"
    )
    database_url: str | None = None

    mediamtx_exe: Path | None = None
    mediamtx_config: Path = Field(
        default_factory=lambda: (
            Path(__file__).resolve().parents[2]
            / "third_party"
            / "mediamtx"
            / "mediamtx.yml"
        )
    )
    mediamtx_rtsp_port: int = 8554
    mediamtx_webrtc_port: int = 8889
    # Extra IP/hostnames MediaMTX advertises as WebRTC ICE candidates. Leave
    # empty to let MediaMTX auto-detect the server's interface addresses (works
    # on a single LAN). Set it (e.g. the server LAN IP) for Docker / multi-NIC /
    # NAT setups. Comma-separated via PIPESIGHT_MEDIAMTX_WEBRTC_ADDITIONAL_HOSTS.
    mediamtx_webrtc_additional_hosts: list[str] = Field(default_factory=list)

    ffmpeg_exe: str = "ffmpeg"
    recording_segment_minutes: int = 30

    # Chassis Modbus RTU (485 joystick control). The serial device is expected to
    # be a stable udev symlink. Override via PIPESIGHT_CHASSIS_SERIAL_PORT etc.
    chassis_serial_port: str = "/dev/ttyUSB-Chassis"
    chassis_baudrate: int = 38400
    chassis_slave_id: int = 1

    # IMU (ATK-MS901M) — Euler angles over UART.
    imu_serial_port: str = "/dev/ttyUSB-IMU"
    imu_baudrate: int = 115200
    # Light output through the IMU's D1/D3 PWM pins. Defaults mean:
    # 1/off: D1=0%, D3=0%; 2/low: D1=100%, D3=0%; 3/high: D1=0%, D3=100%.
    # Override with PIPESIGHT_IMU_LIGHT_* if the driver expects another duty.
    imu_light_pwm_period_us: int = 1000
    imu_light_low_d1_pulse_us: int = 1000
    imu_light_low_d3_pulse_us: int = 0
    imu_light_high_d1_pulse_us: int = 0
    imu_light_high_d3_pulse_us: int = 1000
    pointcloud_bridge_ws_url: str = "ws://127.0.0.1:9090"
    depth_bridge_ws_url: str = "ws://127.0.0.1:9091"

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PIPESIGHT_")

    @field_validator("mediamtx_webrtc_additional_hosts", mode="before")
    @classmethod
    def _split_hosts(cls, value: object) -> object:
        # Accept a plain comma-separated env value (e.g. "192.168.1.5, host.lan")
        # in addition to a JSON list.
        if isinstance(value, str):
            stripped = value.strip()
            if not stripped or stripped.startswith("["):
                return value
            return [item.strip() for item in stripped.split(",") if item.strip()]
        return value

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return f"sqlite:///{self.data_dir / 'pipesight.db'}"

    @property
    def active_storage_dir(self) -> Path:
        """Storage root actually used for snapshots/recordings/reports.

        Returns the runtime override saved in the DB ("storage" setting, key
        "path") if it is set and usable, otherwise the env/default storage_dir.
        Read lazily and defensively so an unavailable DB or a vanished USB drive
        never breaks startup — we just fall back to the default.
        """
        override = self._storage_override()
        if override is not None:
            try:
                override.mkdir(parents=True, exist_ok=True)
                self._ensure_subdirs(override)
                return override
            except OSError:
                pass  # e.g. unplugged USB -> fall back to default
        return self.storage_dir

    @staticmethod
    def _storage_override() -> Path | None:
        # Imported lazily to avoid a config<->db import cycle.
        try:
            from sqlalchemy import select

            from app.db import SessionLocal
            from app.models import SystemSetting
        except Exception:
            return None
        try:
            with SessionLocal() as db:
                row = db.scalar(
                    select(SystemSetting).where(SystemSetting.key == "storage")
                )
        except Exception:
            return None
        value = (row.value_json or {}) if row else {}
        path = value.get("path")
        if isinstance(path, str) and path.strip():
            return Path(path.strip())
        return None

    @staticmethod
    def _ensure_subdirs(base: Path) -> None:
        (base / "snapshots").mkdir(parents=True, exist_ok=True)
        (base / "recordings").mkdir(parents=True, exist_ok=True)
        (base / "reports").mkdir(parents=True, exist_ok=True)
        (base / "annotations").mkdir(parents=True, exist_ok=True)
        (base / "annotations" / "rendered").mkdir(parents=True, exist_ok=True)

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        self._ensure_subdirs(self.storage_dir)
        self.mediamtx_config.parent.mkdir(parents=True, exist_ok=True)

    @property
    def resolved_mediamtx_exe(self) -> Path | None:
        # Honor an explicit path only if it actually exists; otherwise fall
        # through to auto-discovery so a stale .env value can't mask a working
        # install (and so health reports the truth instead of a phantom path).
        if self.mediamtx_exe and self.mediamtx_exe.exists():
            return self.mediamtx_exe

        from_path = shutil.which("mediamtx")
        if from_path:
            return Path(from_path)

        root = Path(__file__).resolve().parents[2]
        candidates = [
            root / "third_party" / "mediamtx" / "mediamtx",
        ]
        return next((candidate for candidate in candidates if candidate.exists()), None)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_dirs()
    return settings
