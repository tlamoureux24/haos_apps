#!/usr/bin/env python3
"""Validate the AdGuard Home Home Assistant package without dependencies."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"
EXPECTED_ASSETS = {
    "icon.png": "47965e1bf04025b1663765dc814ddcb93a89eff210b3ec644825ab41d11c80de",
    "logo.png": "141932ff7054ccdf5e14a61db9e1be76b179414a227e6b2b24a66fc2b7a0852b",
}
EXPECTED_PORTS = {
    "53/tcp": "53",
    "53/udp": "53",
    "80/tcp": "null",
    "443/tcp": "null",
    "443/udp": "null",
    "3000/tcp": "3000",
    "3000/udp": "null",
    "853/tcp": "null",
    "853/udp": "null",
    "784/udp": "null",
    "8853/udp": "null",
    "5443/tcp": "null",
    "5443/udp": "null",
    "6060/tcp": "null",
}


def match_one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def main() -> int:
    upstream = (ROOT / "upstream_version").read_text(encoding="utf-8").strip()
    if not re.fullmatch(SEMVER, upstream):
        raise RuntimeError(f"Invalid upstream version: {upstream}")

    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")
    readme_en = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_fr = (ROOT / "README.fr.md").read_text(encoding="utf-8")
    docs = (ROOT / "DOCS.md").read_text(encoding="utf-8")

    docker_upstream = match_one(
        r'^ARG ADGUARD_HOME_VERSION="([^"]+)"$',
        dockerfile,
        "Docker AdGuard Home version",
    )
    docker_package = match_one(
        r'^ARG BUILD_VERSION="([^"]+)"$',
        dockerfile,
        "Docker app version",
    )
    config_package = match_one(
        r'^version: "([^"]+)"$',
        config,
        "config app version",
    )
    package_pattern = re.compile(rf"^{re.escape(upstream)}-(\d+)$")

    if docker_upstream != upstream:
        raise RuntimeError(f"Docker version {docker_upstream} != {upstream}")
    if docker_package != config_package or not package_pattern.fullmatch(config_package):
        raise RuntimeError(
            f"Package versions must match {upstream}-REVISION: "
            f"Docker={docker_package}, config={config_package}"
        )
    expected_from = "FROM adguard/adguardhome:v${ADGUARD_HOME_VERSION}"
    if expected_from not in dockerfile:
        raise RuntimeError("Dockerfile must derive from the pinned official image")

    required_config = (
        'slug: "adguard_home"',
        "  - aarch64",
        "  - amd64",
        "init: false",
        "apparmor: true",
        "tmpfs: true",
        "backup: cold",
        'webui: "[PROTO:ssl]://[HOST]:[PORT:3000]/"',
        "  - type: addon_config",
        "    read_only: false",
        "  ssl: false",
        "  ssl: bool",
    )
    for item in required_config:
        if item not in config:
            raise RuntimeError(f"Missing config invariant: {item}")

    actual_ports = dict(
        re.findall(r"^  (\d+/(?:tcp|udp)): (\d+|null)$", config, flags=re.MULTILINE)
    )
    if actual_ports != EXPECTED_PORTS:
        raise RuntimeError(f"Unexpected port map: {actual_ports}")
    for dhcp_port in ("67/udp", "68/tcp", "68/udp"):
        if dhcp_port in config:
            raise RuntimeError(f"DHCP port must not be published: {dhcp_port}")

    forbidden_config_keys = (
        "ingress:",
        "host_network:",
        "privileged:",
        "hassio_api:",
        "homeassistant_api:",
        "auth_api:",
        "docker_api:",
        "full_access:",
    )
    for key in forbidden_config_keys:
        if re.search(rf"^{re.escape(key)}", config, flags=re.MULTILINE):
            raise RuntimeError(f"Forbidden config key: {key}")

    launcher_invariants = (
        'readonly CONFIG_ROOT="/config"',
        'if su-exec nobody:nogroup test -s "${CONFIG_FILE}"; then',
        "start_unprivileged",
        'find "${CONF_DIR}" "${WORK_DIR}" -depth',
        "normalize_default_admin_port",
        'sub(/:80[[:space:]]*$/, ":3000")',
        "First-run setup requires temporary administrator privileges",
        "Initial configuration created; dropping privileges",
        "-exec chown nobody:nogroup '{}' \\;",
        'exec su-exec nobody:nogroup /opt/adguardhome/AdGuardHome',
        "--no-check-update",
        '--config "${CONFIG_FILE}"',
        '--work-dir "${WORK_DIR}"',
    )
    for item in launcher_invariants:
        if item not in launcher:
            raise RuntimeError(f"Missing launcher invariant: {item}")
    if 'chmod 700 "${CONF_DIR}" "${WORK_DIR}"' in launcher:
        raise RuntimeError("Launcher must not chmod Home Assistant mount points")
    if "SUPERVISOR_TOKEN" in launcher or "bashio" in launcher:
        raise RuntimeError("Launcher must remain independent from Supervisor APIs")

    for capability in ("net_admin", "net_raw", "sys_admin", "sys_ptrace"):
        if re.search(rf"capability\s+{capability}", apparmor):
            raise RuntimeError(f"Forbidden AppArmor capability: {capability}")
    if "capability net_bind_service," not in apparmor:
        raise RuntimeError("AppArmor must permit binding DNS port 53")

    official_link = "https://github.com/AdguardTeam/AdGuardHome"
    for name, document in (
        ("README.md", readme_en),
        ("README.fr.md", readme_fr),
        ("DOCS.md", docs),
    ):
        if official_link not in document:
            raise RuntimeError(f"Missing official documentation link in {name}")
        if "host_network" not in document or "DHCP" not in document:
            raise RuntimeError(f"Missing bridge/DHCP limitation in {name}")
    if "That option changes only the shortcut scheme" not in readme_en:
        raise RuntimeError("English HTTPS shortcut warning is missing")
    if "Cette option ne modifie que le schéma du raccourci" not in readme_fr:
        raise RuntimeError("French HTTPS shortcut warning is missing")

    for filename, expected in EXPECTED_ASSETS.items():
        actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unexpected {filename} checksum: {actual}")

    print(f"Validated AdGuard Home {upstream}, Home Assistant app {config_package}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
