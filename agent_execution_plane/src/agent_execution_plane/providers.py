"""Thin validation and execution adapters for supported model families."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import json
import re
from typing import Any

import httpx

from agent_execution_plane.codex_runtime import CodexRuntime, CodexRuntimeError
from agent_execution_plane.execution import Capability, ProviderReply, ToolCall, ToolResult, canonical

PROBE_TIMEOUT_SECONDS = 15.0


@dataclass(frozen=True)
class ProviderCheck:
    state: str
    code: str | None = None


def headers(credential: str | None) -> dict[str, str]:
    return {"Authorization": f"Bearer {credential}"} if credential else {}


def ollama_check(base_url: str, model: str, credential: str | None, explicit: bool) -> ProviderCheck:
    try:
        response = httpx.post(f"{base_url.rstrip('/')}/api/show", json={"model": model}, headers=headers(credential), timeout=PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        capabilities = response.json().get("capabilities")
        if isinstance(capabilities, list):
            return ProviderCheck("available" if "tools" in capabilities else "incompatible", None if "tools" in capabilities else "tools_unsupported")
        return ProviderCheck("unverified", "tool_capability_unreported")
    except (httpx.HTTPError, ValueError, TypeError):
        return ProviderCheck("unavailable", "provider_unreachable")


def openai_check(base_url: str, model: str, credential: str | None, explicit: bool) -> ProviderCheck:
    common_headers = headers(credential)
    try:
        response = httpx.get(f"{base_url.rstrip('/')}/v1/models", headers=common_headers, timeout=PROBE_TIMEOUT_SECONDS)
        response.raise_for_status()
        models = response.json().get("data", [])
        if not any(item.get("id") == model for item in models if isinstance(item, dict)):
            return ProviderCheck("unavailable", "model_not_found")
        if not explicit:
            return ProviderCheck("unverified", "explicit_probe_required")
        probe = httpx.post(
            f"{base_url.rstrip('/')}/v1/chat/completions",
            headers=common_headers,
            timeout=PROBE_TIMEOUT_SECONDS,
            json={"model": model, "messages": [{"role": "user", "content": "Call capability_probe."}], "tools": [{"type": "function", "function": {"name": "capability_probe", "description": "Compatibility probe", "parameters": {"type": "object", "properties": {}, "additionalProperties": False}}}], "tool_choice": {"type": "function", "function": {"name": "capability_probe"}}, "max_tokens": 8, "temperature": 0},
        )
        probe.raise_for_status()
        calls = probe.json()["choices"][0]["message"].get("tool_calls", [])
        compatible = any(call.get("function", {}).get("name") == "capability_probe" for call in calls)
        return ProviderCheck("available" if compatible else "incompatible", None if compatible else "tools_unsupported")
    except (httpx.HTTPError, ValueError, TypeError, KeyError, IndexError):
        return ProviderCheck("unavailable", "provider_unreachable")


def oauth_check(runtime: CodexRuntime, model: str) -> ProviderCheck:
    try:
        runtime.validate_model(model)
        return ProviderCheck("available")
    except CodexRuntimeError as exc:
        code = str(exc)
        return ProviderCheck("unavailable" if code == "auth_required" else "incompatible", code)


def check(family: str, base_url: str | None, model: str, credential: str | None, *, explicit: bool, codex_runtime: CodexRuntime | None = None) -> ProviderCheck:
    if family == "openai_chatgpt_oauth":
        return oauth_check(codex_runtime, model) if codex_runtime else ProviderCheck("incompatible", "runtime_or_model_incompatible")
    adapter = ollama_check if family == "ollama_compatible" else openai_check
    if base_url is None:
        return ProviderCheck("incompatible", "runtime_or_model_incompatible")
    return adapter(base_url, model, credential, explicit)


def _openai_tools(tools: tuple[Capability,...]) -> list[dict[str,Any]]:
    return [{'type':'function','function':{'name':t.name,'description':t.description,'parameters':t.input_schema}} for t in tools]


OPENAI_NAME = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class TransportNames:
    """Deterministic reversible 1:1 provider transport names; never authorization."""
    def __init__(self, tools: tuple[Capability, ...], *, constrained: bool):
        reserved={tool.name for tool in tools if not constrained or OPENAI_NAME.fullmatch(tool.name)}
        self.source_to_transport:dict[str,str]={}; used:set[str]=set()
        for tool in tools:
            if not constrained or OPENAI_NAME.fullmatch(tool.name): alias=tool.name
            else:
                digest=hashlib.sha256(tool.name.encode()).hexdigest()
                alias=f"aep_{digest[:60]}"
                counter=0
                while alias in reserved or alias in used:
                    counter+=1;alias=f"aep_{hashlib.sha256(f'{tool.name}:{counter}'.encode()).hexdigest()[:60]}"
            if alias in used: raise ValueError('provider_tool_alias_collision')
            used.add(alias);self.source_to_transport[tool.name]=alias
        self.transport_to_source={alias:source for source,alias in self.source_to_transport.items()}
    def capabilities(self,tools): return tuple(Capability(self.source_to_transport[t.name],t.description,t.input_schema) for t in tools)
    def source(self,name):
        try:return self.transport_to_source[name]
        except KeyError:raise ValueError('unknown_provider_tool') from None


def _openai_messages(messages,names):
    output=[]
    for message in messages:
        if isinstance(message,ToolResult): output.append({'role':'tool','tool_call_id':message.call_id,'content':canonical(message.result)})
        else: output.append(message)
    return output


def _ollama_messages(messages,names):
    output=[]
    for message in messages:
        if isinstance(message,ToolResult): output.append({'role':'tool','tool_name':names.source_to_transport[message.source_name],'content':canonical(message.result)})
        else: output.append(message)
    return output


class OpenAIExecutionAdapter:
    def __init__(self,model:dict[str,Any]): self.model=model
    async def turn(self,messages,tools,result_schema,remaining,dispatch):
        names=TransportNames(tools,constrained=True);transport=names.capabilities(tools)
        payload={'model':self.model['provider_model'],'messages':_openai_messages(messages,names),'tools':_openai_tools(transport),'temperature':0}
        if result_schema is not None: payload['response_format']={'type':'json_schema','json_schema':{'name':'source_result','strict':True,'schema':result_schema}}
        async with httpx.AsyncClient(headers=headers(self.model.get('credential')),timeout=remaining) as client:
            response=await client.post(f"{self.model['base_url'].rstrip('/')}/v1/chat/completions",json=payload); response.raise_for_status()
        message=response.json()['choices'][0]['message']; calls=[]
        for raw in message.get('tool_calls') or []:
            function=raw['function']
            try: arguments=json.loads(function['arguments']) if isinstance(function['arguments'],str) else function['arguments']
            except json.JSONDecodeError: arguments=function['arguments']
            calls.append(ToolCall(str(raw['id']),names.source(function['name']),arguments))
        return ProviderReply(message.get('content'),tuple(calls),message)


class OllamaExecutionAdapter:
    def __init__(self,model:dict[str,Any]): self.model=model
    async def turn(self,messages,tools,result_schema,remaining,dispatch):
        names=TransportNames(tools,constrained=False);transport=names.capabilities(tools)
        payload={'model':self.model['provider_model'],'messages':_ollama_messages(messages,names),'tools':[{'type':'function','function':{'name':t.name,'description':t.description,'parameters':t.input_schema}} for t in transport],'stream':False}
        if result_schema is not None: payload['format']=result_schema
        async with httpx.AsyncClient(headers=headers(self.model.get('credential')),timeout=remaining) as client:
            response=await client.post(f"{self.model['base_url'].rstrip('/')}/api/chat",json=payload); response.raise_for_status()
        message=response.json()['message']; calls=[]
        for index,raw in enumerate(message.get('tool_calls') or []):
            function=raw['function']; calls.append(ToolCall(str(raw.get('id',f'ollama-{index}')),names.source(function['name']),function.get('arguments',{})))
        return ProviderReply(message.get('content'),tuple(calls),message)


class OAuthExecutionAdapter:
    def __init__(self,model:dict[str,Any],runtime:CodexRuntime): self.model=model; self.runtime=runtime
    async def turn(self,messages,tools,result_schema,remaining,dispatch):
        names=TransportNames(tools,constrained=True);transport=names.capabilities(tools)
        async def routed(call): return await dispatch(ToolCall(call.id,names.source(call.name),call.arguments))
        return await self.runtime.execute_turn(self.model['provider_model'],messages,transport,result_schema,remaining,routed)


def execution_adapter(model:dict[str,Any],runtime:CodexRuntime|None=None):
    family=model['provider_family']
    if family=='ollama_compatible': return OllamaExecutionAdapter(model)
    if family=='openai_compatible': return OpenAIExecutionAdapter(model)
    if runtime is None: raise RuntimeError('runtime_or_model_incompatible')
    return OAuthExecutionAdapter(model,runtime)
