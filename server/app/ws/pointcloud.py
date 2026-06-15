from __future__ import annotations

import contextlib
import logging

import websockets
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from websockets.exceptions import ConnectionClosed

from app.config import get_settings


router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/pointcloud")
async def pointcloud(websocket: WebSocket) -> None:
    await websocket.accept()
    target = get_settings().pointcloud_bridge_ws_url
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
        logger.warning("pointcloud bridge unavailable at %s: %s", target, exc)
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="pointcloud bridge unavailable")
    except Exception:
        logger.exception("pointcloud websocket proxy failed")
        with contextlib.suppress(Exception):
            await websocket.close(code=1011, reason="pointcloud proxy failed")
