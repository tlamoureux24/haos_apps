"""ASGI entry point with strictly separated admin and public surfaces."""

from __future__ import annotations

import html
from uuid import uuid4

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from agent_gateway import __version__
from agent_gateway.database import database_ready
from agent_gateway.settings import load_settings


settings = load_settings()


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        request.state.correlation_id = request.headers.get("x-request-id") or str(uuid4())
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
        return response


async def live(_: Request) -> JSONResponse:
    return JSONResponse({"status": "live"})


async def ready(_: Request) -> JSONResponse:
    if not database_ready(settings.database_path):
        return JSONResponse({"status": "not_ready"}, status_code=503)
    return JSONResponse({"status": "ready", "version": __version__})


async def admin_index(request: Request) -> HTMLResponse:
    prefix = request.scope.get("root_path", "")
    safe_prefix = html.escape(prefix, quote=True)
    document = f"""<!doctype html>
<html lang="fr">
<head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Gateway</title></head>
<body><main><h1>Agent Gateway</h1><p>Plan de contrôle initialisé.</p>
<p><a href="{safe_prefix}/health/ready">État de préparation</a></p></main></body></html>"""
    return HTMLResponse(document)


async def not_found(_: Request, __: Exception) -> Response:
    return JSONResponse({"error": {"code": "not_found"}}, status_code=404)


common_routes = [
    Route("/health/live", live, methods=["GET"]),
    Route("/health/ready", ready, methods=["GET"]),
]
if settings.surface == "admin":
    routes = [Route("/", admin_index, methods=["GET"]), *common_routes]
else:
    routes = common_routes

app = Starlette(
    debug=False,
    routes=routes,
    middleware=[Middleware(SecurityHeadersMiddleware)],
    exception_handlers={404: not_found},
)
