from __future__ import annotations

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
CMD_HEAD = b"\x55\xAF"
CMD_RETURNSET = 0x08
CMD_RETURNRATE = 0x0A
RETURNSET_EULER_ONLY = 0x01
RETURNRATE_10HZ = 0x06

RECONNECT_S = 2.0


class ImuService:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._roll: float | None = None
        self._pitch: float | None = None
        self._yaw: float | None = None
        self._connected = False
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

    # --- internals ---------------------------------------------------------

    def _run(self) -> None:
        while not self._stop.is_set():
            ser = self._open()
            if ser is None:
                time.sleep(RECONNECT_S)
                continue
            self._connected = True
            self._configure_stream(ser)
            buf = bytearray()
            try:
                while not self._stop.is_set():
                    chunk = ser.read(64)
                    if chunk:
                        buf.extend(chunk)
                        self._parse(buf)
                    # read() returns b"" on timeout; keep looping.
            except Exception:
                pass
            finally:
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
        except Exception:
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
        except Exception:
            return None

    def _configure_stream(self, ser) -> None:
        try:
            self._write_command(ser, CMD_RETURNSET, bytes([RETURNSET_EULER_ONLY]))
            self._write_command(ser, CMD_RETURNRATE, bytes([RETURNRATE_10HZ]))
        except Exception:
            pass

    @staticmethod
    def _write_command(ser, frame_id: int, data: bytes) -> None:
        length = len(data)
        checksum = (0x55 + 0xAF + frame_id + length + sum(data)) & 0xFF
        ser.write(CMD_HEAD + bytes([frame_id, length]) + data + bytes([checksum]))

    def _parse(self, buf: bytearray) -> None:
        # Consume as many complete frames as are buffered; keep the remainder.
        i = 0
        n = len(buf)
        while i + 4 <= n:
            if not (buf[i] == 0x55 and buf[i + 1] == 0x55):
                i += 1
                continue
            length = buf[i + 3]
            frame_end = i + 4 + length + 1  # head(2)+id(1)+len(1)+data+sum(1)
            if frame_end > n:
                break  # incomplete; wait for more bytes
            frame_id = buf[i + 2]
            data = buf[i + 4 : i + 4 + length]
            checksum = buf[i + 4 + length]
            calc = (0x55 + 0x55 + frame_id + length + sum(data)) & 0xFF
            if calc == checksum:
                if frame_id == ID_EULER and length == LEN_EULER:
                    roll, pitch, yaw = struct.unpack("<hhh", bytes(data))
                    with self._lock:
                        self._roll = roll / 32768.0 * 180.0
                        self._pitch = pitch / 32768.0 * 180.0
                        self._yaw = yaw / 32768.0 * 180.0
                i = frame_end
            else:
                # Bad checksum: resync past this head and keep scanning.
                i += 2
        # Drop everything we've consumed/skipped.
        del buf[:i]


imu_service = ImuService()
