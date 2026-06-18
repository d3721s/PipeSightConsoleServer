from __future__ import annotations

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from sqlalchemy import select

from app.db import SessionLocal
from app.drivers.onvif_client import OnvifError
from app.drivers.onvif_ptz import ptz_driver
from app.models import CameraDevice
from app.services.modbus_service import modbus_chassis_service


router = APIRouter()


DIRECTIONS = {
    "up": (0.0, -1.0),
    "down": (0.0, 1.0),
    "left": (-1.0, 0.0),
    "right": (1.0, 0.0),
}


@router.websocket("/ws/camera-control")
async def camera_control(websocket: WebSocket) -> None:
    await websocket.accept()
    modbus_chassis_service.set_chassis_enabled(False)
    try:
        while True:
            payload = await websocket.receive_json()
            ref = payload.get("ref")
            try:
                await handle_control(payload)
            except Exception as exc:
                await websocket.send_json({"type": "ack", "ref": ref, "ok": False, "error": str(exc)})
            else:
                await websocket.send_json({"type": "ack", "ref": ref, "ok": True})
    except WebSocketDisconnect:
        modbus_chassis_service.set_chassis_enabled(False)
        return


async def handle_control(payload: dict) -> None:
    msg_type = payload.get("type")

    if msg_type == "chassis_control":
        modbus_chassis_service.set_chassis_enabled(bool(payload.get("enabled")))
        return

    # Chassis joystick has no camera context — handle before the camera lookup.
    if msg_type == "chassis_move":
        x = float(payload.get("x", 0))
        y = float(payload.get("y", 0))
        modbus_chassis_service.set_joystick(x, y)
        return

    device = payload.get("device", "front")
    channel = int(payload.get("channel", 1))
    if channel != 1:
        raise ValueError("PTZ is only available on channel 1")

    with SessionLocal() as db:
        camera = db.scalar(select(CameraDevice).where(CameraDevice.code == device))
        if camera is None:
            raise ValueError("camera not found")
        if not camera.ip:
            raise ValueError("camera IP is empty")

        if msg_type == "ptz_stop":
            await ptz_driver.stop(camera)
            return

        direction = payload.get("direction")
        if direction not in DIRECTIONS:
            raise ValueError("invalid direction")
        dx, dy = DIRECTIONS[direction]

        try:
            if msg_type == "ptz_step":
                await ptz_driver.step(camera, dx, dy)
            elif msg_type == "ptz_start":
                await ptz_driver.start(camera, dx, dy)
            else:
                raise ValueError("invalid control type")
        except OnvifError:
            raise

