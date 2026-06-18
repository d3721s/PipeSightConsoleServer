from __future__ import annotations

from datetime import datetime
from pathlib import Path


# OSD font. Install on the cart with: sudo apt install -y fonts-wqy-zenhei
OSD_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OSD_TEXT_X = 30
OSD_TEXT_Y = 20
OSD_FONT_SIZE = 46
OSD_TEXT_COLOR = "white"
OSD_BOX_COLOR = "black@0.45"
OSD_BOX_BORDER_W = 10
OSD_LINE_SPACING = 12
OSD_SHADOW_COLOR = "black@0.8"


def format_wheel_mileage(left: int | float | None, right: int | float | None) -> str:
    if left is None or right is None:
        return "--"
    return f"{float(left):.2f}m-{float(right):.2f}m"


def current_wheel_mileage_text() -> str:
    from app.services.modbus_service import modbus_chassis_service

    telemetry = modbus_chassis_service.get_telemetry()
    return format_wheel_mileage(telemetry.left_mileage, telemetry.right_mileage)


def _ff_escape_path(path: str | Path) -> str:
    # Inside an ffmpeg filter argument, ':' and '\' must be escaped.
    return str(path).replace("\\", "\\\\").replace(":", "\\:")


def osd_text(project_name: str, project_location: str, *, now: datetime | None = None) -> str:
    ts = (now or datetime.now()).strftime("%Y-%m-%d %H:%M:%S")
    return (
        f"时间: {ts}\n"
        f"距离: {current_wheel_mileage_text()}\n"
        f"项目名称: {project_name or '-'}\n"
        f"项目地点: {project_location or '-'}\n"
    )


def build_ffmpeg_osd_filter(textfile: str | Path, *, fontfile: str = OSD_FONT, reload: bool = True) -> str:
    font = _ff_escape_path(fontfile)
    body_file = _ff_escape_path(textfile)
    reload_opt = ":reload=1" if reload else ""
    return (
        f"drawtext=fontfile={font}:textfile={body_file}{reload_opt}:"
        f"x={OSD_TEXT_X}:y={OSD_TEXT_Y}:fontsize={OSD_FONT_SIZE}:fontcolor={OSD_TEXT_COLOR}:"
        f"box=1:boxcolor={OSD_BOX_COLOR}:boxborderw={OSD_BOX_BORDER_W}:"
        f"line_spacing={OSD_LINE_SPACING}:"
        f"shadowcolor={OSD_SHADOW_COLOR}:shadowx=1:shadowy=2"
    )
