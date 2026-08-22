"""Precisely bounded SSH adapter with pinned host keys and token templates."""

from __future__ import annotations

import asyncio
import json
import logging
import math
import socket
from dataclasses import dataclass
from typing import Any

import asyncssh

from mcp_capability_bridge.contracts import AdapterCallError, Capability, validate_schema

MAX_TOKEN_BYTES = 4096
MAX_CAPABILITIES = 64
MAX_OUTPUT_LIMIT = 256 * 1024

# AsyncSSH logs complete remote command strings at INFO by default. Commands
# contain caller arguments, so the adapter keeps the dependency at WARNING
# even when Bridge application diagnostics are enabled.
logging.getLogger("asyncssh").setLevel(logging.WARNING)


class SSHCallError(AdapterCallError):
    pass


@dataclass(frozen=True)
class HostKeyScan:
    host: str
    port: int
    resolved_address: str
    algorithm: str
    fingerprint: str
    public_key: str


def _text(value: object, minimum: int, maximum: int, code: str) -> str:
    if not isinstance(value, str):
        raise ValueError(code)
    value = value.strip()
    if not minimum <= len(value) <= maximum:
        raise ValueError(code)
    return value


def quote_posix_token(value: str) -> str:
    encoded = value.encode("utf-8")
    if not encoded or len(encoded) > MAX_TOKEN_BYTES or "\x00" in value:
        raise ValueError("invalid_command_token")
    if any((ord(char) < 32 and char not in {"\n", "\t"}) or ord(char) == 127 for char in value):
        raise ValueError("invalid_command_token")
    return "'" + value.replace("'", "'\"'\"'") + "'"


def scalar_token(value: object) -> str:
    if isinstance(value, str):
        return value
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, int):
        return str(value)
    if isinstance(value, float) and math.isfinite(value):
        return json.dumps(value, allow_nan=False, separators=(",", ":"))
    raise ValueError("invalid_scalar_argument")


def build_command(executable: str, template: list[dict[str, str]], arguments: dict[str, Any]) -> str:
    tokens = [executable]
    for entry in template:
        if set(entry) == {"literal"}:
            tokens.append(entry["literal"])
        elif set(entry) == {"parameter"} and entry["parameter"] in arguments:
            tokens.append(scalar_token(arguments[entry["parameter"]]))
        else:
            raise ValueError("invalid_token_template")
    return " ".join(quote_posix_token(token) for token in tokens)


def validate_ssh_configuration(configuration: dict[str, Any]) -> None:
    allowed = {"host", "port", "username", "host_public_key", "host_fingerprint", "capabilities"}
    if set(configuration) != allowed:
        raise ValueError("invalid_ssh_target")
    _text(configuration["host"], 1, 253, "invalid_ssh_host")
    _text(configuration["username"], 1, 128, "invalid_ssh_username")
    if not isinstance(configuration["port"], int) or not 1 <= configuration["port"] <= 65535:
        raise ValueError("invalid_ssh_port")
    public_key = _text(configuration["host_public_key"], 16, 16384, "invalid_host_key")
    try:
        key = asyncssh.import_public_key(public_key)
    except (asyncssh.KeyImportError, ValueError) as exc:
        raise ValueError("invalid_host_key") from exc
    if configuration["host_fingerprint"] != key.get_fingerprint("sha256"):
        raise ValueError("invalid_host_key")
    capabilities = configuration["capabilities"]
    if not isinstance(capabilities, list) or len(capabilities) > MAX_CAPABILITIES:
        raise ValueError("invalid_ssh_capabilities")
    seen: set[str] = set()
    for item in capabilities:
        validate_ssh_capability(item)
        if item["id"] in seen or item["key"] in seen:
            raise ValueError("duplicate_capability")
        seen.update((item["id"], item["key"]))


