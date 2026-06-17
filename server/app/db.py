from __future__ import annotations

from collections.abc import Generator

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app.config import get_settings
from app.models import Base, CameraDevice, SystemSetting


settings = get_settings()
engine = create_engine(
    settings.resolved_database_url,
    connect_args={"check_same_thread": False} if settings.resolved_database_url.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False, expire_on_commit=False)


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    Base.metadata.create_all(bind=engine)
    _upgrade_schema()
    with SessionLocal() as db:
        _seed_camera(db, "front", "前摄")
        _seed_camera(db, "rear", "后摄")
        if db.scalar(select(SystemSetting).where(SystemSetting.key == "active_camera")) is None:
            db.add(SystemSetting(key="active_camera", value_json={"device": "front", "channel": 1}))
        db.commit()


def _upgrade_schema() -> None:
    if not settings.resolved_database_url.startswith("sqlite"):
        return
    with engine.begin() as conn:
        columns = {row[1] for row in conn.exec_driver_sql("PRAGMA table_info(media_assets)")}
        if "left_mileage" not in columns:
            conn.exec_driver_sql("ALTER TABLE media_assets ADD COLUMN left_mileage FLOAT")
        if "right_mileage" not in columns:
            conn.exec_driver_sql("ALTER TABLE media_assets ADD COLUMN right_mileage FLOAT")


def _seed_camera(db: Session, code: str, name: str) -> None:
    existing = db.scalar(select(CameraDevice).where(CameraDevice.code == code))
    if existing:
        return
    db.add(
        CameraDevice(
            code=code,
            name=name,
            ip="",
            username="admin",
            password="",
            onvif_port=80,
            rtsp_port=554,
            status="disconnected",
        )
    )

