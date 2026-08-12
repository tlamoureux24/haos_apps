"""ASGI entry point with strictly separated admin and public surfaces."""

from __future__ import annotations

import html
import os
import secrets
from uuid import uuid4

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from agent_gateway import __version__
from agent_gateway.admin_ui import ADMIN_CSS, ADMIN_JS
from agent_gateway.database import database_ready
from agent_gateway.control_plane import ControlPlane
from agent_gateway.http_api import (
    admin_create_identity,
    admin_list_identities,
    admin_revoke_identity,
    admin_status,
    create_event,
    effective_permissions,
)
from agent_gateway.settings import load_settings
from agent_gateway.surfaces import exposed_paths


if os.geteuid() != 1000:
    raise RuntimeError("Agent Gateway application listeners must run with UID 1000")

settings = load_settings()
csrf_token = secrets.token_urlsafe(32)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.correlation_id = request.headers.get("x-request-id") or str(uuid4())
        if settings.surface == "admin":
            client_ip = request.client.host if request.client else ""
            if client_ip != settings.ingress_proxy_ip:
                return JSONResponse({"error": {"code": "ingress_only"}}, status_code=403)
            if request.url.path not in {"/health/live", "/health/ready"} and not request.headers.get(
                "x-ingress-path"
            ):
                return JSONResponse({"error": {"code": "ingress_context_required"}}, status_code=403)
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Request-ID"] = request.state.correlation_id
        if settings.surface == "admin":
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'self'"
            )
            if request.method == "GET" and request.url.path == "/":
                response.set_cookie(
                    "agw_csrf",
                    csrf_token,
                    httponly=False,
                    secure=True,
                    samesite="strict",
                    path=request.headers.get("x-ingress-path", "/"),
                )
        return response


async def live(_: Request) -> JSONResponse:
    return JSONResponse({"status": "live"})


async def ready(_: Request) -> JSONResponse:
    if not database_ready(settings.database_path):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return JSONResponse({"status": "ready", "version": __version__})


async def admin_index(request: Request) -> HTMLResponse:
    prefix = request.headers.get("x-ingress-path", request.scope.get("root_path", "")).rstrip("/")
    safe_prefix = html.escape(prefix, quote=True)
    document = f"""<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Gateway</title><link rel="stylesheet" href="{safe_prefix}/admin/assets/admin.css"></head>
<body><header><h1>Agent Gateway</h1><p>Plan de contrôle des agents et automatisations</p></header>
<main class="shell" data-base="{safe_prefix}" data-csrf="{csrf_token}">
<section class="summary"><div class="metric"><strong id="total">–</strong><span>Identités</span></div><div class="metric"><strong id="active">–</strong><span>Actives</span></div><div class="metric"><strong>Prêt</strong><span><a href="{safe_prefix}/health/ready">État du service</a></span></div></section>
<div class="grid"><section class="panel"><h2>Nouvelle identité</h2><p class="muted">L’identifiant secret ne sera affiché qu’une seule fois.</p><form id="create"><label>Nom<input name="display_name" maxlength="120" required></label><label>Type<select name="identity_type"><option value="client">Client MCP</option><option value="event_source">Source d’événements</option><option value="scheduler">Planificateur</option></select></label><fieldset><legend>Permissions</legend><label><input type="checkbox" name="actions" value="permissions.effective.read">Lire ses permissions</label><label><input type="checkbox" name="actions" value="events.create">Créer des événements</label><label><input type="checkbox" name="actions" value="events.read">Lire les événements</label><label><input type="checkbox" name="actions" value="jobs.read">Lire les tâches</label><label><input type="checkbox" name="actions" value="reports.read">Lire les rapports</label></fieldset><button type="submit">Créer l’identité</button><p id="message" class="error"></p></form><aside id="credential" class="credential"><strong>Copiez cet identifiant maintenant</strong><code></code><span>Il ne sera plus affiché ensuite.</span></aside></section><section class="panel"><h2>Identités</h2><div id="identities"><p class="muted">Chargement…</p></div></section></div>
</main><script src="{safe_prefix}/admin/assets/admin.js" defer></script></body></html>"""
    return HTMLResponse(document)


async def admin_css(_: Request) -> Response:
    return Response(ADMIN_CSS, media_type="text/css")


async def admin_js(_: Request) -> Response:
    return Response(ADMIN_JS, media_type="application/javascript")


async def not_found(_: Request, __: Exception) -> Response:
    return JSONResponse({"error": {"code": "not_found"}}, status_code=404)


route_handlers = {
    "/": admin_index,
    "/admin/assets/admin.css": admin_css,
    "/admin/assets/admin.js": admin_js,
    "/admin/api/v1/status": admin_status,
    "/admin/api/v1/identities": admin_create_identity,
    "/admin/api/v1/identities/revoke": admin_revoke_identity,
    "/api/v1/events": create_event,
    "/api/v1/permissions/effective": effective_permissions,
    "/health/live": live,
    "/health/ready": ready,
}
routes = [
    Route(
        path,
        route_handlers[path],
        methods=["POST"] if path in {"/admin/api/v1/identities", "/admin/api/v1/identities/revoke", "/api/v1/events"} else ["GET"],
    )
    for path in exposed_paths(settings.surface)
]
if settings.surface == "admin":
    routes.append(Route("/admin/api/v1/identities", admin_list_identities, methods=["GET"]))

app = Starlette(
    debug=False,
    routes=routes,
    middleware=[Middleware(SecurityHeadersMiddleware)],
    exception_handlers={404: not_found},
)
app.state.control_plane = ControlPlane(
    settings.database_path,
    settings.data_dir / "private",
)
