from __future__ import annotations

import json
import socket
import threading
import time


# The cart's odometer service is a separate process on the same machine that
# pushes one JSON object per TCP packet, e.g. {"mileage_cm": 82}. We connect as
# a client, keep the latest mileage in memory, and auto-reconnect on drop.
ODOMETER_HOST = "127.0.0.1"
ODOMETER_PORT = 10001
RECONNECT_DELAY_S = 2.0
RECV_BUF = 4096


class OdometerService:
    def __init__(self, host: str = ODOMETER_HOST, port: int = ODOMETER_PORT) -> None:
        self._host = host
        self._port = port
        self._lock = threading.Lock()
        self._mileage_cm: int | None = None
        self._connected = False
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._run, name="odometer", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    def get_current_mileage_cm(self) -> int | None:
        with self._lock:
            return self._mileage_cm

    def get_current_mileage_m(self) -> float | None:
        cm = self.get_current_mileage_cm()
        return None if cm is None else cm / 100.0

    def _run(self) -> None:
        while not self._stop.is_set():
            try:
                self._connect_and_read()
            except OSError:
                pass
            finally:
                with self._lock:
                    self._connected = False
            if self._stop.is_set():
                break
            time.sleep(RECONNECT_DELAY_S)

    def _connect_and_read(self) -> None:
        with socket.create_connection((self._host, self._port), timeout=5) as sock:
            sock.settimeout(1.0)
            with self._lock:
                self._connected = True
            while not self._stop.is_set():
                try:
                    data = sock.recv(RECV_BUF)
                except socket.timeout:
                    continue
                if not data:
                    return  # peer closed -> reconnect
                self._handle_packet(data)

    def _handle_packet(self, data: bytes) -> None:
        # One JSON object per packet. Be tolerant of trailing whitespace/newline
        # and of a packet that happens to carry more than one object.
        text = data.decode("utf-8", errors="ignore").strip()
        if not text:
            return
        for chunk in text.splitlines() or [text]:
            chunk = chunk.strip()
            if not chunk:
                continue
            try:
                obj = json.loads(chunk)
            except json.JSONDecodeError:
                continue
            value = obj.get("mileage_cm")
            if isinstance(value, (int, float)):
                with self._lock:
                    self._mileage_cm = int(value)


odometer_service = OdometerService()
