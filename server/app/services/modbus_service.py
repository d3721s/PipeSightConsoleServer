from __future__ import annotations

import queue
import threading
import time
from dataclasses import dataclass, field

from app.config import get_settings


settings = get_settings()

# Chassis Modbus RTU map (from the protocol doc, 485 joystick mode).
REG_JOY_VERTICAL = 0x0A    # signed -800..800 (Y / forward)
REG_JOY_HORIZONTAL = 0x0B  # signed -800..800 (X)
REG_L_SPEED = 0x36         # signed, read-only (actual left wheel speed)
REG_R_SPEED = 0x37         # signed, read-only (actual right wheel speed)
REG_L_MILEAGE_H = 0x38     # 32-bit unsigned pulses, H/L (left)
REG_L_MILEAGE_L = 0x39
REG_R_MILEAGE_H = 0x3A     # 32-bit unsigned pulses, H/L (right)
REG_R_MILEAGE_L = 0x3B
REG_LIGHT = 0x3D           # rw: 0x01 off, 0x02 low beam, 0x03 high beam
REG_ERROR = 0x47           # ro: 0x00 normal
REG_CONTROL_MODE = 0x50    # rw: 0 remote, 1 speed-loop, 3 position-loop, 4 joystick
REG_START_STOP = 0x51      # rw: 0 stop, 1 start

MODE_JOYSTICK = 4
JOY_LIMIT = 800
# 0.51 m per encoder revolution; pulses->metres needs the encoder line count,
# which we don't have here, so mileage is reported in raw pulses for now.
HEARTBEAT_S = 0.05         # joystick write cadence (controller stops if >1s idle)
TELEMETRY_EVERY_S = 0.2    # how often telemetry registers are polled
RECONNECT_S = 2.0
CONFIRM_TIMEOUT_S = 1.5


def _to_u16(value: int) -> int:
    v = max(-JOY_LIMIT, min(JOY_LIMIT, int(value)))
    return v & 0xFFFF


def _to_signed16(value: int) -> int:
    return value - 0x10000 if value >= 0x8000 else value


@dataclass
class _WriteCmd:
    address: int
    value: int
    done: threading.Event = field(default_factory=threading.Event)
    ok: bool = False


@dataclass
class Telemetry:
    connected: bool = False
    left_speed: int | None = None
    right_speed: int | None = None
    left_mileage: int | None = None   # raw pulses
    right_mileage: int | None = None
    light: int | None = None
    mode: int | None = None
    error: int | None = None


