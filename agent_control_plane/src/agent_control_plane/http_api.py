"""HTTP adapters for the control-plane application services."""

from __future__ import annotations

import hmac
import logging
import sqlite3
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse, Response

from agent_control_plane.contracts import (
    ConnectorCreateRequest,
    ConnectorUpdateRequest,
    ConnectorSecretRotationRequest,
    ConnectorEnabledRequest,
    ConnectorArchivedRequest,
    ConnectorIdRequest,
    EventCreateRequest,
    EventMappingCreateRequest,
    EventMappingEnabledRequest,
    EventMappingIdRequest,
    EventMappingUpdateRequest,
    IdentityCreateRequest,
    IdentityArchiveRequest,
    IdentityRevokeRequest,
    JobCancelRequest,
    TaskCreateRequest,
    TaskEnabledRequest,
    TaskArchivedRequest,
    TaskIdRequest,
    TaskRunRequest,
    ScheduleCreateRequest,
    ScheduleEnabledRequest,
    ScheduleIdRequest,
    ScheduleUpdateRequest,
    RetentionPolicyRequest,
    RetentionRunRequest,
)
from agent_control_plane.connectors import (
    SCHEMA_REJECTION_CODES,
    ConnectorCertificateMismatch,
    ConnectorSchemaRejected,
    discover_streamable_http,
    validate_streamable_http_url,
)
from agent_control_plane.control_plane import (
    AuthenticatedIdentity,
    AuthenticationError,
    AuthorizationError,
    ControlPlane,
    QueueFullError,
    RateLimitExceeded,
    TaskExecutionActiveError,
    canonical_json,
)
from agent_control_plane.security import token_credential_id


MAX_BODY_BYTES = 32 * 1024
LOGGER = logging.getLogger("agent_control_plane.connectors")


def log_schema_rejection(
    connector: str, error: ConnectorSchemaRejected, correlation_id: str
) -> None:
    LOGGER.warning(
        "MCP connector schema rejected connector=%r tool=%r error=%s correlation_id=%r",
        connector,
        error.tool_name or "-",
        error.code,
        correlation_id,
    )


def error_response(status: int, code: str, correlation_id: str) -> JSONResponse:
    return JSONResponse(
        {"error": {"code": code}, "correlation_id": correlation_id},
        status_code=status,
    )


async def json_contract(request: Request, model_type):
    if request.headers.get("content-type", "").split(";", 1)[0].strip() != "application/json":
        raise ValueError("unsupported_media_type")
    body = await request.body()
    if len(body) > MAX_BODY_BYTES:
        raise OverflowError("body_too_large")
    return model_type.model_validate_json(body)


def bearer_token(request: Request) -> str:
    authorization = request.headers.get("authorization", "")
    scheme, separator, token = authorization.partition(" ")
    if not separator or scheme.lower() != "bearer" or not token:
        raise AuthenticationError("missing_credential")
    return token


def csrf_valid(request: Request) -> bool:
    cookie = request.cookies.get("acp_csrf", "")
    header = request.headers.get("x-csrf-token", "")
    return bool(cookie and header and hmac.compare_digest(cookie, header))


async def audit_denial(
    request: Request,
    action: str,
    reason_code: str,
    identity: AuthenticatedIdentity | None = None,
    token: str = "",
    metadata: object | None = None,
) -> None:
    await run_in_threadpool(
        request.app.state.control_plane.record_audit,
        actor_identity_id=identity.identity_id if identity else None,
        credential_id=identity.credential_id if identity else token_credential_id(token),
        action=action,
        decision="denied",
        reason_code=reason_code,
        correlation_id=request.state.correlation_id,
        metadata=metadata if metadata is not None else {"path": request.url.path},
    )


