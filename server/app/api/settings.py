from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.db import get_db
from app.services import storage_service
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


@router.get("/storage")
def read_storage(db: Session = Depends(get_db)) -> dict:
    # Current path + internal default + currently-mounted removable drives.
    return storage_service.options()


class StoragePathIn(BaseModel):
    path: str | None = None  # None / "" => reset to internal default


@router.put("/storage")
def write_storage(payload: StoragePathIn, db: Session = Depends(get_db)) -> dict:
    raw = (payload.path or "").strip()
    if not raw:
        # Reset to internal default.
        set_setting(db, "storage", {})
    else:
        try:
            target = storage_service.validate_path(raw)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        set_setting(db, "storage", {"path": target.path})

    result = storage_service.options()
    # Path is resolved at process startup, so a running server keeps using the
    # old location until restarted. Tell the UI so it can prompt the user.
    result["restartRequired"] = True
    return result


@router.get("/recording")
def read_recording(db: Session = Depends(get_db)) -> dict:
    value = get_setting(db, "recording", {})
    return {"segmentMinutes": int(value.get("segmentMinutes", 30)), "default": 30}


class RecordingSettingsIn(BaseModel):
    segment_minutes: int = Field(default=30, alias="segmentMinutes", ge=1)


@router.put("/recording")
def write_recording(payload: RecordingSettingsIn, db: Session = Depends(get_db)) -> dict:
    set_setting(db, "recording", {"segmentMinutes": payload.segment_minutes})
    return read_recording(db)

