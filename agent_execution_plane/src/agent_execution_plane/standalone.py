"""Thin authenticated standalone HTTP source boundary."""

from __future__ import annotations

import asyncio
import json
import secrets
from typing import Any
from urllib.parse import urlparse

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError
from starlette.requests import Request
from starlette.responses import JSONResponse

from agent_execution_plane.database import record_activity
from agent_execution_plane.execution import Capability, ExecutionEngine, ExecutionFailure, ExecutionOutcome, ExecutionRequest
from agent_execution_plane.lifecycle import LifecycleBusy, LifecycleStore

MAX_BODY_BYTES = 4 * 1024 * 1024


async def bounded_json(request: Request, limit: int = MAX_BODY_BYTES) -> Any:
    body = bytearray()
    async for chunk in request.stream():
        body.extend(chunk)
        if len(body) > limit: raise OverflowError
    try: value = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError): raise ValueError("malformed_json") from None
    return value


def execution_request(data: dict[str, Any], execution_id: str) -> ExecutionRequest:
    if set(data) - {"objective", "input", "mcp", "result_schema"} or "input" not in data: raise ValueError("invalid_execution_contract")
    objective = data.get("objective"); mcp = data.get("mcp")
    if not isinstance(objective, str) or not objective.strip() or not isinstance(mcp, dict) or set(mcp) - {"url", "bearer_token", "certificate_sha256", "tools"}: raise ValueError("invalid_execution_contract")
    url = mcp.get("url"); parsed = urlparse(url) if isinstance(url, str) else None
    if not parsed or parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.username or parsed.password: raise ValueError("invalid_execution_contract")
    bearer = mcp.get("bearer_token")
    if bearer is not None and not isinstance(bearer, str): raise ValueError("invalid_execution_contract")
    from agent_execution_plane.pinned_http import normalize_certificate_sha256
    fingerprint=normalize_certificate_sha256(mcp.get("certificate_sha256"))
    if fingerprint and parsed.scheme != "https": raise ValueError("invalid_execution_contract")
    tools = mcp.get("tools")
    if not isinstance(tools, list): raise ValueError("invalid_execution_contract")
    capabilities=[]
    for item in tools:
        if not isinstance(item, dict) or set(item) != {"name", "description", "input_schema"}: raise ValueError("invalid_execution_contract")
        if not isinstance(item["name"], str) or not item["name"] or not isinstance(item["description"], str) or not isinstance(item["input_schema"], dict): raise ValueError("invalid_execution_contract")
        capabilities.append(Capability(item["name"], item["description"], item["input_schema"]))
    result_schema = data.get("result_schema")
    if result_schema is not None and not isinstance(result_schema, dict): raise ValueError("invalid_execution_contract")
    request = ExecutionRequest(execution_id, execution_id, objective, data["input"], url, bearer, tuple(capabilities), result_schema, None, fingerprint)
    try: ExecutionEngine.validate_request(request)
    except ExecutionFailure as exc: raise ValueError(exc.code) from None
    return request


class StandaloneBoundary:
    def __init__(self, lifecycle: LifecycleStore, engine: Any, database):
        self.lifecycle=lifecycle; self.engine=engine; self.database=database; self.tasks:set[asyncio.Task]=set()

    def _peer(self, request: Request) -> str | None: return request.client.host if request.client else None

    def _authenticate(self, request: Request) -> JSONResponse | None:
        header=request.headers.get("authorization", ""); token=header[7:] if header.startswith("Bearer ") else ""
        status=self.lifecycle.authenticate(token)
        if status == "accepted": return None
        record_activity(self.database, "standalone_auth_rejected", "security", "failure", self._peer(request))
        code="credential_not_configured" if status == "not_configured" else "unauthenticated"
        return JSONResponse({"error":{"code":code}}, status_code=503 if status == "not_configured" else 401, headers={"WWW-Authenticate":"Bearer"})

    async def submit(self, request: Request) -> JSONResponse:
        if failure := self._authenticate(request): return failure
        try: data=await bounded_json(request)
        except OverflowError: return JSONResponse({"error":{"code":"body_too_large"}},status_code=413)
        except ValueError as exc: return JSONResponse({"error":{"code":str(exc)}},status_code=400)
        if not isinstance(data, dict): return JSONResponse({"error":{"code":"invalid_execution_contract"}},status_code=422)
        execution_id=secrets.token_urlsafe(24)
        try: execution=execution_request(data,execution_id)
        except ValueError as exc: return JSONResponse({"error":{"code":"invalid_execution_contract","detail":str(exc)}},status_code=422)
        try: self.lifecycle.reserve(execution_id)
        except LifecycleBusy as exc:
            record_activity(self.database,"execution_refused_busy","execution","failure",self._peer(request))
            return JSONResponse({"error":{"code":str(exc)}},status_code=409)
        record_activity(self.database,"execution_accepted","execution","success",self._peer(request))
        task=asyncio.create_task(self._run(execution));self.tasks.add(task);task.add_done_callback(self.tasks.discard)
        return JSONResponse({"execution_id":execution_id,"status":"accepted"},status_code=202)

    async def _run(self, request: ExecutionRequest) -> None:
        try:
            outcome=await self.engine.execute(request)
            self.lifecycle.complete(request.execution_id,outcome)
            record_activity(self.database,"result_available","execution","success" if outcome.success else "failure")
        except asyncio.CancelledError: raise
        except Exception:
            try: self.lifecycle.complete(request.execution_id, ExecutionOutcome(False,error_code="internal_failure"))
            except Exception: pass
            record_activity(self.database,"result_available","execution","failure")

    async def get(self, request: Request) -> JSONResponse:
        if failure := self._authenticate(request): return failure
        state,payload=self.lifecycle.execution(request.path_params["execution_id"])
        if state=="not_found": return JSONResponse({"error":{"code":"execution_not_found"}},status_code=404)
        if state=="result_available": record_activity(self.database,"result_retrieved","execution","success",self._peer(request))
        return JSONResponse(payload)

    async def ack(self, request: Request) -> JSONResponse:
        if failure := self._authenticate(request): return failure
        execution_id=request.path_params["execution_id"]; status=self.lifecycle.ack(execution_id)
        if status=="result_not_available": return JSONResponse({"error":{"code":status}},status_code=409)
        if status=="not_found": return JSONResponse({"error":{"code":"execution_not_found"}},status_code=404)
        record_activity(self.database,"result_acknowledged","execution","success",self._peer(request))
        return JSONResponse({"execution_id":execution_id,"status":"acknowledged"})
