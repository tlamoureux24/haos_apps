"""Authenticated namespace-filtered MCP Streamable HTTP server."""

from __future__ import annotations

import json
from typing import Any

import anyio
from jsonschema import Draft202012Validator
from mcp.server.fastmcp import Context, FastMCP
from mcp.server.fastmcp.exceptions import ToolError
from mcp.server.fastmcp.server import Settings as FastMCPSettings
from mcp.types import TextContent, Tool as MCPTool
from starlette.responses import JSONResponse

from mcp_capability_bridge.runtime_state import RuntimeCounters
from mcp_capability_bridge.contracts import AdapterCallError, InvocationContext
from mcp_capability_bridge.store import NamespaceContext, NamespaceStore

MAX_RESULT_BYTES = 256 * 1024
FastMCPSettings.model_rebuild()


def bearer_from_context(context: Context) -> str:
    authorization = context.request_context.request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise PermissionError("invalid_credential")
    return token


class SessionHub:
    def __init__(self):
        self._sessions: list[tuple[str, object]] = []

    def observe(self, namespace_id: str, session: object) -> None:
        if not any(existing is session for _, existing in self._sessions):
            self._sessions.append((namespace_id, session))
            self._sessions = self._sessions[-256:]

    async def tools_changed(self, namespace_id: str) -> None:
        retained: list[tuple[str, object]] = []
        for owner, session in self._sessions:
            try:
                if owner == namespace_id:
                    await session.send_tool_list_changed()
                retained.append((owner, session))
            except Exception:
                continue
        self._sessions = retained


class NamespaceMCP(FastMCP):
    def __init__(self, store: NamespaceStore, counters: RuntimeCounters):
        super().__init__(
            "MCP Capability Bridge",
            instructions="Namespace-isolated access to explicitly published technical capabilities.",
            stateless_http=True,
            json_response=False,
            streamable_http_path="/mcp",
            host="0.0.0.0",
        )
        self.store = store
        self.counters = counters
        self.hub = SessionHub()

    def namespace(self) -> NamespaceContext:
        return self.store.authenticate(bearer_from_context(self.get_context()))

    async def list_tools(self):
        namespace = await anyio.to_thread.run_sync(self.namespace)
        context = self.get_context()
        self.hub.observe(namespace.namespace_id, context.session)
        capabilities = await anyio.to_thread.run_sync(self.store.visible_capabilities, namespace.namespace_id)
        return [
            MCPTool(
                name=item.capability.name,
                description=item.capability.description,
                inputSchema=item.capability.input_schema,
            )
            for item in capabilities
        ]

    async def call_tool(self, name: str, arguments: dict[str, Any]):
        namespace = await anyio.to_thread.run_sync(self.namespace)
        self.hub.observe(namespace.namespace_id, self.get_context().session)
        try:
            published = await anyio.to_thread.run_sync(self.store.resolve, namespace.namespace_id, name)
        except KeyError:
            raise ValueError("capability_not_available") from None
        try:
            Draft202012Validator(published.capability.input_schema).validate(arguments)
        except Exception:
            raise ValueError("invalid_arguments") from None
        async with self.counters.operation(namespace.namespace_id, published.target_id, published.adapter_type):
            # Resolve again under the target lease. An admin mutation may have
            # happened while this call was waiting for a concurrency slot.
            try:
                published = await anyio.to_thread.run_sync(self.store.resolve, namespace.namespace_id, name)
            except KeyError:
                raise ValueError("capability_not_available") from None
            adapter = self.store.registry.get(published.adapter_type)
            secret = self.store.secret_box.decrypt(published.encrypted_secret) if published.encrypted_secret is not None else None
            try:
                scoped = getattr(adapter, "invoke_scoped", None)
                if callable(scoped):
                    result = await scoped(
                        InvocationContext(namespace.namespace_id, namespace.credential_generation, published.target_id),
                        published.capability.capability_id, published.configuration, secret, arguments,
                    )
                else:
                    result = await adapter.invoke(published.capability.capability_id, published.configuration, secret, arguments)
            except AdapterCallError as exc:
                error = json.dumps({"error": {"code": exc.code, "effect_possible": exc.effect_possible}}, separators=(",", ":"))
                raise ToolError(error) from None
            except Exception:
                raise ToolError('{"error":{"code":"adapter_call_failed","effect_possible":false}}') from None
        payload = {"result": result, "effect_possible": bool(published.capability.effect_capable)}
        try:
            encoded = json.dumps(payload, ensure_ascii=False, separators=(",", ":"), allow_nan=False)
        except (TypeError, ValueError):
            raise ValueError("invalid_adapter_result") from None
        if len(encoded.encode()) > MAX_RESULT_BYTES:
            raise ValueError("result_too_large")
        return [TextContent(type="text", text=encoded)]


class OpaqueBearerMiddleware:
    def __init__(self, app, store: NamespaceStore):
        self.app = app
        self.store = store

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("path") not in {"/mcp", "/mcp/"}:
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        raw = headers.get(b"authorization", b"").decode("latin-1")
        scheme, separator, token = raw.partition(" ")
        try:
            if not separator or scheme.lower() != "bearer" or not token:
                raise PermissionError("invalid_credential")
            await anyio.to_thread.run_sync(self.store.authenticate, token)
        except PermissionError:
            response = JSONResponse({"error": {"code": "invalid_credential"}}, status_code=401)
            return await response(scope, receive, send)
        return await self.app(scope, receive, send)
