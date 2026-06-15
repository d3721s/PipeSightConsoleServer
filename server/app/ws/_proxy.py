from __future__ import annotations

import contextlib
import logging

import websockets
from fastapi import WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed


async def proxy_bridge_stream(
    websocket: WebSocket,
    target: str,
    logger: logging.Logger,
    label: str,
) -> None:
    await websocket.accept()
    try:
        async with websockets.connect(target, max_size=None, open_timeout=3) as upstream:
            while True:
                frame = await upstream.recv()
                if isinstance(frame, bytes):
                    await websocket.send_bytes(frame)
                else:
                    await websocket.send_text(frame)
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
