"""Strictly isolated administration and authenticated MCP ASGI applications."""

from __future__ import annotations

import html
import hmac
import json
import os
import secrets
import sqlite3
import time
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route

from mcp_capability_bridge import __version__
from mcp_capability_bridge.activity import ActivityJournal
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.browser_runtime import BrowserRuntime
from mcp_capability_bridge.contracts import AdapterRegistry, InvocationContext
from mcp_capability_bridge.database import database_ready
from mcp_capability_bridge.mcp_api import NamespaceMCP, OpaqueBearerMiddleware
from mcp_capability_bridge.runtime_state import RuntimeCounters
from mcp_capability_bridge.security import SecretBox, load_or_create_key
from mcp_capability_bridge.settings import Settings
from mcp_capability_bridge.ssh_adapter import SSHAdapter, scan_host_key
from mcp_capability_bridge.store import NamespaceStore
from mcp_capability_bridge.web_adapter import WebAdapter, origin, resolve_host
from mcp_capability_bridge.web_sessions import WebSessionManager


@dataclass(frozen=True)
class RuntimeState:
    settings: Settings
    store: NamespaceStore
    counters: RuntimeCounters
    csrf_token: str
    host_scans: dict[str, tuple[float, object]]
    web_resolutions: dict[str, tuple[float, str, tuple[str, ...]]]
    browser: BrowserRuntime
    web_sessions: WebSessionManager
    activity: ActivityJournal