def validate_ssh_capability(item: object) -> None:
    if not isinstance(item, dict) or set(item) != {"id", "key", "display_name", "description", "executable", "template", "input_schema", "timeout_seconds", "stdout_limit", "stderr_limit", "enabled", "effect_capable"}:
        raise ValueError("invalid_ssh_capability")
    capability_id = _text(item["id"], 1, 64, "invalid_ssh_capability")
    key = _text(item["key"], 2, 32, "invalid_ssh_capability")
    if not key.replace("_", "a").isalnum() or not key[0].isalpha() or key.lower() != key:
        raise ValueError("invalid_ssh_capability")
    _text(item["display_name"], 1, 100, "invalid_ssh_capability")
    _text(item["description"], 1, 2000, "invalid_ssh_capability")
    executable = _text(item["executable"], 2, 1024, "invalid_ssh_executable")
    if not executable.startswith("/") or "//" in executable or executable.endswith("/"):
        raise ValueError("invalid_ssh_executable")
    quote_posix_token(executable)
    template = item["template"]
    if not isinstance(template, list) or len(template) > 64:
        raise ValueError("invalid_token_template")
    for entry in template:
        if not isinstance(entry, dict) or len(entry) != 1:
            raise ValueError("invalid_token_template")
        if "literal" in entry:
            quote_posix_token(_text(entry["literal"], 1, MAX_TOKEN_BYTES, "invalid_command_token"))
        elif "parameter" in entry:
            _text(entry["parameter"], 1, 64, "invalid_token_template")
        else:
            raise ValueError("invalid_token_template")
    if not isinstance(item["input_schema"], dict):
        raise ValueError("invalid_ssh_capability")
    validate_schema(item["input_schema"])
    properties = item["input_schema"].get("properties", {})
    if any(entry.get("parameter") not in properties for entry in template if "parameter" in entry):
        raise ValueError("invalid_token_template")
    if any(not isinstance(schema, dict) or schema.get("type") not in {"string", "integer", "number", "boolean"} for schema in properties.values()):
        raise ValueError("ssh_parameters_must_be_scalar")
    if not isinstance(item["timeout_seconds"], int) or not 1 <= item["timeout_seconds"] <= 300:
        raise ValueError("invalid_ssh_timeout")
    for field in ("stdout_limit", "stderr_limit"):
        if not isinstance(item[field], int) or not 0 <= item[field] <= MAX_OUTPUT_LIMIT:
            raise ValueError("invalid_output_limit")
    if not isinstance(item["enabled"], bool) or not isinstance(item["effect_capable"], bool):
        raise ValueError("invalid_ssh_capability")
    Capability(capability_id, f"ssh_{key}", item["description"], item["input_schema"], item["effect_capable"]).validated()


async def scan_host_key(host: str, port: int, timeout: float = 10.0) -> HostKeyScan:
    host = _text(host, 1, 253, "invalid_ssh_host")
    if not isinstance(port, int) or not 1 <= port <= 65535:
        raise ValueError("invalid_ssh_port")
    try:
        addresses = await asyncio.wait_for(asyncio.to_thread(socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM), timeout)
        key = await asyncio.wait_for(asyncssh.get_server_host_key(host, port=port, config=None), timeout)
    except (OSError, asyncssh.Error, asyncio.TimeoutError) as exc:
        raise ValueError("ssh_host_scan_failed") from exc
    if key is None or not addresses:
        raise ValueError("ssh_host_scan_failed")
    exported = key.export_public_key("openssh").decode("ascii").strip()
    return HostKeyScan(host, port, addresses[0][4][0], key.get_algorithm(), key.get_fingerprint("sha256"), exported)


async def _drain(reader, limit: int) -> tuple[bytes, bool, int]:
    retained = bytearray()
    total = 0
    while True:
        chunk = await reader.read(16384)
        if not chunk:
            break
        if isinstance(chunk, str):
            chunk = chunk.encode("utf-8", "replace")
        total += len(chunk)
        if len(retained) < limit:
            retained.extend(chunk[: limit - len(retained)])
    return bytes(retained), total > limit, total


def _redact_output(value: bytes, auth: dict[str, Any]) -> str:
    text = value.decode("utf-8", "replace")
    for field in ("password", "private_key", "passphrase"):
        secret = auth.get(field)
        if isinstance(secret, str) and len(secret) >= 3:
            text = text.replace(secret, "[REDACTED]")
    return text


