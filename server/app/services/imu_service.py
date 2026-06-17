from __future__ import annotations

import logging
import struct
import threading
import time
from dataclasses import dataclass, field

from app.config import get_settings


settings = get_settings()

# ATK-MS901M active-report frame: 0x55 0x55 | ID | LEN | DATA[LEN] | SUM.
# Host command/response frame: 0x55 0xAF | ID | LEN | DATA[LEN] | SUM.
# SUM = low 8 bits of the sum of every byte except SUM itself.
# Euler-angle frame: ID=0x01, LEN=0x06, DATA = RollL RollH PitchL PitchH YawL YawH
# angle(deg) = int16(H<<8|L) / 32768 * 180
ACTIVE_HEAD_2 = 0x55
COMMAND_HEAD_2 = 0xAF
ID_EULER = 0x01
LEN_EULER = 0x06
MAX_DATA_LEN = 64

CMD_READ = 0x80
CMD_D1MODE = 0x11
CMD_D3MODE = 0x13
CMD_D1PULSE = 0x16
CMD_D3PULSE = 0x1A
CMD_D1PERIOD = 0x1F
CMD_D3PERIOD = 0x23
PORT_MODE_PWM = 0x04

RECONNECT_S = 2.0
FRESH_FRAME_S = 2.0
STALL_FRAME_S = 5.0
COMMAND_TIMEOUT_S = 1.0

logger = logging.getLogger(__name__)


@dataclass
class _PendingRead:
    command_id: int
    done: threading.Event = field(default_factory=threading.Event)
    data: bytes | None = None