class ModbusChassisService:
    """Single-threaded Modbus RTU scheduler for the cart chassis.

    One worker owns the serial port and serializes everything (no concurrent
    serial access): each loop writes the joystick heartbeat, drains queued
    confirmed writes (light / mode), and periodically reads telemetry.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._x = 0
        self._y = 0
        self._client = None
        self._connected = False
        self._mode_set = False
        self._telemetry = Telemetry()
        self._cmds: "queue.Queue[_WriteCmd]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_telemetry = 0.0

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="modbus-chassis", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def connected(self) -> bool:
        return self._connected

    def set_joystick(self, x: float, y: float) -> None:
        with self._lock:
            self._x = max(-JOY_LIMIT, min(JOY_LIMIT, int(x)))
            self._y = max(-JOY_LIMIT, min(JOY_LIMIT, int(y)))

    def get_telemetry(self) -> Telemetry:
        with self._lock:
            t = self._telemetry
            return Telemetry(
                connected=self._connected,
                left_speed=t.left_speed,
                right_speed=t.right_speed,
                left_mileage=t.left_mileage,
                right_mileage=t.right_mileage,
                light=t.light,
                mode=t.mode,
                error=t.error,
            )

    def set_light(self, value: int) -> bool:
        return self._command_confirmed(REG_LIGHT, int(value))

    def set_mode(self, value: int) -> bool:
        ok = self._command_confirmed(REG_CONTROL_MODE, int(value))
        if ok and int(value) == MODE_JOYSTICK:
            self._mode_set = True
        return ok

    # --- command with read-back confirmation -------------------------------

    def _command_confirmed(self, address: int, value: int) -> bool:
        if not self._connected:
            return False
        cmd = _WriteCmd(address=address, value=value)
        self._cmds.put(cmd)
        if not cmd.done.wait(timeout=CONFIRM_TIMEOUT_S):
            return False
        return cmd.ok

    # --- serial internals --------------------------------------------------

    def _connect(self) -> bool:
        try:
            from pymodbus.client import ModbusSerialClient
        except Exception:
            return False
        try:
            client = ModbusSerialClient(
                port=settings.chassis_serial_port,
                baudrate=settings.chassis_baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.2,
            )
            if not client.connect():
                return False
            self._client = client
            self._connected = True
            self._mode_set = False
            return True
        except Exception:
            return False

    def _write(self, address: int, value: int) -> bool:
        client = self._client
        if client is None:
            return False
        try:
            try:
                rr = client.write_register(address, value, slave=settings.chassis_slave_id)
            except TypeError:
                rr = client.write_register(address, value, unit=settings.chassis_slave_id)
            return not (rr is None or (hasattr(rr, "isError") and rr.isError()))
        except Exception:
            self._connected = False
            return False

    def _read(self, address: int, count: int = 1):
        client = self._client
        if client is None:
            return None
        try:
            try:
                rr = client.read_holding_registers(address, count=count, slave=settings.chassis_slave_id)
            except TypeError:
                rr = client.read_holding_registers(address, count, unit=settings.chassis_slave_id)
            if rr is None or (hasattr(rr, "isError") and rr.isError()):
                return None
            return rr.registers
        except Exception:
            self._connected = False
            return None

    def _ensure_mode(self) -> None:
        if self._mode_set:
            return
        if self._write(REG_CONTROL_MODE, MODE_JOYSTICK) and self._write(REG_START_STOP, 1):
            self._mode_set = True

    def _drain_commands(self) -> None:
        # Execute queued light/mode writes, each confirmed by reading it back.
        while True:
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                return
            wrote = self._write(cmd.address, cmd.value)
            ok = False
            if wrote:
                regs = self._read(cmd.address, 1)
                ok = bool(regs) and regs[0] == cmd.value
            cmd.ok = ok
            cmd.done.set()

    def _poll_telemetry(self) -> None:
        now = time.monotonic()
        if now - self._last_telemetry < TELEMETRY_EVERY_S:
            return
        self._last_telemetry = now

        l_speed = self._read(REG_L_SPEED, 1)
        r_speed = self._read(REG_R_SPEED, 1)
        l_mil = self._read(REG_L_MILEAGE_H, 2)
        r_mil = self._read(REG_R_MILEAGE_H, 2)
        light = self._read(REG_LIGHT, 1)
        mode = self._read(REG_CONTROL_MODE, 1)
        error = self._read(REG_ERROR, 1)

        with self._lock:
            t = self._telemetry
            if l_speed:
                t.left_speed = _to_signed16(l_speed[0])
            if r_speed:
                t.right_speed = _to_signed16(r_speed[0])
            if l_mil and len(l_mil) == 2:
                t.left_mileage = (l_mil[0] << 16) | l_mil[1]
            if r_mil and len(r_mil) == 2:
                t.right_mileage = (r_mil[0] << 16) | r_mil[1]
            if light:
                t.light = light[0]
            if mode:
                t.mode = mode[0]
            if error:
                t.error = error[0]

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self._connected:
                # Fail any pending commands while disconnected.
                self._fail_pending()
                if not self._connect():
                    time.sleep(RECONNECT_S)
                    continue
            self._ensure_mode()

            with self._lock:
                x, y = self._x, self._y
            ok_v = self._write(REG_JOY_VERTICAL, _to_u16(y))
            ok_h = self._write(REG_JOY_HORIZONTAL, _to_u16(x))
            if not (ok_v and ok_h):
                self._drop_connection()
                continue

            self._drain_commands()
            self._poll_telemetry()
            time.sleep(HEARTBEAT_S)

        self._drop_connection()

    def _drop_connection(self) -> None:
        self._connected = False
        try:
            if self._client is not None:
                self._client.close()
        except Exception:
            pass
        self._client = None
        with self._lock:
            self._telemetry.connected = False
        self._fail_pending()

    def _fail_pending(self) -> None:
        while True:
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                return
            cmd.ok = False
            cmd.done.set()


modbus_chassis_service = ModbusChassisService()
