from __future__ import annotations

import asyncio
import contextlib
import logging

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed


PROXY_FRAME_INTERVAL_SECONDS = 1 / 15


async def proxy_bridge_stream(
    websocket: WebSocket,
    target: str,
    logger: logging.Logger,
    label: str,
) -> None:
    await websocket.accept()
    try:
        async with websockets.connect(
            target,
            max_size=None,
            max_queue=1,
            open_timeout=3,
            ping_interval=None,
        ) as upstream:
            latest_frame: bytes | str | None = None
            frame_available = asyncio.Event()

            async def read_upstream() -> None:
                nonlocal latest_frame
                async for frame in upstream:
                    latest_frame = frame
                    frame_available.set()

            reader = asyncio.create_task(read_upstream())
            try:
                while True:
                    if latest_frame is None:
                        if reader.done():
                            await reader
                            return
                        with contextlib.suppress(asyncio.TimeoutError):
                            await asyncio.wait_for(frame_available.wait(), timeout=0.25)
                        continue

                    frame = latest_frame
                    latest_frame = None
                    frame_available.clear()
                    if isinstance(frame, bytes):
                        await websocket.send_bytes(frame)
                    else:
                        await websocket.send_text(frame)
                    await asyncio.sleep(PROXY_FRAME_INTERVAL_SECONDS)
            finally:
                reader.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await reader
    except WebSocketDisconnect:
        return
    except ConnectionClosed:
        with contextlib.suppress(Exception):
            await websocket.close()
    except OSError as exc:
        logger.warning("%s unavailable at %s: %s", label, target, exc)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"{label} unavailable")
    except Exception:
        logger.exception("%s websocket proxy failed", label)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason=f"{label} proxy failed")
