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
from agent_gateway.database import database_ready
from agent_gateway.control_plane import ControlPlane
from agent_gateway.http_api import (
    admin_create_identity,
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
                "default-src 'self'; style-src 'self' 'unsafe-inline'; "
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
<title>Agent Gateway</title></head>
<body><main data-csrf="{csrf_token}"><h1>Agent Gateway</h1><p>Plan de contrôle initialisé.</p>
<p><a href="{safe_prefix}/health/ready">État de préparation</a></p></main></body></html>"""
    return HTMLResponse(document)


async def not_found(_: Request, __: Exception) -> Response:
    return JSONResponse({"error": {"code": "not_found"}}, status_code=404)


route_handlers = {
    "/": admin_index,
    "/admin/api/v1/status": admin_status,
    "/admin/api/v1/identities": admin_create_identity,
    "/api/v1/events": create_event,
    "/api/v1/permissions/effective": effective_permissions,
    "/health/live": live,
    "/health/ready": ready,
}
routes = [
    Route(
        path,
        route_handlers[path],
        methods=["POST"] if path in {"/admin/api/v1/identities", "/api/v1/events"} else ["GET"],
    )
    for path in exposed_paths(settings.surface)
]

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
