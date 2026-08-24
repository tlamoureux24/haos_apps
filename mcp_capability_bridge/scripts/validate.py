#!/usr/bin/env python3
"""Validate MCP Capability Bridge 1.0 Lot 0-4 invariants."""

from __future__ import annotations

import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def require(text: str, value: str, context: str) -> None:
    if value not in text:
        raise RuntimeError(f"Missing {context}: {value}")


def main() -> int:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    package = (ROOT / "src/mcp_capability_bridge/__init__.py").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
    runtime = (ROOT / "src/mcp_capability_bridge/runtime.py").read_text(encoding="utf-8")
    main_source = (ROOT / "src/mcp_capability_bridge/main.py").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")
    plan = (ROOT / "IMPLEMENTATION_PLAN.md").read_text(encoding="utf-8")
    requirements = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    mcp_source = (ROOT / "src/mcp_capability_bridge/mcp_api.py").read_text(encoding="utf-8")
    security = (ROOT / "src/mcp_capability_bridge/security.py").read_text(encoding="utf-8")

    for value in (
        'slug: "mcp_capability_bridge"', 'version: "1.1.10"',
        "  - amd64", "init: false", "stage: stable", "apparmor: true",
        "tmpfs: true", "backup: cold", "ingress: true", "ingress_port: 8099",
        "  8098/tcp: null",
    ):
        require(config, value, "App metadata invariant")
    require(package, '__version__ = "1.1.10"', "synchronized package version")
    require(launcher + apparmor, "/run/mcp-capability-bridge-external-tls", "ephemeral external TLS staging")
    if "/data/private/external-tls" in launcher + apparmor: raise RuntimeError("External TLS staging must remain ephemeral under /run")
    require(config, "arch:\n  - amd64\nstartup:", "AMD64-only architecture")
    if "aarch64" in config:
        raise RuntimeError("MCP Capability Bridge must support amd64 only")
    for dependency in ("mcp==1.28.1", "jsonschema[format-nongpl]==4.26.0", "cryptography==50.0.0", "asyncssh==2.24.0", "selenium==4.46.0"):
        require(requirements, dependency, "pinned dependency")
    require(dockerfile, "adduser -S -D -H", "unprivileged user")
    require(dockerfile, 'org.opencontainers.image.base.digest="${BASE_IMAGE_DIGEST}"', "base provenance")
    require(dockerfile, "COPY icon.png /app/icon.png", "authoritative icon packaging")
    require(dockerfile, "COPY logo.png /app/logo.png", "authoritative logo packaging")
    require(launcher, "#!/usr/bin/with-contenv /bin/sh", "s6 environment launcher")
    require(launcher, "su-exec mcp-capability-bridge:mcp-capability-bridge", "privilege drop")
    if launcher.count("python3 -m mcp_capability_bridge.runtime") != 1:
        raise RuntimeError("Launcher must start exactly one Bridge runtime")
    if "python3 -m uvicorn" in launcher:
        raise RuntimeError("Launcher must not split listeners across processes")
    for value in ("asyncio.gather", "ManagedServer", "signal.SIGTERM", "signal.SIGINT"):
        require(runtime, value, "shared runtime/shutdown invariant")
    for value in ('Route("/health/live"', 'Route("/health/ready"', "*health"):
        require(main_source, value, "health route")
    for value in ("NamespaceMCP", "OpaqueBearerMiddleware", "streamable_http_app", "session_manager.run"):
        require(main_source + mcp_source, value, "authenticated MCP invariant")
    for value in ("RequestBodyLimitMiddleware", "request_too_large", "state.counters.shutdown"):
        require(main_source, value, "Lot 4 request/shutdown invariant")
    counters = (ROOT / "src/mcp_capability_bridge/runtime_state.py").read_text()
    for value in ("bridge_busy", "namespace_busy", "adapter_busy", "target_busy", "runtime_stopping"):
        require(counters, value, "Lot 4 fail-fast capacity invariant")
    for value in ("secrets.token_urlsafe(32)", "hmac.compare_digest", "TOKEN_PATTERN", "SecretBox"):
        require(security, value, "credential/secret security invariant")
    for forbidden in ("paramiko", "playwright"):
        if forbidden in requirements.lower() or forbidden in main_source.lower():
            raise RuntimeError(f"Unsupported adapter runtime: {forbidden}")
    if "Accepted on real HAOS with version 0.1.0:" not in plan:
        raise RuntimeError("Implementation plan Lot 0 status must match delivery state")
    if "Accepted on real HAOS with version 0.2.0:" not in plan:
        raise RuntimeError("Implementation plan Lot 1 status must match delivery state")
    if "Accepted on real HAOS with version 0.3.0:" not in plan:
        raise RuntimeError("Implementation plan Lot 2 status must match delivery state")
    for value in ("chromium=151.0.7922.173-r0","chromium-chromedriver=151.0.7922.173-r0"):
        require(dockerfile,value,"pinned Lot 3A browser package")
    browser=(ROOT/"src/mcp_capability_bridge/browser_runtime.py").read_text()
    web=(ROOT/"src/mcp_capability_bridge/web_adapter.py").read_text()
    for value in ("--headless=new","--no-sandbox","--host-resolver-rules=","profile-"):
        require(browser,value,"browser confinement invariant")
    for value in ("web_resolution_changed","web_origin_denied","class WebAdapter"):
        require(web,value,"Web target confinement invariant")
    if "Accepted on real HAOS with version 0.4.4:" not in plan:
        raise RuntimeError("Implementation plan Lot 3A status must match delivery state")
    if "Accepted on real HAOS with version 0.4.5:" not in plan:
        raise RuntimeError("Implementation plan generated-key micro-lot status must match delivery state")
    for value in ("class WebSessionManager", "Accessibility.getFullAXTree", "hmac.compare_digest", "close_namespace"):
        require((ROOT/"src/mcp_capability_bridge/web_sessions.py").read_text(),value,"Lot 3B session invariant")
    if "capability sys_admin" in apparmor or "network raw" in apparmor or "complain" in apparmor:
        raise RuntimeError("AppArmor contains an excessive permission")
    for rule in (
        "/init rix,", "/sbin/su-exec ix,", "/usr/bin/python3 ix,",
        "/run/s6/{,**} rwk,", "/run/service/{,**} rwk,",
        "/data/mcp_capability_bridge.db rwlk,",
        "/data/mcp_capability_bridge.db-{journal,shm,wal} rwlk,",
        "/data/private/credential-pepper rwlk,",
        "/data/private/target-secret-key rwlk,",
        "/proc/ r,",
        "/proc/** r,",
        "/etc/fonts/{,**} r,",
        "/var/cache/fontconfig/{,**} r,",
        "/usr/share/fonts/{,**} r,",
        "/usr/share/fontconfig/{,**} r,",
    ):
        require(apparmor, rule, "AppArmor runtime rule")
    for forbidden in ("/bin/** ix,", "/usr/bin/** ix,", "/package/** ix,", "/data/**"):
        if forbidden in apparmor:
            raise RuntimeError(f"AppArmor contains broad rule: {forbidden}")
    for name in ("icon.png", "logo.png", "README.md", "README.fr.md", "DOCS.md"):
        if not (ROOT / name).is_file():
            raise RuntimeError(f"Missing packaged/documentation file: {name}")
    for name in ("icon.png", "logo.png"):
        if not (ROOT / name).read_bytes().startswith(b"\x89PNG\r\n\x1a\n"):
            raise RuntimeError(f"Invalid authoritative PNG asset: {name}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
