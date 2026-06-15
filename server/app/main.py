from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import annotations, cameras, chassis, media, media_proxy, projects, reports, settings, system
from app.config import get_settings
from app.db import init_db
from app.services.mediamtx_service import mediamtx_service
from app.services.modbus_service import modbus_chassis_service
from app.services.imu_service import imu_service
from app.services.odometer_service import odometer_service
from app.services.storage_service import enforce_media_quota
from app.ws import camera_control


settings_obj = get_settings()

app = FastAPI(title="PipeSight API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def on_startup() -> None:
    init_db()
    try:
        enforce_media_quota()
    except Exception:
        pass
    mediamtx_service.start()
    odometer_service.start()
    modbus_chassis_service.start()
    imu_service.start()


@app.on_event("shutdown")
def on_shutdown() -> None:
    mediamtx_service.stop()
    odometer_service.stop()
    modbus_chassis_service.stop()
    imu_service.stop()


app.include_router(system.router)
app.include_router(settings.router)
app.include_router(projects.router)
app.include_router(cameras.router)
app.include_router(media.router)
app.include_router(annotations.router)
app.include_router(reports.router)
app.include_router(camera_control.router)
app.include_router(media_proxy.router)
app.include_router(chassis.router)

# Serve stored media from the active storage dir (resolved at startup; changing
# the path in settings requires a restart — that's the documented behavior).
storage_root = settings_obj.active_storage_dir
if storage_root.exists():
    app.mount("/storage", StaticFiles(directory=str(storage_root)), name="storage")

frontend_dist = Path(__file__).resolve().parents[2] / "front_end" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

