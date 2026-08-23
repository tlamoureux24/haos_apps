"""Authenticated, policy-filtered MCP Streamable HTTP surface."""

from __future__ import annotations

import json
from typing import Any, Iterable

import anyio
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.server import Settings as FastMCPSettings
from mcp.types import TextContent, Tool as MCPTool
from starlette.responses import JSONResponse

from agent_control_plane import __version__
from agent_control_plane.connectors import invoke_streamable_http
from agent_control_plane.control_plane import AuthenticationError, AuthorizationError, ControlPlane
from agent_control_plane.redaction import redact


TOOL_ACTIONS = {
    "control_plane_status_v1": "control_plane.status.read",
    "permissions_get_effective_v1": "permissions.effective.read",
    "events_list_v1": "events.read",
    "events_get_v1": "events.read",
    "jobs_list_v1": "jobs.read",
    "jobs_get_v1": "jobs.read",
    "jobs_claim_v1": "jobs.claim",
    "jobs_heartbeat_v1": "jobs.heartbeat",
    "jobs_complete_v1": "jobs.complete",
    "jobs_fail_v1": "jobs.fail",
    "reports_list_v1": "reports.read",
    "reports_get_v1": "reports.read",
}

# mcp 1.28.1 leaves its generic lifespan annotation unresolved when imported
# under Python 3.14. Rebuild after the SDK module is fully loaded, before its
# BaseSettings instance reads any source.
FastMCPSettings.model_rebuild()


def capability_result_content(
    result: Any, sensitive_values: Iterable[Any] = ()
) -> list[TextContent]:
    """Serialize an upstream result only after transient value-aware redaction."""
    safe_result = redact(result, sensitive_values)
    return [TextContent(type="text", text=json.dumps(safe_result, ensure_ascii=False))]


def request_token(context: Context) -> str:
    authorization = context.request_context.request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("missing_credential")
    return token


class GovernedMCP(FastMCP):
    def __init__(self, control_plane: ControlPlane):
        super().__init__(
            "Agent Control Plane",
            instructions="Governed access to Agent Control Plane jobs and state.",
            stateless_http=True,
            # Dynamic task capabilities require server notifications.  Keep the
            # Streamable HTTP response open as SSE so clients can receive
            # notifications/tools/list_changed alongside a tool result.
            json_response=False,
            streamable_http_path="/mcp",
            host="0.0.0.0",
        )
        self.control_plane = control_plane

    def current_identity(self):
        return self.control_plane.authenticate(request_token(self.get_context()))

    async def list_tools(self):
        identity = await anyio.to_thread.run_sync(self.current_identity)
        tools = await super().list_tools()
        visible = [tool for tool in tools if TOOL_ACTIONS.get(tool.name) in identity.actions]
        if "jobs.claim" in identity.actions:
            capabilities = await anyio.to_thread.run_sync(self.control_plane.active_capabilities, identity)
            if not capabilities:
                capabilities = await anyio.to_thread.run_sync(self.control_plane.next_queued_capabilities, identity)
            visible.extend(
                MCPTool(
                    name=capability["name"],
                    description=capability["description"],
                    inputSchema=capability["input_schema"],
                )
                for capability in capabilities
            )
        return visible

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        action = TOOL_ACTIONS.get(name)
        if action is None:
            identity = await anyio.to_thread.run_sync(self.current_identity)
            context = self.get_context()
            correlation_id = context.request_context.request.headers.get("x-request-id", "mcp-capability")
            resolved = await anyio.to_thread.run_sync(
                self.control_plane.resolve_active_capability,
                identity,
                name,
                arguments,
                correlation_id,
            )
            try:
                result = await invoke_streamable_http(
                    resolved["url"],
                    resolved["bearer_token"],
                    resolved["tool_name"],
                    resolved["arguments"],
                    resolved["certificate_sha256"],
                )
            except Exception:
                await anyio.to_thread.run_sync(
                    self.control_plane.record_capability_result,
                    identity,
                    name,
                    resolved["job_id"],
                    resolved["connector_id"],
                    False,
                    correlation_id,
                )
                # Do not retain an upstream exception that may echo injected
                # sensitive arguments in an ASGI traceback or application log.
                raise ValueError("upstream_call_failed") from None
            await anyio.to_thread.run_sync(
                self.control_plane.record_capability_result,
                identity,
                name,
                resolved["job_id"],
                resolved["connector_id"],
                True,
                correlation_id,
            )
            return capability_result_content(result, resolved.get("sensitive_values", ()))
        identity = await anyio.to_thread.run_sync(self.current_identity)
        self.control_plane.authorize(identity, action)
        return await super().call_tool(name, arguments)


