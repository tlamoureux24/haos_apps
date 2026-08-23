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
    "icon.png": "80fb69a44befb214c60d3bbde7618fbb087e3e82906a7e59d5a380379145a20d",
    "logo.png": "b8950cdeb846867d4e6040ca58f265712fa0f5e28cad9289d68d46f32436a83d",
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
    frontend_css = (ROOT / "rootfs/www/assets/app.css").read_text(encoding="utf-8")
    frontend_js = (ROOT / "rootfs/www/assets/app.js").read_text(encoding="utf-8")
    manager = (ROOT / "rootfs/usr/local/bin/rsync_manager.sh").read_text(
        encoding="utf-8"
    )
    cron = (ROOT / "rootfs/usr/local/bin/rsync_cron.sh").read_text(encoding="utf-8")
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
    if f"v{config_version}" not in index:
        raise RuntimeError("The branded interface version must match the App version")
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
            "privileged:\n  - SYS_ADMIN\n  - DAC_READ_SEARCH",
        ),
        "config invariant",
    )
    for forbidden in (
        "codenotary:",
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
            "COPY icon.png /www/assets/icon.png",
        ),
        "Docker invariant",
    )
    if "fcgi" in dockerfile:
        raise RuntimeError("The unused FastCGI package must not be installed")

    if re.search(r"^\s*capability,\s*$", apparmor, flags=re.MULTILINE):
        raise RuntimeError("AppArmor must not grant every capability")
    if "flags=(attach_disconnected,mediate_deleted,complain)" not in apparmor:
        raise RuntimeError("The bounded diagnostic AppArmor profile must remain in complain mode")
    for forbidden_rule in (
        "  file,",
        "  /bin/** ix,",
        "  /sbin/** ix,",
        "  /usr/bin/** ix,",
        "  /usr/sbin/** ix,",
        "  /usr/local/bin/** ix,",
        "  /package/** ix,",
        "  /command/** ix,",
    ):
        if forbidden_rule in apparmor:
            raise RuntimeError(f"Broad AppArmor diagnostic rule: {forbidden_rule.strip()}")
    require(
        apparmor,
        (
            "capability dac_override,",
            "capability dac_read_search,",
            "capability setpcap,",
            "capability sys_admin,",
            "/data/** rwlk,",
            "/share/** rwlk,",
            "/media/** rwlk,",
            "/backup/** rwlk,",
            "audit /mnt/** rwlk,",
            "/etc/crontabs/** rwlk,",
            "/command/s6-svwait ix,",
            "/package/admin/s6-2.15.0.0/command/s6-svwait ix,",
            "/run/s6-rc:s6-rc-init:*/servicedirs/cron/run rix,",
            "/run/s6-rc:s6-rc-init:*/servicedirs/runner/run rix,",
            "/run/s6-rc:s6-rc-init:*/servicedirs/web/run rix,",
            "/usr/bin/rsync ix,",
            "/usr/bin/msmtp ix,",
            "/sbin/mount.cifs ix,",
        ),
        "AppArmor invariant",
    )
    if re.search(r"^\s*/mnt/\*\* rwlk,\s*$", apparmor, flags=re.MULTILINE):
        raise RuntimeError("Recursive /mnt access must retain its explicit audit qualifier")
    for forbidden in ("/config/**", "/addons/**", "/ssl/**"):
        if re.search(rf"^\s*{re.escape(forbidden)}", apparmor, flags=re.MULTILINE):
            raise RuntimeError(f"Overbroad AppArmor rule: {forbidden}")

    if "--tls-certcheck=on" not in manager or "--tls-certcheck=off" in manager:
        raise RuntimeError("SMTP certificate verification must remain enabled")
    require(
        cron,
        (
            'if (.enabled | type) == \\"boolean\\" then .enabled else true end',
            'Job $JOB_ID ($NAME) ignoré: désactivé.',
        ),
        "disabled cron job invariant",
    )
    require(
        manager,
        (
            'if [ "$TRIGGER" = "cron" ]',
            "Exécution cron ignorée pour le job désactivé",
        ),
        "disabled cron execution invariant",
    )

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
            'href="assets/app.css"',
            'src="assets/app.js"',
            'src="assets/icon.png"',
            'class="site-header"',
            'class="metrics"',
            'id="job-drawer-shell"',
            'id="log-drawer-shell"',
            'id="language-toggle"',
            'id="theme-toggle"',
        ),
        "frontend shell invariant",
    )
    require(
        frontend_css,
        (
            "--cyan:#058caf",
            "html[data-theme=dark]",
            ".drawer-shell",
            ".endpoint-grid",
            "@media(max-width:620px)",
        ),
        "frontend style invariant",
    )
    require(
        frontend_js,
        (
            "rsync-manager-language",
            "navigator.language",
            "function applyLanguage()",
            "toLocaleString(language==='en'?'en-GB':'fr-FR')",
            "save_jobs",
            "test_email",
            "mount_test",
            "get_log",
            "importConfig",
            "exportConfig",
        ),
        "frontend behavior invariant",
    )
    if "bootstrap" in index.lower():
        raise RuntimeError("The redesigned Ingress UI must not depend on Bootstrap")
    if any("cdn.jsdelivr.net" in asset for asset in (index, frontend_css, frontend_js)):
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
