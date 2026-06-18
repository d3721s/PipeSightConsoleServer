from __future__ import annotations

import inspect
import logging
import queue
import threading
import time
from dataclasses import dataclass, field

from app.config import get_settings


settings = get_settings()
logger = logging.getLogger(__name__)

# Chassis Modbus RTU map (from the protocol doc).
REG_JOY_VERTICAL = 0x0A    # signed -800..800 (Y / forward)
REG_JOY_HORIZONTAL = 0x0B  # signed -800..800 (X)
REG_L_TARGET_SPEED = 0x0C  # signed target speed (not used by UI)
REG_R_TARGET_SPEED = 0x0D  # signed target speed (not used by UI)
REG_L_MILEAGE_H = 0x19     # signed 32-bit pulse count, H/L (left)
REG_L_MILEAGE_L = 0x1A
REG_R_MILEAGE_H = 0x1B     # signed 32-bit pulse count, H/L (right)
REG_R_MILEAGE_L = 0x1C
REG_BATTERY = 0x1D         # raw value * 0.01
REG_FAULT_CODE = 0x1E      # 0x00 normal
REG_MILEAGE_CLEAR = 0x1F   # write 1 to clear odometer

BATTERY_SCALE = 0.01
JOY_LIMIT = 800
PULSES_PER_MM = 7.35
PULSES_PER_M = PULSES_PER_MM * 1000.0
HEARTBEAT_S = 0.05         # joystick write cadence (controller stops if >1s idle)
TELEMETRY_EVERY_S = 0.2    # how often telemetry registers are polled
RECONNECT_S = 2.0
CONFIRM_TIMEOUT_S = 1.5
LOG_REPEAT_S = 10.0


def _to_u16(value: int) -> int:
    v = max(-JOY_LIMIT, min(JOY_LIMIT, int(value)))
    return v & 0xFFFF


def _to_signed32(high: int, low: int) -> int:
    value = (high << 16) | low
    return value - 0x100000000 if value >= 0x80000000 else value


def _pulses_to_meters(pulses: int) -> float:
    return round(pulses / PULSES_PER_M, 4)


def _modbus_slave_kwargs(method) -> dict[str, int]:
    """Return the slave-id keyword accepted by the installed pymodbus version."""
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        params = {}
    for name in ("device_id", "slave", "unit"):
        if name in params:
            return {name: settings.chassis_slave_id}
    return {}


def _modbus_accepts_kwarg(method, name: str) -> bool:
    try:
        params = inspect.signature(method).parameters
    except (TypeError, ValueError):
        return True
    return name in params or any(param.kind is inspect.Parameter.VAR_KEYWORD for param in params.values())


@dataclass
class _WriteCmd:
    address: int
    value: int
    confirm: bool = True
    done: threading.Event = field(default_factory=threading.Event)
    ok: bool = False


@dataclass
class Telemetry:
    connected: bool = False
    left_mileage: float | None = None   # metres
    right_mileage: float | None = None
    battery: float | None = None
    fault_code: int | None = None


