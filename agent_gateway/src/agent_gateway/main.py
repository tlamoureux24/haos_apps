"""ASGI entry point with strictly separated admin and public surfaces."""

from __future__ import annotations

import html
import os
import secrets
import asyncio
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
    admin_update_connector,
    admin_rotate_connector_secret,
    admin_delete_connector,
    admin_list_connectors,
    admin_list_connector_tools,
    admin_set_connector_enabled,
    admin_set_connector_archived,
    admin_create_task,
    admin_delete_task,
    admin_list_tasks,
    admin_set_task_enabled,
    admin_set_task_archived,
    admin_run_task,
    admin_list_schedules,
    admin_create_schedule,
    admin_update_schedule,
    admin_set_schedule_enabled,
    admin_delete_schedule,
    admin_list_event_mappings,
    admin_create_event_mapping,
    admin_update_event_mapping,
    admin_set_event_mapping_enabled,
    admin_retry_event_incident,
    admin_delete_event_mapping,
    admin_list_events,
    admin_list_identities,
    admin_list_jobs,
    admin_cancel_job,
    admin_requeue_job,
    admin_list_reports,
    admin_list_audit,
    admin_export_audit,
    admin_verify_audit,
    admin_retention_status,
    admin_update_retention,
    admin_run_retention,
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
<header class="site-header"><div class="header-main"><a class="brand" href="#overview"><img src="{safe_prefix}/admin/assets/logo.png" alt=""><span>Agent Gateway <b>v{__version__}</b><small>Control plane</small></span></a><div class="header-actions"><button id="language" class="theme" type="button" aria-label="Changer de langue">EN</button><button id="theme" class="theme" type="button" aria-label="Changer de thème">☾</button></div></div><div class="nav-scroll"><nav class="nav" aria-label="Navigation"><a class="active" data-view="overview" href="#overview">Vue d’ensemble</a><a data-view="identities-view" href="#identities-view">Identités</a><a data-view="events" href="#events">Événements</a><a data-view="tasks" href="#tasks">Tâches</a><a data-view="triggers" href="#triggers">Déclencheurs</a><a data-view="schedules" href="#schedules">Planifications</a><a data-view="jobs" href="#jobs">Exécutions</a><a data-view="reports" href="#reports">Rapports</a><a data-view="connectors" href="#connectors">Connecteurs</a><a data-view="audit" href="#audit">Audit</a></nav></div></header>
<section id="overview" class="view active"><section class="hero"><div><h1>Vue d’ensemble</h1><p>Consultez l’état opérationnel de la passerelle.</p><span class="freshness" data-freshness="overview"></span></div><div class="health"><i></i><a href="{safe_prefix}/health/ready">Service opérationnel</a></div></section>
<section class="cockpit-section"><div class="section-title"><h2>Configuration</h2><p>Disponibilité des ressources qui composent les automatisations.</p></div><div class="cockpit-grid"><a class="cockpit-card" href="#connectors"><span class="cockpit-label">Connecteurs</span><strong id="metric-connectors">–</strong><small id="metric-connectors-detail">Chargement…</small></a><a class="cockpit-card" href="#tasks"><span class="cockpit-label">Tâches</span><strong id="metric-tasks">–</strong><small id="metric-tasks-detail">Chargement…</small></a><a class="cockpit-card" href="#identities-view"><span class="cockpit-label">Identités actives</span><strong id="active">–</strong><small id="metric-identities-detail">Chargement…</small></a><a class="cockpit-card" href="#triggers"><span class="cockpit-label">Déclencheurs actifs</span><strong id="metric-triggers">–</strong><small id="metric-triggers-detail">Chargement…</small></a><a class="cockpit-card" href="#schedules"><span class="cockpit-label">Planifications actives</span><strong id="metric-schedules">–</strong><small id="metric-schedules-detail">Chargement…</small></a></div></section>
<section class="cockpit-section"><div class="section-title"><h2>Activité et sécurité</h2><p>État récent de la file, des incidents et de la chaîne d’audit.</p></div><div class="cockpit-grid"><a class="cockpit-card" href="#events"><span class="cockpit-label">Événements sur 24 h</span><strong id="metric-events">–</strong><small>Reçus par la passerelle</small></a><a class="cockpit-card" href="#reports"><span class="cockpit-label">Rapports sur 24 h</span><strong id="metric-reports">–</strong><small>Produits par les agents</small></a><a class="cockpit-card" href="#jobs"><span class="cockpit-label">Exécutions actives</span><strong id="metric-active-jobs">–</strong><small id="metric-jobs-detail">Chargement…</small></a><a class="cockpit-card" href="#triggers"><span class="cockpit-label">Incidents de grâce</span><strong id="metric-incidents">–</strong><small id="metric-incidents-detail">Chargement…</small></a><a class="cockpit-card" href="#audit"><span class="cockpit-label">Chaîne d’audit</span><strong id="metric-audit">–</strong><small id="metric-audit-detail">Chargement…</small></a><a class="cockpit-card attention" href="#jobs"><span class="cockpit-label">À traiter</span><strong id="metric-attention">–</strong><small id="metric-attention-detail">Échecs récents et dead letters</small></a></div></section></section>
<section id="identities-view" class="view"><div class="pagehead split"><div><h1>Identités</h1><p>Gérez les clients, sources et planificateurs autorisés.</p></div><button id="identity-create-open" class="page-action" type="button">Nouvelle identité</button></div><section class="card identities"><div class="cardhead"><div><h2>Identités configurées</h2><p>Chaque identité possède ses propres permissions et identifiants révocables.</p></div><span id="identity-count" class="count">–</span></div><div id="identities"><p class="loading">Chargement…</p></div></section></section>
<section id="events" class="view"><div class="pagehead"><h1>Événements</h1><p>Derniers événements authentifiés reçus par la passerelle.</p><span class="freshness" data-freshness="events"></span></div><section class="card"><div id="events-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="tasks" class="view"><div class="pagehead"><h1>Tâches</h1><p>Composez des tâches à partir d’outils précis provenant d’un ou plusieurs connecteurs.</p></div><div class="workspace task-workspace"><section class="card"><div class="cardhead"><div><h2>Nouvelle tâche</h2><p>Au moins un outil d’un connecteur opérationnel est obligatoire.</p></div></div><form id="task-create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Diagnostic d’incident" required></label><label>Instructions transmises à l’agent<textarea name="objective" maxlength="4000" rows="5" placeholder="Décrivez précisément le résultat attendu…" required></textarea></label><label>Tentatives maximales<select name="max_attempts"><option>1</option><option selected>3</option><option>5</option></select></label><fieldset><legend>Outils autorisés</legend><div id="task-tool-picker"><p class="loading">Chargement…</p></div></fieldset><button class="primary" type="submit">Créer la tâche</button><p id="task-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Tâches configurées</h2><p>Une dépendance modifiée rend la tâche indisponible.</p></div><span id="task-count" class="count">–</span></div><label class="archive-filter"><input id="task-show-archived" type="checkbox"> Afficher les tâches archivées</label><div id="task-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="triggers" class="view"><div class="pagehead"><h1>Déclencheurs</h1><p>Associez explicitement une source et un type d’événement à une tâche.</p></div><div class="workspace"><section class="card"><div class="cardhead"><div><h2 id="mapping-form-title">Nouveau déclencheur</h2><p>La source ne pourra pas choisir une autre tâche dans sa requête.</p></div></div><form id="mapping-create"><input type="hidden" name="mapping_id"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Alerte supervision" required></label><label>Source d’événements<select id="mapping-source" name="source_identity_id" required></select></label><label>Type d’événement<input name="event_type" maxlength="120" pattern="[a-z][a-z0-9_.-]*" placeholder="service.alert" required></label><label>Tâche<select id="mapping-task" name="task_id" required></select></label><label>Entrée transmise à l’agent<select name="input_mode"><option value="full_event" selected>Événement complet</option><option value="subject">Sujet uniquement</option><option value="attributes">Attributs uniquement</option></select></label><label>Délai de grâce<select id="mapping-grace" name="grace_minutes"><option value="0" selected>Aucun</option><option value="1">1 minute</option><option value="5">5 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">1 heure</option></select></label><label id="mapping-correlation-label" hidden>Corrélation pendant la grâce<select name="correlation_mode"><option value="simple" selected>Simple — tout le déclencheur</option><option value="aggregate_by_subject">Agrégée par sujet</option></select><small class="loading">Le mode agrégé exige un sujet stable non vide et crée un seul incident.</small></label><label id="mapping-recovery-label" hidden>Type d’événement de rétablissement<input name="recovery_event_type" maxlength="120" pattern="[a-z][a-z0-9_.-]*" placeholder="service.recovered"><small class="loading">Rétablit le déclencheur entier ou uniquement le sujet correspondant.</small></label><label>Cooldown<select name="cooldown_minutes"><option value="0">Aucun</option><option value="5">5 minutes</option><option value="15" selected>15 minutes</option><option value="30">30 minutes</option><option value="60">1 heure</option><option value="360">6 heures</option><option value="1440">24 heures</option></select></label><button id="mapping-submit" class="primary" type="submit">Créer le déclencheur</button><button id="mapping-edit-cancel" class="danger" type="button" hidden>Annuler la modification</button><p id="mapping-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Déclencheurs configurés</h2><p>Cooldown, grâce, incidents et rétablissements restent visibles et audités.</p></div><span id="mapping-count" class="count">–</span></div><div id="mapping-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="schedules" class="view"><div class="pagehead"><h1>Planifications</h1><p>Créez automatiquement des exécutions récurrentes à partir de tâches prêtes.</p></div><div class="workspace"><section class="card"><div class="cardhead"><div><h2 id="schedule-form-title">Nouvelle planification</h2><p>Les occurrences manquées pendant un arrêt ne sont pas rejouées en rafale.</p></div></div><form id="schedule-create"><input type="hidden" name="schedule_id"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Diagnostic quotidien" required></label><label>Tâche<select id="schedule-task" name="task_id" required></select></label><label>Mode<select id="schedule-kind" name="schedule_kind"><option value="interval">Intervalle</option><option value="daily">Chaque jour</option><option value="weekly">Chaque semaine</option></select></label><label id="schedule-interval-label">Fréquence<select name="interval_minutes"><option value="5">Toutes les 5 minutes</option><option value="15">Toutes les 15 minutes</option><option value="30">Toutes les 30 minutes</option><option value="60" selected>Toutes les heures</option><option value="360">Toutes les 6 heures</option><option value="1440">Tous les jours</option><option value="10080">Toutes les semaines</option></select></label><div id="schedule-calendar" hidden><label id="schedule-weekday-label" hidden>Jour<select name="weekday"><option value="0">Lundi</option><option value="1">Mardi</option><option value="2">Mercredi</option><option value="3">Jeudi</option><option value="4">Vendredi</option><option value="5">Samedi</option><option value="6">Dimanche</option></select></label><label>Heure<input name="time_of_day" type="time" value="09:00"></label><label>Fuseau horaire<input name="timezone" maxlength="120" placeholder="Europe/Paris"></label></div><button id="schedule-submit" class="primary" type="submit">Créer la planification</button><button id="schedule-edit-cancel" class="danger" type="button" hidden>Annuler la modification</button><p id="schedule-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Planifications configurées</h2><p>Une tâche indisponible est ignorée sans créer de travail invalide.</p></div><span id="schedule-count" class="count">–</span></div><div id="schedule-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="jobs" class="view"><div class="pagehead"><h1>Exécutions</h1><p>File persistante des travaux demandés à la passerelle.</p><span class="freshness" data-freshness="jobs"></span></div><section class="metrics job-metrics"><article class="metric amber"><strong id="jobs-queued">–</strong><span>En attente</span></article><article class="metric"><strong id="jobs-running">–</strong><span>En cours</span></article><article class="metric danger-metric"><strong id="jobs-dead-letter">–</strong><span>À traiter</span></article></section><section class="card"><div class="job-toolbar" role="group" aria-label="Filtrer les exécutions"><button class="job-filter active" type="button" data-state="all">Toutes</button><button class="job-filter" type="button" data-state="active">Actives</button><button class="job-filter" type="button" data-state="dead_letter">À traiter</button></div><div id="jobs-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="reports" class="view"><div class="pagehead"><h1>Rapports</h1><p>Résultats structurés et persistants produits par les agents.</p><span class="freshness" data-freshness="reports"></span></div><section class="card"><div id="reports-list" class="tablewrap loading">Chargement…</div></section></section>
<section id="connectors" class="view"><div class="pagehead"><h1>Connecteurs MCP</h1><p>Ajoutez les serveurs MCP externes dont les outils pourront ensuite être attribués aux tâches.</p></div><div class="workspace"><section class="card"><div class="cardhead"><div><h2>Nouveau connecteur</h2><p>La connexion et l’inventaire sont validés avant l’enregistrement.</p></div></div><form id="connector-create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Home Assistant" required></label><label>URL Streamable HTTP<input name="url" maxlength="2048" type="url" placeholder="http://serveur:port/mcp" required></label><label>Jeton Bearer facultatif<input name="bearer_token" maxlength="4096" type="password" autocomplete="new-password"></label><button class="primary" type="submit">Tester et ajouter</button><p id="connector-message" class="error"></p></form><form id="connector-edit" hidden><input name="connector_id" type="hidden"><p class="drawer-intro">Le secret actuel est conservé automatiquement et n’est jamais affiché.</p><label>Nom<input name="display_name" maxlength="120" required></label><p class="loading">Endpoint actuel : <span id="connector-current-endpoint"></span></p><label>Nouvelle URL Streamable HTTP<input name="url" maxlength="2048" type="url" placeholder="Laisser vide pour conserver l’endpoint actuel"></label><button class="primary" type="submit">Enregistrer et vérifier</button><p id="connector-edit-message" class="error"></p></form><form id="connector-rotate-secret" hidden><input name="connector_id" type="hidden"><p class="drawer-intro">Le secret existant ne peut pas être affiché. Le nouveau secret remplacera la copie utilisée par Agent Gateway après vérification.</p><p id="connector-secret-state" class="loading"></p><label>Nouveau jeton Bearer<input name="bearer_token" maxlength="4096" type="password" autocomplete="new-password" required></label><button class="primary" type="submit">Remplacer et vérifier le secret</button><p id="connector-secret-message" class="error"></p></form></section><section class="card identities"><div class="cardhead"><div><h2>Connecteurs configurés</h2><p>La découverte n’autorise aucun outil automatiquement.</p></div><span id="connector-count" class="count">–</span></div><label class="archive-filter"><input id="connector-show-archived" type="checkbox"> Afficher les connecteurs archivés</label><div id="connector-list"><p class="loading">Chargement…</p></div></section></div></section>
<section id="audit" class="view"><div class="pagehead split"><div><h1>Audit et rétention</h1><p>Vérifiez la chaîne d’audit et maîtrisez le volume des données opérationnelles.</p><span class="freshness" data-freshness="audit"></span></div><div class="page-actions"><button id="audit-verify" class="page-action" type="button">Vérifier maintenant</button><a class="export" href="{safe_prefix}/admin/api/v1/audit/export" download>Exporter JSONL v1</a></div></div><div class="workspace maintenance"><section class="card"><div class="cardhead"><div><h2>Politique de rétention</h2><p>Les exécutions actives et l’audit ne sont jamais supprimés.</p></div></div><form id="retention-form"><label>Conserver les données terminées<select name="retention_days"><option value="30">30 jours</option><option value="90">90 jours</option><option value="180">180 jours</option><option value="365">1 an</option><option value="730">2 ans</option></select></label><label>Maximum par passage<select name="batch_size"><option value="100">100 éléments</option><option value="250">250 éléments</option><option value="500">500 éléments</option><option value="1000">1 000 éléments</option></select></label><label class="permission"><input name="automatic" type="checkbox"><span>Nettoyage automatique<small>Un passage borné au maximum toutes les 24 heures.</small></span></label><button class="primary" type="submit">Enregistrer la politique</button><p id="retention-message" class="error"></p></form></section><section class="card"><div class="cardhead"><div><h2>Aperçu du nettoyage</h2><p id="retention-last">Chargement…</p></div><i id="audit-chain-dot" class="status-dot disabled" role="img"></i></div><div id="retention-preview" class="metrics"><article class="metric"><strong>–</strong><span>Exécutions</span></article></div><p id="audit-chain-status" class="actions">Vérification de la chaîne…</p><button id="retention-run" class="danger" type="button">Nettoyer maintenant</button></section></div><section class="card audit-card"><div id="audit-list" class="tablewrap loading">Chargement…</div></section></section>
<div id="drawer-shell" class="drawer-shell" hidden><div class="drawer-overlay" data-drawer-close></div><aside id="admin-drawer" class="drawer" role="dialog" aria-modal="true" aria-labelledby="drawer-title" tabindex="-1"><header class="drawer-head"><div><p class="drawer-kicker">Agent Gateway</p><h2 id="drawer-title">Nouvelle identité</h2></div><button id="drawer-close" class="drawer-close" type="button" aria-label="Fermer">×</button></header><div class="drawer-body"><section id="identity-drawer-panel" class="drawer-panel"><p class="drawer-intro">Le secret ne sera affiché qu’une seule fois.</p><form id="create"><label>Nom<input name="display_name" maxlength="120" placeholder="Ex. Codex laptop" required></label><label>Type<select name="identity_type"><option value="client">Client MCP</option><option value="event_source">Source d’événements</option><option value="scheduler">Planificateur</option></select></label><fieldset><legend>Permissions de la passerelle</legend><label class="permission"><input type="checkbox" name="actions" value="permissions.effective.read"><span>Lire ses permissions<small>Inspecter les droits effectifs de cette identité</small></span></label><label class="permission"><input type="checkbox" name="actions" value="events.create"><span>Créer des événements<small>Soumettre des événements authentifiés</small></span></label><label class="permission"><input type="checkbox" name="actions" value="events.read"><span>Lire les événements</span></label><label class="permission"><input type="checkbox" name="actions" value="jobs.read"><span>Lire les tâches</span></label><label class="permission"><input type="checkbox" name="actions" value="jobs.claim"><span>Traiter les tâches<small>Réclamer, maintenir, terminer ou échouer une tâche</small></span></label><input type="hidden" name="worker_actions" value="jobs.heartbeat,jobs.complete,jobs.fail"><label class="permission"><input type="checkbox" name="actions" value="reports.read"><span>Lire les rapports</span></label></fieldset><button class="primary" type="submit">Créer l’identité</button><p id="message" class="error" aria-live="polite"></p></form><aside id="credential" class="credential" aria-live="assertive"><strong>Copiez cet identifiant maintenant</strong><code></code><span>Il ne pourra pas être récupéré plus tard.</span><button id="credential-dismiss" class="primary" type="button">J’ai copié le secret</button></aside></section></div></aside></div>
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
    "/admin/api/v1/connectors/update": admin_update_connector,
    "/admin/api/v1/connectors/rotate-secret": admin_rotate_connector_secret,
    "/admin/api/v1/connectors/delete": admin_delete_connector,
    "/admin/api/v1/connectors/enabled": admin_set_connector_enabled,
    "/admin/api/v1/connectors/archived": admin_set_connector_archived,
    "/admin/api/v1/connectors/tools": admin_list_connector_tools,
    "/admin/api/v1/tasks": admin_create_task,
    "/admin/api/v1/tasks/delete": admin_delete_task,
    "/admin/api/v1/tasks/enabled": admin_set_task_enabled,
    "/admin/api/v1/tasks/archived": admin_set_task_archived,
    "/admin/api/v1/tasks/run": admin_run_task,
    "/admin/api/v1/schedules": admin_create_schedule,
    "/admin/api/v1/schedules/update": admin_update_schedule,
    "/admin/api/v1/schedules/enabled": admin_set_schedule_enabled,
    "/admin/api/v1/schedules/delete": admin_delete_schedule,
    "/admin/api/v1/event-mappings": admin_create_event_mapping,
    "/admin/api/v1/event-mappings/update": admin_update_event_mapping,
    "/admin/api/v1/event-mappings/enabled": admin_set_event_mapping_enabled,
    "/admin/api/v1/event-mappings/incidents/retry": admin_retry_event_incident,
    "/admin/api/v1/event-mappings/delete": admin_delete_event_mapping,
    "/admin/api/v1/identities": admin_create_identity,
    "/admin/api/v1/identities/revoke": admin_revoke_identity,
    "/admin/api/v1/events": admin_list_events,
    "/admin/api/v1/jobs": admin_list_jobs,
    "/admin/api/v1/jobs/cancel": admin_cancel_job,
    "/admin/api/v1/jobs/requeue": admin_requeue_job,
    "/admin/api/v1/reports": admin_list_reports,
    "/admin/api/v1/audit": admin_list_audit,
    "/admin/api/v1/audit/export": admin_export_audit,
    "/admin/api/v1/audit/verify": admin_verify_audit,
    "/admin/api/v1/retention": admin_retention_status,
    "/admin/api/v1/retention/update": admin_update_retention,
    "/admin/api/v1/retention/run": admin_run_retention,
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
        methods=["POST"] if path in {"/admin/api/v1/connectors", "/admin/api/v1/connectors/check", "/admin/api/v1/connectors/update", "/admin/api/v1/connectors/rotate-secret", "/admin/api/v1/connectors/delete", "/admin/api/v1/connectors/enabled", "/admin/api/v1/connectors/archived", "/admin/api/v1/tasks", "/admin/api/v1/tasks/delete", "/admin/api/v1/tasks/enabled", "/admin/api/v1/tasks/archived", "/admin/api/v1/tasks/run", "/admin/api/v1/schedules", "/admin/api/v1/schedules/update", "/admin/api/v1/schedules/enabled", "/admin/api/v1/schedules/delete", "/admin/api/v1/event-mappings", "/admin/api/v1/event-mappings/update", "/admin/api/v1/event-mappings/enabled", "/admin/api/v1/event-mappings/incidents/retry", "/admin/api/v1/event-mappings/delete", "/admin/api/v1/identities", "/admin/api/v1/identities/revoke", "/admin/api/v1/jobs/cancel", "/admin/api/v1/jobs/requeue", "/admin/api/v1/audit/verify", "/admin/api/v1/retention/update", "/admin/api/v1/retention/run", "/api/v1/events"} else ["GET"],
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
    routes.append(Route("/admin/api/v1/schedules", admin_list_schedules, methods=["GET"]))
    routes.append(Route("/admin/api/v1/event-mappings", admin_list_event_mappings, methods=["GET"]))
if settings.surface == "public":
    routes.append(Route("/api/v1/events", list_events, methods=["GET"]))
    routes.append(Mount("/", app=OpaqueBearerMiddleware(mcp_application, control_plane)))


@asynccontextmanager
async def lifespan(_: Starlette):
    if mcp_server is None:
        async def schedule_loop():
            loop = asyncio.get_running_loop()
            next_retention_check = 0.0
            next_audit_check = 0.0
            first_audit_check = True
            while True:
                await asyncio.to_thread(control_plane.run_due_schedules)
                await asyncio.to_thread(control_plane.run_due_event_triggers)
                if loop.time() >= next_retention_check:
                    await asyncio.to_thread(control_plane.run_retention, "automatic-retention", True)
                    next_retention_check = loop.time() + 86_400
                if loop.time() >= next_audit_check:
                    await asyncio.to_thread(
                        control_plane.maintain_audit_verification, first_audit_check
                    )
                    first_audit_check = False
                    next_audit_check = loop.time() + 60
                await asyncio.sleep(15)
        task = asyncio.create_task(schedule_loop())
        try:
            yield
        finally:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
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
