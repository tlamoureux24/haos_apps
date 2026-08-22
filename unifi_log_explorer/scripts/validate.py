#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[1]
errors = []

config_text = (ROOT / "config.yaml").read_text()
top_level = set(re.findall(r"^([a-z_]+):", config_text, re.MULTILINE))
required = {"name", "slug", "version", "description", "arch", "ports", "options", "schema"}
missing = sorted(required - top_level)
if missing:
    errors.append(f"config.yaml missing: {', '.join(missing)}")
if not re.search(r'^slug: "unifi_log_explorer"$', config_text, re.MULTILINE):
    errors.append("unexpected slug")
if not re.search(r'^version: "1\.1\.4"$', config_text, re.MULTILINE):
    errors.append("App version must be 1.1.4")
for expected in ('ingress: true', 'ingress_port: 8090', 'panel_title: "UniFi Log Explorer"',
                 'panel_icon: "mdi:file-search-outline"', 'panel_admin: true'):
    if expected not in config_text:
        errors.append(f"missing Ingress setting: {expected}")
if re.search(r"^webui:", config_text, re.MULTILINE):
    errors.append("direct webui must remain disabled")
if not re.search(r"^  8090/tcp: null$", config_text, re.MULTILINE):
    errors.append("TCP port 8090 must not be published")
if not re.search(r"^  5514/udp: 5514$", config_text, re.MULTILINE):
    errors.append("UDP port 5514 must remain published")
if 'watchdog: "http://[HOST]:[PORT:8090]/health"' not in config_text:
    errors.append("watchdog must continue to use internal port 8090 /health")
if not re.search(r'^\s+- "192\.168\.1\.1"$', config_text, re.MULTILINE):
    errors.append("default allowed source must be 192.168.1.1")
for port in ("8090/tcp", "5514/udp"):
    if not re.search(rf"^\s+{re.escape(port)}:", config_text, re.MULTILINE):
        errors.append(f"missing port {port}")
for filename in ("Dockerfile", "run.sh", "apparmor.txt", "README.md", "README.fr.md", "DOCS.md", "CHANGELOG.md", "unifi_log_explorer.py", "icon.png", "logo.png"):
    if not (ROOT / filename).is_file():
        errors.append(f"missing {filename}")
if not (ROOT / "tests" / "test_unifi_log_explorer.py").is_file():
    errors.append("missing tests/test_unifi_log_explorer.py")
if not (ROOT / "scripts" / "validate_apparmor_inventory.py").is_file():
    errors.append("missing scripts/validate_apparmor_inventory.py")
dockerfile = (ROOT / "Dockerfile").read_text()
apparmor = (ROOT / "apparmor.txt").read_text()
if re.search(r"^COPY\s+(?:tests|\.)", dockerfile, re.MULTILINE):
    errors.append("development tests must not be copied into the runtime image")

for broad_rule in (
    "  capability,", "  file,", "  network,", "/bin/** ix,", "/sbin/** ix,",
    "/usr/bin/** ix,", "/usr/sbin/** ix,", "/usr/local/bin/** ix,",
    "/run/{s6,s6-rc*,service}/** ix,", "/package/** ix,", "/command/** ix,",
    "/etc/services.d/** rwix,", "/etc/cont-init.d/** rwix,",
    "/etc/cont-finish.d/** rwix,", "/run/{,**} rwk,", "/data/** rwk,",
):
    if broad_rule in apparmor:
        errors.append(f"AppArmor retains broad rule: {broad_rule.strip()}")
enforced_profile = "profile unifi_log_explorer flags=(attach_disconnected,mediate_deleted) {"
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
    "/data/ rw,", "/data/options.json r,", "/data/diagnostics.db rwlk,",
    "/data/diagnostics.db-{journal,shm,wal} rwlk,",
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
    "/init rix,", "/bin/sh ix,", "/usr/bin/python3 ix,",
    "/usr/bin/with-contenv rix,", "/command/execlineb ix,",
    "/command/s6-rc-compile ix,", "/command/s6-supervise ix,",
    "/command/s6-svscan ix,",
    "/package/admin/s6-linux-init/command/s6-linux-init-hpr ix,",
    "/package/admin/s6-linux-init-1.2.0.1/command/s6-linux-init-hpr ix,",
    "/run.sh rix,",
):
    if executable_rule not in apparmor:
        errors.append(f"missing targeted AppArmor executable rule: {executable_rule}")

if errors:
    print("\n".join(f"ERROR: {error}" for error in errors))
    sys.exit(1)
print("UniFi Log Explorer validation passed")
