"""ASGI entry point with isolated Ingress administration and standalone surfaces."""

from __future__ import annotations

import asyncio
import html
import hmac
import json
import os
import secrets
from contextlib import asynccontextmanager
from pathlib import Path
from urllib.parse import parse_qs

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from agent_execution_plane import __version__
from agent_execution_plane.acp import AcpBoundary, AcpStore
from agent_execution_plane.admin_ui import ADMIN_CSS, ADMIN_JS
from agent_execution_plane.codex_runtime import CodexRuntime, CodexRuntimeError
from agent_execution_plane.database import database_ready, list_activity, record_activity
from agent_execution_plane.execution import ExecutionEngine
from agent_execution_plane.lifecycle import LifecycleStore
from agent_execution_plane.mcp_client import session_factory
from agent_execution_plane.models import Candidate, ModelStore
from agent_execution_plane.providers import execution_adapter
from agent_execution_plane.settings import load_settings
from agent_execution_plane.standalone import StandaloneBoundary

if os.geteuid() != 1000:
    raise RuntimeError("Agent Execution Plane listeners must run with UID 1000")

settings = load_settings()
icon_path = Path(os.environ.get("AGENT_EXECUTION_PLANE_ICON_PATH", "/app/icon.png"))
csrf_token = secrets.token_urlsafe(32)
codex_runtime = CodexRuntime(settings.data_dir / "private" / "codex-home")
model_store = ModelStore(settings.database_path, settings.data_dir / "private", codex_runtime)
lifecycle_store = LifecycleStore(settings.database_path)
execution_engine = ExecutionEngine(model_store, lambda model: execution_adapter(model, codex_runtime), session_factory)
standalone_boundary = StandaloneBoundary(lifecycle_store, execution_engine, settings.database_path)
acp_store = AcpStore(settings.database_path, model_store.key)
acp_boundary = AcpBoundary(acp_store, lifecycle_store, execution_engine, model_store, session_factory, settings.database_path)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if settings.surface == "admin":
            client_ip = request.client.host if request.client else ""
            if client_ip != settings.ingress_proxy_ip:
                return JSONResponse({"error": {"code": "ingress_only"}}, status_code=403)
            if request.url.path not in {"/health/live", "/health/ready"} and not request.headers.get("x-ingress-path"):
                return JSONResponse({"error": {"code": "ingress_context_required"}}, status_code=403)
        response = await call_next(request)
        response.headers.update({"X-Content-Type-Options": "nosniff", "Referrer-Policy": "no-referrer", "Cache-Control": "no-store"})
        if settings.surface == "admin":
            response.headers["Content-Security-Policy"] = "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; frame-ancestors 'self'"
            if request.method == "GET" and request.url.path == "/":
                response.set_cookie("aep_csrf", csrf_token, httponly=False, secure=True, samesite="strict", path=request.headers.get("x-ingress-path", "/"))
        return response


async def live(_: Request) -> JSONResponse:
    return JSONResponse({"status": "live"})


async def ready(_: Request) -> JSONResponse:
    if not database_ready(settings.database_path):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return JSONResponse({"status": "ready", "version": __version__})


