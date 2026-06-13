"""One-off ONVIF write: switch the channel-1 main stream to H.264.

  ⚠️ THIS MODIFIES THE CAMERA. It changes VideoEncoder000 (channel=1 main
  stream) encoding from H265 to H264. Resolution/fps/bitrate/GOP/quality are
  copied verbatim from the probe output and left unchanged. It is reversible
  (run again with ENCODING="H265" or change it back in the camera web UI).

Run on the Ubuntu server:
    cd ~/PipeSightConsoleServer/server
    source .venv/bin/activate
    python scripts/onvif_set_h264.py

After it prints "VERIFY: ... Encoding=H264", restart the backend so MediaMTX
re-pulls the now-H.264 stream:
    (Ctrl-C the running ./run.sh, then) ./run.sh
and refresh the web page on channel 1.
"""
from __future__ import annotations

import asyncio
import sys
import xml.dom.minidom as minidom

sys.path.insert(0, ".")

from app.db import SessionLocal  # noqa: E402
from app.drivers.onvif_client import (  # noqa: E402
    OnvifConfig,
    OnvifError,
    normalize_xaddr,
    post_soap,
    service_url,
    service_xaddr,
)
from app.models import CameraDevice  # noqa: E402
from sqlalchemy import select  # noqa: E402


MEDIA2_NS = "http://www.onvif.org/ver20/media/wsdl"

CAMERA_CODE = "front"
# Values taken VERBATIM from the probe of VideoEncoder000, with only Encoding
# changed H265 -> H264. Resolution kept at 2880x1620 as requested.
CONFIG_TOKEN = "VideoEncoder000"
CONFIG_NAME = "VideoEncoder000"
ENCODING = "H264"          # the only real change (was H265)
WIDTH = 2880
HEIGHT = 1620
GOV_LENGTH = 60
H264_PROFILE = "Main"      # H264 options list ProfilesSupported="Baseline Main High"
FRAME_RATE = 15
BITRATE = 1664
QUALITY = "4.000000"


def pretty(xml_text: str) -> str:
    try:
        return minidom.parseString(xml_text).toprettyxml(indent="  ")
    except Exception:
        return xml_text


def build_set_body() -> str:
    # Media2 SetVideoEncoderConfiguration. Profile element for H264 is
    # tt:Profile inside the config; firmwares vary, so we include it.
    return f"""
<tr2:SetVideoEncoderConfiguration>
  <tr2:Configuration token="{CONFIG_TOKEN}" GovLength="{GOV_LENGTH}" Profile="{H264_PROFILE}">
    <tt:Name>{CONFIG_NAME}</tt:Name>
    <tt:Encoding>{ENCODING}</tt:Encoding>
    <tt:Resolution>
      <tt:Width>{WIDTH}</tt:Width>
      <tt:Height>{HEIGHT}</tt:Height>
    </tt:Resolution>
    <tt:RateControl ConstantBitRate="false">
      <tt:FrameRateLimit>{FRAME_RATE}</tt:FrameRateLimit>
      <tt:BitrateLimit>{BITRATE}</tt:BitrateLimit>
    </tt:RateControl>
    <tt:Quality>{QUALITY}</tt:Quality>
  </tr2:Configuration>
</tr2:SetVideoEncoderConfiguration>
"""


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
    try:
        services_xml = await post_soap(config, device_url, "<tds:GetServices><tds:IncludeCapability>false</tds:IncludeCapability></tds:GetServices>")
        discovered = service_xaddr(services_xml, MEDIA2_NS)
        if discovered:
            media2_url = normalize_xaddr(device_url, discovered)
    except OnvifError as exc:
        print(f"[warn] GetServices failed, using default media2 url: {exc}")

    print(f"media2 url : {media2_url}")
    print(f"target     : {CONFIG_TOKEN}  ->  Encoding={ENCODING}, {WIDTH}x{HEIGHT}, "
          f"profile={H264_PROFILE}, fps={FRAME_RATE}, bitrate={BITRATE}")
    print("-" * 60)

    # Apply.
    try:
        resp = await post_soap(config, media2_url, build_set_body())
        print("SetVideoEncoderConfiguration OK. Response:")
        print(pretty(resp))
    except OnvifError as exc:
        print(f"[ERROR] SetVideoEncoderConfiguration failed: {exc}")
        print("Nothing was changed if this is a schema/validation fault.")
        return

    # Verify by reading the configuration back.
    print("-" * 60)
    print("VERIFY: reading VideoEncoder000 back ...")
    verify_body = f"<tr2:GetVideoEncoderConfigurations><tr2:ConfigurationToken>{CONFIG_TOKEN}</tr2:ConfigurationToken></tr2:GetVideoEncoderConfigurations>"
    try:
        verify_xml = await post_soap(config, media2_url, verify_body)
        print(pretty(verify_xml))
        if "<tt:Encoding>H264</tt:Encoding>" in verify_xml or ">H264<" in verify_xml:
            print("\n>>> SUCCESS: channel 1 main stream is now H264.")
            print(">>> Now restart the backend (./run.sh) and refresh the page on channel 1.")
        else:
            print("\n>>> WARNING: readback does not show H264. Check the XML above.")
    except OnvifError as exc:
        print(f"[warn] verify read failed: {exc}")


if __name__ == "__main__":
    asyncio.run(main())
