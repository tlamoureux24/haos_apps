"""Strictly isolated administration and authenticated MCP ASGI applications."""

from __future__ import annotations

import html
import hmac
import json
import os
import secrets
import sqlite3
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route

from mcp_capability_bridge import __version__
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.contracts import AdapterRegistry
from mcp_capability_bridge.database import database_ready
from mcp_capability_bridge.mcp_api import NamespaceMCP, OpaqueBearerMiddleware
from mcp_capability_bridge.runtime_state import RuntimeCounters
from mcp_capability_bridge.security import SecretBox, load_or_create_key
from mcp_capability_bridge.settings import Settings
from mcp_capability_bridge.store import NamespaceStore


@dataclass(frozen=True)
class RuntimeState:
    settings: Settings
    store: NamespaceStore
    counters: RuntimeCounters
    csrf_token: str


def build_runtime_state(settings: Settings, registry: AdapterRegistry | None = None) -> RuntimeState:
    private = settings.data_dir / "private"
    pepper = load_or_create_key(private / "credential-pepper")
    target_key = load_or_create_key(private / "target-secret-key")
    store = NamespaceStore(settings.database_path, pepper, SecretBox(target_key), registry or AdapterRegistry())
    return RuntimeState(settings, store, RuntimeCounters(), secrets.token_urlsafe(32))


class SecurityHeadersMiddleware:
    def __init__(self, app, *, admin: bool, ingress_proxy_ip: str):
        self.app = app
        self.admin = admin
        self.ingress_proxy_ip = ingress_proxy_ip

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http":
            return await self.app(scope, receive, send)
        headers = {key.lower(): value for key, value in scope.get("headers", [])}
        if self.admin:
            client_ip = scope.get("client", ("", 0))[0]
            if client_ip != self.ingress_proxy_ip:
                response = JSONResponse({"error": {"code": "ingress_only"}}, status_code=403)
                return await response(scope, receive, send)
            if b"x-ingress-path" not in headers:
                response = JSONResponse({"error": {"code": "ingress_context_required"}}, status_code=403)
                return await response(scope, receive, send)

        async def send_with_headers(message):
            if message["type"] == "http.response.start":
                additions = [(b"cache-control", b"no-store"), (b"referrer-policy", b"no-referrer"), (b"x-content-type-options", b"nosniff")]
                if self.admin:
                    additions.append((b"content-security-policy", b"default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'"))
                message["headers"] = list(message.get("headers", [])) + additions
            await send(message)

        return await self.app(scope, receive, send_with_headers)


async def json_body(request: Request) -> dict[str, object]:
    body = await request.body()
    if len(body) > 32 * 1024:
        raise OverflowError
    value = json.loads(body)
    if not isinstance(value, dict):
        raise ValueError
    return value


