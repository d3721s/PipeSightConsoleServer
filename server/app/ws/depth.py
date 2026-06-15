from __future__ import annotations

import logging

from fastapi import APIRouter, WebSocket

from app.config import get_settings
from app.ws._proxy import proxy_bridge_stream


router = APIRouter()
logger = logging.getLogger(__name__)


@router.websocket("/ws/depth")
async def depth(websocket: WebSocket) -> None:
    await proxy_bridge_stream(
        websocket,
        get_settings().depth_bridge_ws_url,
        logger,
        "depth bridge",
    )
