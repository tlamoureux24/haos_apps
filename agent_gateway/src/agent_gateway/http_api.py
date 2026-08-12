"""HTTP adapters for the control-plane application services."""

from __future__ import annotations

import hmac
from datetime import UTC, datetime, timedelta

from pydantic import ValidationError
from starlette.concurrency import run_in_threadpool
from starlette.requests import Request
from starlette.responses import JSONResponse

from agent_gateway.contracts import EventCreateRequest, IdentityCreateRequest
from agent_gateway.control_plane import (
    AuthenticatedIdentity,
    AuthenticationError,
    AuthorizationError,
    ControlPlane,
    QueueFullError,
)
from agent_gateway.security import token_credential_id


MAX_BODY_BYTES = 32 * 1024


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
    cookie = request.cookies.get("agw_csrf", "")
    header = request.headers.get("x-csrf-token", "")
    return bool(cookie and header and hmac.compare_digest(cookie, header))


async def audit_denial(
    request: Request,
    action: str,
    reason_code: str,
    identity: AuthenticatedIdentity | None = None,
    token: str = "",
) -> None:
    await run_in_threadpool(
        request.app.state.control_plane.record_audit,
        actor_identity_id=identity.identity_id if identity else None,
        credential_id=identity.credential_id if identity else token_credential_id(token),
        action=action,
        decision="denied",
        reason_code=reason_code,
        correlation_id=request.state.correlation_id,
        metadata={"path": request.url.path},
    )


async def admin_status(request: Request) -> JSONResponse:
    return JSONResponse({"status": "ready", "surface": "admin"})


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
            "gateway_actions": list(identity.actions),
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
    except (ValueError, ValidationError):
        await audit_denial(request, "events.create", "invalid_request", identity)
        return error_response(422, "invalid_request", correlation_id)
    return JSONResponse(
        {
            "event_id": result.event_id,
            "job_id": result.job_id,
            "duplicate": result.duplicate,
            "status": "queued",
        },
        status_code=200 if result.duplicate else 202,
    )
