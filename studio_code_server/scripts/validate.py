#!/usr/bin/env python3
"""Validate Studio Code Server + Codex App metadata without third-party modules."""

from __future__ import annotations

import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"


def one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def main() -> int:
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
    codex_wrapper = (ROOT / "codex-unprivileged.sh").read_text(encoding="utf-8")
    codex_shell = (ROOT / "codex-shell.sh").read_text(encoding="utf-8")
    versions_text = (ROOT / "upstream_versions").read_text(encoding="utf-8")
    versions = dict(
        line.split("=", 1)
        for line in versions_text.splitlines()
        if line.strip()
    )

    expected_args = {
        "code-server": "CODE_SERVER_VERSION",
        "codex": "CODEX_VERSION",
        "ha-cli": "HA_CLI_VERSION",
        "home-assistant-extension": "HOME_ASSISTANT_EXTENSION_VERSION",
        "yaml-extension": "YAML_EXTENSION_VERSION",
    }
    for key, arg in expected_args.items():
        value = versions.get(key)
        if not value:
            raise RuntimeError(f"Missing upstream version: {key}")
        docker_value = one(
            rf'^ARG {arg}="([^"]+)"$', dockerfile, f"Docker {arg}"
        )
        if docker_value != value:
            raise RuntimeError(f"{arg}={docker_value} does not match {key}={value}")

    installer = (ROOT / "install-codex-extension.sh").read_text(encoding="utf-8")
    installer_extension = one(
        r'^readonly CODEX_EXTENSION_VERSION="([^"]+)"$',
        installer,
        "Codex extension installer version",
    )
    if installer_extension != versions.get("codex-extension"):
        raise RuntimeError("Codex extension installer version does not match upstream_versions")

    app_version = one(r'^version: "([^"]+)"$', config, "App version")
    build_version = one(
        r'^ARG BUILD_VERSION="([^"]+)"$', dockerfile, "Docker App version"
    )
    if not re.fullmatch(SEMVER, app_version) or build_version != app_version:
        raise RuntimeError(
            f"App and Docker versions must be identical semantic versions: "
            f"{app_version} / {build_version}"
        )

    required_config = (
        'slug: "studio_code_server"',
        "ingress: true",
        "ingress_port: 1337",
        "ingress_stream: true",
        "hassio_api: true",
        "hassio_role: manager",
        "homeassistant_api: true",
        "backup: cold",
        'workspace_path: "/data/workspace"',
        'ha_mcp_url: "password?"',
        "  - aarch64",
        "  - amd64",
    )
    for item in required_config:
        if item not in config:
            raise RuntimeError(f"Missing config invariant: {item}")

    forbidden_config = ("ports:", "host_network:", "privileged:", "full_access:")
    for key in forbidden_config:
        if re.search(rf"^{re.escape(key)}", config, flags=re.MULTILINE):
            raise RuntimeError(f"Forbidden direct exposure or privilege key: {key}")

    required_launcher = (
        'readonly DATA_HOME="/data/home"',
        'export HOME="${DATA_HOME}"',
        'export HASS_SERVER="http://supervisor/core"',
        'exec s6-setuidgid codex',
        'code-server \\',
        '--auth none',
        '--disable-telemetry',
        '--disable-update-check',
        'codex login --device-auth',
        'install-codex-extension',
        "bashio::config 'ha_mcp_url'",
        'add home-assistant --url "${ha_mcp_url}"',
        '.["git.autofetch"] = true',
    )
    for item in required_launcher:
        if item not in launcher:
            raise RuntimeError(f"Missing launcher invariant: {item}")

    required_wrapper = (
        "s6-setuidgid codex",
        "-u HASS_TOKEN",
        "-u SUPERVISOR_TOKEN",
        "/usr/local/bin/codex-real",
    )
    for item in required_wrapper:
        if item not in codex_wrapper:
            raise RuntimeError(f"Missing Codex wrapper invariant: {item}")
        if item != "/usr/local/bin/codex-real" and item not in codex_shell:
            raise RuntimeError(f"Missing Codex shell invariant: {item}")

    if "OPENAI_API_KEY" in dockerfile or "OPENAI_API_KEY" in launcher:
        raise RuntimeError("The App must not configure OpenAI Platform API keys")
    if "eval " in launcher:
        raise RuntimeError("Initialization commands must not use shell eval")

    settings = json.loads((ROOT / "settings.json").read_text(encoding="utf-8"))
    if settings.get("telemetry.telemetryLevel") != "off":
        raise RuntimeError("VS Code telemetry must remain disabled")
    if settings.get("terminal.integrated.defaultProfile.linux") != "Codex workspace":
        raise RuntimeError("The default terminal must be the unprivileged Codex workspace")
    if settings.get("git.autofetch") is not True:
        raise RuntimeError("Git automatic fetch must be enabled")

    required_files = (
        "CHANGELOG.md",
        "DOCS.md",
        "LICENSE.upstream.md",
        "README.fr.md",
        "README.md",
        "THIRD_PARTY.md",
        "UPSTREAM.md",
        "codex-shell.sh",
        "codex-unprivileged.sh",
        "install-codex-extension.sh",
        "translations/en.yaml",
        "translations/fr.yaml",
    )
    for filename in required_files:
        if not (ROOT / filename).is_file():
            raise RuntimeError(f"Missing required file: {filename}")

    translation_keys: dict[str, set[str]] = {}
    for language in ("en", "fr"):
        translation = (ROOT / "translations" / f"{language}.yaml").read_text(
            encoding="utf-8"
        )
        translation_keys[language] = set(
            re.findall(r"^  ([a-z_]+):$", translation, flags=re.MULTILINE)
        )
    expected_translation_keys = {
        "log_level",
        "workspace_path",
        "ha_mcp_url",
        "packages",
        "init_commands",
    }
    if translation_keys["en"] != translation_keys["fr"]:
        raise RuntimeError("French and English translation keys differ")
    if translation_keys["en"] != expected_translation_keys:
        raise RuntimeError(
            f"Unexpected translation keys: {sorted(translation_keys['en'])}"
        )

    print(
        f"Validated Studio Code Server + Codex {app_version}: "
        f"code-server {versions['code-server']}, Codex {versions['codex']}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
