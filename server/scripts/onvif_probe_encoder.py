"""One-off, READ-ONLY ONVIF probe for the camera's video encoder settings.

Run on the Ubuntu server:
    cd ~/PipeSightConsoleServer/server
    source .venv/bin/activate
    python scripts/onvif_probe_encoder.py

It changes NOTHING on the camera. It prints:
  - the Media2 service URL and profile tokens
  - each profile's current video encoder config (token, encoding, resolution, fps, bitrate)
  - the supported encoder OPTIONS (so we can confirm H.264 is allowed)

Paste the full output back so the H.264 write request can be built with the
exact tokens/values this camera expects.
"""
from __future__ import annotations

import asyncio
import sys
import xml.dom.minidom as minidom

# Reuse the project's ONVIF client (auth, SOAP, fault parsing).
sys.path.insert(0, ".")

from app.config import get_settings  # noqa: E402
from app.db import SessionLocal  # noqa: E402
from app.drivers.onvif_client import (  # noqa: E402
    OnvifConfig,
    OnvifError,
    normalize_xaddr,
    post_soap,
    profile_tokens,
    service_url,
    service_xaddr,
)
from app.models import CameraDevice  # noqa: E402
from sqlalchemy import select  # noqa: E402


MEDIA2_NS = "http://www.onvif.org/ver20/media/wsdl"
CAMERA_CODE = "front"  # change to "rear" if probing the other camera


def pretty(xml_text: str) -> str:
    try:
        return minidom.parseString(xml_text).toprettyxml(indent="  ")
    except Exception:
        return xml_text


async def main() -> None:
    with SessionLocal() as db:
        camera = db.scalar(select(CameraDevice).where(CameraDevice.code == CAMERA_CODE))
    if camera is None or not camera.ip:
        print(f"camera '{CAMERA_CODE}' not found or has no IP")
        return

    config = OnvifConfig(
        ip=camera.ip,
        username=camera.username,
        password=camera.password,
        port=camera.onvif_port or 80,
    )
    device_url = service_url(config, "/onvif/device_service")
    media2_url = service_url(config, "/onvif/media2_service")

    # Discover the real Media2 endpoint (some firmwares differ from the default).
    try:
        services_xml = await post_soap(config, device_url, "<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>")
        discovered = service_xaddr(services_xml, MEDIA2_NS)
        if discovered:
            media2_url = normalize_xaddr(device_url, discovered)
    except OnvifError as exc:
        print(f"[warn] GetServices failed, using default media2 url: {exc}")

    print("=" * 70)
    print(f"camera code   : {camera.code}")
    print(f"camera ip     : {camera.ip}")
    print(f"media2 url    : {media2_url}")
    print("=" * 70)

    # 1) Profiles (with embedded video encoder config tokens).
    profiles_xml = await post_soap(config, media2_url, "<tr2:GetProfiles/>")
    tokens = profile_tokens(profiles_xml)
    print(f"\n### PROFILE TOKENS: {tokens}\n")
    print("### RAW GetProfiles (look for VideoEncoderConfiguration token + Encoding):")
    print(pretty(profiles_xml))

    # 2) Current video encoder configurations.
    print("\n### GetVideoEncoderConfigurations (current settings):")
    try:
        vec_xml = await post_soap(config, media2_url, "<tr2:GetVideoEncoderConfigurations/>")
        print(pretty(vec_xml))
    except OnvifError as exc:
        print(f"[warn] GetVideoEncoderConfigurations failed: {exc}")

    # 3) Supported options PER profile — this proves whether H.264 is selectable.
    for token in tokens:
        print(f"\n### GetVideoEncoderConfigurationOptions for profile '{token}':")
        body = f"<tr2:GetVideoEncoderConfigurationOptions><tr2:ProfileToken>{token}</tr2:ProfileToken></tr2:GetVideoEncoderConfigurationOptions>"
        try:
            opts_xml = await post_soap(config, media2_url, body)
            print(pretty(opts_xml))
        except OnvifError as exc:
            print(f"[warn] options for '{token}' failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
