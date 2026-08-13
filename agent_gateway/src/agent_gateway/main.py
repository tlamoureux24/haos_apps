"""ASGI entry point with strictly separated admin and public surfaces."""

from __future__ import annotations

import html
import os
import secrets
from contextlib import asynccontextmanager
from uuid import uuid4

from starlette.applications import Starlette
from starlette.middleware import Middleware
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import HTMLResponse, JSONResponse, Response
from starlette.routing import Mount, Route

from agent_gateway import __version__
from agent_gateway.admin_ui import ADMIN_CSS, ADMIN_JS
from agent_gateway.database import database_ready
from agent_gateway.control_plane import ControlPlane
from agent_gateway.http_api import (
    admin_create_identity,
    admin_create_connector,
    admin_check_connector,
    admin_delete_connector,
    admin_list_connectors,
    admin_list_connector_tools,
    admin_set_connector_enabled,
    admin_create_task,
    admin_delete_task,
    admin_list_tasks,
    admin_set_task_enabled,
    admin_run_task,
    admin_list_events,
    admin_list_identities,
    admin_list_jobs,
    admin_cancel_job,
    admin_list_reports,
    admin_list_audit,
    admin_export_audit,
    admin_revoke_identity,
    admin_status,
    create_event,
    effective_permissions,
    list_events,
    list_jobs,
    list_reports,
)
from agent_gateway.mcp_api import OpaqueBearerMiddleware, create_mcp
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
<body><main class="app" data-base="{safe_prefix}" data-csrf="{csrf_token}">
<header class="top"><a class="brand" href="#overview"><img src="{safe_prefix}/admin/assets/logo.png" alt=""><span>Agent Gateway <b>v{__version__}</b><small>Control plane</small></span></a><nav class="nav" aria-label="Navigation"><a class="active" data-view="overview" href="#overview">Vue d’ensemble</a><a data-view="events" href="#events">Événements</a><a data-view="tasks" href="#tasks">Tâches</a><a data-view="jobs" href="#jobs">Exécutions</a><a data-view="reports" href="#reports">Rapports</a><a data-view="connectors" href="#connectors">Connecteurs</a><a data-view="audit" href="#audit">Audit</a></nav><button id="theme" class="theme" type="button" aria-label="Changer de thème">☾</button></header>
<section id="overview" class="view active"><section class="hero"><div><h1>Vue d’ensemble</h1><p>Gérez les identités et leurs autorisations d’accès à la passerelle.</p></div><div class="health"><i></i><a href="{safe_prefix}/health/ready">Service opérationnel</a></div></section>
<section class="metrics"><article class="metric"><strong id="total">–</strong><span>Identités enregistrées</span></article><article class="metric"><strong id="active">–</strong><span>Identités actives</span></article><article class="metric amber"><strong id="revoked">–</strong><span>Identités révoquées</span></article></section>
<div class="workspace"><section class="card"><div class="cardhead"><div><h2>Nouvelle identité</h2><p>Le secret ne sera affiché qu’une seule fois.</p></div></div><form id="create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Codex laptop" required></label><label>Type<select name="identity_type"><option value="client">Client MCP</option><option value="event_source">Source d’événements</option><option value="scheduler">Planificateur</option></select></label><fieldset><legend>Permissions de la passerelle</legend><label class="permission"><input type="checkbox" name="actions" value="permissions.effective.read"><span>Lire ses permissions<small>Inspecter les droits effectifs de cette identité</small></span></label><label class="permission"><input type="checkbox" name="actions" value="events.create"><span>Créer des événements<small>Soumettre des événements authentifiés</small></span></label><label class="permission"><input type="checkbox" name="actions" value="events.read"><span>Lire les événements</span></label><label class="permission"><input type="checkbox" name="actions" value="jobs.read"><span>Lire les tâches</span></label><label class="permission"><input type="checkbox" name="actions" value="jobs.claim"><span>Traiter les tâches<small>Réclamer, maintenir, terminer ou échouer une tâche</small></span></label><input type="hidden" name="worker_actions" value="jobs.heartbeat,jobs.complete,jobs.fail"><label class="permission"><input type="checkbox" name="actions" value="reports.read"><span>Lire les rapports</span></label></fieldset><button class="primary" type="submit">Créer l’identité</button><p id="message" class="error"></p></form><aside id="credential" class="credential"><strong>Copiez cet identifiant maintenant</strong><code></code><span>Il ne pourra pas être récupéré plus tard.</span><button id="credential-dismiss" class="danger" type="button">J’ai copié le secret</button></aside></section><section class="card identities"><div class="cardhead"><div><h2>Identités</h2><p>Clients, sources et planificateurs autorisés.</p></div><span id="identity-count" class="count">–</span></div><div id="identities"><p class="loading">Chargement…</p></div></section></div>
 </section>
