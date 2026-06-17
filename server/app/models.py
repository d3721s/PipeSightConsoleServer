from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import DateTime, Float, ForeignKey, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


def now() -> datetime:
    return datetime.now()


class CameraDevice(Base):
    __tablename__ = "camera_devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name: Mapped[str] = mapped_column(String(64))
    ip: Mapped[str] = mapped_column(String(64), default="")
    username: Mapped[str] = mapped_column(String(64), default="admin")
    password: Mapped[str] = mapped_column(String(256), default="")
    onvif_port: Mapped[int] = mapped_column(Integer, default=80)
    rtsp_port: Mapped[int] = mapped_column(Integer, default=554)
    status: Mapped[str] = mapped_column(String(32), default="disconnected")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=now, onupdate=now)


class Project(Base):
    __tablename__ = "projects"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(128))
    fan_model: Mapped[str] = mapped_column(String(128), default="")
    fan_no: Mapped[str] = mapped_column(String(128), default="")
    blade_model: Mapped[str] = mapped_column(String(128), default="")
    blade_length: Mapped[str] = mapped_column(String(64), default="")
    blade_factory_no: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)

    sessions: Mapped[list[InspectionSession]] = relationship(back_populates="project")


class InspectionSession(Base):
    __tablename__ = "inspection_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="running")
    report_title: Mapped[str] = mapped_column(String(128), default="")
    report_location: Mapped[str] = mapped_column(String(256), default="")

    project: Mapped[Project] = relationship(back_populates="sessions")


class MediaAsset(Base):
    __tablename__ = "media_assets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_sessions.id"), nullable=True)
    camera_device: Mapped[str] = mapped_column(String(32), default="front")
    camera_channel: Mapped[int] = mapped_column(Integer, default=1)
    type: Mapped[str] = mapped_column(String(32))
    file_path: Mapped[str] = mapped_column(String(512))
    thumbnail_path: Mapped[str] = mapped_column(String(512), default="")
    captured_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    left_mileage: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_mileage: Mapped[float | None] = mapped_column(Float, nullable=True)


class Annotation(Base):
    __tablename__ = "annotations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    media_asset_id: Mapped[int] = mapped_column(ForeignKey("media_assets.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_sessions.id"), nullable=True)
    annotation_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    rendered_path: Mapped[str] = mapped_column(String(512), default="")
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Marker(Base):
    __tablename__ = "markers"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int | None] = mapped_column(ForeignKey("projects.id"), nullable=True)
    session_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_sessions.id"), nullable=True)
    media_asset_id: Mapped[int | None] = mapped_column(ForeignKey("media_assets.id"), nullable=True)
    defect_type: Mapped[str] = mapped_column(String(128), default="")
    defect_code: Mapped[str] = mapped_column(String(64), default="")
    severity: Mapped[str] = mapped_column(String(64), default="")
    direction: Mapped[str] = mapped_column(String(64), default="")
    position: Mapped[str] = mapped_column(String(128), default="")
    note: Mapped[str] = mapped_column(Text, default="")
    left_mileage: Mapped[float | None] = mapped_column(Float, nullable=True)
    right_mileage: Mapped[float | None] = mapped_column(Float, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=now)


class Report(Base):
    __tablename__ = "reports"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    project_id: Mapped[int] = mapped_column(ForeignKey("projects.id"))
    session_id: Mapped[int | None] = mapped_column(ForeignKey("inspection_sessions.id"), nullable=True)
    title: Mapped[str] = mapped_column(String(128), default="")
    location: Mapped[str] = mapped_column(String(256), default="")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    pdf_path: Mapped[str] = mapped_column(String(512), default="")
    started_at: Mapped[datetime] = mapped_column(DateTime, default=now)
    ended_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    exported_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)


class SystemSetting(Base):
    __tablename__ = "system_settings"
    __table_args__ = (UniqueConstraint("key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    key: Mapped[str] = mapped_column(String(128), index=True)
    value_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class SystemLog(Base):
    __tablename__ = "system_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime, default=now)
    level: Mapped[str] = mapped_column(String(32), default="info")
    source: Mapped[str] = mapped_column(String(64), default="")
    message: Mapped[str] = mapped_column(Text, default="")

