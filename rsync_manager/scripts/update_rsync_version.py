#!/usr/bin/env python3
"""Record a new Alpine rsync package and increment the Home Assistant App."""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
PACKAGE = re.compile(r"^\d+\.\d+\.\d+-r\d+$")
APP_VERSION = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")


def replace_once(path: pathlib.Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected exactly one version field in {path}")
    path.write_text(updated, encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} RSYNC_PACKAGE_VERSION", file=sys.stderr)
        return 2

    package = sys.argv[1]
    if not PACKAGE.fullmatch(package):
        print(f"Unsupported Alpine rsync package version: {package}", file=sys.stderr)
        return 2

    package_file = ROOT / "rsync_package_version"
    current_package = package_file.read_text(encoding="utf-8").strip()
    if current_package == package:
        print(f"rsync package {package} is already recorded")
        return 0
    if not PACKAGE.fullmatch(current_package):
        raise RuntimeError(f"Invalid recorded rsync package: {current_package}")

    config = (ROOT / "config.yaml").read_text(encoding="utf-8")
    current_app = re.search(r'^version: "([^"]+)"$', config, flags=re.MULTILINE)
    if current_app is None or not APP_VERSION.fullmatch(current_app.group(1)):
        raise RuntimeError("Invalid current Home Assistant App version")
    major, minor, patch = map(int, current_app.group(1).split("."))
    new_app = f"{major}.{minor}.{patch + 1}"

    replace_once(ROOT / "config.yaml", r'^version: "[^"]+"$', f'version: "{new_app}"')
    replace_once(
        ROOT / "Dockerfile",
        r'^ARG BUILD_VERSION="[^"]+"$',
        f'ARG BUILD_VERSION="{new_app}"',
    )
    package_file.write_text(f"{package}\n", encoding="utf-8")

    changelog = ROOT / "CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8")
    if not existing.startswith("# Changelog\n\n"):
        raise RuntimeError("Unexpected CHANGELOG.md header")
    date = dt.datetime.now(dt.UTC).date().isoformat()
    entry = (
        f"## {new_app} - {date}\n\n"
        f"- Update the Alpine rsync package from {current_package} to {package}.\n\n"
    )
    changelog.write_text(
        "# Changelog\n\n" + entry + existing[len("# Changelog\n\n"):],
        encoding="utf-8",
    )

    print(
        f"Updated rsync package {current_package} -> {package}; "
        f"Home Assistant App {current_app.group(1)} -> {new_app}"
    )
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (OSError, RuntimeError) as err:
        print(f"Update failed: {err}", file=sys.stderr)
        raise SystemExit(1) from err