<section id="events" class="view"><div class="pagehead"><h1>Événements</h1><p>Derniers événements authentifiés reçus par la passerelle.</p></div><section class="card"><div id="events-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="tasks" class="view"><div class="pagehead"><h1>Tâches</h1><p>Composez des tâches à partir d’outils précis provenant d’un ou plusieurs connecteurs.</p></div><div class="workspace task-workspace"><section class="card"><div class="cardhead"><div><h2>Nouvelle tâche</h2><p>Au moins un outil d’un connecteur opérationnel est obligatoire.</p></div></div><form id="task-create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Diagnostic d’incident" required></label><label>Instructions transmises à l’agent<textarea name="objective" maxlength="4000" rows="5" placeholder="Décrivez précisément le résultat attendu…" required></textarea></label><label>Tentatives maximales<select name="max_attempts"><option>1</option><option selected>3</option><option>5</option></select></label><fieldset><legend>Outils autorisés</legend><div id="task-tool-picker"><p class="loading">Chargement…</p></div></fieldset><button class="primary" type="submit">Créer la tâche</button><p id="task-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Tâches configurées</h2><p>Une dépendance modifiée rend la tâche indisponible.</p></div><span id="task-count" class="count">–</span></div><div id="task-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="jobs" class="view"><div class="pagehead"><h1>Exécutions</h1><p>File persistante des travaux demandés à la passerelle.</p></div><section class="card"><div id="jobs-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="reports" class="view"><div class="pagehead"><h1>Rapports</h1><p>Résultats structurés et persistants produits par les agents.</p></div><section class="card"><div id="reports-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="connectors" class="view"><div class="pagehead"><h1>Connecteurs MCP</h1><p>Ajoutez les serveurs MCP externes dont les outils pourront ensuite être attribués aux tâches.</p></div><div class="workspace"><section class="card"><div class="cardhead"><div><h2>Nouveau connecteur</h2><p>La connexion et l’inventaire sont validés avant l’enregistrement.</p></div></div><form id="connector-create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Home Assistant" required></label><label>URL Streamable HTTP<input name="url" maxlength="2048" type="url" placeholder="http://serveur:port/mcp" required></label><label>Jeton Bearer facultatif<input name="bearer_token" maxlength="4096" type="password" autocomplete="new-password"></label><button class="primary" type="submit">Tester et ajouter</button><p id="connector-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Connecteurs configurés</h2><p>La découverte n’autorise aucun outil automatiquement.</p></div><span id="connector-count" class="count">–</span></div><div id="connector-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="audit" class="view"><div class="pagehead split"><div><h1>Journal d’audit</h1><p>Décisions de sécurité chaînées et expurgées de la passerelle.</p></div><a class="export" href="{safe_prefix}/admin/api/v1/audit/export" download>Exporter JSONL v1</a></div><section class="card"><div id="audit-list" class="tablewrap loading">Chargement…</div></section></section>
</main><script src="{safe_prefix}/admin/assets/admin.js" defer></script></body></html>"""
    return HTMLResponse(document)


async def admin_css(_: Request) -> Response:
    return Response(ADMIN_CSS, media_type="text/css")


async def admin_js(_: Request) -> Response:
    return Response(ADMIN_JS, media_type="application/javascript")


async def admin_logo(_: Request) -> Response:
    return Response(open("/app/logo.png", "rb").read(), media_type="image/png")


async def not_found(_: Request, __: Exception) -> Response:
    return JSONResponse({"error": {"code": "not_found"}}, status_code=404)


route_handlers = {
    "/": admin_index,
    "/admin/assets/admin.css": admin_css,
    "/admin/assets/admin.js": admin_js,
    "/admin/assets/logo.png": admin_logo,
    "/admin/api/v1/status": admin_status,
    "/admin/api/v1/connectors": admin_create_connector,
    "/admin/api/v1/connectors/check": admin_check_connector,
    "/admin/api/v1/connectors/delete": admin_delete_connector,
    "/admin/api/v1/connectors/enabled": admin_set_connector_enabled,
    "/admin/api/v1/connectors/tools": admin_list_connector_tools,
    "/admin/api/v1/tasks": admin_create_task,
    "/admin/api/v1/tasks/delete": admin_delete_task,
    "/admin/api/v1/tasks/enabled": admin_set_task_enabled,
    "/admin/api/v1/tasks/run": admin_run_task,
    "/admin/api/v1/identities": admin_create_identity,
    "/admin/api/v1/identities/revoke": admin_revoke_identity,
    "/admin/api/v1/events": admin_list_events,
    "/admin/api/v1/jobs": admin_list_jobs,
    "/admin/api/v1/jobs/cancel": admin_cancel_job,
    "/admin/api/v1/reports": admin_list_reports,
    "/admin/api/v1/audit": admin_list_audit,
    "/admin/api/v1/audit/export": admin_export_audit,
    "/api/v1/events": create_event,
    "/api/v1/jobs": list_jobs,
    "/api/v1/reports": list_reports,
    "/api/v1/permissions/effective": effective_permissions,
    "/health/live": live,
    "/health/ready": ready,
}
routes = [
    Route(
        path,
        route_handlers[path],
        methods=["POST"] if path in {"/admin/api/v1/connectors", "/admin/api/v1/connectors/check", "/admin/api/v1/connectors/delete", "/admin/api/v1/connectors/enabled", "/admin/api/v1/tasks", "/admin/api/v1/tasks/delete", "/admin/api/v1/tasks/enabled", "/admin/api/v1/tasks/run", "/admin/api/v1/identities", "/admin/api/v1/identities/revoke", "/admin/api/v1/jobs/cancel", "/api/v1/events"} else ["GET"],
    )
    for path in exposed_paths(settings.surface)
]
control_plane = ControlPlane(
    settings.database_path,
    settings.data_dir / "private",
    intake_rate_limit_per_minute=settings.intake_rate_limit_per_minute,
)
mcp_server = create_mcp(control_plane) if settings.surface == "public" else None
mcp_application = mcp_server.streamable_http_app() if mcp_server else None

if settings.surface == "admin":
    routes.append(Route("/admin/api/v1/identities", admin_list_identities, methods=["GET"]))
    routes.append(Route("/admin/api/v1/connectors", admin_list_connectors, methods=["GET"]))
    routes.append(Route("/admin/api/v1/tasks", admin_list_tasks, methods=["GET"]))
if settings.surface == "public":
    routes.append(Route("/api/v1/events", list_events, methods=["GET"]))
    routes.append(Mount("/", app=OpaqueBearerMiddleware(mcp_application, control_plane)))


@asynccontextmanager
async def lifespan(_: Starlette):
    if mcp_server is None:
        yield
    else:
        async with mcp_server.session_manager.run():
            yield

app = Starlette(
    debug=False,
    routes=routes,
    middleware=[Middleware(SecurityHeadersMiddleware)],
    exception_handlers={404: not_found},
    lifespan=lifespan,
)
app.state.control_plane = control_plane