def create_apps(state: RuntimeState) -> tuple[Starlette, Starlette]:
    mcp_server = NamespaceMCP(state.store, state.counters)
    mcp_application = mcp_server.streamable_http_app()

    async def live(_: Request) -> JSONResponse:
        return JSONResponse({"status": "live"})

    async def ready(_: Request) -> JSONResponse:
        if not database_ready(state.settings.database_path):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready", "version": __version__})

    async def status(_: Request) -> JSONResponse:
        namespaces = state.store.list_namespaces(include_archived=True)
        return JSONResponse({"status": "ready" if database_ready(state.settings.database_path) else "not_ready", "version": __version__, "database_generation": 1, "public_surface": "authenticated_mcp", "adapters": state.store.registry.describe(), "namespaces": {"active": sum(item["status"] == "active" for item in namespaces), "revoked": sum(item["status"] == "revoked" for item in namespaces), "archived": sum(item["status"] == "archived" for item in namespaces)}, "targets": len(state.store.list_targets()), "publications": len(state.store.list_publications()), "runtime": state.counters.snapshot()})

    def csrf_valid(request: Request) -> bool:
        cookie = request.cookies.get("mcb_csrf", "")
        return bool(cookie) and hmac.compare_digest(cookie, request.headers.get("x-csrf-token", ""))

    async def namespaces(request: Request) -> JSONResponse:
        if request.method == "GET":
            return JSONResponse({"namespaces": state.store.list_namespaces(request.query_params.get("include_archived") == "true")})
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            namespace, credential = state.store.create_namespace(str(data.get("key", "")), str(data.get("display_name", "")))
        except OverflowError:
            return JSONResponse({"error": {"code": "body_too_large"}}, status_code=413)
        except json.JSONDecodeError:
            return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)
        except ValueError as exc:
            code = str(exc) or "invalid_namespace"
            return JSONResponse({"error": {"code": code}}, status_code=409 if code == "namespace_key_exists" else 422)
        return JSONResponse({"namespace": namespace, "token": credential.token}, status_code=201)

    async def namespace_action(request: Request) -> JSONResponse:
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            namespace_id = str(data.get("id", ""))
            action = request.path_params["action"]
            if action == "rotate":
                credential = state.store.rotate(namespace_id)
                await state.counters.cancel_namespace(namespace_id)
                await mcp_server.hub.tools_changed(namespace_id)
                return JSONResponse({"token": credential.token})
            if action == "revoke":
                changed = state.store.revoke(namespace_id)
                await state.counters.cancel_namespace(namespace_id)
                await mcp_server.hub.tools_changed(namespace_id)
                return JSONResponse({"status": "revoked", "changed": changed})
            if action == "archive":
                state.store.archive(namespace_id)
                return JSONResponse({"status": "archived"})
            return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
        except KeyError as exc:
            return JSONResponse({"error": {"code": str(exc).strip("'")}}, status_code=404)
        except (OverflowError, json.JSONDecodeError):
            return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)
        except ValueError as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc) else "invalid_request"
            return JSONResponse({"error": {"code": code}}, status_code=409 if code.startswith("namespace_") else 422)

    async def targets(_: Request) -> JSONResponse:
        return JSONResponse({"targets": state.store.list_targets(), "adapters": state.store.registry.describe()})

    async def publications(request: Request) -> JSONResponse:
        if request.method == "GET":
            return JSONResponse({"publications": state.store.list_publications()})
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            namespace_id = str(data.get("namespace_id", ""))
            action = request.path_params["action"]
            if action not in {"publish", "unpublish"}:
                return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
            if action == "publish":
                revision = state.store.publish(namespace_id, str(data.get("target_id", "")), str(data.get("capability_id", "")))
            else:
                revision = state.store.unpublish(namespace_id, str(data.get("published_name", "")))
            await mcp_server.hub.tools_changed(namespace_id)
            return JSONResponse({"inventory_revision": revision})
        except KeyError as exc:
            return JSONResponse({"error": {"code": str(exc).strip("'")}}, status_code=404)
        except sqlite3.IntegrityError:
            return JSONResponse({"error": {"code": "publication_exists"}}, status_code=409)
        except ValueError as exc:
            return JSONResponse({"error": {"code": str(exc) or "invalid_publication"}}, status_code=409)

    async def index(request: Request) -> HTMLResponse:
        prefix = request.headers.get("x-ingress-path", "").rstrip("/")
        response = HTMLResponse(admin_page(html.escape(prefix, quote=True)))
        response.set_cookie("mcb_csrf", state.csrf_token, httponly=False, secure=True, samesite="strict", path=prefix or "/")
        return response

    async def css(_: Request) -> Response:
        return Response(ADMIN_CSS, media_type="text/css")

    async def js(_: Request) -> Response:
        return Response(ADMIN_JS, media_type="application/javascript")

    async def icon(_: Request) -> Response:
        path = Path(os.environ.get("MCP_CAPABILITY_BRIDGE_ICON_PATH", "/app/icon.png"))
        return Response(path.read_bytes(), media_type="image/png")

    health = [Route("/health/live", live), Route("/health/ready", ready)]
    admin = Starlette(routes=[Route("/", index), Route("/admin/assets/admin.css", css), Route("/admin/assets/admin.js", js), Route("/admin/assets/icon.png", icon), Route("/admin/api/v1/status", status), Route("/admin/api/v1/namespaces", namespaces, methods=["GET", "POST"]), Route("/admin/api/v1/namespaces/{action}", namespace_action, methods=["POST"]), Route("/admin/api/v1/targets", targets), Route("/admin/api/v1/publications", publications, methods=["GET"]), Route("/admin/api/v1/publications/{action}", publications, methods=["POST"]), *health], middleware=[Middleware(SecurityHeadersMiddleware, admin=True, ingress_proxy_ip=state.settings.ingress_proxy_ip)])

    @asynccontextmanager
    async def public_lifespan(_: Starlette):
        async with mcp_server.session_manager.run():
            yield

    public = Starlette(routes=[*health, Mount("/", app=OpaqueBearerMiddleware(mcp_application, state.store))], middleware=[Middleware(SecurityHeadersMiddleware, admin=False, ingress_proxy_ip=state.settings.ingress_proxy_ip)], lifespan=public_lifespan)
    admin.state.runtime = state
    public.state.runtime = state
    public.state.mcp_server = mcp_server
    return admin, public


