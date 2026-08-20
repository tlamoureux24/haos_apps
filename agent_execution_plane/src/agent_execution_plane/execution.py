"""Source-neutral single-slot execution engine and MCP operational tool loop."""

from __future__ import annotations

import asyncio
import json
import math
import time
from dataclasses import dataclass, field
from typing import Any, Awaitable, Callable, Protocol

from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError, ValidationError

MAX_DOCUMENT_BYTES = 4 * 1024 * 1024
MAX_CAPABILITIES = 128
MAX_DISPATCHES = 128
MAX_ARGUMENT_BYTES = 512 * 1024
MAX_TOOL_RESULT_BYTES = 2 * 1024 * 1024


def canonical(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), allow_nan=False)


class ExecutionFailure(RuntimeError):
    def __init__(self, code: str, *, mcp_effect_possible: bool = False):
        super().__init__(code); self.code = code; self.mcp_effect_possible = mcp_effect_possible


class BusyError(RuntimeError): pass


@dataclass(frozen=True)
class Capability:
    name: str
    description: str
    input_schema: dict[str, Any]


@dataclass(frozen=True)
class ExecutionRequest:
    execution_id: str
    source_reference: str
    objective: str
    input: Any
    mcp_url: str
    mcp_bearer_token: str | None
    capabilities: tuple[Capability, ...] = ()
    result_schema: dict[str, Any] | None = None


@dataclass(frozen=True)
class ExecutionOutcome:
    success: bool
    result: Any = None
    error_code: str | None = None
    model_id: str | None = None
    mcp_effect_possible: bool = False


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    arguments: Any


@dataclass(frozen=True)
class ToolResult:
    call_id: str
    source_name: str
    result: Any


@dataclass(frozen=True)
class ProviderReply:
    content: Any = None
    tool_calls: tuple[ToolCall, ...] = ()
    assistant_message: Any = None


class ProviderAdapter(Protocol):
    async def turn(self, messages: list[dict[str, Any]], tools: tuple[Capability, ...], result_schema: dict[str, Any] | None, remaining: float, dispatch: Callable[[ToolCall], Awaitable[Any]]) -> ProviderReply: ...


class McpSession(Protocol):
    async def list_tools(self, cursor: str | None = None) -> tuple[list[Capability], str | None]: ...
    async def call_tool(self, name: str, arguments: dict[str, Any]) -> Any: ...
    async def changed(self) -> bool: ...


class McpSessionContext(Protocol):
    async def __aenter__(self) -> McpSession: ...
    async def __aexit__(self, *args: Any) -> None: ...


@dataclass
class AttemptState:
    deadline: float
    dispatches: int = 0
    mcp_effect_possible: bool = False

    def remaining(self) -> float:
        value = self.deadline - time.monotonic()
        if value <= 0: raise ExecutionFailure("attempt_timeout", mcp_effect_possible=self.mcp_effect_possible)
        return value


