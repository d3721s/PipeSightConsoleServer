from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import shutil

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "PipeSight"
    host: str = "0.0.0.0"
    port: int = 8000

    data_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "data")
    storage_dir: Path = Field(default_factory=lambda: Path(__file__).resolve().parents[1] / "storage")
    database_url: str | None = None

    mediamtx_exe: Path | None = None
    mediamtx_config: Path = Field(
        default_factory=lambda: Path(__file__).resolve().parents[2] / "third_party" / "mediamtx" / "mediamtx.yml"
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

    def ensure_dirs(self) -> None:
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self.storage_dir.mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "snapshots").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "recordings").mkdir(parents=True, exist_ok=True)
        (self.storage_dir / "reports").mkdir(parents=True, exist_ok=True)
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
