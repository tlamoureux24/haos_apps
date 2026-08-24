#!/usr/bin/env python3
"""Validate Agent Execution Plane Lot 1 repository invariants."""

from __future__ import annotations

import hashlib
import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = ROOT.parent


def leaf_keys(text: str, section: str) -> set[str]:
    active = False; keys: set[str] = set()
    for line in text.splitlines():
        if line and not line.startswith(" "):
            active = line == f"{section}:"; continue
        if active and (match := re.match(r"^  ([^:#]+):\s*$", line)):
            keys.add(match.group(1))
    return keys


def generic_s6_rules(text: str) -> tuple[str, ...]:
    lines = text.splitlines()
    start = lines.index("  /init rix,")
    end = lines.index("  /run/ rw,")
    return tuple(line for line in lines[start:end] if line)


def main() -> int:
    config = (ROOT / "config.yaml").read_text()
    package = (ROOT / "src/agent_execution_plane/__init__.py").read_text()
    main_py = (ROOT / "src/agent_execution_plane/main.py").read_text()
    ui = (ROOT / "src/agent_execution_plane/admin_ui.py").read_text()
    dockerfile = (ROOT / "Dockerfile").read_text()
    launcher = (ROOT / "run.sh").read_text()
    apparmor = (ROOT / "apparmor.txt").read_text()
    acp_apparmor = (REPOSITORY_ROOT / "agent_control_plane/apparmor.txt").read_text()
    for text in ('slug: "agent_execution_plane"', 'version: "1.1.11"', "stage: stable", "ingress_port: 8099", "  8098/tcp: null", "apparmor: true", "tmpfs: true"):
        if text not in config: raise RuntimeError(f"Missing metadata invariant: {text}")
    if '__version__ = "1.1.11"' not in package: raise RuntimeError("Version sources differ")
    if "arch:\n  - amd64\nstartup:" not in config or "aarch64" in config: raise RuntimeError("Agent Execution Plane must support amd64 only")
    if "FROM ghcr.io/home-assistant/base:latest" not in dockerfile or "BASE_IMAGE_DIGEST" not in dockerfile: raise RuntimeError("Base provenance discipline missing")
    if "adduser -S -D -H" not in dockerfile or launcher.count("python3 -m uvicorn") != 3: raise RuntimeError("Unprivileged listener variants missing")
    if launcher.count("--log-config /app/src/agent_execution_plane/uvicorn_logging.json") != 3: raise RuntimeError("Timestamped listener logging missing")
    if "prepare_certificate" not in launcher or "2>&1" not in launcher or "tls_error=" not in launcher: raise RuntimeError("Concise TLS startup error handling missing")
    if "os.geteuid() != 1000" not in main_py or "ingress_only" not in main_py or "x-ingress-path" not in main_py: raise RuntimeError("Ingress boundary missing")
    for invariant in ("Agent Execution Plane <b>v{__version__}</b>", "/admin/assets/icon.png", "aep-language", "navigator.language", "aep-theme", "prefers-color-scheme", "activityTitle", "app_stopped:'Application arrêtée'", "app_stopped:'Application stopped'"):
        if invariant not in main_py + ui: raise RuntimeError(f"UI invariant missing: {invariant}")
    if ".app{max-width:1840px" not in ui or ".app{max-width:1400px" in ui: raise RuntimeError("Administration layout width must match Agent Control Plane")
    if ":root{color-scheme:light;scrollbar-gutter:stable;" not in ui: raise RuntimeError("Stable root scrollbar gutter missing")
    if 'id="standalone-transport-help"' not in ui or "standalone-transport-help').hidden=data.api.transport!=='https'" not in ui: raise RuntimeError("HTTP transport must not display HTTPS certificate guidance")
    forbidden = ("chatgptauthtokens",)
    source = "".join(p.read_text(errors="ignore") for p in (ROOT / "src").rglob("*.py"))
    for item in forbidden:
        if item in source.lower(): raise RuntimeError(f"Later-lot behavior present: {item}")
    if "privileged:" in config or "host_network:" in config or "homeassistant_api:" in config: raise RuntimeError("Excess HAOS privileges")
    if "capability sys_admin" in apparmor or "network raw" in apparmor or "complain" in apparmor: raise RuntimeError("Excess AppArmor privilege")
    if generic_s6_rules(apparmor) != generic_s6_rules(acp_apparmor): raise RuntimeError("Generic s6-overlay AppArmor rules must match the HAOS-proven Agent Control Plane bootstrap inventory")
    if "agent_control_plane" in apparmor or "credential-pepper" in apparmor: raise RuntimeError("Agent Execution Plane AppArmor must not inherit Agent Control Plane data permissions")
    for invariant in ("cryptography==46.0.3", "httpx==0.28.1", "mcp==1.28.1", "jsonschema[format-nongpl]==4.26.0", "openai-codex==0.144.4", "openai-codex-cli-bin==0.144.4"):
        if invariant not in (ROOT / "requirements.txt").read_text(): raise RuntimeError(f"Missing Lot 1 dependency: {invariant}")
    for invariant in ("/data/private/provider-key rwlk,", "/data/private/.provider-key.*.tmp rwlk,"):
        if invariant not in apparmor: raise RuntimeError(f"Missing provider-key AppArmor rule: {invariant}")
    for invariant in ("/usr/lib/python3*/site-packages/codex_cli_bin/bin/codex ix,", "/usr/lib/python3*/site-packages/codex_cli_bin/bin/codex-code-mode-host ix,", "/usr/lib/python3*/site-packages/codex_cli_bin/codex-path/rg ix,", "/usr/lib/python3*/site-packages/codex_cli_bin/codex-resources/bwrap ix,", "/usr/lib/python3*/site-packages/codex_cli_bin/codex-resources/zsh/bin/zsh ix,", "/data/private/codex-home/** rwlk,"):
        if invariant not in apparmor: raise RuntimeError(f"Missing Codex AppArmor rule: {invariant}")
    if "CREATE TABLE IF NOT EXISTS models" not in (ROOT / "src/agent_execution_plane/database.py").read_text(): raise RuntimeError("Missing generation-1 models persistence")
    for invariant in ("CREATE TABLE IF NOT EXISTS settings", "CREATE TABLE IF NOT EXISTS active_execution", "CREATE TABLE IF NOT EXISTS pending_result"):
        if invariant not in (ROOT / "src/agent_execution_plane/database.py").read_text(): raise RuntimeError(f"Missing Lot 3 persistence: {invariant}")
    if 'data-view="models"' not in ui or "explicitWarning" not in ui or "openai_chatgpt_oauth" not in ui or "chatgptAccount" not in ui: raise RuntimeError("Missing bilingual Models administration view")
    if "form.reset();form.id.value=model?.id??''" not in ui or "data={id:f.id.value||null" not in ui: raise RuntimeError("Explicit model create/edit identity invariant missing")
    for invariant in ("/api/v1/execute", "/api/v1/executions/{execution_id}", "StandaloneBoundary", "credential_verifier", "recover_interrupted"):
        if invariant not in source: raise RuntimeError(f"Missing Lot 3 standalone invariant: {invariant}")
    codex = (ROOT / "src/agent_execution_plane/codex_runtime.py").read_text()
    for invariant in ('CODEX_VERSION = "0.144.4"', 'forced_login_method = "chatgpt"', 'cli_auth_credentials_store = "file"', '"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"'):
        if invariant not in codex: raise RuntimeError(f"Missing Codex OAuth isolation invariant: {invariant}")
    if 'web_search = "live"\n\n[features]' not in codex or 'web_search = false' in codex: raise RuntimeError("Canonical Codex native Web search setting missing")
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
    for invariant in ("class ExecutionRequest", "class ExecutionOutcome", "MAX_CAPABILITIES = 128", "mcp_effect_possible"):
        if invariant not in source: raise RuntimeError(f"Missing Lot 2 engine invariant: {invariant}")
    for invariant in ("class AcpBoundary", "jobs_claim_v1", "jobs_heartbeat_v1", "jobs_complete_v1", "jobs_fail_v1", "allowed_capabilities", "source_lease_lost"):
        if invariant not in source: raise RuntimeError(f"Missing Lot 4 ACP boundary invariant: {invariant}")
    print("Agent Execution Plane Lots 0-4 validation passed")
    return 0


if __name__ == "__main__": raise SystemExit(main())