async def admin_status(request: Request) -> JSONResponse:
    counts = await run_in_threadpool(request.app.state.control_plane.status_counts)
    connectors = await run_in_threadpool(request.app.state.control_plane.list_connectors)
    tasks = await run_in_threadpool(request.app.state.control_plane.list_tasks)
    mappings = await run_in_threadpool(request.app.state.control_plane.list_event_mappings)
    schedules = await run_in_threadpool(request.app.state.control_plane.list_schedules)
    audit = await run_in_threadpool(request.app.state.control_plane.audit_status)
    active_connectors = [item for item in connectors if not item["archived_at"]]
    active_tasks = [item for item in tasks if not item["archived_at"]]
    public_listener_status = request.app.state.public_listener_status()
    return JSONResponse(
        {
            "status": public_listener_status,
            "surface": "admin",
            **counts,
            "connectors": {
                "total": len(active_connectors),
                "ready": sum(item["status"] == "ready" for item in active_connectors),
                "unavailable": sum(item["enabled"] and item["status"] != "ready" for item in active_connectors),
                "disabled": sum(not item["enabled"] for item in active_connectors),
                "archived": sum(bool(item["archived_at"]) for item in connectors),
            },
            "tasks": {
                "total": len(active_tasks),
                "ready": sum(item["status"] == "ready" for item in active_tasks),
                "unavailable": sum(item["enabled"] and item["status"] != "ready" for item in active_tasks),
                "disabled": sum(not item["enabled"] for item in active_tasks),
                "archived": sum(bool(item["archived_at"]) for item in tasks),
            },
            "triggers": {
                "total": len(mappings),
                "active": sum(item["status"] == "active" for item in mappings),
                "suspended": sum(item["status"] == "suspended" for item in mappings),
                "disabled": sum(item["status"] == "paused" for item in mappings),
            },
            "schedules": {
                "total": len(schedules),
                "active": sum(item["status"] == "active" for item in schedules),
                "suspended": sum(item["status"] == "suspended" for item in schedules),
                "disabled": sum(item["status"] == "paused" for item in schedules),
            },
            "audit": audit,
        }
    )


async def admin_list_identities(request: Request) -> JSONResponse:
    identities = await run_in_threadpool(request.app.state.control_plane.list_identities)
    return JSONResponse({"identities": identities})


async def admin_list_connectors(request: Request) -> JSONResponse:
    connectors = await run_in_threadpool(request.app.state.control_plane.list_connectors)
    return JSONResponse({"connectors": connectors, "count": len(connectors)})


async def admin_list_tasks(request: Request) -> JSONResponse:
    tasks = await run_in_threadpool(request.app.state.control_plane.list_tasks)
    return JSONResponse({"tasks": tasks, "count": len(tasks)})