class ModbusChassisService:
    """Single-threaded Modbus RTU scheduler for the cart chassis.

    One worker owns the serial port and serializes everything (no concurrent
    serial access): each loop writes the joystick heartbeat, drains queued
    writes, and periodically reads telemetry.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._x = 0
        self._y = 0
        self._client = None
        self._connected = False
        self._telemetry = Telemetry()
        self._cmds: "queue.Queue[_WriteCmd]" = queue.Queue()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._last_telemetry = 0.0
        self._last_logged_error: str | None = None
        self._last_error_times: dict[str, float] = {}

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
                left_mileage=t.left_mileage,
                right_mileage=t.right_mileage,
                battery=t.battery,
                fault_code=t.fault_code,
            )

    def clear_mileage(self) -> bool:
        ok = self._command(REG_MILEAGE_CLEAR, 1, confirm=False)
        if ok:
            with self._lock:
                self._telemetry.left_mileage = 0.0
                self._telemetry.right_mileage = 0.0
        return ok

    # --- queued writes -----------------------------------------------------

    def _command(self, address: int, value: int, *, confirm: bool = True) -> bool:
        if not self._connected:
            return False
        cmd = _WriteCmd(address=address, value=value, confirm=confirm)
        self._cmds.put(cmd)
        if not cmd.done.wait(timeout=CONFIRM_TIMEOUT_S):
            return False
        return cmd.ok

    # --- serial internals --------------------------------------------------

    def _connect(self) -> bool:
        try:
            from pymodbus.client import ModbusSerialClient
        except Exception as exc:
            self._record_error(f"pymodbus import failed: {exc}")
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
                self._record_error(
                    f"chassis serial open failed: {settings.chassis_serial_port} @ {settings.chassis_baudrate}"
                )
                return False
            self._client = client
            self._connected = True
            self._last_logged_error = None
            self._last_error_times.clear()
            logger.info(
                "chassis serial opened: %s @ %s slave=%s",
                settings.chassis_serial_port,
                settings.chassis_baudrate,
                settings.chassis_slave_id,
            )
            return True
        except Exception as exc:
            self._record_error(
                f"chassis serial open failed ({settings.chassis_serial_port} @ {settings.chassis_baudrate}): {exc}"
            )
            return False

    def _write(self, address: int, value: int) -> bool:
        client = self._client
        if client is None:
            return False
        try:
            rr = client.write_register(address, value, **_modbus_slave_kwargs(client.write_register))
            ok = not (rr is None or (hasattr(rr, "isError") and rr.isError()))
            if not ok:
                self._record_error(f"chassis write failed: register=0x{address:02X} value={value}")
            return ok
        except Exception as exc:
            self._record_error(f"chassis write exception: register=0x{address:02X} value={value}: {exc}")
            self._connected = False
            return False

    def _read(self, address: int, count: int = 1):
        client = self._client
        if client is None:
            return None
        try:
            kwargs = _modbus_slave_kwargs(client.read_holding_registers)
            if _modbus_accepts_kwarg(client.read_holding_registers, "count"):
                rr = client.read_holding_registers(address, count=count, **kwargs)
            else:
                rr = client.read_holding_registers(address, count, **kwargs)
            if rr is None or (hasattr(rr, "isError") and rr.isError()):
                self._record_error(f"chassis read failed: register=0x{address:02X} count={count}")
                return None
            return rr.registers
        except Exception as exc:
            self._record_error(f"chassis read exception: register=0x{address:02X} count={count}: {exc}")
            self._connected = False
            return None

    def _drain_commands(self) -> None:
        # Some write-only flags self-clear, so read-back confirmation is optional.
        while True:
            try:
                cmd = self._cmds.get_nowait()
            except queue.Empty:
                return
            wrote = self._write(cmd.address, cmd.value)
            ok = False
            if wrote and not cmd.confirm:
                ok = True
            elif wrote:
                regs = self._read(cmd.address, 1)
                ok = bool(regs) and regs[0] == cmd.value
            cmd.ok = ok
            cmd.done.set()

    def _poll_telemetry(self) -> None:
        now = time.monotonic()
        if now - self._last_telemetry < TELEMETRY_EVERY_S:
            return
        self._last_telemetry = now

        l_mil = self._read(REG_L_MILEAGE_H, 2)
        r_mil = self._read(REG_R_MILEAGE_H, 2)
        battery = self._read(REG_BATTERY, 1)
        fault_code = self._read(REG_FAULT_CODE, 1)

        with self._lock:
            t = self._telemetry
            if l_mil and len(l_mil) == 2:
                t.left_mileage = _pulses_to_meters(_to_signed32(l_mil[0], l_mil[1]))
            if r_mil and len(r_mil) == 2:
                t.right_mileage = _pulses_to_meters(_to_signed32(r_mil[0], r_mil[1]))
            if battery:
                t.battery = round(battery[0] * BATTERY_SCALE, 2)
            if fault_code:
                t.fault_code = fault_code[0]

    def _run(self) -> None:
        while not self._stop.is_set():
            if not self._connected:
                # Fail any pending commands while disconnected.
                self._fail_pending()
                if not self._connect():
                    time.sleep(RECONNECT_S)
                    continue
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

    def _record_error(self, message: str) -> None:
        now = time.monotonic()
        last_at = self._last_error_times.get(message, 0.0)
        if now - last_at >= LOG_REPEAT_S:
            logger.warning(message)
            self._last_error_times[message] = now
            self._last_logged_error = message


modbus_chassis_service = ModbusChassisService()