class SSHAdapter:
    type_key = "ssh"
    display_name = "SSH"

    def validate_target(self, configuration: dict[str, Any], secret: bytes | None) -> None:
        validate_ssh_configuration(configuration)
        if secret is None:
            raise ValueError("ssh_secret_required")
        try:
            auth = json.loads(secret)
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise ValueError("invalid_ssh_secret") from exc
        if not isinstance(auth, dict) or auth.get("mode") not in {"password", "private_key"}:
            raise ValueError("invalid_ssh_secret")
        if auth["mode"] == "password" and (set(auth) != {"mode", "password"} or not isinstance(auth["password"], str) or not auth["password"]):
            raise ValueError("invalid_ssh_secret")
        if auth["mode"] == "private_key":
            if set(auth) != {"mode", "private_key", "passphrase"} or not isinstance(auth["private_key"], str) or not isinstance(auth["passphrase"], str):
                raise ValueError("invalid_ssh_secret")
            try:
                asyncssh.import_private_key(auth["private_key"], auth["passphrase"] or None)
            except (asyncssh.KeyImportError, ValueError) as exc:
                raise ValueError("invalid_ssh_private_key") from exc

    def capabilities(self, configuration: dict[str, Any]) -> tuple[Capability, ...]:
        result = []
        for item in configuration.get("capabilities", []):
            if item.get("enabled"):
                result.append(Capability(item["id"], f"ssh_{item['key']}", item["description"], item["input_schema"], item["effect_capable"]).validated())
        return tuple(result)

    async def invoke(self, capability_id: str, configuration: dict[str, Any], secret: bytes | None, arguments: dict[str, Any]) -> object:
        self.validate_target(configuration, secret)
        capability = next((item for item in configuration["capabilities"] if item["id"] == capability_id and item["enabled"]), None)
        if capability is None:
            raise SSHCallError("capability_not_available")
        command = build_command(capability["executable"], capability["template"], arguments)
        auth = json.loads(secret)
        connect_args: dict[str, Any] = {"host": configuration["host"], "port": configuration["port"], "username": configuration["username"], "known_hosts": ([asyncssh.import_public_key(configuration["host_public_key"])], [], []), "config": None, "agent_path": None, "client_host_keys": [], "keepalive_interval": 0}
        if auth["mode"] == "password":
            connect_args.update(password=auth["password"], client_keys=[])
        else:
            connect_args.update(client_keys=[asyncssh.import_private_key(auth["private_key"], auth["passphrase"] or None)], password=None)
        accepted = False
        connection = None
        process = None
        drain_tasks: list[asyncio.Task] = []
        try:
            async with asyncio.timeout(capability["timeout_seconds"]):
                connection = await asyncssh.connect(**connect_args)
                process = await connection.create_process(command, input=None, encoding=None, term_type=None, env={})
                accepted = True
                stdout_task = asyncio.create_task(_drain(process.stdout, capability["stdout_limit"]))
                stderr_task = asyncio.create_task(_drain(process.stderr, capability["stderr_limit"]))
                drain_tasks = [stdout_task, stderr_task]
                await process.wait()
                stdout, stderr = await asyncio.gather(stdout_task, stderr_task)
                return {"exit_status": process.exit_status, "stdout": _redact_output(stdout[0], auth), "stderr": _redact_output(stderr[0], auth), "stdout_truncated": stdout[1], "stderr_truncated": stderr[1], "stdout_bytes": stdout[2], "stderr_bytes": stderr[2]}
        except TimeoutError as exc:
            raise SSHCallError("ssh_timeout", accepted) from exc
        except asyncio.CancelledError:
            raise
        except (OSError, asyncssh.Error, ValueError) as exc:
            raise SSHCallError("ssh_transport_failed", accepted) from exc
        finally:
            if process is not None:
                process.close()
            if connection is not None:
                connection.close()
                await connection.wait_closed()
            for task in drain_tasks:
                if not task.done():
                    task.cancel()
            if drain_tasks:
                await asyncio.gather(*drain_tasks, return_exceptions=True)
