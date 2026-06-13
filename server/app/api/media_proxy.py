from __future__ import annotations

import httpx
from fastapi import APIRouter, Request, Response

from app.config import get_settings


router = APIRouter(tags=["whep-proxy"])
settings = get_settings()


def _mediamtx_base() -> str:
    return f"http://127.0.0.1:{settings.mediamtx_webrtc_port}"


# WebRTC/WHEP reverse proxy.
#
# The browser may be on a different machine than the server, so the page uses a
# relative "/whep/..." URL (see media_service.whep_url) and we forward it here to
# MediaMTX running on localhost. Only the WHEP *signaling* (SDP offer/answer)
# flows through this proxy; the actual media is UDP and connects directly to
# MediaMTX via ICE candidates, so it never touches this route.
@router.api_route(
    "/whep/{path:path}",
    methods=["GET", "POST", "PATCH", "DELETE", "OPTIONS"],
)
async def whep_proxy(path: str, request: Request) -> Response:
    target = f"{_mediamtx_base()}/{path}"
    body = await request.body()
    # Drop hop-by-hop / host headers; let httpx set its own.
    headers = {
        key: value
        for key, value in request.headers.items()
        if key.lower() not in {"host", "content-length", "connection"}
    }
    async with httpx.AsyncClient(timeout=15.0) as client:
        upstream = await client.request(
            request.method,
            target,
            content=body,
            headers=headers,
            params=request.query_params,
        )
    response_headers = {
        key: value
        for key, value in upstream.headers.items()
        if key.lower() not in {"content-length", "content-encoding", "transfer-encoding", "connection"}
    }
    return Response(
        content=upstream.content,
        status_code=upstream.status_code,
        headers=response_headers,
        media_type=upstream.headers.get("content-type"),
    )
