"""Strictly isolated administration and public ASGI applications."""

from __future__ import annotations

import html
from dataclasses import dataclass
from pathlib import Path

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Route

from mcp_capability_bridge import __version__
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.database import database_ready
from mcp_capability_bridge.settings import Settings


@dataclass(frozen=True)
class RuntimeState:
    settings: Settings


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, *, admin: bool, ingress_proxy_ip: str):
        super().__init__(app)
        self.admin = admin
        self.ingress_proxy_ip = ingress_proxy_ip

    async def dispatch(self, request: Request, call_next):
        if self.admin:
            client_ip = request.client.host if request.client else ""
            if client_ip != self.ingress_proxy_ip:
                return JSONResponse({"error": {"code": "ingress_only"}}, status_code=403)
            if not request.headers.get("x-ingress-path"):
                return JSONResponse({"error": {"code": "ingress_context_required"}}, status_code=403)
        response = await call_next(request)
        response.headers.update({
            "Cache-Control": "no-store",
            "Referrer-Policy": "no-referrer",
            "X-Content-Type-Options": "nosniff",
        })
        if self.admin:
            response.headers["Content-Security-Policy"] = (
                "default-src 'self'; script-src 'self'; style-src 'self'; "
                "img-src 'self' data:; frame-ancestors 'self'"
            )
        return response


def create_apps(state: RuntimeState) -> tuple[Starlette, Starlette]:
    async def live(_: Request) -> JSONResponse:
        return JSONResponse({"status": "live"})

    async def ready(_: Request) -> JSONResponse:
        if not database_ready(state.settings.database_path):
            return JSONResponse({"status": "not_ready"}, status_code=503)
        return JSONResponse({"status": "ready", "version": __version__})

    async def status(_: Request) -> JSONResponse:
        return JSONResponse({
            "status": "ready" if database_ready(state.settings.database_path) else "not_ready",
            "version": __version__,
            "database_generation": 1,
            "public_surface": "health_only",
        })

    async def index(request: Request) -> HTMLResponse:
        prefix = request.headers.get("x-ingress-path", "").rstrip("/")
        safe = html.escape(prefix, quote=True)
        navigation = "".join(
            f'<a data-view="{key}" href="#{key}" data-i18n="{key}">{label}</a>'
            for key, label in (
                ("overview", "Vue d’ensemble"), ("clients", "Clients MCP"),
                ("targets", "Cibles"), ("ssh", "Capacités SSH"),
                ("web", "Cibles Web"), ("sessions", "Sessions"),
            )
        )
        planned = "".join(
            f'<section id="{key}" class="view"><div class="pagehead"><div><h1 data-i18n="{key}"></h1><p data-i18n="plannedText"></p></div></div><article class="card"><h2 data-i18n="plannedTitle"></h2><p data-i18n="plannedText"></p></article></section>'
            for key in ("clients", "targets", "ssh", "web", "sessions")
        )
        return HTMLResponse(f'''<!doctype html><html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>MCP Capability Bridge</title><link rel="stylesheet" href="{safe}/admin/assets/admin.css"></head><body><main class="app" data-base="{safe}"><header class="site-header"><div class="header-main"><a class="brand" href="#overview"><img src="{safe}/admin/assets/icon.png" alt=""><span>MCP Capability Bridge <b>v{__version__}</b></span></a><div class="header-actions"><button id="language" class="switch" type="button">EN</button><button id="theme" class="switch" type="button">☾</button></div></div><div class="nav-scroll"><nav class="nav" aria-label="Navigation">{navigation}</nav></div></header><section id="overview" class="view active"><div class="pagehead"><div><h1 data-i18n="overviewTitle"></h1><p data-i18n="overviewIntro"></p></div><button id="status-open" class="primary" type="button" data-i18n="statusAction"></button></div><section class="metrics"><article class="metric"><strong class="state" data-i18n="ready"></strong><span data-i18n="appState"></span></article><article class="metric"><strong data-i18n="healthOnly"></strong><span data-i18n="publicSurface"></span></article><article class="metric"><strong data-i18n="generation"></strong><span data-i18n="database"></span></article></section><article class="card notice"><h2 data-i18n="foundationTitle"></h2><p data-i18n="foundationText"></p></article></section>{planned}</main><div id="drawer-shell" class="drawer-shell" hidden><div class="drawer-overlay"></div><aside id="admin-drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1"><header class="drawer-head"><h2 id="drawer-title" data-i18n="drawerTitle"></h2><button id="drawer-close" class="secondary drawer-close" type="button" data-i18n-aria="close">×</button></header><div class="drawer-body"><dl><dt data-i18n="runtime"></dt><dd data-i18n="singleRuntime"></dd><dt data-i18n="listeners"></dt><dd data-i18n="listenerValues"></dd><dt data-i18n="scope"></dt><dd data-i18n="scopeValue"></dd></dl></div></aside></div><script src="{safe}/admin/assets/admin.js" defer></script></body></html>''')

    async def css(_: Request) -> Response:
        return Response(ADMIN_CSS, media_type="text/css")

    async def js(_: Request) -> Response:
        return Response(ADMIN_JS, media_type="application/javascript")

    async def icon(_: Request) -> Response:
        return Response(Path("/app/icon.png").read_bytes(), media_type="image/png")

    health = [Route("/health/live", live), Route("/health/ready", ready)]
    admin = Starlette(
        routes=[Route("/", index), Route("/admin/assets/admin.css", css),
                Route("/admin/assets/admin.js", js), Route("/admin/assets/icon.png", icon),
                Route("/admin/api/v1/status", status), *health],
        middleware=[Middleware(SecurityHeadersMiddleware, admin=True,
                               ingress_proxy_ip=state.settings.ingress_proxy_ip)],
    )
    public = Starlette(
        routes=health,
        middleware=[Middleware(SecurityHeadersMiddleware, admin=False,
                               ingress_proxy_ip=state.settings.ingress_proxy_ip)],
    )
    return admin, public
