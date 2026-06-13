from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SystemSetting


def get_setting(db: Session, key: str, default: dict | None = None) -> dict:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        return default or {}
    return row.value_json or {}


def set_setting(db: Session, key: str, value: dict) -> dict:
    row = db.scalar(select(SystemSetting).where(SystemSetting.key == key))
    if row is None:
        row = SystemSetting(key=key, value_json=value)
        db.add(row)
    else:
        row.value_json = value
    db.commit()
    return value


def get_recording_segment_minutes(default: int = 30) -> int:
    """Persisted recording segment length (minutes), read in its own session.

    Used by the recorder when the request does not specify a value. Falls back
    to `default` on any error or invalid stored value.
    """
    try:
        from app.db import SessionLocal

        with SessionLocal() as db:
            value = get_setting(db, "recording", {})
        minutes = int(value.get("segmentMinutes", default))
        return minutes if minutes > 0 else default
    except Exception:
        return default

