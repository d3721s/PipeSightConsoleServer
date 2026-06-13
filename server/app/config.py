from __future__ import annotations

from functools import lru_cache
from pathlib import Path
import shutil

from pydantic import Field
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

    ffmpeg_exe: str = "ffmpeg"
    recording_segment_minutes: int = 30

    model_config = SettingsConfigDict(env_file=".env", env_prefix="PIPESIGHT_")

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
        if self.mediamtx_exe:
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
