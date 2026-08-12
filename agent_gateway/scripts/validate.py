#!/usr/bin/env python3
"""Validate Agent Gateway repository invariants without third-party packages."""

from __future__ import annotations

import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def yaml_leaf_keys(text: str, section: str) -> set[str]:
    lines = text.splitlines()
    keys: set[str] = set()
    in_section = False
    for line in lines:
        if line and not line.startswith(" "):
            in_section = line == f"{section}:"
            continue
        if in_section:
            match = re.match(r"^  ([^:#]+):\s*$", line)
            if match:
                keys.add(match.group(1))
    return keys


def main() -> int:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")
    application = (ROOT / "src/agent_gateway/main.py").read_text(encoding="utf-8")

    required_config = (
        'slug: "agent_gateway"',
        'version: "0.1.2"',
        "  - aarch64",
        "  - amd64",
        "init: false",
        "stage: experimental",
        "apparmor: true",
        "tmpfs: true",
        "backup: cold",
        "ingress: true",
        "ingress_port: 8099",
        "panel_admin: true",
        "homeassistant_api: true",
        "  8098/tcp: null",
    )
    for invariant in required_config:
        if invariant not in config:
            raise RuntimeError(f"Missing config invariant: {invariant}")

    if "privileged:" in config or "host_network:" in config:
        raise RuntimeError("Agent Gateway must not request privileged or host networking")
    if "hassio_role:" in config or "hassio_api:" in config:
        raise RuntimeError("Phase 0 must not request the Supervisor API")

    for language in ("fr", "en"):
        translation = ROOT / "translations" / f"{language}.yaml"
        if not translation.is_file():
            raise RuntimeError(f"Missing {language} translation")
    french = (ROOT / "translations/fr.yaml").read_text(encoding="utf-8")
    english = (ROOT / "translations/en.yaml").read_text(encoding="utf-8")
    for section in ("configuration", "network"):
        if yaml_leaf_keys(french, section) != yaml_leaf_keys(english, section):
            raise RuntimeError(f"Translation key mismatch in {section}")

    if "adduser -S -D -H" not in dockerfile:
        raise RuntimeError("Container must create an unprivileged runtime user")
    if launcher.count("su-exec agent-gateway:agent-gateway") != 3:
        raise RuntimeError("Migrations and both listeners must run unprivileged")
    if "os.geteuid() != 1000" not in application:
        raise RuntimeError("Application must refuse to run under an unexpected UID")
    if "AGENT_GATEWAY_SURFACE=admin" not in launcher:
        raise RuntimeError("Missing isolated admin listener")
    if "AGENT_GATEWAY_SURFACE=public" not in launcher:
        raise RuntimeError("Missing isolated public listener")
    if "capability sys_admin" in apparmor or "network raw" in apparmor:
        raise RuntimeError("AppArmor grants an excessive capability")
    if "/init rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read and execute /init")
    if "/package/admin/s6-overlay-*/libexec/preinit rix," not in apparmor:
        raise RuntimeError("AppArmor must allow the shell to read the s6-overlay preinit script")

    ignored_documents = (
        "/agent_gateway/PROJECT_BRIEF.md",
        "/agent_gateway/IMPLEMENTATION_PLAN.md",
        "/agent_gateway/docs/adr/0001-control-plane-foundation.md",
    )
    ignore = (REPOSITORY_ROOT / ".gitignore").read_text(encoding="utf-8")
    for document in ignored_documents:
        if document not in ignore:
            raise RuntimeError(f"Local design document is not ignored: {document}")

    print("Validated Agent Gateway repository invariants")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
