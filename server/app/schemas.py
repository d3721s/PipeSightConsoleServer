from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class CameraConfigIn(BaseModel):
    ip: str = ""
    username: str = "admin"
    password: str = ""
    onvif_port: int = Field(default=80, alias="onvifPort")
    rtsp_port: int = Field(default=554, alias="rtspPort")


class CameraOut(CameraConfigIn):
    id: int
    code: Literal["front", "rear"] | str
    name: str
    status: str

    model_config = {"from_attributes": True, "populate_by_name": True}


class CameraChannelOut(BaseModel):
    channel: int
    type: Literal["ptz", "fixed"]
    name: str
    ptz_enabled: bool = Field(alias="ptzEnabled")


class ActiveCameraIn(BaseModel):
    device: Literal["front", "rear"]
    channel: int = Field(ge=1, le=2)


class StreamOut(BaseModel):
    device: str
    channel: int
    path: str
    rtsp_url: str = Field(alias="rtspUrl")
    whep_url: str = Field(alias="whepUrl")
    recording_relay: bool = Field(default=False, alias="recordingRelay")


class ProjectCreate(BaseModel):
    name: str
    fan_model: str = Field(default="", alias="fanModel")
    fan_no: str = Field(default="", alias="fanNo")
    blade_model: str = Field(default="", alias="bladeModel")
    blade_length: str = Field(default="", alias="bladeLength")
    blade_factory_no: str = Field(default="", alias="bladeFactoryNo")
    location: str = ""


class ProjectOut(ProjectCreate):
    id: int
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SessionCreate(BaseModel):
    project_id: int = Field(alias="projectId")
    report_title: str = Field(default="", alias="reportTitle")
    report_location: str = Field(default="", alias="reportLocation")


class SessionOut(BaseModel):
    id: int
    project_id: int = Field(alias="projectId")
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    status: str
    report_title: str = Field(alias="reportTitle")
    report_location: str = Field(alias="reportLocation")

    model_config = {"from_attributes": True, "populate_by_name": True}


class SnapshotIn(BaseModel):
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    device: Literal["front", "rear"] | None = None
    channel: int | None = Field(default=None, ge=1, le=2)
    left_mileage: float | None = Field(default=None, alias="leftMileage")
    right_mileage: float | None = Field(default=None, alias="rightMileage")
    project_name: str = Field(default="", alias="projectName")
    project_location: str = Field(default="", alias="projectLocation")


class ImageSnapshotIn(BaseModel):
    # A client-rendered image (e.g. 3D point-cloud canvas) saved as a snapshot.
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    left_mileage: float | None = Field(default=None, alias="leftMileage")
    right_mileage: float | None = Field(default=None, alias="rightMileage")
    image: str  # PNG data URL
    source: str = "3d"  # tag for the snapshot origin
    # Optional raw depth blob (base64) saved alongside depth snapshots so the area
    # can be measured later. Layout: see front_end/src/utils/depthArea.ts.
    depth_raw: str | None = Field(default=None, alias="depthRaw")


class MediaAssetOut(BaseModel):
    id: int
    project_id: int | None = Field(alias="projectId")
    session_id: int | None = Field(alias="sessionId")
    camera_device: str = Field(alias="cameraDevice")
    camera_channel: int = Field(alias="cameraChannel")
    type: str
    file_path: str = Field(alias="filePath")
    captured_at: datetime = Field(alias="capturedAt")
    left_mileage: float | None = Field(default=None, alias="leftMileage")
    right_mileage: float | None = Field(default=None, alias="rightMileage")

    model_config = {"from_attributes": True, "populate_by_name": True}


class RecordingStartIn(SnapshotIn):
    segment_minutes: int | None = Field(default=None, alias="segmentMinutes")


class RecordingStatusOut(BaseModel):
    active: bool
    device: str | None = None
    channel: int | None = None
    started_at: datetime | None = Field(default=None, alias="startedAt")
    output_pattern: str | None = Field(default=None, alias="outputPattern")
    error: str | None = None


class AnnotationCreate(BaseModel):
    media_asset_id: int = Field(alias="mediaAssetId")
    annotation_json: dict[str, Any] = Field(alias="annotationJson")
    rendered_path: str = Field(default="", alias="renderedPath")


class GraphicAnnotationIn(BaseModel):
    # Graphical annotation saved from the editor (image or video frame).
    media_asset_id: int | None = Field(default=None, alias="mediaAssetId")
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    source_type: str = Field(default="photo", alias="sourceType")  # photo | video
    video_time: float | None = Field(default=None, alias="videoTime")
    shapes: list[dict[str, Any]] = Field(default_factory=list)
    base_size: dict[str, Any] = Field(default_factory=dict, alias="baseSize")
    rendered_png: str | None = Field(default=None, alias="renderedPng")  # data URL
    # Defect info (also written to a Marker row for reporting/listing).
    defect_type: str = Field(default="", alias="defectType")
    defect_code: str = Field(default="", alias="defectCode")
    severity: str = ""
    direction: str = ""
    position: str = ""
    note: str = ""
    left_mileage: float | None = Field(default=None, alias="leftMileage")
    right_mileage: float | None = Field(default=None, alias="rightMileage")
    # Measured surface area (m²) for depth-snapshot region annotations.
    area_m2: float | None = Field(default=None, alias="areaM2")


class MarkerCreate(BaseModel):
    project_id: int | None = Field(default=None, alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    media_asset_id: int | None = Field(default=None, alias="mediaAssetId")
    defect_type: str = Field(default="", alias="defectType")
    defect_code: str = Field(default="", alias="defectCode")
    severity: str = ""
    direction: str = ""
    position: str = ""
    note: str = ""
    left_mileage: float | None = Field(default=None, alias="leftMileage")
    right_mileage: float | None = Field(default=None, alias="rightMileage")


class MarkerOut(MarkerCreate):
    id: int
    created_at: datetime = Field(alias="createdAt")

    model_config = {"from_attributes": True, "populate_by_name": True}


class ReportCreate(BaseModel):
    project_id: int = Field(alias="projectId")
    session_id: int | None = Field(default=None, alias="sessionId")
    title: str = ""
    location: str = ""


class ReportOut(ReportCreate):
    id: int
    status: str
    pdf_path: str = Field(alias="pdfPath")
    started_at: datetime = Field(alias="startedAt")
    ended_at: datetime | None = Field(default=None, alias="endedAt")
    exported_at: datetime | None = Field(default=None, alias="exportedAt")

    model_config = {"from_attributes": True, "populate_by_name": True}

