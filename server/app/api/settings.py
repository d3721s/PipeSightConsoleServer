from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.db import get_db
from app.services.settings_service import get_setting, set_setting


router = APIRouter(prefix="/api/settings", tags=["settings"])


@router.get("")
def read_settings(db: Session = Depends(get_db)) -> dict:
    return {
        "ui": get_setting(db, "ui", {"language": "zh-CN"}),
        "storage": get_setting(db, "storage", {}),
        "osd": get_setting(db, "osd", {"showProject": True, "showTime": True}),
    }


@router.put("")
def write_settings(payload: dict, db: Session = Depends(get_db)) -> dict:
    for key in ("ui", "storage", "osd"):
        if key in payload and isinstance(payload[key], dict):
            set_setting(db, key, payload[key])
    return read_settings(db)