class OpaqueBearerMiddleware:
    def __init__(self, app, control_plane: ControlPlane):
        self.app = app
        self.control_plane = control_plane

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") != "/mcp":
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

    @server.tool(name="control_plane_status_v1", structured_output=True)
    def control_plane_status() -> dict[str, object]:
        """Return the control plane version and durable object counters."""
        return {"status": "ready", "version": __version__, **control_plane.status_counts()}

    @server.tool(name="permissions_get_effective_v1", structured_output=True)
    def permissions_get_effective(ctx: Context) -> dict[str, object]:
        """Return the authenticated caller identity and effective control-plane actions."""
        identity = control_plane.authenticate(request_token(ctx))
        return {
            "identity": {"id": identity.identity_id, "type": identity.identity_type, "display_name": identity.display_name},
            "policy_revision_id": identity.policy_revision_id,
            "control_plane_actions": list(identity.actions),
            "capabilities": [],
        }

    @server.tool(name="events_list_v1", structured_output=True)
    def events_list() -> dict[str, object]:
        """List up to 100 newest redacted events."""
        return {"events": control_plane.list_events(), "limit": 100}

    @server.tool(name="events_get_v1", structured_output=True)
    def events_get(event_id: str) -> dict[str, object]:
        """Return one redacted event by its exact opaque identifier."""
        event = control_plane.get_event(event_id)
        if event is None:
            raise ValueError("event_not_found")
        return {"event": event}

    @server.tool(name="jobs_list_v1", structured_output=True)
    def jobs_list() -> dict[str, object]:
        """List up to 100 newest durable jobs."""
        return {"jobs": control_plane.list_jobs(), "limit": 100}

    @server.tool(name="jobs_get_v1", structured_output=True)
    def jobs_get(job_id: str) -> dict[str, object]:
        """Return one durable job and its redacted input by exact identifier."""
        job = control_plane.get_job(job_id)
        if job is None:
            raise ValueError("job_not_found")
        return {"job": job}

    @server.tool(name="jobs_claim_v1", structured_output=True)
    async def jobs_claim(ctx: Context) -> dict[str, object]:
        """Atomically lease the oldest queued job eligible for this client."""
        identity = await anyio.to_thread.run_sync(control_plane.authenticate, request_token(ctx))
        lease = await anyio.to_thread.run_sync(
            control_plane.claim_job,
            identity,
            ctx.request_context.request.headers.get("x-request-id", "mcp-claim"),
        )
        if lease is None:
            return {"claimed": False}
        await ctx.session.send_tool_list_changed()
        return {"claimed": True, "job": lease.job, "lease_token": lease.lease_token, "lease_expires_at": lease.lease_expires_at}

    @server.tool(name="jobs_heartbeat_v1", structured_output=True)
    def jobs_heartbeat(job_id: str, lease_token: str, ctx: Context) -> dict[str, object]:
        """Extend an owned unexpired lease within its maximum runtime."""
        identity = control_plane.authenticate(request_token(ctx))
        expires = control_plane.heartbeat_job(identity, job_id, lease_token, "mcp-heartbeat")
        return {"job_id": job_id, "lease_expires_at": expires}

    @server.tool(name="jobs_complete_v1", structured_output=True)
    async def jobs_complete(job_id: str, lease_token: str, completion_key: str, report: dict[str, object], ctx: Context) -> dict[str, object]:
        """Complete an owned lease with one immutable redacted report."""
        identity = await anyio.to_thread.run_sync(control_plane.authenticate, request_token(ctx))
        report_id = await anyio.to_thread.run_sync(
            control_plane.complete_job,
            identity,
            job_id,
            lease_token,
            completion_key,
            report,
            "mcp-complete",
        )
        await ctx.session.send_tool_list_changed()
        return {"job_id": job_id, "state": "completed", "report_id": report_id}

    @server.tool(name="jobs_fail_v1", structured_output=True)
    async def jobs_fail(job_id: str, lease_token: str, completion_key: str, reason: str, retryable: bool, ctx: Context) -> dict[str, object]:
        """Idempotently finish an owned lease as failed with a bounded reason."""
        identity = await anyio.to_thread.run_sync(control_plane.authenticate, request_token(ctx))
        state = await anyio.to_thread.run_sync(
            control_plane.fail_job,
            identity,
            job_id,
            lease_token,
            completion_key,
            reason,
            retryable,
            "mcp-fail",
        )
        await ctx.session.send_tool_list_changed()
        return {"job_id": job_id, "state": state}

    @server.tool(name="reports_list_v1", structured_output=True)
    def reports_list() -> dict[str, object]:
        """List up to 100 newest redacted structured reports."""
        return {"reports": control_plane.list_reports(), "limit": 100}

    @server.tool(name="reports_get_v1", structured_output=True)
    def reports_get(report_id: str) -> dict[str, object]:
        """Return one redacted structured report by its exact identifier."""
        report = control_plane.get_report(report_id)
        if report is None:
            raise ValueError("report_not_found")
        return {"report": report}

    return server
