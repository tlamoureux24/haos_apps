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
dockerfile = (ROOT / "Dockerfile").read_text()
if re.search(r"^COPY\s+(?:tests|\.)", dockerfile, re.MULTILINE):
    errors.append("development tests must not be copied into the runtime image")

if errors:
    print("\n".join(f"ERROR: {error}" for error in errors))
    sys.exit(1)
print("UniFi Log Explorer validation passed")
