from __future__ import annotations

from datetime import datetime
from pathlib import Path


# Keep these values visually aligned with front_end/src/components/OsdOverlay.vue
# and the 3D snapshot canvas renderer in Inspect3dPage.vue.
OSD_FONT = "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc"
OSD_PANEL_X = 30
OSD_PANEL_Y = 20
OSD_BLUE_BAR_W = 9
OSD_PADDING_X = 36
OSD_PADDING_Y = 24
OSD_FONT_SIZE = 46
OSD_LINE_HEIGHT = round(OSD_FONT_SIZE * 1.45)
OSD_LINE_SPACING = OSD_LINE_HEIGHT - OSD_FONT_SIZE
OSD_TEXT_COLOR = "0xf4f4f4"
OSD_ACCENT_COLOR = "0x0f62fe@1"
OSD_PANEL_COLOR = "black@0.45"
OSD_SHADOW_COLOR = "black@0.8"
OSD_LINE_COUNT = 4


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
        f"时间：{ts}\n"
        f"距离：{current_wheel_mileage_text()}\n"
        f"项目名称：{project_name or '未创建项目'}\n"
        f"地点：{project_location or '-'}\n"
    )


def build_ffmpeg_osd_filter(textfile: str | Path, *, fontfile: str = OSD_FONT, reload: bool = True) -> str:
    font = _ff_escape_path(fontfile)
    body_file = _ff_escape_path(textfile)
    text_x = OSD_PANEL_X + OSD_BLUE_BAR_W + OSD_PADDING_X
    text_y = OSD_PANEL_Y + OSD_PADDING_Y
    panel_h = OSD_PADDING_Y * 2 + OSD_LINE_HEIGHT * OSD_LINE_COUNT

    # Keep this compatible with older ffmpeg builds: some drawtext versions only
    # accept a single integer for boxborderw, not the four-side "a|b|c|d" form.
    # Draw the panel and accent with drawbox, then render text without drawtext's
    # own box.
    panel_w = "iw*0.62"
    reload_opt = ":reload=1" if reload else ""

    panel_layer = (
        f"drawbox=x={OSD_PANEL_X}:y={OSD_PANEL_Y}:w={panel_w}:h={panel_h}:"
        f"c={OSD_PANEL_COLOR}:t=fill"
    )
    accent_layer = (
        f"drawbox=x={OSD_PANEL_X}:y={OSD_PANEL_Y}:w={OSD_BLUE_BAR_W}:h={panel_h}:"
        f"c={OSD_ACCENT_COLOR}:t=fill"
    )
    text_layer = (
        f"drawtext=fontfile={font}:textfile={body_file}{reload_opt}:"
        f"x={text_x}:y={text_y}:fontsize={OSD_FONT_SIZE}:fontcolor={OSD_TEXT_COLOR}:"
        f"line_spacing={OSD_LINE_SPACING}:"
        f"shadowcolor={OSD_SHADOW_COLOR}:shadowx=1:shadowy=2"
    )
    return f"{panel_layer},{accent_layer},{text_layer}"
