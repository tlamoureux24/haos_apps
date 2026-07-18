#!/usr/bin/env python3
"""Validate the thin NPM Home Assistant package without third-party modules."""

from __future__ import annotations

import hashlib
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = r"\d+\.\d+\.\d+"
EXPECTED_ASSETS = {
    "icon.png": "59faeaf2ca438f177416490584af465b29fd5b5c9499d895ad999a87e8a9c37c",
    "logo.png": "faf5a1dc594cc1536f6a10761cd599023f076e0f19a9ac6c6b5abdcec461a94d",
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
    docker_upstream = match_one(r'^ARG NPM_VERSION="([^"]+)"$', dockerfile, "Docker NPM version")
    docker_package = match_one(r'^ARG BUILD_VERSION="([^"]+)"$', dockerfile, "Docker app version")
    config_package = match_one(r'^version: "([^"]+)"$', config, "config app version")
    package_pattern = re.compile(rf"^{re.escape(upstream)}-(\d+)$")

    if docker_upstream != upstream:
        raise RuntimeError(f"Docker NPM version {docker_upstream} != {upstream}")
    if docker_package != config_package or not package_pattern.fullmatch(config_package):
        raise RuntimeError(
            f"Package versions must match {upstream}-REVISION: "
            f"Docker={docker_package}, config={config_package}"
        )

    required_config = (
        'slug: "nginx_proxy_manager"',
        "  - aarch64",
        "  - amd64",
        "init: false",
        "apparmor: true",
        "backup: cold",
        "  80/tcp: 80",
        "  81/tcp: 81",
        "  443/tcp: 443",
    )
    for item in required_config:
        if item not in config:
            raise RuntimeError(f"Missing config invariant: {item}")

    if re.search(r"^webui:", config, flags=re.MULTILINE):
        raise RuntimeError("webui must stay disabled to avoid generating an external admin URL")

    entrypoint = (ROOT / "entrypoint.sh").read_text(encoding="utf-8")
    if "/data/letsencrypt" not in entrypoint or "exec /init" not in entrypoint:
        raise RuntimeError("Entrypoint no longer guarantees persistent Let's Encrypt data")

    for filename, expected in EXPECTED_ASSETS.items():
        actual = hashlib.sha256((ROOT / filename).read_bytes()).hexdigest()
        if actual != expected:
            raise RuntimeError(f"Unexpected {filename} checksum: {actual}")

    print(f"Validated NPM {upstream}, Home Assistant app {config_package}")
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Validation failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
