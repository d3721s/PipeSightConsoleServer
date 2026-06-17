from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.modbus_service import modbus_chassis_service
from app.services.imu_service import imu_service


router = APIRouter(prefix="/api/chassis", tags=["chassis"])


@router.get("/telemetry")
def telemetry() -> dict:
    t = modbus_chassis_service.get_telemetry()
    imu = imu_service.snapshot()
    imu_fresh = bool(imu["fresh"])
    return {
        "connected": t.connected,
        "leftSpeed": t.left_speed,
        "rightSpeed": t.right_speed,
        "leftMileage": t.left_mileage,   # raw encoder pulses
        "rightMileage": t.right_mileage,
        "light": t.light,                # 1 off / 2 low / 3 high
        "mode": t.mode,                  # 0 remote / 1 speed / 3 position / 4 joystick
        "error": t.error,
        # IMU Euler angles (deg): roll/pitch/yaw from ATK-MS901M over UART.
        "imuConnected": imu_fresh,
        "imuPortOpen": imu["portOpen"],
        "imuFresh": imu_fresh,
        "imuLastFrameAgeS": imu["lastFrameAgeS"],
        "imuRxBytes": imu["rxBytes"],
        "imuValidFrames": imu["validFrames"],
        "imuBadFrames": imu["badFrames"],
        "imuLastError": imu["lastError"],
        "roll": imu["roll"] if imu_fresh else None,
        "pitch": imu["pitch"] if imu_fresh else None,
        "yaw": imu["yaw"] if imu_fresh else None,
    }


class LightIn(BaseModel):
    value: int = Field(ge=1, le=3)  # 1 off, 2 low beam, 3 high beam


@router.post("/light")
def set_light(payload: LightIn) -> dict:
    # Writes the register then reads it back; only reports success on confirm.
    if not modbus_chassis_service.set_light(payload.value):
        raise HTTPException(status_code=502, detail="底盘未确认灯光指令")
    return {"ok": True, "light": payload.value}


class ModeIn(BaseModel):
    value: int = Field(ge=0, le=4)  # 0 remote, 1 speed, 3 position, 4 joystick


@router.post("/mode")
def set_mode(payload: ModeIn) -> dict:
    if not modbus_chassis_service.set_mode(payload.value):
        raise HTTPException(status_code=502, detail="底盘未确认控制模式指令")
    return {"ok": True, "mode": payload.value}
