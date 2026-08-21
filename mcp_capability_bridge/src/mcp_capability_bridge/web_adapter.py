"""Static Web target contract for the browser confinement gate."""

from __future__ import annotations

import asyncio
import ipaddress
import socket
from typing import Any
from urllib.parse import urlparse


def origin(value: str) -> str:
    parsed=urlparse(value)
    if parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.username or parsed.password or parsed.fragment:
        raise ValueError("invalid_web_origin")
    port=parsed.port
    authority=parsed.hostname.lower() if port is None or (parsed.scheme=="http" and port==80) or (parsed.scheme=="https" and port==443) else f"{parsed.hostname.lower()}:{port}"
    return f"{parsed.scheme}://{authority}"


def validate_addresses(values: object) -> tuple[str,...]:
    if not isinstance(values,list) or not 1<=len(values)<=16:raise ValueError("invalid_web_addresses")
    try:result=tuple(sorted({str(ipaddress.ip_address(str(value))) for value in values}))
    except ValueError as exc:raise ValueError("invalid_web_addresses") from exc
    if len(result)!=len(values):raise ValueError("invalid_web_addresses")
    return result


async def resolve_host(host: str, port: int) -> tuple[str,...]:
    def resolve():return socket.getaddrinfo(host,port,type=socket.SOCK_STREAM)
    try:rows=await asyncio.wait_for(asyncio.to_thread(resolve),timeout=10)
    except (OSError,asyncio.TimeoutError) as exc:raise ValueError("web_resolution_failed") from exc
    return tuple(sorted({str(ipaddress.ip_address(row[4][0])) for row in rows}))


class NetworkPolicy:
    def __init__(self,configuration:dict[str,Any]):
        self.base_origin=origin(configuration["base_url"]);self.addresses=validate_addresses(configuration["resolved_addresses"])
        self.origins={category:frozenset(configuration.get(category,[])) for category in ("navigation_origins","authentication_origins","resource_origins","websocket_origins")}
    def authorize(self,url:str,category:str)->None:
        if category not in self.origins:raise ValueError("invalid_web_request_category")
        candidate=origin(url)
        if candidate not in self.origins[category]:raise PermissionError("web_origin_denied")
    async def verify_resolution(self)->None:
        parsed=urlparse(self.base_origin);current=await resolve_host(parsed.hostname or "",parsed.port or (443 if parsed.scheme=="https" else 80))
        if current!=self.addresses:raise PermissionError("web_resolution_changed")


class WebAdapter:
    type_key="web"
    display_name="Web"
    def validate_target(self,configuration:dict[str,Any],secret:bytes|None)->None:
        required={"base_url","resolved_addresses","navigation_origins","authentication_origins","resource_origins","websocket_origins","verify_tls","inactivity_seconds","absolute_seconds"}
        if set(configuration)!=required or secret is not None:raise ValueError("invalid_web_target")
        base=origin(str(configuration["base_url"]));validate_addresses(configuration["resolved_addresses"])
        for category in ("navigation_origins","authentication_origins","resource_origins","websocket_origins"):
            values=configuration[category]
            if not isinstance(values,list) or len(values)>16 or len(values)!=len(set(values)):raise ValueError("invalid_web_origins")
            normalized=[origin(str(value)) for value in values]
            if normalized!=values:raise ValueError("invalid_web_origins")
        if base not in configuration["navigation_origins"] or base not in configuration["resource_origins"]:raise ValueError("invalid_web_origins")
        if configuration["navigation_origins"]!=[base] or configuration["resource_origins"]!=[base] or configuration["authentication_origins"] or configuration["websocket_origins"]:raise ValueError("invalid_web_origins")
        if not isinstance(configuration["verify_tls"],bool):raise ValueError("invalid_web_tls_policy")
        if not isinstance(configuration["inactivity_seconds"],int) or not 30<=configuration["inactivity_seconds"]<=3600:raise ValueError("invalid_web_session_limits")
        if not isinstance(configuration["absolute_seconds"],int) or not configuration["inactivity_seconds"]<=configuration["absolute_seconds"]<=14400:raise ValueError("invalid_web_session_limits")
    def capabilities(self,configuration:dict[str,Any]):return ()
    async def invoke(self,*_):raise RuntimeError("web_tools_not_available")
