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
if re.search(r"^ingress:\s*true", config_text, re.MULTILINE):
    errors.append("Ingress must remain disabled")
if not re.search(r'^\s+- "192\.168\.1\.1"$', config_text, re.MULTILINE):
    errors.append("default allowed source must be 192.168.1.1")
for port in ("8090/tcp", "5514/udp"):
    if not re.search(rf"^\s+{re.escape(port)}:", config_text, re.MULTILINE):
        errors.append(f"missing port {port}")
for filename in ("Dockerfile", "run.sh", "apparmor.txt", "README.md", "README.fr.md", "DOCS.md", "CHANGELOG.md", "unifi_log_explorer.py", "icon.png", "logo.png"):
    if not (ROOT / filename).is_file():
        errors.append(f"missing {filename}")

if errors:
    print("\n".join(f"ERROR: {error}" for error in errors))
    sys.exit(1)
print("UniFi Log Explorer validation passed")