class ImuService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roll: float | None = None
        self._pitch: float | None = None
        self._yaw: float | None = None
        self._light: int | None = None
        self._connected = False
        self._last_frame_at: float | None = None
        self._last_logged_error: str | None = None
        self._serial = None
        self._io_lock = threading.Lock()
        self._command_lock = threading.Lock()
        self._pending_lock = threading.Lock()
        self._pending_read: _PendingRead | None = None
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="imu", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def connected(self) -> bool:
        return self._connected

    def get_euler(self) -> tuple[float | None, float | None, float | None]:
        with self._lock:
            return self._roll, self._pitch, self._yaw

    def get_light(self) -> int | None:
        with self._lock:
            return self._light

    def set_light(self, value: int) -> bool:
        value = int(value)
        if value not in (1, 2, 3):
            return False

        period = self._bounded_u16(settings.imu_light_pwm_period_us, minimum=1)
        d1_pulse, d3_pulse = self._light_pulses(value, period)
        commands = [
            (CMD_D1MODE, bytes([PORT_MODE_PWM])),
            (CMD_D3MODE, bytes([PORT_MODE_PWM])),
            (CMD_D1PERIOD, self._u16le(period)),
            (CMD_D3PERIOD, self._u16le(period)),
            (CMD_D1PULSE, self._u16le(d1_pulse)),
            (CMD_D3PULSE, self._u16le(d3_pulse)),
        ]

        with self._command_lock:
            for command_id, data in commands:
                if not self._write_command(command_id, data):
                    return False
            for command_id, expected in commands:
                actual = self._read_command(command_id)
                if actual != expected:
                    return False

        with self._lock:
            self._light = value
        return True

    def snapshot(self) -> dict:
        now = time.monotonic()
        with self._lock:
            fresh = (
                self._last_frame_at is not None
                and now - self._last_frame_at <= FRESH_FRAME_S
            )
            return {
                "fresh": fresh,
                "roll": self._roll,
                "pitch": self._pitch,
                "yaw": self._yaw,
            }

    # --- internals ---------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            ser = self._open()
            if ser is None:
                time.sleep(RECONNECT_S)
                continue
            opened_at = time.monotonic()
            with self._io_lock:
                self._serial = ser
            with self._lock:
                self._connected = True
                self._last_frame_at = None
            self._last_logged_error = None
            logger.info(
                "IMU serial opened: %s @ %s",
                settings.imu_serial_port,
                settings.imu_baudrate,
            )
            buf = bytearray()
            try:
                while not self._stop.is_set():
                    chunk = ser.read(64)
                    if chunk:
                        buf.extend(chunk)
                        self._parse(buf)
                    if self._should_reconnect(opened_at):
                        self._record_error(
                            f"IMU stream stalled for >{STALL_FRAME_S:.0f}s; reopening"
                        )
                        break
                    # read() returns b"" on timeout; keep looping.
            except Exception as exc:
                self._record_error(f"IMU serial read failed: {exc}")
            finally:
                with self._io_lock:
                    if self._serial is ser:
                        self._serial = None
                with self._lock:
                    self._connected = False
                self._fail_pending_read()
                try:
                    ser.close()
                except Exception:
                    pass
            if not self._stop.is_set():
                time.sleep(RECONNECT_S)

    def _open(self):
        try:
            import serial  # pyserial
        except Exception as exc:
            self._record_error(f"pyserial import failed: {exc}")
            return None
        try:
            return serial.Serial(
                port=settings.imu_serial_port,
                baudrate=settings.imu_baudrate,
                bytesize=8,
                parity="N",
                stopbits=1,
                timeout=0.2,
            )
        except Exception as exc:
            self._record_error(
                f"IMU serial open failed ({settings.imu_serial_port} @ "
                f"{settings.imu_baudrate}): {exc}"
            )
            return None

    def _parse(self, buf: bytearray) -> None:
        # Active-report frames (55 55) and command responses (55 AF) share the
        # serial stream. Consume both so read-back confirmation can coexist with
        # the normal Euler-angle stream.
        while True:
            start = buf.find(0x55)
            if start < 0:
                buf.clear()
                break
            if start > 0:
                del buf[:start]
            if len(buf) < 2:
                break

            if buf[1] == ACTIVE_HEAD_2:
                if not self._consume_active_frame(buf):
                    break
            elif buf[1] == COMMAND_HEAD_2:
                if not self._consume_command_response(buf):
                    break
            else:
                del buf[0]

    def _consume_active_frame(self, buf: bytearray) -> bool:
        if len(buf) < 4:
            return False
        data_len = buf[3]
        if data_len > MAX_DATA_LEN:
            del buf[0]
            return True
        frame_size = 2 + 1 + 1 + data_len + 1
        if len(buf) < frame_size:
            return False

        frame = bytes(buf[:frame_size])
        if self._checksum(frame[:-1]) != frame[-1]:
            del buf[0]
            return True

        frame_id = frame[2]
        data = frame[4:-1]
        if frame_id == ID_EULER and data_len == LEN_EULER:
            roll, pitch, yaw = struct.unpack("<hhh", data)
            with self._lock:
                self._roll = roll / 32768.0 * 180.0
                self._pitch = pitch / 32768.0 * 180.0
                self._yaw = yaw / 32768.0 * 180.0
                self._last_frame_at = time.monotonic()

        del buf[:frame_size]
        return True

    def _consume_command_response(self, buf: bytearray) -> bool:
        if len(buf) < 4:
            return False
        data_len = buf[3]
        if data_len > MAX_DATA_LEN:
            del buf[0]
            return True
        frame_size = 2 + 1 + 1 + data_len + 1
        if len(buf) < frame_size:
            return False

        frame = bytes(buf[:frame_size])
        if self._checksum(frame[:-1]) != frame[-1]:
            del buf[0]
            return True

        self._complete_pending_read(frame[2], frame[4:-1])
        del buf[:frame_size]
        return True

    def _should_reconnect(self, opened_at: float) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_frame_at
        if last is None:
            return now - opened_at > STALL_FRAME_S
        return now - last > STALL_FRAME_S

    def _write_command(self, command_id: int, data: bytes) -> bool:
        return self._serial_write(self._command_frame(command_id, data))

    def _read_command(self, command_id: int) -> bytes | None:
        pending = _PendingRead(command_id=command_id)
        with self._pending_lock:
            if self._pending_read is not None:
                return None
            self._pending_read = pending

        if not self._serial_write(self._command_frame(command_id | CMD_READ, b"\x00")):
            with self._pending_lock:
                if self._pending_read is pending:
                    self._pending_read = None
            return None

        pending.done.wait(timeout=COMMAND_TIMEOUT_S)
        with self._pending_lock:
            if self._pending_read is pending:
                self._pending_read = None
        return pending.data

    def _complete_pending_read(self, command_id: int, data: bytes) -> None:
        with self._pending_lock:
            pending = self._pending_read
            if pending is None or pending.command_id != command_id:
                return
            self._pending_read = None
            pending.data = data
            pending.done.set()

    def _fail_pending_read(self) -> None:
        with self._pending_lock:
            pending = self._pending_read
            self._pending_read = None
        if pending is not None:
            pending.done.set()

    def _serial_write(self, frame: bytes) -> bool:
        with self._io_lock:
            ser = self._serial
            if ser is None or not self._connected:
                return False
            try:
                ser.write(frame)
                ser.flush()
                return True
            except Exception as exc:
                self._record_error(f"IMU serial write failed: {exc}")
                self._connected = False
                return False

    @staticmethod
    def _command_frame(command_id: int, data: bytes) -> bytes:
        frame = bytes([0x55, 0xAF, command_id & 0xFF, len(data) & 0xFF]) + data
        return frame + bytes([ImuService._checksum(frame)])

    @staticmethod
    def _checksum(data: bytes) -> int:
        return sum(data) & 0xFF

    @staticmethod
    def _u16le(value: int) -> bytes:
        return int(value).to_bytes(2, byteorder="little", signed=False)

    @staticmethod
    def _bounded_u16(value: int, minimum: int = 0) -> int:
        return max(minimum, min(0xFFFF, int(value)))

    @staticmethod
    def _bounded_pulse(value: int, period: int) -> int:
        return max(0, min(period, int(value)))

    def _light_pulses(self, value: int, period: int) -> tuple[int, int]:
        if value == 1:
            return 0, 0
        if value == 2:
            return (
                self._bounded_pulse(settings.imu_light_low_d1_pulse_us, period),
                self._bounded_pulse(settings.imu_light_low_d3_pulse_us, period),
            )
        return (
            self._bounded_pulse(settings.imu_light_high_d1_pulse_us, period),
            self._bounded_pulse(settings.imu_light_high_d3_pulse_us, period),
        )

    def _record_error(self, message: str) -> None:
        if message != self._last_logged_error:
            logger.warning(message)
            self._last_logged_error = message


imu_service = ImuService()
