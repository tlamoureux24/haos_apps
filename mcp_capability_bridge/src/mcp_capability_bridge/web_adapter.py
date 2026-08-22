"""Static Web target contract for the browser confinement gate."""

from __future__ import annotations

import asyncio
import ipaddress
import json
import socket
from typing import Any, TYPE_CHECKING
from urllib.parse import urlparse
from mcp_capability_bridge.contracts import AdapterCallError, Capability, InvocationContext

if TYPE_CHECKING:
    from mcp_capability_bridge.web_sessions import WebSessionManager


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
    def __init__(self, sessions: "WebSessionManager | None" = None): self.sessions=sessions
    def validate_target(self,configuration:dict[str,Any],secret:bytes|None)->None:
        required={"base_url","resolved_addresses","navigation_origins","authentication_origins","resource_origins","websocket_origins","verify_tls","inactivity_seconds","absolute_seconds","authentication"}
        if set(configuration)!=required:raise ValueError("invalid_web_target")
        base=origin(str(configuration["base_url"]));validate_addresses(configuration["resolved_addresses"])
        for category in ("navigation_origins","authentication_origins","resource_origins","websocket_origins"):
            values=configuration[category]
            if not isinstance(values,list) or len(values)>16 or len(values)!=len(set(values)):raise ValueError("invalid_web_origins")
            normalized=[origin(str(value)) for value in values]
            if normalized!=values:raise ValueError("invalid_web_origins")
        if base not in configuration["navigation_origins"] or base not in configuration["resource_origins"]:raise ValueError("invalid_web_origins")
        if configuration["navigation_origins"]!=[base] or configuration["resource_origins"]!=[base] or configuration["websocket_origins"]:raise ValueError("invalid_web_origins")
        authentication=configuration["authentication"]
        if not isinstance(authentication,dict) or authentication.get("mode") not in {"none","basic","form"}:raise ValueError("invalid_web_authentication")
        mode=authentication["mode"]
        if mode=="none" and (set(authentication)!={"mode"} or secret is not None):raise ValueError("invalid_web_authentication")
        if mode=="basic" and (set(authentication)!={"mode"} or secret is None):raise ValueError("invalid_web_authentication")
        if mode=="form":
            fields={"mode","login_path","username_selector","password_selector","submit_selector"}
            if set(authentication)!=fields or secret is None or not str(authentication["login_path"]).startswith("/"):raise ValueError("invalid_web_authentication")
            if any(not 1<=len(str(authentication[key]))<=256 for key in fields-{"mode"}):raise ValueError("invalid_web_authentication")
            if configuration["authentication_origins"]!=[base]:raise ValueError("invalid_web_origins")
        elif configuration["authentication_origins"]:raise ValueError("invalid_web_origins")
        if mode in {"basic","form"}:
            try:credentials=json.loads((secret or b"").decode())
            except Exception as exc:raise ValueError("invalid_web_authentication") from exc
            if set(credentials)!={"mode","username","password"} or credentials.get("mode")!=mode or not 1<=len(credentials.get("username",""))<=256 or not 1<=len(credentials.get("password",""))<=1024:raise ValueError("invalid_web_authentication")
        if not isinstance(configuration["verify_tls"],bool):raise ValueError("invalid_web_tls_policy")
        if not isinstance(configuration["inactivity_seconds"],int) or not 30<=configuration["inactivity_seconds"]<=3600:raise ValueError("invalid_web_session_limits")
        if not isinstance(configuration["absolute_seconds"],int) or not configuration["inactivity_seconds"]<=configuration["absolute_seconds"]<=14400:raise ValueError("invalid_web_session_limits")
    def capabilities(self,configuration:dict[str,Any]):
        handle={"type":"string","minLength":40,"maxLength":64}
        return (
            Capability("open","web_open","Open a fresh isolated read-only Web session.",{"type":"object","properties":{},"additionalProperties":False}),
            Capability("snapshot","web_snapshot","Read a bounded accessibility snapshot.",{"type":"object","properties":{"session":handle},"required":["session"],"additionalProperties":False}),
            Capability("wait","web_wait","Wait briefly, then read a fresh bounded snapshot.",{"type":"object","properties":{"session":handle,"seconds":{"type":"integer","minimum":1,"maximum":30}},"required":["session","seconds"],"additionalProperties":False}),
            Capability("close","web_close","Close an isolated Web session.",{"type":"object","properties":{"session":handle},"required":["session"],"additionalProperties":False}),
        )
    def capabilities_for_target(self,configuration:dict[str,Any],target_key:str):
        return tuple(Capability(item.capability_id,f"web_{target_key}_{item.capability_id}",item.description,item.input_schema,item.effect_capable) for item in self.capabilities(configuration))
    async def invoke(self,*_):raise AdapterCallError("web_session_context_required")
    async def invoke_scoped(self,context:InvocationContext,capability_id:str,configuration:dict[str,Any],secret:bytes|None,arguments:dict[str,Any]):
        if self.sessions is None:raise AdapterCallError("web_runtime_unavailable")
        if capability_id=="open":return await self.sessions.open(context,configuration,secret)
        handle=str(arguments.get("session",""))
        if capability_id=="snapshot":return await self.sessions.snapshot(context,handle)
        if capability_id=="wait":return await self.sessions.wait(context,handle,int(arguments["seconds"]))
        if capability_id=="close":return await self.sessions.close(context,handle)
        raise AdapterCallError("capability_not_available")
