from __future__ import annotations

import shutil

from fastapi import APIRouter

from app.config import get_settings
from app.services.mediamtx_service import mediamtx_service
from app.services.recorder_service import recorder_service


router = APIRouter(prefix="/api/system", tags=["system"])
settings = get_settings()


@router.get("/health")
def health() -> dict:
    mediamtx_state = mediamtx_service.state
    return {
        "ok": True,
        "ffmpeg": shutil.which(settings.ffmpeg_exe) is not None,
        "mediamtx": settings.resolved_mediamtx_exe is not None,
        "mediamtxRunning": mediamtx_state.running,
        "mediamtxError": mediamtx_state.error,
        "recording": recorder_service.state.active,
    }


@router.get("/info")
def info() -> dict:
    return {
        "name": settings.app_name,
        "version": "0.1.0",
        "mediamtxExe": str(settings.resolved_mediamtx_exe) if settings.resolved_mediamtx_exe else "",
        "mediamtxConfig": str(settings.mediamtx_config),
        "storageDir": str(settings.storage_dir),
    }