class ExecutionEngine:
    def __init__(self, model_store: Any, provider_factory: Callable[[dict[str, Any]], ProviderAdapter], mcp_factory: Callable[[ExecutionRequest], McpSessionContext]):
        self.model_store=model_store; self.provider_factory=provider_factory; self.mcp_factory=mcp_factory
        self._slot=asyncio.Lock(); self._occupied=False

    async def execute(self, request: ExecutionRequest) -> ExecutionOutcome:
        async with self._slot:
            if self._occupied: raise BusyError("busy")
            self._occupied=True
        try: return await self._execute(request)
        finally:
            async with self._slot: self._occupied=False

    def _validate_request(self, request: ExecutionRequest) -> None:
        if len(request.capabilities)>MAX_CAPABILITIES: raise ExecutionFailure("capability_limit")
        names=[c.name for c in request.capabilities]
        if len(names)!=len(set(names)) or any(not n for n in names): raise ExecutionFailure("invalid_capability_envelope")
        documents=[request.objective,request.input,request.result_schema,*[{'name':c.name,'description':c.description,'input_schema':c.input_schema} for c in request.capabilities]]
        try:
            if any(len(canonical(value).encode())>MAX_DOCUMENT_BYTES for value in documents if value is not None): raise ExecutionFailure("document_limit")
            total={'objective':request.objective,'input':request.input,'capabilities':[{'name':c.name,'description':c.description,'input_schema':c.input_schema} for c in request.capabilities],'result_schema':request.result_schema}
            if len(canonical(total).encode())>MAX_DOCUMENT_BYTES: raise ExecutionFailure("request_limit")
            for capability in request.capabilities: Draft202012Validator.check_schema(capability.input_schema)
            if request.result_schema is not None: Draft202012Validator.check_schema(request.result_schema)
        except (ValueError, TypeError, SchemaError): raise ExecutionFailure("invalid_schema") from None

    async def _execute(self, request: ExecutionRequest) -> ExecutionOutcome:
        try: self._validate_request(request)
        except ExecutionFailure as exc: return ExecutionOutcome(False,error_code=exc.code)
        models=self.model_store.execution_models()
        if not models: return ExecutionOutcome(False,error_code="no_compatible_model")
        try:
            async with self.mcp_factory(request) as session:
                await self._verify_envelope(session,request.capabilities)
                for model in models:
                    self.model_store.begin_use(model['id'])
                    try:
                        return await self._attempt(request,model,session)
                    except ExecutionFailure as exc:
                        if exc.mcp_effect_possible: return ExecutionOutcome(False,error_code=exc.code,model_id=model['id'],mcp_effect_possible=True)
                        last=exc.code
                    finally: self.model_store.end_use(model['id'])
                return ExecutionOutcome(False,error_code=last)
        except ExecutionFailure as exc:
            return ExecutionOutcome(False,error_code=exc.code,mcp_effect_possible=exc.mcp_effect_possible)
        except Exception:
            return ExecutionOutcome(False,error_code="mcp_failure")

    async def _verify_envelope(self, session: McpSession, envelope: tuple[Capability,...]) -> None:
        inventory: dict[str,Capability]={}; cursor=None
        while True:
            page,cursor=await session.list_tools(cursor)
            for tool in page: inventory[tool.name]=tool
            if cursor is None: break
        for expected in envelope:
            actual=inventory.get(expected.name)
            if actual is None: raise ExecutionFailure("capability_missing")
            if canonical(actual.input_schema)!=canonical(expected.input_schema): raise ExecutionFailure("capability_schema_mismatch")

    async def _attempt(self, request: ExecutionRequest, model: dict[str,Any], session: McpSession) -> ExecutionOutcome:
        timeout=float(model['timeout_minutes'])*60
        if not math.isfinite(timeout) or timeout<=0: raise ExecutionFailure("invalid_timeout")
        state=AttemptState(time.monotonic()+timeout); adapter=self.provider_factory(model)
        messages=[{'role':'user','content':canonical({'objective':request.objective,'input':request.input})}]
        async def dispatch(call: ToolCall) -> Any: return await self._dispatch(call,request.capabilities,session,state)
        while True:
            try: reply=await asyncio.wait_for(adapter.turn(messages,request.capabilities,request.result_schema,state.remaining(),dispatch),timeout=state.remaining())
            except asyncio.TimeoutError: raise ExecutionFailure("attempt_timeout",mcp_effect_possible=state.mcp_effect_possible) from None
            except ExecutionFailure: raise
            except Exception as exc:
                code="attempt_timeout" if str(exc)=="attempt_timeout" else "provider_failure"
                raise ExecutionFailure(code,mcp_effect_possible=state.mcp_effect_possible) from None
            if reply.tool_calls:
                messages.append(reply.assistant_message or {'role':'assistant','content':reply.content,'tool_calls':[{'id':c.id,'name':c.name,'arguments':c.arguments} for c in reply.tool_calls]})
                for call in reply.tool_calls:
                    result=await dispatch(call); messages.append(ToolResult(call.id,call.name,result))
                continue
            result=reply.content
            if request.result_schema is not None:
                try:
                    candidate=json.loads(result) if isinstance(result,str) else result
                    Draft202012Validator(request.result_schema).validate(candidate); result=candidate
                except (json.JSONDecodeError,ValidationError,TypeError): raise ExecutionFailure("result_schema_invalid",mcp_effect_possible=state.mcp_effect_possible) from None
            try: size=len(canonical(result).encode())
            except (ValueError,TypeError): raise ExecutionFailure("invalid_result",mcp_effect_possible=state.mcp_effect_possible) from None
            if size>MAX_DOCUMENT_BYTES: raise ExecutionFailure("result_limit",mcp_effect_possible=state.mcp_effect_possible)
            return ExecutionOutcome(True,result=result,model_id=model['id'],mcp_effect_possible=state.mcp_effect_possible)

    async def _dispatch(self, call: ToolCall, envelope: tuple[Capability,...], session: McpSession, state: AttemptState) -> Any:
        capability=next((c for c in envelope if c.name==call.name),None)
        if capability is None: raise ExecutionFailure("unknown_tool",mcp_effect_possible=state.mcp_effect_possible)
        if not isinstance(call.arguments,dict): raise ExecutionFailure("invalid_tool_arguments",mcp_effect_possible=state.mcp_effect_possible)
        try: encoded=canonical(call.arguments).encode()
        except (ValueError,TypeError): raise ExecutionFailure("invalid_tool_arguments",mcp_effect_possible=state.mcp_effect_possible) from None
        if len(encoded)>MAX_ARGUMENT_BYTES: raise ExecutionFailure("tool_argument_limit",mcp_effect_possible=state.mcp_effect_possible)
        try: Draft202012Validator(capability.input_schema).validate(call.arguments)
        except ValidationError: raise ExecutionFailure("invalid_tool_arguments",mcp_effect_possible=state.mcp_effect_possible) from None
        if state.dispatches>=MAX_DISPATCHES: raise ExecutionFailure("dispatch_limit",mcp_effect_possible=state.mcp_effect_possible)
        if await session.changed(): await self._verify_envelope(session,envelope)
        state.dispatches+=1; state.mcp_effect_possible=True
        try: result=await asyncio.wait_for(session.call_tool(call.name,call.arguments),timeout=state.remaining())
        except asyncio.TimeoutError: raise ExecutionFailure("attempt_timeout",mcp_effect_possible=True) from None
        except Exception: raise ExecutionFailure("mcp_failure",mcp_effect_possible=True) from None
        try: size=len(canonical(result).encode())
        except (ValueError,TypeError): raise ExecutionFailure("invalid_tool_result",mcp_effect_possible=True) from None
        if size>MAX_TOOL_RESULT_BYTES: raise ExecutionFailure("tool_result_limit",mcp_effect_possible=True)
        return result
