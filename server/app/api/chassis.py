from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app.services.modbus_service import modbus_chassis_service
from app.services.imu_service import imu_service


router = APIRouter(prefix="/api/chassis", tags=["chassis"])
LIGHT_PWM_PERIOD_US = 100


@router.get("/telemetry")
def telemetry() -> dict:
    t = modbus_chassis_service.get_telemetry()
    imu = imu_service.snapshot()
    imu_fresh = bool(imu["fresh"])
    light = imu_service.get_light()
    light_pwm = imu_service.get_light_pwm()
    return {
        "connected": t.connected,
        "leftMileage": t.left_mileage,   # metres converted from encoder pulses
        "rightMileage": t.right_mileage,
        "battery": t.battery,
        "faultCode": t.fault_code,
        "light": light,                  # IMU D1/D3 PWM: 1 off / 2 low / 3 high
        "lightPwm": light_pwm,
        # IMU Euler angles (deg): roll/pitch/yaw from ATK-MS901M over UART.
        "roll": imu["roll"] if imu_fresh else None,
        "pitch": imu["pitch"] if imu_fresh else None,
        "yaw": imu["yaw"] if imu_fresh else None,
    }


class LightIn(BaseModel):
    value: int = Field(ge=1, le=3)  # 1 off, 2 low beam, 3 high beam


class LightPwmIn(BaseModel):
    periodUs: int | None = Field(default=LIGHT_PWM_PERIOD_US, ge=LIGHT_PWM_PERIOD_US, le=LIGHT_PWM_PERIOD_US)
    d1PulseUs: int = Field(ge=0, le=LIGHT_PWM_PERIOD_US)
    d3PulseUs: int = Field(ge=0, le=LIGHT_PWM_PERIOD_US)


@router.post("/light")
def set_light(payload: LightIn) -> dict:
    if not imu_service.set_light(payload.value):
        raise HTTPException(status_code=502, detail="IMU未确认灯光PWM指令")
    return {"ok": True, "light": payload.value}


@router.post("/light/pwm")
def set_light_pwm(payload: LightPwmIn) -> dict:
    if not imu_service.set_light_pwm(
        payload.d1PulseUs,
        payload.d3PulseUs,
        LIGHT_PWM_PERIOD_US,
    ):
        raise HTTPException(status_code=502, detail="IMU未确认灯光PWM指令")
    return {"ok": True, "lightPwm": imu_service.get_light_pwm()}


@router.post("/odometer/clear")
def clear_odometer() -> dict:
    if not modbus_chassis_service.clear_mileage():
        raise HTTPException(status_code=502, detail="底盘未确认里程计清零指令")
    return {"ok": True}


@router.post("/attitude/calibrate")
def calibrate_attitude() -> dict:
    # SENCAL accelerometer calibration ("姿态清零") over the IMU UART.
    if not imu_service.calibrate_accelerometer():
        raise HTTPException(status_code=502, detail="IMU未连接，姿态校准指令发送失败")
    return {"ok": True}
