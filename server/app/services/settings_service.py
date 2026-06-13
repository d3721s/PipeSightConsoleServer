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

