"""One-off: delete ALL ONVIF OSDs from the camera via Media2.

The camera burns its own OSD (timestamp / channel name) onto the stream before
encoding. Since PipeSight burns its own OSD (time/distance/project) with ffmpeg,
the camera's native OSD is redundant and overlaps ours. This removes every OSD
the camera reports, so only PipeSight's OSD remains.

It is reversible only via the camera's own web UI (re-enabling OSD there); ONVIF
DeleteOSD is permanent for the deleted entries.

Run on the Ubuntu server:
    cd ~/PipeSightConsoleServer/server
    source .venv/bin/activate

    # Option 1: look the camera up from the DB by code (needs the backend to
    # have created the tables and the camera to be configured):
    python scripts/onvif_delete_osd.py                # camera code 'front'
    python scripts/onvif_delete_osd.py rear           # another camera code

    # Option 2: pass connection details directly (no DB needed):
    python scripts/onvif_delete_osd.py 192.168.71.21 admin L26FDBCF
    python scripts/onvif_delete_osd.py 192.168.71.21 admin L26FDBCF 80

It first prints every OSD token it finds, deletes each one, then re-reads to
confirm none remain.
"""
from __future__ import annotations

import asyncio
import sys
import xml.dom.minidom as minidom
import xml.etree.ElementTree as ET

sys.path.insert(0, ".")

from app.drivers.onvif_client import (  # noqa: E402
    OnvifConfig,
    OnvifError,
    local_name,
    normalize_xaddr,
    post_soap,
    service_url,
    service_xaddr,
    xml_escape,
)


MEDIA2_NS = "http://www.onvif.org/ver20/media/wsdl"


def _config_from_args() -> tuple[OnvifConfig, str]:
    """Build an OnvifConfig from CLI args, or from the DB by camera code.

    Forms:
      <ip> <user> <pass> [port]   -> direct connection (no DB)
      [code]                      -> look up camera by code in the DB
    """
    args = sys.argv[1:]
    looks_like_ip = bool(args) and args[0].count(".") == 3 and args[0].replace(".", "").isdigit()
    if looks_like_ip:
        ip = args[0]
        user = args[1] if len(args) > 1 else "admin"
        password = args[2] if len(args) > 2 else ""
        port = int(args[3]) if len(args) > 3 else 80
        return OnvifConfig(ip=ip, username=user, password=password, port=port), ip

    code = args[0] if args else "front"
    from app.db import SessionLocal
    from app.models import CameraDevice
    from sqlalchemy import select

    with SessionLocal() as db:
        camera = db.scalar(select(CameraDevice).where(CameraDevice.code == code))
    if camera is None or not camera.ip:
        raise SystemExit(
            f"camera '{code}' not found / has no IP. Either start the backend and "
            f"configure the camera, or pass details directly: "
            f"python scripts/onvif_delete_osd.py <ip> <user> <pass> [port]"
        )
    return (
        OnvifConfig(
            ip=camera.ip,
            username=camera.username,
            password=camera.password,
            port=camera.onvif_port or 80,
        ),
        camera.code,
    )


def pretty(xml_text: str) -> str:
    try:
        return minidom.parseString(xml_text).toprettyxml(indent="  ")
    except Exception:
        return xml_text


def osd_tokens(xml_text: str) -> list[str]:
    """Pull the token attribute off every <...:OSDs> element in GetOSDsResponse."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    tokens: list[str] = []
    for elem in root.iter():
        if local_name(elem.tag) != "OSDs":
            continue
        token = elem.attrib.get("token")
        if token is None:
            # Some stacks namespace the attribute.
            for key, value in elem.attrib.items():
                if local_name(key) == "token":
                    token = value
                    break
        if token and token not in tokens:
            tokens.append(token)
    return tokens


async def resolve_media2(config: OnvifConfig) -> str:
    device_url = service_url(config, "/onvif/device_service")
    media2_url = service_url(config, "/onvif/media2_service")
    body = "<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>"
    try:
        services_xml = await post_soap(config, device_url, body)
        discovered = service_xaddr(services_xml, MEDIA2_NS)
        if discovered:
            media2_url = normalize_xaddr(device_url, discovered)
    except OnvifError as exc:
        print(f"[warn] GetServices failed, using default media2 url: {exc}")
    return media2_url


async def main() -> None:
    config, label = _config_from_args()
    media2_url = await resolve_media2(config)
    print("=" * 64)
    print(f"camera     : {label} ({config.ip})")
    print(f"media2 url  : {media2_url}")
    print("=" * 64)

    osds_xml = await post_soap(config, media2_url, "<tr2:GetOSDs/>")
    tokens = osd_tokens(osds_xml)
    print(f"found OSD tokens: {tokens or '(none)'}")
    if not tokens:
        print("Nothing to delete.")
        print("\n### RAW GetOSDs (in case tokens were not parsed):")
        print(pretty(osds_xml))
        return

    for token in tokens:
        body = f"<tr2:DeleteOSD><tr2:OSDToken>{xml_escape(token)}</tr2:OSDToken></tr2:DeleteOSD>"
        try:
            await post_soap(config, media2_url, body)
            print(f"deleted OSD: {token}")
        except OnvifError as exc:
            print(f"[ERROR] failed to delete {token}: {exc}")

    # Verify.
    remaining = osd_tokens(await post_soap(config, media2_url, "<tr2:GetOSDs/>"))
    if remaining:
        print(f"\n>>> WARNING: OSDs still present: {remaining}")
    else:
        print("\n>>> SUCCESS: all OSDs removed.")


if __name__ == "__main__":
    asyncio.run(main())
