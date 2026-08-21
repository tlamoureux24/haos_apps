#!/usr/bin/env python3
"""Validate MCP Capability Bridge Lot 0 repository invariants."""

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

    for value in (
        'slug: "mcp_capability_bridge"', 'version: "0.1.0"',
        "  - aarch64", "  - amd64", "init: false", "apparmor: true",
        "tmpfs: true", "backup: cold", "ingress: true", "ingress_port: 8099",
        "  8098/tcp: null",
    ):
        require(config, value, "App metadata invariant")
    require(package, '__version__ = "0.1.0"', "synchronized package version")
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
    for value in ('Route("/health/live"', 'Route("/health/ready"', "routes=health"):
        require(main_source, value, "health route")
    if 'Route("/mcp"' in main_source:
        raise RuntimeError("Lot 0 must not expose an MCP endpoint")
    if any(term in main_source.lower() for term in ("bearer", "credential_verifier", "ssh client", "selenium")):
        raise RuntimeError("Lot 0 application source exceeds its boundary")
    if "Status: **accepted on HAOS — 2026-08-21**." not in plan:
        raise RuntimeError("Implementation plan Lot 0 status must match delivery state")
    if "capability sys_admin" in apparmor or "network raw" in apparmor or "complain" in apparmor:
        raise RuntimeError("AppArmor contains an excessive permission")
    for rule in (
        "/init rix,", "/sbin/su-exec ix,", "/usr/bin/python3 ix,",
        "/run/s6/{,**} rwk,", "/run/service/{,**} rwk,",
        "/data/mcp_capability_bridge.db rwlk,",
        "/data/mcp_capability_bridge.db-{journal,shm,wal} rwlk,",
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
