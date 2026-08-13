"""Authenticated, policy-filtered MCP Streamable HTTP surface."""

from __future__ import annotations

from typing import Any

import anyio
from mcp.server.fastmcp import Context, FastMCP
from starlette.responses import JSONResponse

from agent_gateway import __version__
from agent_gateway.control_plane import AuthenticationError, AuthorizationError, ControlPlane


TOOL_ACTIONS = {
    "gateway_status_v1": "gateway.status.read",
    "permissions_get_effective_v1": "permissions.effective.read",
    "events_list_v1": "events.read",
    "jobs_list_v1": "jobs.read",
    "reports_list_v1": "reports.read",
}


def request_token(context: Context) -> str:
    authorization = context.request_context.request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("missing_credential")
    return token


class GovernedMCP(FastMCP):
    def __init__(self, control_plane: ControlPlane):
        super().__init__(
            "Agent Gateway",
            instructions="Governed read-only access to Agent Gateway state.",
            stateless_http=True,
            json_response=True,
            streamable_http_path="/mcp",
            host="0.0.0.0",
        )
        self.control_plane = control_plane

    def current_identity(self):
        return self.control_plane.authenticate(request_token(self.get_context()))

    async def list_tools(self):
        identity = await anyio.to_thread.run_sync(self.current_identity)
        tools = await super().list_tools()
        return [tool for tool in tools if TOOL_ACTIONS[tool.name] in identity.actions]

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        action = TOOL_ACTIONS.get(name)
        if action is None:
            raise AuthorizationError("unknown_action")
        identity = await anyio.to_thread.run_sync(self.current_identity)
        self.control_plane.authorize(identity, action)
        return await super().call_tool(name, arguments)


class OpaqueBearerMiddleware:
    def __init__(self, app, control_plane: ControlPlane):
        self.app = app
        self.control_plane = control_plane

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw = headers.get(b"authorization", b"").decode("latin-1")
        scheme, separator, token = raw.partition(" ")
        try:
            if not separator or scheme.lower() != "bearer" or not token:
                raise AuthenticationError("missing_credential")
            await anyio.to_thread.run_sync(self.control_plane.authenticate, token)
        except AuthenticationError as exc:
            response = JSONResponse({"error": {"code": str(exc)}}, status_code=401)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)


def create_mcp(control_plane: ControlPlane) -> GovernedMCP:
    server = GovernedMCP(control_plane)

    @server.tool(name="gateway_status_v1", structured_output=True)
    def gateway_status() -> dict[str, object]:
        """Return the gateway version and durable object counters."""
        return {"status": "ready", "version": __version__, **control_plane.status_counts()}

    @server.tool(name="permissions_get_effective_v1", structured_output=True)
    def permissions_get_effective(ctx: Context) -> dict[str, object]:
        """Return the authenticated caller identity and effective gateway actions."""
        identity = control_plane.authenticate(request_token(ctx))
        return {
            "identity": {"id": identity.identity_id, "type": identity.identity_type, "display_name": identity.display_name},
            "policy_revision_id": identity.policy_revision_id,
            "gateway_actions": list(identity.actions),
            "capabilities": [],
        }

    @server.tool(name="events_list_v1", structured_output=True)
    def events_list() -> dict[str, object]:
        """List up to 100 newest redacted events."""
        return {"events": control_plane.list_events(), "limit": 100}

    @server.tool(name="jobs_list_v1", structured_output=True)
    def jobs_list() -> dict[str, object]:
        """List up to 100 newest durable jobs."""
        return {"jobs": control_plane.list_jobs(), "limit": 100}

    @server.tool(name="reports_list_v1", structured_output=True)
    def reports_list() -> dict[str, object]:
        """List up to 100 newest redacted structured reports."""
        return {"reports": control_plane.list_reports(), "limit": 100}

    return server