async def admin_index(request: Request) -> HTMLResponse:
    prefix = request.headers.get("x-ingress-path", request.scope.get("root_path", "")).rstrip("/")
    safe = html.escape(prefix, quote=True)
    return HTMLResponse(f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Agent Execution Plane</title><link rel="stylesheet" href="{safe}/admin/assets/admin.css"></head><body><main class="app" data-base="{safe}"><header class="site-header"><div class="header-main"><a class="brand" href="#overview"><img src="{safe}/admin/assets/icon.png" alt=""><span>Agent Execution Plane <b>v{__version__}</b></span></a><div class="header-actions"><button id="language" class="switch" type="button">EN</button><button id="theme" class="switch" type="button">☾</button></div></div><div class="nav-scroll"><nav class="nav" aria-label="Navigation"><a class="active" data-view="overview" href="#overview" data-i18n="overview">Vue d’ensemble</a><a data-view="activity" href="#activity" data-i18n="activity">Activité</a></nav></div></header><section id="overview" class="view active"><section class="hero"><div><h1 data-i18n="overviewTitle">Vue d’ensemble</h1><p data-i18n="overviewIntro">Consultez l’état opérationnel du moteur d’exécution.</p></div><div class="health"><i></i><span data-i18n="operational">Service opérationnel</span></div></section><section class="metrics"><article class="metric"><strong data-i18n="ready">Prête</strong><span data-i18n="appState">Application</span></article><article class="metric"><strong id="engine-state" data-i18n="idle">Inactif</strong><span data-i18n="engineState">Moteur</span></article><article class="metric"><strong id="api-state" data-i18n="notConfigured">Non configuré</strong><span data-i18n="apiState">API autonome</span></article></section><article id="lifecycle-detail" class="card notice"></article></section><section id="activity" class="view"><div class="pagehead"><h1 data-i18n="activityTitle">Activité</h1><p data-i18n="activityIntro">Journal opérationnel persistant, limité aux métadonnées non sensibles.</p><span class="freshness" data-freshness="activity"></span></div><article class="card"><div class="tablewrap"><table><thead><tr><th data-i18n="date">Date</th><th data-i18n="event">Événement</th><th data-i18n="category">Catégorie</th><th data-i18n="status">État</th><th data-i18n="source">Source</th></tr></thead><tbody id="activity-rows"></tbody></table></div><div class="pager"><button id="previous" type="button" data-i18n="previous">Précédent</button><button id="next" type="button" data-i18n="next">Suivant</button></div></article></section></main><script src="{safe}/admin/assets/admin.js" defer></script></body></html>''')


async def activity(request: Request) -> JSONResponse:
    query = parse_qs(request.url.query)
    try:
        limit = int(query.get("limit", ["50"])[0]); offset = int(query.get("offset", ["0"])[0])
    except ValueError:
        return JSONResponse({"error": {"code": "invalid_pagination"}}, status_code=422)
    return JSONResponse(list_activity(settings.database_path, limit, offset))


def csrf_valid(request: Request) -> bool:
    return hmac.compare_digest(request.cookies.get("aep_csrf", ""), request.headers.get("x-csrf-token", "")) and bool(request.cookies.get("aep_csrf"))


async def json_body(request: Request) -> dict:
    body = await request.body()
    if len(body) > 32 * 1024: raise OverflowError
    value = json.loads(body)
    if not isinstance(value, dict): raise ValueError
    return value


async def models_api(request: Request) -> JSONResponse:
    if request.method == "GET": return JSONResponse({"models": model_store.list()})
    if not csrf_valid(request): return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
    try:
        data = await json_body(request)
        base_url = data.get("base_url")
        credential = data.get("credential")
        if base_url is not None and not isinstance(base_url, str): raise ValueError
        if credential is not None and not isinstance(credential, str): raise ValueError
        candidate = Candidate(str(data.get("display_name", "")), str(data.get("provider_family", "")), base_url or None, str(data.get("provider_model", "")), credential or None, bool(data.get("replace_credential", False)), bool(data.get("enabled", True)), float(data.get("timeout_minutes", 5)))
        model, check = await asyncio.to_thread(model_store.save, candidate, data.get("id"))
    except OverflowError: return JSONResponse({"error": {"code": "body_too_large"}}, status_code=413)
    except RuntimeError as exc:
        if str(exc) == "model_in_use": return JSONResponse({"error": {"code": "model_in_use"}}, status_code=409)
        raise
    except (ValueError, TypeError): return JSONResponse({"error": {"code": "invalid_model"}}, status_code=422)
    except KeyError: return JSONResponse({"error": {"code": "model_not_found"}}, status_code=404)
    if model is None: return JSONResponse({"error": {"code": check.code or check.state}, "technical_state": check.state}, status_code=422)
    return JSONResponse({"model": model}, status_code=200 if data.get("id") else 201)


async def model_action(request: Request) -> JSONResponse:
    if not csrf_valid(request): return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
    try: data = await json_body(request)
    except (ValueError, OverflowError): return JSONResponse({"error": {"code": "invalid_request"}}, status_code=422)
    action = request.path_params["action"]
    try:
        if action == "delete": found = await asyncio.to_thread(model_store.delete, str(data.get("id", "")))
        elif action == "enabled": found = await asyncio.to_thread(model_store.set_enabled, str(data.get("id", "")), bool(data.get("enabled")))
        elif action == "reorder": await asyncio.to_thread(model_store.reorder, [str(item) for item in data.get("ids", [])]); found = True
        else: return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
    except RuntimeError as exc:
        if str(exc) == "model_in_use": return JSONResponse({"error": {"code": "model_in_use"}}, status_code=409)
        raise
    except ValueError: return JSONResponse({"error": {"code": "invalid_order"}}, status_code=422)
    if not found: return JSONResponse({"error": {"code": "model_not_found"}}, status_code=404)
    return JSONResponse({"status": "ok"})


async def oauth_account(_: Request) -> JSONResponse:
    try:
        return JSONResponse(await asyncio.to_thread(codex_runtime.login_status))
    except CodexRuntimeError:
        return JSONResponse({"status": "error", "code": "runtime_or_model_incompatible"}, status_code=503)


async def oauth_models(_: Request) -> JSONResponse:
    try:
        return JSONResponse({"models": await asyncio.to_thread(codex_runtime.models)})
    except CodexRuntimeError as exc:
        code = "auth_required" if str(exc) == "auth_required" else "runtime_or_model_incompatible"
        return JSONResponse({"error": {"code": code}}, status_code=422 if code == "auth_required" else 503)


async def oauth_action(request: Request) -> JSONResponse:
    if not csrf_valid(request): return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
    action = request.path_params["action"]
    try:
        if action == "login":
            result = await asyncio.to_thread(codex_runtime.login_start)
            record_activity(settings.database_path, "chatgpt_login_started", "configuration", "success")
            return JSONResponse(result)
        if action == "cancel":
            await asyncio.to_thread(codex_runtime.login_cancel)
            record_activity(settings.database_path, "chatgpt_login_cancelled", "configuration", "success")
        elif action == "logout":
            await asyncio.to_thread(codex_runtime.logout)
            record_activity(settings.database_path, "chatgpt_logout", "configuration", "success")
        else:
            return JSONResponse({"error": {"code": "not_found"}}, status_code=404)
    except CodexRuntimeError:
        return JSONResponse({"error": {"code": "runtime_or_model_incompatible"}}, status_code=503)
    return JSONResponse({"status": "ok"})


async def standalone_admin_state(_: Request) -> JSONResponse:
    return JSONResponse({"credential_configured": lifecycle_store.credential_configured(), "lifecycle": lifecycle_store.overview()})


async def acp_admin(request: Request) -> JSONResponse:
    if request.method == "GET":
        config=acp_store.configuration();return JSONResponse({**acp_boundary.state(),"url":config["url"] if config else None})
    if not csrf_valid(request):return JSONResponse({"error":{"code":"csrf_failed"}},status_code=403)
    try:
        data=await json_body(request);url=data.get("url");credential=data.get("credential");replace=bool(data.get("replace_credential"))
        if not isinstance(url,str) or (credential is not None and not isinstance(credential,str)):raise ValueError("invalid_acp_configuration")
        await acp_boundary.configure(url,credential or None,replace)
        record_activity(settings.database_path,"acp_connection_configured","configuration","success")
        return JSONResponse({"status":"configured"})
    except (ValueError,RuntimeError) as exc:return JSONResponse({"error":{"code":str(exc)}},status_code=422)


async def standalone_credential_action(request: Request) -> JSONResponse:
    if not csrf_valid(request): return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
    action=request.path_params["action"]
    try:
        if action in {"create", "rotate"}:
            token=await asyncio.to_thread(lifecycle_store.create_credential,rotate=action=="rotate")
            record_activity(settings.database_path,f"standalone_credential_{'created' if action=='create' else 'rotated'}","configuration","success")
            return JSONResponse({"status":"configured","token":token},status_code=201)
        if action=="revoke":
            if not await asyncio.to_thread(lifecycle_store.revoke_credential): return JSONResponse({"error":{"code":"credential_not_configured"}},status_code=404)
            record_activity(settings.database_path,"standalone_credential_revoked","configuration","success")
            return JSONResponse({"status":"not_configured"})
    except ValueError as exc: return JSONResponse({"error":{"code":str(exc)}},status_code=409)
    return JSONResponse({"error":{"code":"not_found"}},status_code=404)


async def abandon_pending(request: Request) -> JSONResponse:
    if not csrf_valid(request): return JSONResponse({"error": {"code": "csrf_failed"}}, status_code=403)
    try: data=await json_body(request); execution_id=data.get("execution_id")
    except (ValueError,OverflowError): return JSONResponse({"error":{"code":"invalid_request"}},status_code=422)
    if not isinstance(execution_id,str) or not await asyncio.to_thread(lifecycle_store.abandon,execution_id): return JSONResponse({"error":{"code":"pending_result_changed"}},status_code=409)
    await asyncio.to_thread(acp_boundary.abandon,execution_id)
    record_activity(settings.database_path,"pending_result_abandoned","execution","success")
    return JSONResponse({"execution_id":execution_id,"status":"abandoned"})


async def asset_css(_: Request) -> Response: return Response(ADMIN_CSS, media_type="text/css")
async def asset_js(_: Request) -> Response: return Response(ADMIN_JS, media_type="application/javascript")
async def asset_icon(_: Request) -> Response: return Response(icon_path.read_bytes(), media_type="image/png")


@asynccontextmanager
async def lifespan(_: Starlette):
    health_task = None
    if settings.surface == "admin":
        record_activity(settings.database_path, "app_started", "system", "success")
        record_activity(settings.database_path, "app_ready", "system", "success")
        health_task = asyncio.create_task(asyncio.to_thread(model_store.refresh_health))
    else:
        await asyncio.to_thread(model_store.clear_usage)
        recovered = await asyncio.to_thread(lifecycle_store.recover_interrupted)
        if recovered: record_activity(settings.database_path,"interrupted_execution_recovered","execution","failure")
        await acp_boundary.start()
    try:
        yield
    finally:
        if settings.surface == "api": await acp_boundary.stop()
        codex_runtime.close()
        if settings.surface == "admin":
            record_activity(settings.database_path, "app_stopped", "system", "success")


common = [Route("/health/live", live), Route("/health/ready", ready)]
admin = [Route("/", admin_index), Route("/admin/assets/admin.css", asset_css), Route("/admin/assets/admin.js", asset_js), Route("/admin/assets/icon.png", asset_icon), Route("/admin/api/v1/activity", activity), Route("/admin/api/v1/models", models_api, methods=["GET", "POST"]), Route("/admin/api/v1/models/{action}", model_action, methods=["POST"]), Route("/admin/api/v1/oauth/account", oauth_account), Route("/admin/api/v1/oauth/models", oauth_models), Route("/admin/api/v1/oauth/{action}", oauth_action, methods=["POST"]), Route("/admin/api/v1/standalone",standalone_admin_state), Route("/admin/api/v1/standalone/credential/{action}",standalone_credential_action,methods=["POST"]), Route("/admin/api/v1/acp",acp_admin,methods=["GET","POST"]), Route("/admin/api/v1/pending/abandon",abandon_pending,methods=["POST"])]
api = [Route("/api/v1/execute",standalone_boundary.submit,methods=["POST"]),Route("/api/v1/executions/{execution_id}",standalone_boundary.get,methods=["GET"]),Route("/api/v1/executions/{execution_id}/ack",standalone_boundary.ack,methods=["POST"])]
routes = common + (admin if settings.surface == "admin" else api)
app = Starlette(routes=routes, middleware=[Middleware(SecurityHeadersMiddleware)], lifespan=lifespan)
