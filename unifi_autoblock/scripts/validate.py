#!/usr/bin/env python3
"""Validate UniFi Autoblock repository and AppArmor diagnostic invariants."""

from __future__ import annotations

from pathlib import Path
import re
import sys


ROOT = Path(__file__).resolve().parents[1]
errors: list[str] = []
config = (ROOT / "config.yaml").read_text(encoding="utf-8")
dockerfile = (ROOT / "Dockerfile").read_text(encoding="utf-8")
launcher = (ROOT / "run.sh").read_text(encoding="utf-8")
apparmor = (ROOT / "apparmor.txt").read_text(encoding="utf-8")

for invariant in (
    'slug: "unifi_autoblock"', 'version: "0.5.3"', "apparmor: true",
    "tmpfs: true", "hassio_api: true", "homeassistant_api: true",
    "ingress: true", "ingress_port: 8099",
):
    if invariant not in config:
        errors.append(f"missing config invariant: {invariant}")
for filename in (
    "Dockerfile", "run.sh", "apparmor.txt", "README.md", "README.fr.md",
    "DOCS.md", "CHANGELOG.md", "unifi_autoblock.py", "ingress_ui.py",
    "icon.png", "logo.png",
):
    if not (ROOT / filename).is_file():
        errors.append(f"missing {filename}")
if re.search(r"^COPY\s+(?:tests|\.)", dockerfile, re.MULTILINE):
    errors.append("development tests must not be copied into the runtime image")
if not launcher.startswith("#!/usr/bin/with-contenv bashio\n"):
    errors.append("launcher must preserve the s6 environment through Bashio")

for broad_rule in (
    "  capability,", "  file,", "  network,", "/bin/** ix,", "/sbin/** ix,",
    "/usr/bin/** ix,", "/usr/sbin/** ix,", "/usr/local/bin/** ix,",
    "/run/{s6,s6-rc*,service}/** ix,", "/package/** ix,", "/command/** ix,",
    "/etc/services.d/** rwix,", "/etc/cont-init.d/** rwix,",
    "/etc/cont-finish.d/** rwix,", "/run/{,**} rwk,", "/data/** rwk,",
):
    if broad_rule in apparmor:
        errors.append(f"AppArmor retains broad rule: {broad_rule.strip()}")
enforced_profile = "profile unifi_autoblock flags=(attach_disconnected,mediate_deleted) {"
if enforced_profile not in apparmor:
    errors.append("the final AppArmor profile must run in enforce mode")
if "complain" in apparmor:
    errors.append("the accepted AppArmor profile must not return to complain mode")
for network_rule in (
    "network inet stream,", "network inet6 stream,",
    "network inet dgram,", "network inet6 dgram,",
):
    if network_rule not in apparmor:
        errors.append(f"missing required AppArmor network rule: {network_rule}")
for data_rule in (
    "/data/ rw,", "/data/options.json r,", "/data/state.json rwlk,",
    "/data/state.json.tmp rwlk,", "/data/history.json rwlk,",
    "/data/history.json.tmp rwlk,",
    "/data/last_traffic_matching_list_backup.json rwlk,",
    "/data/last_traffic_matching_list_backup.json.tmp rwlk,",
    "/data/unifi_api_key.enc rwlk,", "/data/unifi_api_key.enc.tmp rwlk,",
    "/data/unifi_api_key.key rwlk,", "/data/unifi_api_key.key.tmp rwlk,",
):
    if data_rule not in apparmor:
        errors.append(f"missing exact AppArmor data rule: {data_rule}")
for runtime_rule in (
    "/run/ rw,", "/run/s6/{,**} rwk,", "/run/s6-rc rw,",
    "/run/s6-rc:s6-rc-init:*/{,**} rwk,", "/run/service/{,**} rwk,",
    "/run/s6-linux-init-container-results/{,**} rwk,",
):
    if runtime_rule not in apparmor:
        errors.append(f"missing bounded AppArmor runtime rule: {runtime_rule}")
for executable_rule in (
    "/init rix,", "/bin/bash ix,", "/bin/sh ix,",
    "/usr/bin/bashio rix,", "/usr/lib/bashio/bashio rix,",
    "/usr/bin/curl ix,", "/usr/bin/jq ix,",
    "/usr/bin/python3 ix,", "/usr/bin/with-contenv rix,",
    "/command/execlineb ix,", "/command/s6-rc-compile ix,",
    "/command/s6-supervise ix,", "/command/s6-svscan ix,",
    "/package/admin/s6-linux-init/command/s6-linux-init-hpr ix,",
    "/package/admin/s6-linux-init-1.2.0.1/command/s6-linux-init-hpr ix,",
    "/run.sh rix,",
):
    if executable_rule not in apparmor:
        errors.append(f"missing targeted AppArmor executable rule: {executable_rule}")
for audited_common_rule in (
    "/etc/fix-attrs.d/ r,", "/etc/services.d/ r,",
    "/sys/fs/cgroup/cpu.max r,", "deny /dev/tty rw,",
):
    if audited_common_rule not in apparmor:
        errors.append(f"missing common HAOS-audited rule: {audited_common_rule}")
if 'export PYTHONDONTWRITEBYTECODE="1"' not in launcher:
    errors.append("runtime must not write Python bytecode inside /app")
if "/app/** w" in apparmor or "/app/** rw" in apparmor or "/app/__pycache__" in apparmor:
    errors.append("AppArmor must keep the application tree read-only")

if errors:
    print("\n".join(f"ERROR: {error}" for error in errors))
    raise SystemExit(1)
print("UniFi Autoblock validation passed")
