#!/usr/bin/env python3
"""Validate the Rsync Manager Home Assistant App without third-party modules."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
APP_VERSION = re.compile(r"\d+\.\d+\.\d+")
RSYNC_PACKAGE = re.compile(r"\d+\.\d+\.\d+-r\d+")
EXPECTED_ASSETS = {
    "icon.png": "42129d43f4b3913b3cde68aee5172b764847a56b77f757822ad416a95113478e",
    "logo.png": "a0d4e8bc695f1228ae76535db6392b86930a96765e7d6d914077063176f1d746",
    "rootfs/www/vendor/bootstrap/bootstrap.bundle.min.js": (
        "e4fd49181388c48ec5040bd3fe66f57c29c8e67fcd8502b3354b96ec7ab47cc7"
    ),
    "rootfs/www/vendor/bootstrap/bootstrap.min.css": (
        "d85327d99c7a3ee1f9b5d0500d1370acea3ad2db39c163c2f51f232baedbdede"
    ),
}


def match_one(pattern: str, text: str, label: str) -> str:
    matches = re.findall(pattern, text, flags=re.MULTILINE)
    if len(matches) != 1:
        raise RuntimeError(f"Expected one {label}, found {len(matches)}")
    return matches[0]


def require(text: str, values: tuple[str, ...], label: str) -> None:
    for value in values:
        if value not in text:
            raise RuntimeError(f"Missing {label}: {value}")


def main() -> int:
    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")
    index = (ROOT / "rootfs/www/index.html").read_text(encoding="utf-8")
    manager = (ROOT / "rootfs/usr/local/bin/rsync_manager.sh").read_text(
        encoding="utf-8"
    )
    package = (ROOT / "rsync_package_version").read_text(encoding="utf-8").strip()

    config_version = match_one(r'^version: "([^"]+)"$', config, "config App version")
    docker_version = match_one(
        r'^ARG BUILD_VERSION="([^"]+)"$', dockerfile, "Docker App version"
    )
    if not APP_VERSION.fullmatch(config_version):
        raise RuntimeError(f"Invalid App version: {config_version}")
    if docker_version != config_version:
        raise RuntimeError(
            f"Docker App version {docker_version} != config version {config_version}"
        )
    if not RSYNC_PACKAGE.fullmatch(package):
        raise RuntimeError(f"Invalid rsync package version: {package}")

    require(
        config,
        (
            'slug: "rsync_manager"',
            "  - aarch64",
            "  - amd64",
            "init: false",
            "apparmor: true",
            "tmpfs: true",
            "backup: cold",
            'watchdog: "http://[HOST]:[PORT:8099]/"',
            "ingress: true",
            "ingress_port: 8099",
            "# map:",
            "#   - type: share\n#     read_only: false",
            "#   - type: media\n#     read_only: false",
            "#   - type: backup\n#     read_only: false",
            "privileged:\n  - SYS_ADMIN",
        ),
        "config invariant",
    )
    for forbidden in (
        "codenotary:",
        "DAC_READ_SEARCH",
        "homeassistant_api:",
        "hassio_api:",
        "docker_api:",
        "homeassistant_config",
        "all_addon_configs",
    ):
        if forbidden in config:
            raise RuntimeError(f"Forbidden config value: {forbidden}")
    if re.search(r"^map:", config, flags=re.MULTILINE):
        raise RuntimeError("Local Home Assistant folders must be disabled by default")

    require(
        dockerfile,
        (
            "FROM ghcr.io/home-assistant/base:latest",
            'io.hass.type="app"',
            'io.hass.arch="${BUILD_ARCH}"',
            "ca-certificates",
            "cifs-utils",
            "lighttpd",
            "msmtp",
            "rsync",
        ),
        "Docker invariant",
    )
    if "fcgi" in dockerfile:
        raise RuntimeError("The unused FastCGI package must not be installed")

    if re.search(r"^\s*capability,\s*$", apparmor, flags=re.MULTILINE):
        raise RuntimeError("AppArmor must not grant every capability")
    require(
        apparmor,
        (
            "capability sys_admin,",
            "/data/** rw,",
            "/share/** rw,",
            "/media/** rw,",
            "/backup/** rw,",
            "/mnt/** rwk,",
        ),
        "AppArmor invariant",
    )
    for forbidden in ("capability dac_read_search", "/config/**", "/addons/**", "/ssl/**"):
        if forbidden in apparmor:
            raise RuntimeError(f"Overbroad AppArmor rule: {forbidden}")

    if "--tls-certcheck=on" not in manager or "--tls-certcheck=off" in manager:
        raise RuntimeError("SMTP certificate verification must remain enabled")

    scripts = list((ROOT / "rootfs").rglob("*.sh")) + [
        ROOT / "rootfs/etc/services.d/cron/run",
        ROOT / "rootfs/etc/services.d/runner/run",
        ROOT / "rootfs/etc/services.d/web/run",
    ]
    for script in scripts:
        if "chmod 666" in script.read_text(encoding="utf-8"):
            raise RuntimeError(f"World-writable persistent data in {script}")

    require(
        index,
        (
            'href="vendor/bootstrap/bootstrap.min.css"',
            'src="vendor/bootstrap/bootstrap.bundle.min.js"',
        ),
        "local frontend asset",
    )
    if "cdn.jsdelivr.net" in index:
        raise RuntimeError("The Ingress UI must not depend on jsDelivr")
    if (ROOT / "rootfs/www/style.css").exists():
        raise RuntimeError("The unused legacy stylesheet must remain removed")

    for relative, expected in EXPECTED_ASSETS.items():
        actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unexpected {relative} checksum: {actual}")

    print(f"Validated Rsync Manager {config_version}, rsync package {package}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
