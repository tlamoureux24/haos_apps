#!/usr/bin/env python3
"""Validate the Gatus Home Assistant package without third-party modules."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"
EXPECTED_ASSETS = {
    "icon.png": "d21db796b9ef3a114115b49f4c95f3433647664fcefffc862bf17e80a67a93f7",
    "logo.png": "8e1c8efcedea42d09c253d50dd6504dced7ffcfd55217e188a57220e2a5635f8",
}
SECRET_VARIABLES = (
    "GATUS_SMS_USER",
    "GATUS_SMS_PASSWORD",
    "GATUS_EMAIL_FROM",
    "GATUS_EMAIL_USERNAME",
    "GATUS_EMAIL_PASSWORD",
    "GATUS_EMAIL_HOST",
    "GATUS_EMAIL_PORT",
    "GATUS_EMAIL_TO",
)


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
    sample = (ROOT / "config.example.yaml").read_text(encoding="utf-8")
    launcher = (ROOT / "run.sh").read_text(encoding="utf-8")

    docker_upstream = match_one(
        r'^ARG GATUS_VERSION="([^"]+)"$',
        dockerfile,
        "Docker Gatus version",
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
        raise RuntimeError(f"Docker Gatus version {docker_upstream} != {upstream}")
    if docker_package != config_package or not package_pattern.fullmatch(config_package):
        raise RuntimeError(
            f"Package versions must match {upstream}-REVISION: "
            f"Docker={docker_package}, config={config_package}"
        )

    required_config = (
        'slug: "gatus"',
        "  - aarch64",
        "  - amd64",
        "init: false",
        "apparmor: true",
        "backup: cold",
        'watchdog: "http://[HOST]:[PORT:8080]/"',
        "  8080/tcp: 8080",
        "  - type: addon_config",
        "    read_only: false",
    )
    for item in required_config:
        if item not in config:
            raise RuntimeError(f"Missing config invariant: {item}")

    forbidden_config_keys = (
        "webui:",
        "ingress:",
        "host_network:",
        "privileged:",
        "hassio_api:",
        "homeassistant_api:",
    )
    for key in forbidden_config_keys:
        if re.search(rf"^{re.escape(key)}", config, flags=re.MULTILINE):
            raise RuntimeError(f"Forbidden config key: {key}")

    if "concurrency: 0" not in sample or "disable-monitoring-lock" in sample:
        raise RuntimeError("Initial configuration must use concurrency: 0")
    if not sample.startswith(
        "# Official configuration documentation: https://github.com/TwiN/gatus#configuration\n"
    ):
        raise RuntimeError("Initial configuration must start with the official documentation link")
    if "Optional persistent history" in sample or re.search(
        r"^\s*storage:", sample, flags=re.MULTILINE
    ):
        raise RuntimeError("Initial configuration must not include a storage example")
    if "endpoints: []" not in sample or re.search(
        r'^\s+url:\s*"(?:icmp|https?)://', sample, flags=re.MULTILINE
    ):
        raise RuntimeError("Initial configuration must not disclose network endpoints")
    if re.search(r"^\s+custom:", sample, flags=re.MULTILINE):
        raise RuntimeError("Free Mobile custom alerting must remain commented")
    if "#   - name: Example ICMP" not in sample or "#   - name: Example HTTPS" not in sample:
        raise RuntimeError("Initial configuration must include commented endpoint examples")
    if "&msg=" not in sample:
        raise RuntimeError("Free Mobile URL must include the msg query parameter")

    for variable in SECRET_VARIABLES:
        placeholder = "${" + variable + "}"
        if placeholder not in sample:
            raise RuntimeError(f"Missing Gatus placeholder: {placeholder}")
        if variable not in launcher:
            raise RuntimeError(f"Launcher does not export {variable}")

    if "exec su-exec gatus:gatus /usr/local/bin/gatus" not in launcher:
        raise RuntimeError("Launcher must drop root before starting Gatus")
    if "NET_RAW" in config or "NET_RAW" in launcher:
        raise RuntimeError("Gatus must use unprivileged ICMP without NET_RAW")
    if re.search(r"bashio::log\.[a-z]+.*GATUS_(?:SMS|EMAIL)", launcher):
        raise RuntimeError("Launcher must not log secret environment variables")

    for filename, expected in EXPECTED_ASSETS.items():
        actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unexpected {filename} checksum: {actual}")

    print(f"Validated Gatus {upstream}, Home Assistant app {config_package}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
