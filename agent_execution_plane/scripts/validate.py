#!/usr/bin/env python3
"""Validate Lot 0 repository invariants without third-party packages."""

from __future__ import annotations

import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]


def leaf_keys(text: str, section: str) -> set[str]:
    active = False; keys: set[str] = set()
    for line in text.splitlines():
        if line and not line.startswith(" "):
            active = line == f"{section}:"; continue
        if active and (match := re.match(r"^  ([^:#]+):\s*$", line)):
            keys.add(match.group(1))
    return keys


def main() -> int:
    config = (ROOT / "config.yaml").read_text()
    package = (ROOT / "src/agent_execution_plane/__init__.py").read_text()
    main_py = (ROOT / "src/agent_execution_plane/main.py").read_text()
    ui = (ROOT / "src/agent_execution_plane/admin_ui.py").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    launcher = (ROOT / "run.sh").read_text()
    apparmor = (ROOT / "apparmor.txt").read_text()
    for text in ('slug: "agent_execution_plane"', 'version: "0.1.0"', "ingress_port: 8099", "  8098/tcp: null", "apparmor: true", "tmpfs: true"):
        if text not in config: raise RuntimeError(f"Missing metadata invariant: {text}")
    if '__version__ = "0.1.0"' not in package: raise RuntimeError("Version sources differ")
    if "FROM ghcr.io/home-assistant/base:latest" not in dockerfile or "BASE_IMAGE_DIGEST" not in dockerfile: raise RuntimeError("Base provenance discipline missing")
    if "adduser -S -D -H" not in dockerfile or launcher.count("python3 -m uvicorn") != 2: raise RuntimeError("Unprivileged two-listener runtime missing")
    if launcher.count("--log-config /app/src/agent_execution_plane/uvicorn_logging.json") != 2: raise RuntimeError("Timestamped listener logging missing")
    if "os.geteuid() != 1000" not in main_py or "ingress_only" not in main_py or "x-ingress-path" not in main_py: raise RuntimeError("Ingress boundary missing")
    for invariant in ("Agent Execution Plane <b>v{__version__}</b>", "/admin/assets/icon.png", "aep-language", "navigator.language", "aep-theme", "prefers-color-scheme", "activityTitle"):
        if invariant not in main_py + ui: raise RuntimeError(f"UI invariant missing: {invariant}")
    forbidden = ("/api/v1/execute", "jobs_claim_v1", "tools/call", "ollama", "chat/completions")
    source = "".join(p.read_text(errors="ignore") for p in (ROOT / "src").rglob("*.py"))
    for item in forbidden:
        if item in source.lower(): raise RuntimeError(f"Later-lot behavior present: {item}")
    if "privileged:" in config or "host_network:" in config or "homeassistant_api:" in config: raise RuntimeError("Excess HAOS privileges")
    if "capability sys_admin" in apparmor or "network raw" in apparmor or "complain" in apparmor: raise RuntimeError("Excess AppArmor privilege")
    for name in ("icon.png", "logo.png"):
        path = ROOT / name
        if not path.is_file() or path.stat().st_size < 1000: raise RuntimeError(f"Missing authoritative {name}")
        if f"COPY {name} /app/{name}" not in dockerfile: raise RuntimeError(f"{name} not packaged")
        print(f"{name} sha256={hashlib.sha256(path.read_bytes()).hexdigest()}")
    fr = (ROOT / "translations/fr.yaml").read_text(); en = (ROOT / "translations/en.yaml").read_text()
    for section in ("configuration", "network"):
        if leaf_keys(fr, section) != leaf_keys(en, section): raise RuntimeError(f"Translation mismatch: {section}")
    for name in ("README.md", "README.fr.md", "DOCS.md", "CHANGELOG.md"):
        if not (ROOT / name).is_file(): raise RuntimeError(f"Missing {name}")
    print("Agent Execution Plane Lot 0 validation passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
