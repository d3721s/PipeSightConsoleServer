from __future__ import annotations


def format_wheel_mileage(left: int | float | None, right: int | float | None) -> str:
    if left is None or right is None:
        return "--"
    return f"{float(left):.2f}m-{float(right):.2f}m"


def current_wheel_mileage_text() -> str:
    from app.services.modbus_service import modbus_chassis_service

    telemetry = modbus_chassis_service.get_telemetry()
    return format_wheel_mileage(telemetry.left_mileage, telemetry.right_mileage)
