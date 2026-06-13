from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from app.api import annotations, cameras, media, projects, reports, settings, system
from app.config import get_settings
from app.db import init_db
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


app.include_router(system.router)
app.include_router(settings.router)
app.include_router(projects.router)
app.include_router(cameras.router)
app.include_router(media.router)
app.include_router(annotations.router)
app.include_router(reports.router)
app.include_router(camera_control.router)

if settings_obj.storage_dir.exists():
    app.mount("/storage", StaticFiles(directory=str(settings_obj.storage_dir)), name="storage")

frontend_dist = Path(__file__).resolve().parents[2] / "front_end" / "dist"
if frontend_dist.exists():
    app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="frontend")