def admin_page(prefix: str) -> str:
    navigation = "".join(f'<a data-view="{key}" href="#{key}" data-i18n="{key}">{label}</a>' for key, label in (("overview", "Vue d’ensemble"), ("clients", "Clients MCP"), ("targets", "Cibles"), ("access", "Accès MCP"), ("ssh", "Capacités SSH"), ("web", "Cibles Web"), ("sessions", "Sessions")))
    planned = "".join(f'<section id="{key}" class="view"><div class="pagehead"><div><h1 data-i18n="{key}"></h1><p data-i18n="plannedText"></p></div></div><article class="card"><h2 data-i18n="plannedTitle"></h2><p data-i18n="plannedText"></p></article></section>' for key in ("ssh", "web", "sessions"))
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCP Capability Bridge</title><link rel="stylesheet" href="{prefix}/admin/assets/admin.css"></head><body><main class="app" data-base="{prefix}"><header class="site-header"><div class="header-main"><a class="brand" href="#overview"><img src="{prefix}/admin/assets/icon.png" alt=""><span>MCP Capability Bridge <b>v{__version__}</b></span></a><div class="header-actions"><button id="language" class="switch" type="button">EN</button><button id="theme" class="switch" type="button">☾</button></div></div><div class="nav-scroll"><nav class="nav" aria-label="Navigation">{navigation}</nav></div></header><section id="overview" class="view active"><div class="pagehead"><div><h1 data-i18n="overviewTitle"></h1><p data-i18n="overviewIntro"></p></div><button id="status-open" class="primary" type="button" data-i18n="statusAction"></button></div><section class="metrics"><article class="metric"><strong class="state" data-i18n="ready"></strong><span data-i18n="appState"></span></article><article class="metric"><strong data-i18n="authenticatedMcp"></strong><span data-i18n="publicSurface"></span></article><article class="metric"><strong id="namespace-count">0</strong><span data-i18n="clients"></span></article></section><article class="card notice"><h2 data-i18n="coreTitle"></h2><p data-i18n="coreText"></p></article></section><section id="clients" class="view"><div class="pagehead"><div><h1 data-i18n="clients"></h1><p data-i18n="clientsIntro"></p></div><button id="namespace-create-open" class="primary" type="button" data-i18n="createClient"></button></div><label class="filter"><input id="show-archived" type="checkbox"> <span data-i18n="showArchived"></span></label><div id="namespace-list" class="card-list"></div></section><section id="targets" class="view"><div class="pagehead"><div><h1 data-i18n="targets"></h1><p data-i18n="targetsIntro"></p></div></div><div id="target-list" class="card-list"></div></section><section id="access" class="view"><div class="pagehead"><div><h1 data-i18n="access"></h1><p data-i18n="accessIntro"></p></div></div><div id="publication-list" class="card-list"></div></section>{planned}</main><div id="drawer-shell" class="drawer-shell" hidden><div class="drawer-overlay"></div><aside id="admin-drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1"><header class="drawer-head"><h2 id="drawer-title"></h2><button id="drawer-close" class="secondary drawer-close" type="button" data-i18n-aria="close">×</button></header><div class="drawer-body"><section id="status-panel" class="drawer-panel"><dl><dt data-i18n="runtime"></dt><dd data-i18n="singleRuntime"></dd><dt data-i18n="listeners"></dt><dd data-i18n="listenerValuesMcp"></dd><dt data-i18n="scope"></dt><dd data-i18n="scopeValue1"></dd></dl></section><section id="namespace-form-panel" class="drawer-panel" hidden><form id="namespace-form" class="form-grid"><label><span data-i18n="technicalKey"></span><input name="key" required pattern="[a-z][a-z0-9_]{{1,31}}" maxlength="32"></label><label><span data-i18n="displayName"></span><input name="display_name" required maxlength="100"></label><p class="warning" data-i18n="credentialWarning"></p><p id="namespace-message" class="message"></p><div class="actions"><button class="primary" type="submit" data-i18n="create"></button><button id="namespace-cancel" class="secondary" type="button" data-i18n="cancel"></button></div></form></section><section id="credential-panel" class="drawer-panel" hidden><p class="warning" data-i18n="credentialOnce"></p><pre id="credential-token" class="credential"></pre><button id="credential-dismiss" class="primary" type="button" data-i18n="copied"></button></section></div></aside></div><script src="{prefix}/admin/assets/admin.js" defer></script></body></html>'''