async def admin_create_task(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "tasks.create", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, TaskCreateRequest)
        task_id = await run_in_threadpool(
            request.app.state.control_plane.create_task,
            contract.display_name,
            contract.name,
            contract.objective,
            contract.max_attempts,
            [item.model_dump() for item in contract.tools],
            correlation_id,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        return error_response(422, "invalid_task", correlation_id)
    except sqlite3.IntegrityError:
        return error_response(409, "task_name_exists", correlation_id)
    return JSONResponse({"task_id": task_id, "status": "ready"}, status_code=201)


async def admin_set_task_enabled(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "tasks.configure", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, TaskEnabledRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_task_request", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.set_task_enabled, contract.task_id, contract.enabled, correlation_id)
    if not found:
        return error_response(404, "task_not_found", correlation_id)
    return JSONResponse({"task_id": contract.task_id, "status": "ready" if contract.enabled else "disabled"})


async def admin_set_task_archived(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "tasks.configure", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, TaskArchivedRequest)
        found = await run_in_threadpool(
            request.app.state.control_plane.set_task_archived,
            contract.task_id,
            contract.archived,
            correlation_id,
        )
    except ValueError as error:
        if str(error) == "task_execution_active":
            return error_response(409, "task_execution_active", correlation_id)
        return error_response(422, "invalid_task_request", correlation_id)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_task_request", correlation_id)
    if not found:
        return error_response(404, "task_not_found", correlation_id)
    return JSONResponse({"task_id": contract.task_id, "status": "archived" if contract.archived else "disabled"})


async def admin_delete_task(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "tasks.delete", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, TaskIdRequest)
        result = await run_in_threadpool(request.app.state.control_plane.delete_task, contract.task_id, correlation_id)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_task_request", correlation_id)
    if result == "not_found":
        return error_response(404, "task_not_found", correlation_id)
    if result == "in_use":
        return error_response(409, "task_in_use", correlation_id)
    return JSONResponse({"task_id": contract.task_id, "status": "deleted"})


async def admin_run_task(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "jobs.create", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, TaskRunRequest)
        job_id = await run_in_threadpool(
            request.app.state.control_plane.enqueue_manual_task,
            contract.task_id,
            contract.input,
            correlation_id,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        return error_response(422, "task_not_ready", correlation_id)
    except QueueFullError:
        return error_response(503, "queue_full", correlation_id)
    except TaskExecutionActiveError:
        return error_response(409, "task_execution_active", correlation_id)
    return JSONResponse({"job_id": job_id, "status": "queued"}, status_code=201)


async def admin_list_schedules(request: Request) -> JSONResponse:
    schedules = await run_in_threadpool(request.app.state.control_plane.list_schedules)
    return JSONResponse({"schedules": schedules, "count": len(schedules)})


async def admin_create_schedule(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ScheduleCreateRequest)
        schedule_id = await run_in_threadpool(request.app.state.control_plane.create_schedule, contract.display_name, contract.task_id, contract.schedule_kind, contract.interval_minutes, contract.time_of_day, contract.weekday, contract.timezone, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_schedule", correlation_id)
    return JSONResponse({"schedule_id": schedule_id, "status": "active"}, status_code=201)


async def admin_update_schedule(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ScheduleUpdateRequest)
        found = await run_in_threadpool(request.app.state.control_plane.update_schedule, contract.schedule_id, contract.display_name, contract.task_id, contract.schedule_kind, contract.interval_minutes, contract.time_of_day, contract.weekday, contract.timezone, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_schedule", correlation_id)
    return JSONResponse({"schedule_id": contract.schedule_id, "status": "updated"}) if found else error_response(404, "schedule_not_found", correlation_id)


async def admin_set_schedule_enabled(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ScheduleEnabledRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_schedule", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.set_schedule_enabled, contract.schedule_id, contract.enabled, correlation_id)
    return JSONResponse({"schedule_id": contract.schedule_id, "status": "active" if contract.enabled else "paused"}) if found else error_response(404, "schedule_not_found", correlation_id)


async def admin_delete_schedule(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ScheduleIdRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_schedule", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.delete_schedule, contract.schedule_id, correlation_id)
    return JSONResponse({"schedule_id": contract.schedule_id, "status": "deleted"}) if found else error_response(404, "schedule_not_found", correlation_id)


async def admin_list_event_mappings(request: Request) -> JSONResponse:
    mappings = await run_in_threadpool(request.app.state.control_plane.list_event_mappings)
    return JSONResponse({"event_mappings": mappings, "count": len(mappings)})


async def admin_create_event_mapping(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, EventMappingCreateRequest)
        mapping_id = await run_in_threadpool(request.app.state.control_plane.create_event_mapping, contract.display_name, contract.source_identity_id, contract.event_type, contract.task_id, contract.cooldown_minutes, contract.grace_minutes, contract.recovery_event_type, contract.input_mode, contract.correlation_mode, correlation_id)
    except sqlite3.IntegrityError:
        return error_response(409, "event_mapping_exists", correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_event_mapping", correlation_id)
    return JSONResponse({"mapping_id": mapping_id, "status": "active"}, status_code=201)


async def admin_update_event_mapping(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, EventMappingUpdateRequest)
        found = await run_in_threadpool(request.app.state.control_plane.update_event_mapping, contract.mapping_id, contract.display_name, contract.source_identity_id, contract.event_type, contract.task_id, contract.cooldown_minutes, contract.grace_minutes, contract.recovery_event_type, contract.input_mode, contract.correlation_mode, correlation_id)
    except sqlite3.IntegrityError:
        return error_response(409, "event_mapping_exists", correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_event_mapping", correlation_id)
    return JSONResponse({"mapping_id": contract.mapping_id, "status": "updated"}) if found else error_response(404, "event_mapping_not_found", correlation_id)


async def admin_set_event_mapping_enabled(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, EventMappingEnabledRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_event_mapping", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.set_event_mapping_enabled, contract.mapping_id, contract.enabled, correlation_id)
    return JSONResponse({"mapping_id": contract.mapping_id, "status": "active" if contract.enabled else "paused"}) if found else error_response(404, "event_mapping_not_found", correlation_id)


async def admin_retry_event_incident(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, EventMappingIdRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_event_mapping", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.retry_event_incident, contract.mapping_id, correlation_id)
    return JSONResponse({"mapping_id": contract.mapping_id, "status": "pending"}) if found else error_response(409, "incident_not_blocked", correlation_id)


async def admin_delete_event_mapping(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, EventMappingIdRequest)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_event_mapping", correlation_id)
    found = await run_in_threadpool(request.app.state.control_plane.delete_event_mapping, contract.mapping_id, correlation_id)
    return JSONResponse({"mapping_id": contract.mapping_id, "status": "deleted"}) if found else error_response(404, "event_mapping_not_found", correlation_id)


async def admin_create_connector(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "connectors.create", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorCreateRequest)
        url = validate_streamable_http_url(contract.url)
        tools = await discover_streamable_http(url, contract.bearer_token, contract.certificate_sha256)
        connector_id = await run_in_threadpool(
            request.app.state.control_plane.create_connector,
            contract.display_name,
            url,
            contract.bearer_token,
            tools,
            correlation_id,
            contract.certificate_sha256,
        )
    except ConnectorCertificateMismatch as error:
        return error_response(422, error.code, correlation_id)
    except ConnectorSchemaRejected as error:
        log_schema_rejection(contract.display_name, error, correlation_id)
        return error_response(422, error.code, correlation_id)
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        return error_response(422, "invalid_connector", correlation_id)
    except Exception:
        return error_response(503, "connector_unreachable", correlation_id)
    return JSONResponse({"connector_id": connector_id, "status": "ready", "tool_count": len(tools)}, status_code=201)


async def admin_list_connector_tools(request: Request) -> JSONResponse:
    connector_id = request.query_params.get("connector_id", "")
    connectors = await run_in_threadpool(request.app.state.control_plane.list_connectors)
    if not any(item["id"] == connector_id for item in connectors):
        return error_response(404, "connector_not_found", request.state.correlation_id)
    tools = await run_in_threadpool(request.app.state.control_plane.list_connector_tools, connector_id)
    return JSONResponse({"tools": tools, "count": len(tools)})


async def admin_check_connector(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorIdRequest)
        config = await run_in_threadpool(request.app.state.control_plane.connector_transport_config, contract.connector_id)
        if config is None:
            return error_response(404, "connector_not_found", correlation_id)
        try:
            tools = await discover_streamable_http(*config)
        except ConnectorCertificateMismatch as error:
            await run_in_threadpool(
                request.app.state.control_plane.refresh_connector,
                contract.connector_id,
                None,
                error.code,
                correlation_id,
            )
            return error_response(422, error.code, correlation_id)
        except ConnectorSchemaRejected as error:
            log_schema_rejection(contract.connector_id, error, correlation_id)
            await run_in_threadpool(
                request.app.state.control_plane.refresh_connector,
                contract.connector_id,
                None,
                error.code,
                correlation_id,
            )
            return error_response(422, error.code, correlation_id)
        except Exception:
            await run_in_threadpool(request.app.state.control_plane.refresh_connector, contract.connector_id, None, "connection_failed", correlation_id)
            return error_response(503, "connector_unreachable", correlation_id)
        await run_in_threadpool(request.app.state.control_plane.refresh_connector, contract.connector_id, tools, None, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_request", correlation_id)
    return JSONResponse({"connector_id": contract.connector_id, "status": "ready", "tool_count": len(tools)})


async def admin_update_connector(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorUpdateRequest)
        config = await run_in_threadpool(
            request.app.state.control_plane.connector_change_transport_config,
            contract.connector_id,
        )
        if config is None:
            return error_response(404, "connector_not_found", correlation_id)
        current_url, bearer_token, current_fingerprint, expected_protected_config = config
        target_url = validate_streamable_http_url(contract.url) if contract.url else current_url
        target_fingerprint = current_fingerprint if contract.certificate_sha256 is None else contract.certificate_sha256
        endpoint_changed = target_url != current_url or target_fingerprint != current_fingerprint
        tools = None
        discovery_error = None
        if endpoint_changed:
            if await run_in_threadpool(
                request.app.state.control_plane.connector_has_active_jobs,
                contract.connector_id,
            ):
                await audit_denial(
                    request,
                    "connectors.update",
                    "connector_execution_active",
                    metadata={"connector_id": contract.connector_id},
                )
                return error_response(409, "connector_execution_active", correlation_id)
            try:
                tools = await discover_streamable_http(target_url, bearer_token, target_fingerprint)
            except ConnectorCertificateMismatch as error:
                return error_response(422, error.code, correlation_id)
            except ConnectorSchemaRejected as error:
                discovery_error = error.code
                log_schema_rejection(contract.connector_id, error, correlation_id)
            except Exception:
                discovery_error = "connection_failed"
        found = await run_in_threadpool(
            request.app.state.control_plane.update_connector,
            contract.connector_id,
            contract.display_name,
            target_url,
            bearer_token,
            expected_protected_config,
            endpoint_changed,
            tools,
            discovery_error,
            correlation_id,
            target_fingerprint,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except sqlite3.IntegrityError:
        return error_response(409, "connector_name_conflict", correlation_id)
    except ValueError as error:
        code = str(error)
        if code == "connector_execution_active":
            await audit_denial(
                request,
                "connectors.update",
                code,
                metadata={"connector_id": contract.connector_id},
            )
        if code in {"connector_archived", "connector_execution_active", "connector_changed"}:
            return error_response(409, code, correlation_id)
        return error_response(422, "invalid_connector", correlation_id)
    except ValidationError:
        return error_response(422, "invalid_connector", correlation_id)
    if not found:
        return error_response(404, "connector_not_found", correlation_id)
    if discovery_error in SCHEMA_REJECTION_CODES:
        return error_response(422, discovery_error, correlation_id)
    if discovery_error:
        return error_response(503, "connector_unreachable", correlation_id)
    connector = next(
        item
        for item in await run_in_threadpool(request.app.state.control_plane.list_connectors)
        if item["id"] == contract.connector_id
    )
    return JSONResponse(
        {
            "connector_id": contract.connector_id,
            "status": connector["status"],
            "tool_count": connector["tool_count"],
        }
    )


async def admin_rotate_connector_secret(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorSecretRotationRequest)
        config = await run_in_threadpool(
            request.app.state.control_plane.connector_change_transport_config,
            contract.connector_id,
        )
        if config is None:
            return error_response(404, "connector_not_found", correlation_id)
        url, _, certificate_sha256, expected_protected_config = config
        if await run_in_threadpool(
            request.app.state.control_plane.connector_has_active_jobs,
            contract.connector_id,
        ):
            await audit_denial(
                request,
                "connectors.secret_rotate",
                "connector_execution_active",
                metadata={"connector_id": contract.connector_id},
            )
            return error_response(409, "connector_execution_active", correlation_id)
        tools = None
        discovery_error = None
        try:
            tools = await discover_streamable_http(url, contract.bearer_token, certificate_sha256)
        except ConnectorCertificateMismatch as error:
            discovery_error = error.code
        except ConnectorSchemaRejected as error:
            discovery_error = error.code
            log_schema_rejection(contract.connector_id, error, correlation_id)
        except Exception:
            discovery_error = "connection_failed"
        found = await run_in_threadpool(
            request.app.state.control_plane.rotate_connector_secret,
            contract.connector_id,
            url,
            contract.bearer_token,
            expected_protected_config,
            tools,
            discovery_error,
            correlation_id,
            certificate_sha256,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except ValueError as error:
        code = str(error)
        if code == "connector_execution_active":
            await audit_denial(
                request,
                "connectors.secret_rotate",
                code,
                metadata={"connector_id": contract.connector_id},
            )
        if code in {"connector_archived", "connector_execution_active", "connector_changed"}:
            return error_response(409, code, correlation_id)
        return error_response(422, "invalid_connector_secret", correlation_id)
    except ValidationError:
        return error_response(422, "invalid_connector_secret", correlation_id)
    if not found:
        return error_response(404, "connector_not_found", correlation_id)
    if discovery_error in SCHEMA_REJECTION_CODES:
        return error_response(422, discovery_error, correlation_id)
    if discovery_error == "certificate_sha256_mismatch":
        return error_response(422, discovery_error, correlation_id)
    if discovery_error:
        return error_response(503, "connector_unreachable", correlation_id)
    connector = next(
        item
        for item in await run_in_threadpool(request.app.state.control_plane.list_connectors)
        if item["id"] == contract.connector_id
    )
    return JSONResponse(
        {
            "connector_id": contract.connector_id,
            "status": connector["status"],
            "tool_count": connector["tool_count"],
            "has_secret": connector["has_secret"],
        }
    )


async def admin_set_connector_enabled(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorEnabledRequest)
        tools = None
        if contract.enabled:
            config = await run_in_threadpool(request.app.state.control_plane.connector_transport_config, contract.connector_id)
            if config is None:
                return error_response(404, "connector_not_found", correlation_id)
            try:
                tools = await discover_streamable_http(*config)
            except ConnectorCertificateMismatch as error:
                await run_in_threadpool(
                    request.app.state.control_plane.refresh_connector,
                    contract.connector_id,
                    None,
                    error.code,
                    correlation_id,
                )
                return error_response(422, error.code, correlation_id)
            except ConnectorSchemaRejected as error:
                log_schema_rejection(contract.connector_id, error, correlation_id)
                await run_in_threadpool(
                    request.app.state.control_plane.refresh_connector,
                    contract.connector_id,
                    None,
                    error.code,
                    correlation_id,
                )
                return error_response(422, error.code, correlation_id)
            except Exception:
                await run_in_threadpool(
                    request.app.state.control_plane.refresh_connector,
                    contract.connector_id,
                    None,
                    "connection_failed",
                    correlation_id,
                )
                return error_response(503, "connector_unreachable", correlation_id)
        found = await run_in_threadpool(request.app.state.control_plane.set_connector_enabled, contract.connector_id, contract.enabled, correlation_id)
        if found and tools is not None:
            await run_in_threadpool(request.app.state.control_plane.refresh_connector, contract.connector_id, tools, None, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_request", correlation_id)
    if not found:
        return error_response(404, "connector_not_found", correlation_id)
    return JSONResponse({"connector_id": contract.connector_id, "status": "ready" if contract.enabled else "disabled"})


async def admin_set_connector_archived(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorArchivedRequest)
        found = await run_in_threadpool(
            request.app.state.control_plane.set_connector_archived,
            contract.connector_id,
            contract.archived,
            correlation_id,
        )
    except ValueError as error:
        if str(error) == "connector_execution_active":
            return error_response(409, "connector_execution_active", correlation_id)
        return error_response(422, "invalid_request", correlation_id)
    except (OverflowError, ValidationError):
        return error_response(422, "invalid_request", correlation_id)
    if not found:
        return error_response(404, "connector_not_found", correlation_id)
    return JSONResponse({"connector_id": contract.connector_id, "status": "archived" if contract.archived else "disabled"})


async def admin_delete_connector(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, ConnectorIdRequest)
        result = await run_in_threadpool(request.app.state.control_plane.delete_connector, contract.connector_id, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_request", correlation_id)
    if result == "not_found":
        return error_response(404, "connector_not_found", correlation_id)
    if result == "in_use":
        return error_response(409, "connector_in_use", correlation_id)
    return JSONResponse({"connector_id": contract.connector_id, "deleted": True})


async def admin_list_events(request: Request) -> JSONResponse:
    events = await run_in_threadpool(request.app.state.control_plane.list_events)
    return JSONResponse({"events": events, "limit": 100})


async def admin_list_jobs(request: Request) -> JSONResponse:
    jobs = await run_in_threadpool(request.app.state.control_plane.list_jobs)
    return JSONResponse({"jobs": jobs, "limit": 100})


async def admin_cancel_job(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "jobs.cancel", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, JobCancelRequest)
        result = await run_in_threadpool(
            request.app.state.control_plane.cancel_job,
            contract.job_id,
            correlation_id,
        )
    except OverflowError:
        await audit_denial(request, "jobs.cancel", "body_too_large")
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        await audit_denial(request, "jobs.cancel", "invalid_request")
        return error_response(422, "invalid_request", correlation_id)
    if result == "not_found":
        await audit_denial(request, "jobs.cancel", "job_not_found")
        return error_response(404, "job_not_found", correlation_id)
    if result == "not_cancellable":
        await audit_denial(request, "jobs.cancel", "job_not_cancellable")
        return error_response(409, "job_not_cancellable", correlation_id)
    return JSONResponse({"job_id": contract.job_id, "state": "cancelled"})


async def admin_requeue_job(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "jobs.requeue", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, JobCancelRequest)
        result, new_job_id = await run_in_threadpool(
            request.app.state.control_plane.requeue_dead_letter,
            contract.job_id,
            correlation_id,
        )
    except OverflowError:
        await audit_denial(request, "jobs.requeue", "body_too_large")
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        await audit_denial(request, "jobs.requeue", "invalid_request")
        return error_response(422, "invalid_request", correlation_id)
    errors = {
        "not_found": (404, "job_not_found"),
        "not_requeueable": (409, "job_not_requeueable"),
        "task_unavailable": (409, "task_unavailable"),
        "task_execution_active": (409, "task_execution_active"),
        "queue_full": (503, "queue_full"),
    }
    if result in errors:
        status, code = errors[result]
        await audit_denial(request, "jobs.requeue", code)
        return error_response(status, code, correlation_id)
    return JSONResponse({"source_job_id": contract.job_id, "job_id": new_job_id, "state": "queued"}, status_code=201)


async def admin_list_reports(request: Request) -> JSONResponse:
    reports = await run_in_threadpool(request.app.state.control_plane.list_reports)
    return JSONResponse({"reports": reports, "limit": 100})


async def admin_list_audit(request: Request) -> JSONResponse:
    entries = await run_in_threadpool(
        request.app.state.control_plane.list_audit_entries, 200
    )
    return JSONResponse({"audit_entries": entries, "limit": 200})


async def admin_list_activity(request: Request) -> JSONResponse:
    entries = await run_in_threadpool(
        request.app.state.control_plane.list_audit_entries, 100
    )
    activity = [
        {
            "occurred_at": entry["occurred_at"],
            "event_code": entry["action"],
            "category": "system"
            if str(entry["action"]).startswith("app_")
            else (entry["target_type"] or "security"),
            "status": "success"
            if str(entry["action"]).startswith("app_")
            else entry["decision"],
            "source": entry["actor_name"] or "system",
        }
        for entry in entries
    ]
    return JSONResponse({"entries": activity, "limit": 100})


async def admin_export_audit(request: Request) -> Response:
    entries = await run_in_threadpool(
        request.app.state.control_plane.list_audit_entries, 10_000
    )
    body = "".join(
        canonical_json({"schema_version": 1, "audit_entry": entry}) + "\n"
        for entry in reversed(entries)
    )
    return Response(
        body,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": 'attachment; filename="agent-control-plane-audit-v1.jsonl"'},
    )


async def admin_retention_status(request: Request) -> JSONResponse:
    status = await run_in_threadpool(request.app.state.control_plane.retention_status)
    return JSONResponse(status)


async def admin_verify_audit(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    await run_in_threadpool(
        request.app.state.control_plane.record_audit,
        actor_identity_id=None,
        credential_id=None,
        action="audit.verify",
        decision="allowed",
        reason_code="ingress_admin",
        correlation_id=correlation_id,
    )
    status = await run_in_threadpool(
        request.app.state.control_plane.maintain_audit_verification, True
    )
    return JSONResponse({"audit": status})


async def admin_update_retention(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, RetentionPolicyRequest)
        await run_in_threadpool(request.app.state.control_plane.set_retention_policy, contract.retention_days, contract.batch_size, contract.automatic, correlation_id)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_retention_policy", correlation_id)
    return JSONResponse(await run_in_threadpool(request.app.state.control_plane.retention_status))


async def admin_run_retention(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        return error_response(403, "csrf_failed", correlation_id)
    try:
        await json_contract(request, RetentionRunRequest)
        deleted = await run_in_threadpool(request.app.state.control_plane.run_retention, correlation_id, False)
    except (OverflowError, ValueError, ValidationError):
        return error_response(422, "invalid_retention_request", correlation_id)
    return JSONResponse({"deleted": deleted})


async def authenticated_collection(
    request: Request, action: str, loader_name: str, response_key: str
) -> JSONResponse:
    correlation_id = request.state.correlation_id
    token = ""
    identity = None
    try:
        token = bearer_token(request)
        identity = await run_in_threadpool(request.app.state.control_plane.authenticate, token)
        request.app.state.control_plane.authorize(identity, action)
        items = await run_in_threadpool(
            getattr(request.app.state.control_plane, loader_name)
        )
    except AuthenticationError as exc:
        await audit_denial(request, action, str(exc), token=token)
        return error_response(401, str(exc), correlation_id)
    except AuthorizationError as exc:
        await audit_denial(request, action, exc.reason_code, identity)
        return error_response(403, exc.reason_code, correlation_id)
    return JSONResponse({response_key: items, "limit": 100})


async def list_events(request: Request) -> JSONResponse:
    return await authenticated_collection(request, "events.read", "list_events", "events")


async def list_jobs(request: Request) -> JSONResponse:
    return await authenticated_collection(request, "jobs.read", "list_jobs", "jobs")


async def list_reports(request: Request) -> JSONResponse:
    return await authenticated_collection(request, "reports.read", "list_reports", "reports")


async def admin_create_identity(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "identities.create", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, IdentityCreateRequest)
        created = await run_in_threadpool(
            request.app.state.control_plane.create_identity,
            contract.display_name,
            contract.identity_type,
            contract.actions,
            correlation_id,
        )
    except OverflowError:
        await audit_denial(request, "identities.create", "body_too_large")
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        await audit_denial(request, "identities.create", "invalid_request")
        return error_response(422, "invalid_request", correlation_id)
    return JSONResponse(
        {
            "identity_id": created.identity_id,
            "policy_revision_id": created.policy_revision_id,
            "credential": created.credential.token,
            "credential_id": created.credential.credential_id,
            "credential_shown_once": True,
        },
        status_code=201,
    )


async def admin_revoke_identity(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "identities.revoke", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, IdentityRevokeRequest)
        found = await run_in_threadpool(
            request.app.state.control_plane.revoke_identity,
            contract.identity_id,
            correlation_id,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except (ValueError, ValidationError):
        return error_response(422, "invalid_request", correlation_id)
    if not found:
        return error_response(404, "identity_not_found", correlation_id)
    return JSONResponse({"identity_id": contract.identity_id, "status": "revoked"})


async def admin_archive_identity(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    if not csrf_valid(request):
        await audit_denial(request, "identities.archive", "csrf_failed")
        return error_response(403, "csrf_failed", correlation_id)
    try:
        contract = await json_contract(request, IdentityArchiveRequest)
        found = await run_in_threadpool(
            request.app.state.control_plane.archive_identity,
            contract.identity_id,
            correlation_id,
        )
    except OverflowError:
        return error_response(413, "body_too_large", correlation_id)
    except ValidationError:
        return error_response(422, "invalid_request", correlation_id)
    except ValueError as exc:
        if str(exc) == "identity_not_revoked":
            return error_response(409, "identity_not_revoked", correlation_id)
        return error_response(422, "invalid_request", correlation_id)
    if not found:
        return error_response(404, "identity_not_found", correlation_id)
    return JSONResponse({"identity_id": contract.identity_id, "status": "archived"})


async def effective_permissions(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    token = ""
    identity = None
    try:
        token = bearer_token(request)
        identity = await run_in_threadpool(
            request.app.state.control_plane.authenticate, token
        )
        request.app.state.control_plane.authorize(identity, "permissions.effective.read")
    except AuthenticationError as exc:
        await audit_denial(request, "permissions.effective.read", str(exc), token=token)
        return error_response(401, str(exc), correlation_id)
    except AuthorizationError as exc:
        await audit_denial(request, "permissions.effective.read", exc.reason_code, identity)
        return error_response(403, exc.reason_code, correlation_id)
    return JSONResponse(
        {
            "identity": {
                "id": identity.identity_id,
                "type": identity.identity_type,
                "display_name": identity.display_name,
            },
            "policy_revision_id": identity.policy_revision_id,
            "control_plane_actions": list(identity.actions),
            "capabilities": [],
        }
    )


async def create_event(request: Request) -> JSONResponse:
    correlation_id = request.state.correlation_id
    token = ""
    identity = None
    try:
        token = bearer_token(request)
        identity = await run_in_threadpool(
            request.app.state.control_plane.authenticate, token
        )
        contract = await json_contract(request, EventCreateRequest)
        now = datetime.now(UTC)
        occurred_at = contract.occurred_at.astimezone(UTC)
        if occurred_at > now + timedelta(minutes=5) or occurred_at < now - timedelta(hours=24):
            raise ValueError("occurred_at_out_of_range")
        event = contract.model_dump(mode="json")
        event["occurred_at"] = occurred_at.isoformat().replace("+00:00", "Z")
        result = await run_in_threadpool(
            request.app.state.control_plane.ingest_event,
            identity,
            request.headers.get("idempotency-key", ""),
            event,
            correlation_id,
        )
    except AuthenticationError as exc:
        await audit_denial(request, "events.create", str(exc), token=token)
        return error_response(401, str(exc), correlation_id)
    except AuthorizationError as exc:
        await audit_denial(request, "events.create", exc.reason_code, identity)
        return error_response(403, exc.reason_code, correlation_id)
    except OverflowError:
        await audit_denial(request, "events.create", "body_too_large", identity)
        return error_response(413, "body_too_large", correlation_id)
    except QueueFullError:
        await audit_denial(request, "events.create", "queue_full", identity)
        return error_response(503, "queue_full", correlation_id)
    except RateLimitExceeded:
        await audit_denial(request, "events.create", "rate_limited", identity)
        response = error_response(429, "rate_limited", correlation_id)
        response.headers["Retry-After"] = "60"
        return response
    except (ValueError, ValidationError):
        await audit_denial(request, "events.create", "invalid_request", identity)
        return error_response(422, "invalid_request", correlation_id)
    return JSONResponse(
        {
            "event_id": result.event_id,
            "job_id": result.job_id,
            "duplicate": result.duplicate,
            "status": result.outcome,
        },
        status_code=200 if result.duplicate else 202,
    )