def build_runtime_state(settings: Settings, registry: AdapterRegistry | None = None) -> RuntimeState:
    private = settings.data_dir / "private"
    pepper = load_or_create_key(private / "credential-pepper")
    target_key = load_or_create_key(private / "target-secret-key")
    browser=BrowserRuntime();browser.prepare()
    web_sessions=WebSessionManager(browser.root)
    store = NamespaceStore(settings.database_path, pepper, SecretBox(target_key), registry or AdapterRegistry((SSHAdapter(),WebAdapter(web_sessions))))
    return RuntimeState(settings, store, RuntimeCounters(), secrets.token_urlsafe(32), {}, {}, browser, web_sessions, ActivityJournal())


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
    mcp_server = NamespaceMCP(state.store, state.counters, state.activity)
    mcp_application = mcp_server.streamable_http_app()

    async def live(_: Request) -> JSONResponse:
        return JSONResponse({"status": "live"})

    async def ready(_: Request) -> JSONResponse:
        if not database_ready(state.settings.database_path):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready", "version": __version__})

    async def status(_: Request) -> JSONResponse:
        namespaces = state.store.list_namespaces(include_archived=True)
        runtime=state.counters.snapshot();runtime["active_sessions"]=state.web_sessions.count()
        return JSONResponse({"status": "ready" if database_ready(state.settings.database_path) else "not_ready", "version": __version__, "database_generation": 1, "public_surface": "authenticated_mcp", "adapters": state.store.registry.describe(), "namespaces": {"active": sum(item["status"] == "active" for item in namespaces), "revoked": sum(item["status"] == "revoked" for item in namespaces), "archived": sum(item["status"] == "archived" for item in namespaces)}, "targets": len(state.store.list_targets()), "publications": len(state.store.list_publications()), "runtime": runtime})

    async def activity(_: Request) -> JSONResponse:
        return JSONResponse({"events": state.activity.list()})

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
                await state.web_sessions.close_namespace(namespace_id)
                await mcp_server.hub.tools_changed(namespace_id)
                return JSONResponse({"token": credential.token})
            if action == "revoke":
                changed = state.store.revoke(namespace_id)
                await state.counters.cancel_namespace(namespace_id)
                await state.web_sessions.close_namespace(namespace_id)
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

    async def targets(request: Request) -> JSONResponse:
        if request.method == "GET":
            listed = state.store.list_targets()
            for item in listed:
                item["in_use"] = state.counters.target_in_use(str(item["id"])) or state.web_sessions.target_in_use(str(item["id"]))
            return JSONResponse({"targets": listed, "adapters": state.store.registry.describe()})
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            scan_id = str(data.get("scan_id", ""))
            scanned_at, scan = state.host_scans.pop(scan_id)
            if time.monotonic() - scanned_at > 300:
                raise ValueError("host_scan_expired")
            auth_mode = str(data.get("auth_mode", ""))
            if auth_mode == "password":
                auth = {"mode": "password", "password": str(data.get("password", ""))}
            elif auth_mode == "private_key":
                auth = {"mode": "private_key", "private_key": str(data.get("private_key", "")), "passphrase": str(data.get("passphrase", ""))}
            else:
                raise ValueError("invalid_ssh_secret")
            configuration = {"host": scan.host, "port": scan.port, "username": str(data.get("username", "")), "host_public_key": scan.public_key, "host_fingerprint": scan.fingerprint, "capabilities": []}
            target = state.store.create_target(str(data.get("key", "")), str(data.get("display_name", "")), "ssh", configuration, json.dumps(auth, separators=(",", ":")).encode())
            return JSONResponse({"target": target}, status_code=201)
        except KeyError:
            return JSONResponse({"error": {"code": "host_scan_not_found"}}, status_code=404)
        except sqlite3.IntegrityError:
            return JSONResponse({"error": {"code": "target_key_exists"}}, status_code=409)
        except (OverflowError, json.JSONDecodeError):
            return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)
        except ValueError as exc:
            return JSONResponse({"error": {"code": str(exc) or "invalid_target"}}, status_code=422)

    async def ssh_scan(request: Request) -> JSONResponse:
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            scan = await scan_host_key(str(data.get("host", "")), int(data.get("port", 22)))
            scan_id = secrets.token_urlsafe(24)
            state.host_scans.clear()
            state.host_scans[scan_id] = (time.monotonic(), scan)
            return JSONResponse({"scan_id": scan_id, "host": scan.host, "port": scan.port, "resolved_address": scan.resolved_address, "algorithm": scan.algorithm, "fingerprint": scan.fingerprint})
        except (ValueError, TypeError, OverflowError, json.JSONDecodeError) as exc:
            code = str(exc) if isinstance(exc, ValueError) and str(exc) else "ssh_host_scan_failed"
            return JSONResponse({"error": {"code": code}}, status_code=422)

    async def web_resolve(request:Request)->JSONResponse:
        if not csrf_valid(request):return JSONResponse({"error":{"code":"csrf_failed"}},status_code=403)
        try:
            data=await json_body(request);base=origin(str(data.get("base_url","")));parsed=urlparse(base);addresses=await resolve_host(parsed.hostname or "",parsed.port or (443 if parsed.scheme=="https" else 80));resolution_id=secrets.token_urlsafe(24)
            state.web_resolutions.clear();state.web_resolutions[resolution_id]=(time.monotonic(),base,addresses)
            return JSONResponse({"resolution_id":resolution_id,"origin":base,"resolved_addresses":addresses})
        except (ValueError,OverflowError,json.JSONDecodeError) as exc:return JSONResponse({"error":{"code":str(exc) or "invalid_web_target"}},status_code=422)

    async def web_targets(request:Request)->JSONResponse:
        if request.method=="GET":return JSONResponse({"targets":[item for item in state.store.list_targets() if item["adapter_type"]=="web"]})
        if not csrf_valid(request):return JSONResponse({"error":{"code":"csrf_failed"}},status_code=403)
        try:
            data=await json_body(request);created_at,base,addresses=state.web_resolutions.pop(str(data.get("resolution_id","")))
            if time.monotonic()-created_at>300 or base!=origin(str(data.get("base_url",""))):raise ValueError("web_resolution_expired")
            mode=str(data.get("auth_mode","none"));authentication={"mode":mode};secret=None
            if mode in {"basic","form"}:
                secret=json.dumps({"mode":mode,"username":str(data.get("auth_username","")),"password":str(data.get("auth_password",""))},separators=(",",":")).encode()
            if mode=="form":
                authentication|={"login_path":str(data.get("login_path","")),"username_selector":str(data.get("username_selector","")),"password_selector":str(data.get("password_selector","")),"submit_selector":str(data.get("submit_selector",""))}
            configuration={"base_url":str(data.get("base_url","")),"resolved_addresses":list(addresses),"navigation_origins":[base],"authentication_origins":[base] if mode=="form" else [],"resource_origins":[base],"websocket_origins":[],"verify_tls":bool(data.get("verify_tls",True)),"inactivity_seconds":int(data.get("inactivity_seconds",300)),"absolute_seconds":int(data.get("absolute_seconds",1800)),"authentication":authentication}
            target=state.store.create_target(str(data.get("key","")),str(data.get("display_name","")),"web",configuration,secret)
            return JSONResponse({"target":target},status_code=201)
        except KeyError:return JSONResponse({"error":{"code":"web_resolution_not_found"}},status_code=404)
        except sqlite3.IntegrityError:return JSONResponse({"error":{"code":"target_key_exists"}},status_code=409)
        except (ValueError,TypeError,OverflowError,json.JSONDecodeError) as exc:return JSONResponse({"error":{"code":str(exc) or "invalid_web_target"}},status_code=422)

    async def web_test(request:Request)->JSONResponse:
        if not csrf_valid(request):return JSONResponse({"error":{"code":"csrf_failed"}},status_code=403)
        try:
            data=await json_body(request);target_id=str(data.get("id",""));target=state.store.get_target(target_id)
            if target["adapter_type"]!="web":raise ValueError("invalid_web_target")
            context=InvocationContext("__admin__",0,target_id)
            async with state.counters.operation("__admin__",target_id,"web"):
                opened=await state.web_sessions.open(context,state.store.get_target_configuration(target_id),state.store.get_target_secret(target_id))
                await state.web_sessions.close(context,str(opened["session"]))
            return JSONResponse({"status":"reachable","origin":opened["origin"]})
        except KeyError:return JSONResponse({"error":{"code":"target_not_found"}},status_code=404)
        except (ValueError,RuntimeError,PermissionError) as exc:return JSONResponse({"error":{"code":str(exc) or "web_probe_failed"}},status_code=422)

    async def target_action(request: Request) -> JSONResponse:
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            target_id = str(data.get("id", ""))
            state.counters.ensure_target_mutable(target_id)
            if state.web_sessions.target_in_use(target_id):raise RuntimeError("target_in_use")
            action = request.path_params["action"]
            if action in {"enable", "disable"}:
                namespaces = state.store.set_target_enabled(target_id, action == "enable")
            elif action == "delete":
                namespaces = state.store.delete_target(target_id)
            elif action == "update":
                current = state.store.get_target(target_id)
                configuration = state.store.get_target_configuration(target_id)
                configuration["username"] = str(data.get("username", configuration["username"]))
                secret = None
                auth_mode = str(data.get("auth_mode", ""))
                if auth_mode == "password":
                    secret = json.dumps({"mode": "password", "password": str(data.get("password", ""))}, separators=(",", ":")).encode()
                elif auth_mode == "private_key":
                    secret = json.dumps({"mode": "private_key", "private_key": str(data.get("private_key", "")), "passphrase": str(data.get("passphrase", ""))}, separators=(",", ":")).encode()
                elif auth_mode:
                    raise ValueError("invalid_ssh_secret")
                namespaces = state.store.update_target(target_id, str(data.get("display_name", current["display_name"])), configuration, secret)
            elif action == "rotate_host_key":
                scanned_at, scan = state.host_scans.pop(str(data.get("scan_id", "")))
                if time.monotonic() - scanned_at > 300:
                    raise ValueError("host_scan_expired")
                configuration = state.store.get_target_configuration(target_id)
                if scan.host != configuration["host"] or scan.port != configuration["port"]:
                    raise ValueError("host_scan_target_mismatch")
                configuration["host_public_key"] = scan.public_key
                configuration["host_fingerprint"] = scan.fingerprint
                current = state.store.get_target(target_id)
                namespaces = state.store.update_target(target_id, str(current["display_name"]), configuration)
            else:
                return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
            for namespace_id in namespaces:
                await mcp_server.hub.tools_changed(namespace_id)
            return JSONResponse({"status": action})
        except RuntimeError as exc:
            return JSONResponse({"error": {"code": str(exc)}}, status_code=409)
        except KeyError as exc:
            return JSONResponse({"error": {"code": str(exc).strip("'")}}, status_code=404)
        except (ValueError, OverflowError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": {"code": str(exc) or "invalid_target"}}, status_code=422)

    async def target_detail(request: Request) -> JSONResponse:
        try:
            return JSONResponse({"target": state.store.get_target(request.path_params["target_id"])})
        except KeyError:
            return JSONResponse({"error": {"code": "target_not_found"}}, status_code=404)

    async def capabilities(request: Request) -> JSONResponse:
        if not csrf_valid(request):
            return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
        try:
            data = await json_body(request)
            target_id = str(data.get("target_id", ""))
            state.counters.ensure_target_mutable(target_id)
            action = request.path_params["action"]
            if action == "save":
                raw = data.get("capability")
                if not isinstance(raw, dict):
                    raise ValueError("invalid_ssh_capability")
                capability = dict(raw)
                capability["id"] = str(capability.get("id") or uuid.uuid4().hex)
                namespaces = state.store.save_capability(target_id, capability)
            elif action == "delete":
                namespaces = state.store.delete_capability(target_id, str(data.get("capability_id", "")))
            else:
                return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
            for namespace_id in namespaces:
                await mcp_server.hub.tools_changed(namespace_id)
            return JSONResponse({"status": action})
        except RuntimeError as exc:
            return JSONResponse({"error": {"code": str(exc)}}, status_code=409)
        except KeyError as exc:
            return JSONResponse({"error": {"code": str(exc).strip("'")}}, status_code=404)
        except (ValueError, OverflowError, json.JSONDecodeError) as exc:
            return JSONResponse({"error": {"code": str(exc) or "invalid_ssh_capability"}}, status_code=422)

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

    async def web_sessions(_: Request) -> JSONResponse:
        namespaces={str(item["id"]):str(item["display_name"]) for item in state.store.list_namespaces(include_archived=True)}
        targets={str(item["id"]):str(item["display_name"]) for item in state.store.list_targets()}
        rows=[]
        for item in state.web_sessions.describe():
            rows.append({**item,"namespace":namespaces.get(str(item["namespace_id"]),"—"),"target":targets.get(str(item["target_id"]),"—")})
        return JSONResponse({"sessions":rows})

    health = [Route("/health/live", live), Route("/health/ready", ready)]
    admin = Starlette(routes=[Route("/", index), Route("/admin/assets/admin.css", css), Route("/admin/assets/admin.js", js), Route("/admin/assets/icon.png", icon), Route("/admin/api/v1/status", status), Route("/admin/api/v1/activity", activity), Route("/admin/api/v1/namespaces", namespaces, methods=["GET", "POST"]), Route("/admin/api/v1/namespaces/{action}", namespace_action, methods=["POST"]), Route("/admin/api/v1/targets", targets, methods=["GET", "POST"]), Route("/admin/api/v1/targets/detail/{target_id}", target_detail, methods=["GET"]), Route("/admin/api/v1/targets/{action}", target_action, methods=["POST"]), Route("/admin/api/v1/ssh/scan", ssh_scan, methods=["POST"]), Route("/admin/api/v1/ssh/capabilities/{action}", capabilities, methods=["POST"]), Route("/admin/api/v1/web/resolve",web_resolve,methods=["POST"]),Route("/admin/api/v1/web/targets",web_targets,methods=["GET","POST"]),Route("/admin/api/v1/web/test",web_test,methods=["POST"]),Route("/admin/api/v1/web/sessions",web_sessions,methods=["GET"]), Route("/admin/api/v1/publications", publications, methods=["GET"]), Route("/admin/api/v1/publications/{action}", publications, methods=["POST"]), *health], middleware=[Middleware(SecurityHeadersMiddleware, admin=True, ingress_proxy_ip=state.settings.ingress_proxy_ip)])

    @asynccontextmanager
    async def public_lifespan(_: Starlette):
        state.activity.record(event="app_started", status="success", source="system")
        async with mcp_server.session_manager.run():
            state.activity.record(event="app_ready", status="success", source="system")
            try:
                yield
            finally:
                await state.web_sessions.close_all()
                await state.browser.close()
                state.activity.record(event="app_stopped", status="success", source="system")

    public = Starlette(routes=[*health, Mount("/", app=OpaqueBearerMiddleware(mcp_application, state.store, state.activity))], middleware=[Middleware(SecurityHeadersMiddleware, admin=False, ingress_proxy_ip=state.settings.ingress_proxy_ip)], lifespan=public_lifespan)
    admin.state.runtime = state
    public.state.runtime = state
    public.state.mcp_server = mcp_server
    return admin, public


def admin_page(prefix: str) -> str:
    navigation = "".join(f'<a data-view="{key}" href="#{key}" data-i18n="{key}">{label}</a>' for key, label in (("overview", "Vue d’ensemble"), ("activity", "Activité"), ("clients", "Clients MCP"), ("access", "Accès MCP"), ("targets", "Cibles"), ("ssh", "Capacités SSH"), ("web", "Cibles Web"), ("sessions", "Sessions")))
    planned = '<section id="sessions" class="view"><div class="pagehead"><div><h1 data-i18n="sessions"></h1><p data-i18n="sessionsIntro"></p></div></div><div id="session-list" class="card-list"></div></section>'
    return f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCP Capability Bridge</title><link rel="stylesheet" href="{prefix}/admin/assets/admin.css"></head><body><main class="app" data-base="{prefix}"><header class="site-header"><div class="header-main"><a class="brand" href="#overview"><img src="{prefix}/admin/assets/icon.png" alt=""><span>MCP Capability Bridge <b>v{__version__}</b></span></a><div class="header-actions"><button id="language" class="switch" type="button">EN</button><button id="theme" class="switch" type="button">☾</button></div></div><div class="nav-scroll"><nav class="nav" aria-label="Navigation">{navigation}</nav></div></header>
<section id="overview" class="view active"><div class="pagehead"><div><h1 data-i18n="overviewTitle"></h1><p data-i18n="overviewIntro"></p></div><span id="service-state" class="service-state state" data-i18n="serviceOperational"></span></div><section class="metrics"><article class="metric"><strong data-i18n="authenticatedMcp"></strong><span data-i18n="publicSurface"></span></article><article class="metric"><strong id="namespace-count">0</strong><span data-i18n="clients"></span></article></section><article class="card notice"><h2 data-i18n="coreTitle"></h2><p data-i18n="coreText"></p></article></section>
<section id="activity" class="view"><div class="pagehead"><div><h1 data-i18n="activity"></h1><p data-i18n="activityIntro"></p><small id="activity-freshness" class="freshness"></small></div></div><div class="table-wrap card"><table><thead><tr><th data-i18n="date"></th><th data-i18n="event"></th><th data-i18n="category"></th><th data-i18n="status"></th><th data-i18n="source"></th></tr></thead><tbody id="activity-list"></tbody></table></div></section>
<section id="clients" class="view"><div class="pagehead"><div><h1 data-i18n="clients"></h1><p data-i18n="clientsIntro"></p></div><button id="namespace-create-open" class="primary" type="button" data-i18n="createClient"></button></div><label class="filter"><input id="show-archived" type="checkbox"> <span data-i18n="showArchived"></span></label><div id="namespace-list" class="card-list"></div></section>
<section id="targets" class="view"><div class="pagehead"><div><h1 data-i18n="targets"></h1><p data-i18n="targetsIntro"></p></div><button id="target-create-open" class="primary" type="button" data-i18n="createTarget"></button></div><div id="target-list" class="card-list"></div></section>
<section id="access" class="view"><div class="pagehead"><div><h1 data-i18n="access"></h1><p data-i18n="accessIntro"></p></div><button id="publication-open" class="primary" type="button" data-i18n="publishCapability"></button></div><div id="publication-list" class="card-list"></div></section>
<section id="ssh" class="view"><div class="pagehead"><div><h1 data-i18n="ssh"></h1><p data-i18n="sshIntro"></p></div><button id="capability-open" class="primary" type="button" data-i18n="createCapability"></button></div><div id="capability-list" class="card-list"></div></section>
<section id="web" class="view"><div class="pagehead"><div><h1 data-i18n="web"></h1><p data-i18n="webIntro"></p></div><button id="web-target-open" class="primary" type="button" data-i18n="createWebTarget"></button></div><div id="web-target-list" class="card-list"></div></section>{planned}</main>
<div id="drawer-shell" class="drawer-shell" hidden><div class="drawer-overlay"></div><aside id="admin-drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1"><header class="drawer-head"><h2 id="drawer-title"></h2><button id="drawer-close" class="secondary drawer-close" type="button" data-i18n-aria="close">×</button></header><div class="drawer-body">
<section id="namespace-form-panel" class="drawer-panel" hidden><form id="namespace-form" class="form-grid"><label><span data-i18n="displayName"></span><input name="display_name" required maxlength="100"></label><p class="warning" data-i18n="credentialWarning"></p><p id="namespace-message" class="message"></p><div class="actions"><button class="primary" type="submit" data-i18n="create"></button><button class="secondary cancel" type="button" data-i18n="cancel"></button></div></form></section>
<section id="credential-panel" class="drawer-panel" hidden><p class="warning" data-i18n="credentialOnce"></p><pre id="credential-token" class="credential"></pre><button id="credential-dismiss" class="primary" type="button" data-i18n="copied"></button></section>
<section id="target-form-panel" class="drawer-panel" hidden><form id="target-form" class="form-grid"><input name="id" type="hidden"><label><span data-i18n="displayName"></span><input name="display_name" required maxlength="100"></label><label><span data-i18n="host"></span><input name="host" required maxlength="253"></label><label><span data-i18n="port"></span><input name="port" type="number" value="22" min="1" max="65535" required></label><label><span data-i18n="username"></span><input name="username" required maxlength="128"></label><label><span data-i18n="authMode"></span><select name="auth_mode"><option value="password" data-i18n="password"></option><option value="private_key" data-i18n="privateKey"></option></select></label><label class="password-field"><span data-i18n="password"></span><input name="password" type="password"></label><label class="key-field" hidden><span data-i18n="privateKey"></span><textarea name="private_key" rows="7"></textarea></label><label class="key-field" hidden><span data-i18n="passphrase"></span><input name="passphrase" type="password"></label><div id="scan-result" class="warning" hidden></div><p id="target-message" class="message"></p><div class="actions"><button id="target-scan" class="primary" type="button" data-i18n="scanHostKey"></button><button id="target-confirm" class="primary" type="submit" data-i18n="confirmAndCreate" hidden></button><button class="secondary cancel" type="button" data-i18n="cancel"></button></div></form></section>
<section id="capability-form-panel" class="drawer-panel" hidden><form id="capability-form" class="form-grid"><input name="id" type="hidden"><label><span data-i18n="target"></span><select name="target_id" required></select></label><label><span data-i18n="displayName"></span><input name="display_name" required maxlength="100"></label><label><span data-i18n="description"></span><textarea name="description" required maxlength="2000"></textarea></label><label><span data-i18n="executable"></span><input name="executable" required placeholder="/usr/bin/uptime"></label><label><span data-i18n="templateJson"></span><textarea name="template" rows="4">[]</textarea></label><label><span data-i18n="schemaJson"></span><textarea name="input_schema" rows="8">{{"type":"object","properties":{{}},"required":[],"additionalProperties":false}}</textarea></label><label><span data-i18n="timeout"></span><input name="timeout_seconds" type="number" value="30" min="1" max="300"></label><label><span data-i18n="stdoutLimit"></span><input name="stdout_limit" type="number" value="65536" min="0" max="262144"></label><label><span data-i18n="stderrLimit"></span><input name="stderr_limit" type="number" value="16384" min="0" max="262144"></label><label><input name="enabled" type="checkbox" checked> <span data-i18n="enabled"></span></label><label><input name="effect_capable" type="checkbox"> <span data-i18n="effectCapable"></span></label><p id="capability-message" class="message"></p><div class="actions"><button class="primary" type="submit" data-i18n="save"></button><button class="secondary cancel" type="button" data-i18n="cancel"></button></div></form></section>
<section id="publication-form-panel" class="drawer-panel" hidden><form id="publication-form" class="form-grid"><label><span data-i18n="client"></span><select name="namespace_id" required></select></label><label><span data-i18n="target"></span><select name="target_id" required></select></label><label><span data-i18n="capability"></span><select name="capability_id" required></select></label><p id="publication-message" class="message"></p><div class="actions"><button class="primary" type="submit" data-i18n="publish"></button><button class="secondary cancel" type="button" data-i18n="cancel"></button></div></form></section>
<section id="web-target-form-panel" class="drawer-panel" hidden><form id="web-target-form" class="form-grid"><p class="warning" data-i18n="webAuthorityWarning"></p><label><span data-i18n="displayName"></span><input name="display_name" required maxlength="100"></label><label><span data-i18n="baseUrl"></span><input name="base_url" type="url" required></label><label><span data-i18n="webAuth"></span><select name="auth_mode"><option value="none" data-i18n="authNone"></option><option value="basic" data-i18n="authBasic"></option><option value="form" data-i18n="authForm"></option></select></label><label class="web-secret" hidden><span data-i18n="username"></span><input name="auth_username" maxlength="256"></label><label class="web-secret" hidden><span data-i18n="password"></span><input name="auth_password" type="password" maxlength="1024"></label><label class="web-form-auth" hidden><span data-i18n="loginPath"></span><input name="login_path" value="/login" maxlength="256"></label><label class="web-form-auth" hidden><span data-i18n="usernameSelector"></span><input name="username_selector" value="input[name=username]" maxlength="256"></label><label class="web-form-auth" hidden><span data-i18n="passwordSelector"></span><input name="password_selector" value="input[type=password]" maxlength="256"></label><label class="web-form-auth" hidden><span data-i18n="submitSelector"></span><input name="submit_selector" value="button[type=submit]" maxlength="256"></label><label><input name="verify_tls" type="checkbox" checked> <span data-i18n="verifyTls"></span></label><label><span data-i18n="inactivityLimit"></span><input name="inactivity_seconds" type="number" min="30" max="3600" value="300"></label><label><span data-i18n="absoluteLimit"></span><input name="absolute_seconds" type="number" min="30" max="14400" value="1800"></label><div id="web-resolution" class="warning" hidden></div><p class="warning" data-i18n="webToolsReady"></p><p class="message"></p><div class="actions"><button id="web-resolve" class="primary" type="button" data-i18n="resolveAndConfirm"></button><button id="web-save" class="primary" type="submit" data-i18n="confirmAndCreate" hidden></button><button class="secondary cancel" type="button" data-i18n="cancel"></button></div></form></section>
</div></aside></div><script src="{prefix}/admin/assets/admin.js" defer></script></body></html>'''
