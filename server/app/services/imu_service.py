from __future__ import annotations

import logging
import struct
import threading
import time

from app.config import get_settings


settings = get_settings()

# ATK-MS901M active-report frame: 0x55 0x55 | ID | LEN | DATA[LEN] | SUM
# SUM = low 8 bits of the sum of every byte except SUM itself.
# Euler-angle frame: ID=0x01, LEN=0x06, DATA = RollL RollH PitchL PitchH YawL YawH
# angle(deg) = int16(H<<8|L) / 32768 * 180
FRAME_HEAD = b"\x55\x55"
ID_EULER = 0x01
LEN_EULER = 0x06
FRAME_SIZE = 2 + 1 + 1 + LEN_EULER + 1

RECONNECT_S = 2.0
FRESH_FRAME_S = 2.0
STALL_FRAME_S = 5.0
RX_TAIL_MAX = 64

logger = logging.getLogger(__name__)


def _hex(data: bytes | bytearray) -> str:
    return " ".join(f"{byte:02X}" for byte in data)


class ImuService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roll: float | None = None
        self._pitch: float | None = None
        self._yaw: float | None = None
        self._connected = False
        self._last_frame_at: float | None = None
        self._rx_bytes = 0
        self._valid_frames = 0
        self._bad_frames = 0
        self._skipped_bytes = 0
        self._buffered_bytes = 0
        self._last_rx_at: float | None = None
        self._rx_tail = bytearray()
        self._last_frame_hex: str | None = None
        self._last_bad_frame_hex: str | None = None
        self._last_error: str | None = None
        self._last_logged_error: str | None = None
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
            with self._lock:
                self._connected = True
                self._last_frame_at = None
                self._last_error = None
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
                        self._record_rx(chunk)
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
                with self._lock:
                    self._connected = False
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

    def _record_rx(self, chunk: bytes) -> None:
        with self._lock:
            self._rx_bytes += len(chunk)
            self._last_rx_at = time.monotonic()
            self._rx_tail.extend(chunk)
            if len(self._rx_tail) > RX_TAIL_MAX:
                del self._rx_tail[: len(self._rx_tail) - RX_TAIL_MAX]

    def _parse(self, buf: bytearray) -> None:
        # The field unit only emits fixed Euler frames:
        # 55 55 01 06 RollL RollH PitchL PitchH YawL YawH SUM.
        skipped = 0
        while True:
            start = buf.find(FRAME_HEAD)
            if start < 0:
                keep = 1 if buf and buf[-1] == FRAME_HEAD[0] else 0
                drop = len(buf) - keep
                if drop > 0:
                    skipped += drop
                    del buf[:drop]
                break
            if start > 0:
                skipped += start
                del buf[:start]
            if len(buf) < FRAME_SIZE:
                break
            if buf[2] != ID_EULER or buf[3] != LEN_EULER:
                skipped += 1
                del buf[0]
                continue
            frame = bytes(buf[:FRAME_SIZE])
            data = frame[4:10]
            checksum = frame[10]
            calc = sum(frame[:10]) & 0xFF
            if calc == checksum:
                roll, pitch, yaw = struct.unpack("<hhh", bytes(data))
                with self._lock:
                    self._roll = roll / 32768.0 * 180.0
                    self._pitch = pitch / 32768.0 * 180.0
                    self._yaw = yaw / 32768.0 * 180.0
                    self._last_frame_at = time.monotonic()
                    self._valid_frames += 1
                    self._last_frame_hex = _hex(frame)
                    self._last_error = None
                del buf[:FRAME_SIZE]
            else:
                # Bad checksum: resync past this head and keep scanning.
                with self._lock:
                    self._bad_frames += 1
                    self._last_bad_frame_hex = _hex(frame)
                del buf[0]
        with self._lock:
            self._skipped_bytes += skipped
            self._buffered_bytes = len(buf)

    def _should_reconnect(self, opened_at: float) -> bool:
        now = time.monotonic()
        with self._lock:
            last = self._last_frame_at
        if last is None:
            return now - opened_at > STALL_FRAME_S
        return now - last > STALL_FRAME_S

    def _record_error(self, message: str) -> None:
        with self._lock:
            self._last_error = message
        if message != self._last_logged_error:
            logger.warning(message)
            self._last_logged_error = message


imu_service = ImuService()
