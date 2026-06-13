from __future__ import annotations

from dataclasses import dataclass

from app.drivers.onvif_client import (
    OnvifConfig,
    OnvifError,
    post_soap,
    profile_tokens,
    service_url,
    service_xaddr,
    sleep_ms,
    xml_escape,
    normalize_xaddr,
)
from app.models import CameraDevice


MEDIA2_NS = "http://www.onvif.org/ver20/media/wsdl"
PTZ_NS = "http://www.onvif.org/ver20/ptz/wsdl"
PAN_TILT_SPACE = "http://www.onvif.org/ver10/tptz/PanTiltSpaces/VelocityGenericSpace"
VELOCITY = 0.25


@dataclass
class PtzSession:
    device_url: str
    media2_url: str
    ptz_url: str
    profile_token: str


class OnvifPtzDriver:
    def __init__(self) -> None:
        self._sessions: dict[str, PtzSession] = {}

    async def probe(self, camera: CameraDevice) -> PtzSession:
        return await self._session_for(camera)

    async def step(self, camera: CameraDevice, dx: float, dy: float) -> None:
        if dx == 0 and dy == 0:
            return
        await self.start(camera, dx, dy, timeout_seconds=1)
        await sleep_ms(120)
        await self.stop(camera)

    async def start(self, camera: CameraDevice, dx: float, dy: float, timeout_seconds: int = 10) -> None:
        session = await self._session_for(camera)
        vx = dx * VELOCITY
        vy = -dy * VELOCITY
        body = f"""
<tptz:ContinuousMove>
  <tptz:ProfileToken>{xml_escape(session.profile_token)}</tptz:ProfileToken>
  <tptz:Velocity>
    <tt:PanTilt x="{vx:.6f}" y="{vy:.6f}" space="{PAN_TILT_SPACE}"></tt:PanTilt>
  </tptz:Velocity>
  <tptz:Timeout>PT{timeout_seconds}S</tptz:Timeout>
</tptz:ContinuousMove>
"""
        await post_soap(self._config(camera), session.ptz_url, body)

    async def stop(self, camera: CameraDevice) -> None:
        session = await self._session_for(camera)
        body = f"""
<tptz:Stop>
  <tptz:ProfileToken>{xml_escape(session.profile_token)}</tptz:ProfileToken>
  <tptz:PanTilt>true</tptz:PanTilt>
</tptz:Stop>
"""
        await post_soap(self._config(camera), session.ptz_url, body)

    def invalidate(self, camera: CameraDevice) -> None:
        self._sessions.pop(self._key(camera), None)

    async def _session_for(self, camera: CameraDevice) -> PtzSession:
        key = self._key(camera)
        existing = self._sessions.get(key)
        if existing:
            return existing

        if not camera.ip:
            raise OnvifError("camera IP is empty")

        config = self._config(camera)
        device_url = service_url(config, "/onvif/device_service")
        media2_url = service_url(config, "/onvif/media2_service")
        ptz_url = service_url(config, "/onvif/ptz_service")

        services_body = """
<tds:GetServices>
  <tds:IncludeCapability>false</tds:IncludeCapability>
</tds:GetServices>
"""
        try:
            services_xml = await post_soap(config, device_url, services_body)
            discovered_media2 = service_xaddr(services_xml, MEDIA2_NS)
            discovered_ptz = service_xaddr(services_xml, PTZ_NS)
            if discovered_media2:
                media2_url = normalize_xaddr(device_url, discovered_media2)
            if discovered_ptz:
                ptz_url = normalize_xaddr(device_url, discovered_ptz)
        except OnvifError:
            # Dahua/Lecheng devices still work with default endpoints in many cases.
            pass

        profiles_xml = await post_soap(config, media2_url, "<tr2:GetProfiles/>")
        tokens = profile_tokens(profiles_xml)
        profile_token = "Profile000" if "Profile000" in tokens else (tokens[0] if tokens else "Profile000")

        session = PtzSession(
            device_url=device_url,
            media2_url=media2_url,
            ptz_url=ptz_url,
            profile_token=profile_token,
        )
        self._sessions[key] = session
        return session

    @staticmethod
    def _config(camera: CameraDevice) -> OnvifConfig:
        return OnvifConfig(
            ip=camera.ip,
            username=camera.username,
            password=camera.password,
            port=camera.onvif_port or 80,
        )

    @staticmethod
    def _key(camera: CameraDevice) -> str:
        return f"{camera.code}|{camera.ip}|{camera.username}|{camera.password}"


ptz_driver = OnvifPtzDriver()

