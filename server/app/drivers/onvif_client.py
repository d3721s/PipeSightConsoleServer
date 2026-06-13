from __future__ import annotations

import asyncio
import html
import xml.etree.ElementTree as ET
from dataclasses import dataclass

import httpx


class OnvifError(RuntimeError):
    pass


@dataclass(frozen=True)
class OnvifConfig:
    ip: str
    username: str
    password: str
    port: int = 80


def local_name(tag: str) -> str:
    if "}" in tag:
        return tag.rsplit("}", 1)[-1]
    if ":" in tag:
        return tag.rsplit(":", 1)[-1]
    return tag


def soap_envelope(body: str) -> str:
    return f"""<?xml version="1.0" encoding="utf-8"?>
<s:Envelope xmlns:s="http://www.w3.org/2003/05/soap-envelope"
  xmlns:tds="http://www.onvif.org/ver10/device/wsdl"
  xmlns:tt="http://www.onvif.org/ver10/schema"
  xmlns:trt="http://www.onvif.org/ver10/media/wsdl"
  xmlns:tr2="http://www.onvif.org/ver20/media/wsdl"
  xmlns:tptz="http://www.onvif.org/ver20/ptz/wsdl">
  <s:Body>
{body.strip()}
  </s:Body>
</s:Envelope>
"""


def service_url(config: OnvifConfig, path: str) -> str:
    return f"http://{config.ip}:{config.port}{path}"


def normalize_xaddr(device_url: str, xaddr: str) -> str:
    if xaddr.startswith("http://") or xaddr.startswith("https://"):
        return xaddr
    base = httpx.URL(device_url)
    if not xaddr.startswith("/"):
        xaddr = "/" + xaddr
    return str(base.copy_with(path=xaddr))


def xml_escape(value: str) -> str:
    return html.escape(value, quote=True)


def fault_text(xml_text: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""
    parts: list[str] = []
    in_fault = False
    for elem in root.iter():
        name = local_name(elem.tag)
        if name == "Fault":
            in_fault = True
            continue
        if in_fault and name in {"Value", "Text"} and elem.text:
            parts.append(elem.text.strip())
    return " | ".join([p for p in parts if p])


async def post_soap(config: OnvifConfig, url: str, body: str, timeout: float = 8.0) -> str:
    headers = {"Content-Type": "application/soap+xml; charset=utf-8", "Connection": "close"}
    payload = soap_envelope(body)
    auth = httpx.DigestAuth(config.username, config.password) if config.username else None

    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            response = await client.post(url, content=payload, headers=headers, auth=auth)
        except httpx.HTTPError as exc:
            raise OnvifError(str(exc)) from exc

        if response.status_code in {401, 403} and config.username:
            basic_auth = httpx.BasicAuth(config.username, config.password)
            response = await client.post(url, content=payload, headers=headers, auth=basic_auth)

    text = response.text
    fault = fault_text(text)
    if fault:
        raise OnvifError(fault)
    if response.status_code < 200 or response.status_code >= 300:
        raise OnvifError(f"HTTP {response.status_code}")
    return text


def service_xaddr(xml_text: str, namespace_uri: str) -> str:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return ""

    for service in root.iter():
        if local_name(service.tag) != "Service":
            continue
        current_namespace = ""
        current_xaddr = ""
        for child in service.iter():
            name = local_name(child.tag)
            if name == "Namespace" and child.text:
                current_namespace = child.text.strip()
            elif name == "XAddr" and child.text:
                current_xaddr = child.text.strip()
        if current_namespace == namespace_uri and current_xaddr:
            return current_xaddr
    return ""


def profile_tokens(xml_text: str) -> list[str]:
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError:
        return []
    tokens: list[str] = []
    for elem in root.iter():
        if local_name(elem.tag) == "Profiles":
            token = elem.attrib.get("token") or elem.attrib.get("{http://www.onvif.org/ver10/schema}token")
            if token and token not in tokens:
                tokens.append(token)
    return tokens


async def sleep_ms(ms: int) -> None:
    await asyncio.sleep(ms / 1000)

