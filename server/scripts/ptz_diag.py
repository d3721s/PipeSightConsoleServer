"""READ-MOSTLY PTZ diagnostic: reuses the app's ptz_driver to send ONE small
pan-tilt step and prints the exact ONVIF error (if any).

  ⚠️ This DOES physically move the PTZ camera a tiny amount (one ~120ms step to
  the right, then stop). Make sure the camera can safely move before running.

Run on the Ubuntu server:
    cd ~/PipeSightConsoleServer/server
    source .venv/bin/activate
    python scripts/ptz_diag.py

It first re-reads which profile token / ptz URL the driver resolves, then tries
a step. If the camera rejects it, the SOAP fault is printed verbatim so we can
see whether the H.264 change affected Profile000's PTZ binding.
"""
from __future__ import annotations

import asyncio
import sys

sys.path.insert(0, ".")

from app.db import SessionLocal  # noqa: E402
from app.drivers.onvif_ptz import ptz_driver  # noqa: E402
from app.models import CameraDevice  # noqa: E402
from sqlalchemy import select  # noqa: E402


CAMERA_CODE = "front"


async def main() -> None:
    with SessionLocal() as db:
        camera = db.scalar(select(CameraDevice).where(CameraDevice.code == CAMERA_CODE))
    if camera is None or not camera.ip:
        print(f"camera '{CAMERA_CODE}' not found or has no IP")
        return

    # Force a fresh session so we see the currently-resolved profile/ptz URL.
    ptz_driver.invalidate(camera)
    try:
        session = await ptz_driver.probe(camera)
    except Exception as exc:
        print(f"[probe FAILED] {type(exc).__name__}: {exc}")
        return

    print("=" * 60)
    print(f"ip            : {camera.ip}")
    print(f"ptz url       : {session.ptz_url}")
    print(f"media2 url    : {session.media2_url}")
    print(f"profile token : {session.profile_token}")
    print("=" * 60)
    print("Sending ONE small step to the right (dx=+1, dy=0) ...")

    try:
        await ptz_driver.step(camera, 1.0, 0.0)
        print(">>> step() returned WITHOUT error. If the camera did not move,")
        print(">>> the command was accepted but ignored (likely profile/PTZ binding).")
    except Exception as exc:
        print(f">>> step() FAILED: {type(exc).__name__}: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
