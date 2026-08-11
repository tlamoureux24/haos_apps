#!/usr/bin/env python3
"""Prepare the minimal persistent OpenClaw configuration for Home Assistant."""

from __future__ import annotations

import json
import os
import re
import secrets
import shlex
import sys
import tempfile
from pathlib import Path
from urllib.parse import urlsplit


MCP_SERVER_NAME = "home-assistant"


def read_json(path: Path) -> dict:
    if not path.exists():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as err:
        raise RuntimeError(f"cannot read valid JSON from {path}: {err}") from err
    if not isinstance(value, dict):
        raise RuntimeError(f"expected a JSON object in {path}")
    return value


def write_json_atomic(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    descriptor, temporary_name = tempfile.mkstemp(
        dir=path.parent, prefix=f".{path.name}.", suffix=".tmp"
    )
    temporary = Path(temporary_name)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8") as handle:
            json.dump(value, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
        temporary.chmod(0o600)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)


def require_mapping(value: dict, key: str) -> dict:
    current = value.get(key)
    if current is None:
        current = {}
        value[key] = current
    if not isinstance(current, dict):
        raise RuntimeError(f"OpenClaw setting {key!r} must be an object")
    return current


def validate_origin(origin: str) -> str:
    parsed = urlsplit(origin)
    if parsed.scheme != "https" or not parsed.netloc:
        raise RuntimeError(f"allowed origin must use HTTPS: {origin!r}")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError(f"allowed origin must not contain a path: {origin!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


def parse_origins(raw: object) -> list[str]:
    if not isinstance(raw, str):
        raise RuntimeError("allowed_origins must be a comma-separated string")
    origins: list[str] = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        origin = validate_origin(item)
        if origin not in origins:
            origins.append(origin)
    if not origins:
        raise RuntimeError("allowed_origins must contain at least one HTTP(S) origin")
    return origins


def validate_mcp_url(raw: object) -> str:
    if raw in {None, ""}:
        return ""
    if not isinstance(raw, str):
        raise RuntimeError("ha_mcp_url must be a string")
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise RuntimeError("ha_mcp_url must be an HTTP(S) URL")
    if not re.search(r"/private_[A-Za-z0-9_-]+/?$", parsed.path):
        raise RuntimeError("ha_mcp_url must end with the HA-MCP private_<secret> path")
    return value


def validate_mobile_pairing_url(raw: object) -> str:
    if raw in {None, ""}:
        return ""
    if not isinstance(raw, str):
        raise RuntimeError("mobile_pairing_url must be a string")
    value = raw.strip()
    parsed = urlsplit(value)
    if parsed.scheme != "wss" or not parsed.hostname:
        raise RuntimeError("mobile_pairing_url must be a wss:// URL")
    if parsed.username or parsed.password:
        raise RuntimeError("mobile_pairing_url must not contain credentials")
    if parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
        raise RuntimeError("mobile_pairing_url must not contain a path, query or fragment")
    return f"{parsed.scheme}://{parsed.netloc}"


def gateway_token(options: dict, config_root: Path) -> tuple[str, bool]:
    configured = options.get("gateway_token", "")
    if configured is not None and not isinstance(configured, str):
        raise RuntimeError("gateway_token must be a string")
    if configured:
        if len(configured) < 24:
            raise RuntimeError("gateway_token must contain at least 24 characters")
        return configured, False

    token_path = config_root / "gateway_token"
    if token_path.exists():
        token = token_path.read_text(encoding="utf-8").strip()
        if len(token) < 24:
            raise RuntimeError(f"stored gateway token in {token_path} is invalid")
        return token, False

    token = secrets.token_urlsafe(32)
    token_path.write_text(token + "\n", encoding="utf-8")
    token_path.chmod(0o600)
    return token, True


def shell_env(options_path: Path, config_root: Path) -> None:
    options = read_json(options_path)
    timezone = options.get("timezone", "Europe/Paris")
    if not isinstance(timezone, str) or not re.fullmatch(r"[A-Za-z0-9_+.-]+(?:/[A-Za-z0-9_+.-]+)+", timezone):
        raise RuntimeError("timezone must be an IANA timezone such as Europe/Paris")
    token, generated = gateway_token(options, config_root)
    oauth_device_login = options.get("openai_oauth_device_login", False)
    if not isinstance(oauth_device_login, bool):
        raise RuntimeError("openai_oauth_device_login must be a boolean")
    print(f"TZ={shlex.quote(timezone)}")
    print(f"OPENCLAW_GATEWAY_TOKEN={shlex.quote(token)}")
    print(f"HA_OPENCLAW_OAUTH_DEVICE_LOGIN={'true' if oauth_device_login else 'false'}")
    if generated:
        print(
            f"INFO: generated Gateway token; retrieve it from {config_root / 'gateway_token'}",
            file=sys.stderr,
        )


def apply(options_path: Path, config_path: Path, workspace: str) -> None:
    options = read_json(options_path)
    config = read_json(config_path)

    gateway = require_mapping(config, "gateway")
    gateway["mode"] = "local"
    gateway["bind"] = "lan"
    gateway["port"] = 18789
    gateway["auth"] = {"mode": "token"}
    gateway["tls"] = {"enabled": True, "autoGenerate": True}

    control_ui = require_mapping(gateway, "controlUi")
    control_ui["allowedOrigins"] = parse_origins(
        options.get("allowed_origins", "https://homeassistant.local:18789")
    )
    control_ui.pop("dangerouslyDisableDeviceAuth", None)

    plugins = require_mapping(config, "plugins")
    entries = require_mapping(plugins, "entries")
    device_pair = require_mapping(entries, "device-pair")
    device_pair_config = require_mapping(device_pair, "config")
    mobile_pairing_url = validate_mobile_pairing_url(
        options.get("mobile_pairing_url", "")
    )
    if mobile_pairing_url:
        device_pair_config["publicUrl"] = mobile_pairing_url
    else:
        device_pair_config.pop("publicUrl", None)

    agents = require_mapping(config, "agents")
    defaults = require_mapping(agents, "defaults")
    defaults["workspace"] = workspace

    models = require_mapping(config, "models")
    pricing = require_mapping(models, "pricing")
    pricing["enabled"] = False

    mcp = require_mapping(config, "mcp")
    servers = require_mapping(mcp, "servers")
    mcp_url = validate_mcp_url(options.get("ha_mcp_url", ""))
    if mcp_url:
        servers[MCP_SERVER_NAME] = {
            "url": mcp_url,
            "transport": "streamable-http",
            "supportsParallelToolCalls": False,
        }
    else:
        servers.pop(MCP_SERVER_NAME, None)

    write_json_atomic(config_path, config)


def main() -> int:
    if len(sys.argv) < 2:
        raise RuntimeError("missing command")
    if sys.argv[1] == "shell-env" and len(sys.argv) == 4:
        shell_env(Path(sys.argv[2]), Path(sys.argv[3]))
        return 0
    if sys.argv[1] == "apply" and len(sys.argv) == 5:
        apply(Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4])
        return 0
    raise RuntimeError("usage: configure.py shell-env OPTIONS CONFIG_ROOT | apply OPTIONS CONFIG WORKSPACE")


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"FATAL: {err}", file=sys.stderr)
        raise SystemExit(1) from err
