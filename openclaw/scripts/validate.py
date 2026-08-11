#!/usr/bin/env python3
"""Validate the thin OpenClaw Home Assistant package."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = r"\d{4}\.\d{1,2}\.\d{1,2}"
EXPECTED_ASSETS = {
    "icon.png": "3d37b2ad47ef29b3205fdf91f5e96343b2d474759457bbd375e4603a67224955",
    "logo.png": "f3ba91ff5f677b7afd199aab9128c7a0d905275823e153fea551473b279879f3",
}


def match_one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def main() -> int:
    upstream = (ROOT / "upstream_version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(VERSION, upstream):
        raise RuntimeError(f"Invalid upstream version: {upstream}")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    build = (ROOT / "build.yaml").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    run = (ROOT / "run.sh").read_text(encoding="utf-8")

    docker_image = match_one(r'^ARG BUILD_FROM="ghcr\.io/openclaw/openclaw:([^\"]+)"$', dockerfile, "Docker image version")
    docker_upstream = match_one(r'^ARG OPENCLAW_VERSION="([^\"]+)"$', dockerfile, "Docker OpenClaw version")
    docker_package = match_one(r'^ARG BUILD_VERSION="([^\"]+)"$', dockerfile, "Docker app version")
    config_package = match_one(r'^version: "([^\"]+)"$', config, "config app version")

    if docker_image != upstream or docker_upstream != upstream:
        raise RuntimeError("Docker image/version does not match upstream_version")
    if docker_package != config_package or not re.fullmatch(rf"{re.escape(upstream)}-\d+", config_package):
        raise RuntimeError("Docker and config package versions must match upstream-REVISION")
    for arch in ("amd64", "aarch64"):
        expected = f"  {arch}: ghcr.io/openclaw/openclaw:{upstream}"
        if expected not in build:
            raise RuntimeError(f"Missing pinned {arch} build image")

    required_config = (
        'slug: "openclaw"', "  - aarch64", "  - amd64", "init: false",
        "apparmor: true", "backup: cold", "  18789/tcp: 18789",
        "  - type: addon_config", "    read_only: false",
        "gateway_token: password?", "allow_insecure_http: bool",
        "openai_oauth_device_login: bool", "ha_mcp_url: password?",
    )
    for item in required_config:
        if item not in config:
            raise RuntimeError(f"Missing config invariant: {item}")
    forbidden_config = ("host_network:", "privileged:", "full_access:", "docker_api:", "homeassistant_api:", "hassio_api:")
    for item in forbidden_config:
        if item in config:
            raise RuntimeError(f"Forbidden privilege in config: {item}")

    if "unset OPENAI_API_KEY CODEX_API_KEY OPENAI_ADMIN_KEY OPENAI_PROJECT_ID" not in run:
        raise RuntimeError("Launcher no longer strips OpenAI Platform API variables")
    if "exec gosu node" not in run:
        raise RuntimeError("Launcher no longer drops privileges to node")
    if "gosu node python3 /usr/local/lib/ha-openclaw-oauth-device-login.py" not in run:
        raise RuntimeError("Launcher no longer supports the private OAuth device-login flow")
    if ":latest" in dockerfile or ":latest" in build:
        raise RuntimeError("Mutable latest image tag is forbidden")

    for filename, expected in EXPECTED_ASSETS.items():
        actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unexpected {filename} checksum: {actual}")

    print(f"Validated OpenClaw {upstream}, Home Assistant app {config_package}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
