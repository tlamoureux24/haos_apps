#!/usr/bin/env python3
"""Validate the Claude Remote App security invariants without third-party modules."""

from __future__ import annotations

import json
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"

# Built-in tools that run commands, read or write files, fetch the web or act
# outside the HA-MCP server. Every one must stay denied.
REQUIRED_DENY = {
    "Agent", "Bash", "Edit", "Glob", "Grep", "Monitor", "NotebookEdit",
    "PowerShell", "Read", "ReadMcpResourceTool", "ListMcpResourcesTool",
    "WebFetch", "WebSearch", "Write",
}
# Variables that would replace the claude.ai login or disable Remote Control.
FORBIDDEN_ENV = {
    "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN", "ANTHROPIC_BASE_URL",
    "CLAUDE_CODE_OAUTH_TOKEN", "CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC",
    "DISABLE_GROWTHBOOK",
}


def one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def require(items: tuple[str, ...], text: str, label: str) -> None:
    for item in items:
        if item not in text:
            raise RuntimeError(f"Missing {label} invariant: {item}")


def main() -> int:
    read = lambda name: (ROOT / name).read_text(encoding="utf-8")  # noqa: E731
    config = read("config.yaml")
    dockerfile = read("Dockerfile")
    launcher = read("run.sh")
    supervisor = read("remote-control.sh")
    nginx = read("nginx.conf")
    apparmor = read("apparmor.txt")

    app_version = one(r'^version: "([^"]+)"$', config, "App version")
    if not re.fullmatch(SEMVER, app_version):
        raise RuntimeError(f"App version must be semantic: {app_version}")

    require((
        'slug: "claude_remote"',
        "boot: manual",
        "init: false",
        "apparmor: true",
        "ingress: true",
        "ingress_port: 8099",
        "panel_admin: true",
        "hassio_api: false",
        "homeassistant_api: false",
        "  - /data/home/.claude/.credentials.json",
        '  ha_mcp_url: "password?"',
        "  confirm_writes: bool",
        "  confirm_writes: true",
        "  - aarch64",
        "  - amd64",
    ), config, "config")
    for key in ("map:", "ports:", "host_network:", "host_pid:", "privileged:",
                "full_access:", "auth_api:", "docker_api:", "hassio_role:",
                "devices:", "uart:", "usb:", "gpio:", "kernel_modules:"):
        if re.search(rf"^{re.escape(key)}", config, flags=re.MULTILINE):
            raise RuntimeError(f"Forbidden privilege or exposure key: {key}")

    if not dockerfile.startswith("FROM ghcr.io/home-assistant/base:"):
        raise RuntimeError("The App must build on the Home Assistant base image")
    claude_version = one(r'^ARG CLAUDE_CODE_VERSION="([^"]+)"$', dockerfile, "Claude Code version")
    if not re.fullmatch(SEMVER, claude_version):
        raise RuntimeError(f"Claude Code version must be pinned: {claude_version}")
    for arch in ("AMD64", "AARCH64"):
        digest = one(rf'^ARG CLAUDE_CODE_SHA512_{arch}="([^"]+)"$', dockerfile, f"{arch} digest")
        if not re.fullmatch(r"[0-9a-f]{128}", digest):
            raise RuntimeError(f"Invalid SHA-512 digest for {arch}")
    require((
        'sha512sum -c -',
        "claude-code-linux-${npm_arch}-musl",
        "COPY managed-settings.json /etc/claude-code/managed-settings.json",
        "adduser -D -u 1000 -G claude -h /data/home",
    ), dockerfile, "Dockerfile")
    if re.search(r"^ARG BUILD_VERSION=", dockerfile, flags=re.MULTILINE):
        raise RuntimeError("The App version must only live in config.yaml")

    settings = json.loads(read("managed-settings.json"))
    permissions = settings.get("permissions", {})
    missing = REQUIRED_DENY - set(permissions.get("deny", []))
    if missing:
        raise RuntimeError(f"Managed policy must deny: {sorted(missing)}")
    if permissions.get("allow"):
        raise RuntimeError("Allow rules belong to the generated HA-MCP drop-in only")
    if permissions.get("defaultMode") != "default":
        raise RuntimeError("Permission mode must stay 'default' so other tools ask")
    if permissions.get("disableBypassPermissionsMode") != "disable":
        raise RuntimeError("bypassPermissions mode must be disabled")
    if permissions.get("disableAutoMode") != "disable":
        raise RuntimeError("auto mode must be disabled")
    for key in ("allowManagedPermissionRulesOnly", "allowManagedHooksOnly", "disableClaudeAiConnectors"):
        if settings.get(key) is not True:
            raise RuntimeError(f"Managed setting {key} must be true")
    env = settings.get("env", {})
    if FORBIDDEN_ENV & set(env):
        raise RuntimeError(f"Forbidden managed env: {sorted(FORBIDDEN_ENV & set(env))}")
    if env.get("DISABLE_UPDATES") != "1":
        raise RuntimeError("Updates must come from the pinned image only")

    require((
        "#!/usr/bin/with-contenv bash",
        'readonly OPTIONS="/data/options.json"',
        '"${MANAGED_DIR}/managed-mcp.json"',
        "/private_[^/[:space:]]+$",
        "(URL not logged)",
        "unset ha_mcp_url",
        'chmod 0640 "${MANAGED_DIR}/managed-mcp.json"',
        "managed-settings.d/50-ha-mcp.json",
        "s6-setuidgid claude env -i",
        "ttyd --interface 127.0.0.1",
    ), launcher, "launcher")
    require((
        "s6-setuidgid claude env -i",
        '.authMethod == "claude.ai"',
        "claude remote-control",
        "--permission-mode default",
        "remoteDialogSeen == true",
        "hasTrustDialogAccepted == true",
        "setup_running",
    ), supervisor, "Remote Control loop")
    for text, name in ((launcher, "run.sh"), (supervisor, "remote-control.sh")):
        for variable in FORBIDDEN_ENV:
            if variable in text:
                raise RuntimeError(f"{name} must not reference {variable}")
        if re.search(r"\becho\b[^\n]*\$\{?ha_mcp_url", text):
            raise RuntimeError(f"{name} must never print the HA-MCP URL")
    require(("allow 172.30.32.2;", "deny all;", "proxy_pass http://127.0.0.1:7681/;"), nginx, "nginx")

    # Supervisor loads one top-level profile per App; the sub-profiles confine
    # Claude Code and every program it starts.
    top_level = re.findall(r"^profile (\S+)", apparmor, flags=re.MULTILINE)
    if top_level != ["claude_remote"]:
        raise RuntimeError(f"apparmor.txt must hold one top-level claude_remote profile: {top_level}")
    shell = apparmor.split("  profile claude_shell", 1)[-1]
    require((
        "  /usr/local/bin/claude Cx -> claude,",
        "  profile claude flags=",
        "  profile claude_shell flags=",
        "    /usr/bin/** Px -> claude_remote//claude_shell,",
        "    deny /data/options.json r,",
    ), apparmor, "AppArmor")
    require((
        "    deny network,",
        "    deny capability,",
        "    deny /usr/local/bin/** x,",
        "    deny /data/home/.claude/.credentials.json r,",
        "    deny /etc/claude-code/managed-mcp.json r,",
    ), shell, "AppArmor claude_shell")

    for filename in (
        "CHANGELOG.md", "DOCS.md", "README.md", "README.fr.md", "claude-remote-setup.sh",
        "claude-shell.sh", "icon.png", "logo.png", "ingress_ui.html", "ingress_ui.py",
        "translations/en.yaml", "translations/fr.yaml",
    ):
        if not (ROOT / filename).is_file():
            raise RuntimeError(f"Missing required file: {filename}")
    for filename in ("icon.png", "logo.png"):
        if not (ROOT / filename).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"Invalid PNG asset: {filename}")

    keys = {}
    for language in ("en", "fr"):
        keys[language] = set(re.findall(r"^  ([a-z_]+):$", read(f"translations/{language}.yaml"), flags=re.MULTILINE))
    if keys["en"] != keys["fr"] or keys["en"] != {"log_level", "ha_mcp_url", "confirm_writes"}:
        raise RuntimeError(f"Unexpected translation keys: {keys}")

    print(f"Validated Claude Remote {app_version}: Claude Code {claude_version}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, ValueError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
