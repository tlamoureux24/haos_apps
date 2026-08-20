"""Thin HTTP adapters used only for model validation and non-inference health."""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from agent_execution_plane.codex_runtime import CodexRuntime, CodexRuntimeError

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
