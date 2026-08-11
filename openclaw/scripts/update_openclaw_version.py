#!/usr/bin/env python3
"""Update the pinned stable OpenClaw image and Home Assistant metadata."""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
VERSION = re.compile(r"^(\d{4})\.(\d{1,2})\.(\d{1,2})$")


def replace_once(path: pathlib.Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected exactly one version field in {path}")
    path.write_text(updated, encoding="utf-8")


def version_key(value: str) -> tuple[int, int, int]:
    match = VERSION.fullmatch(value)
    if not match:
        raise ValueError(value)
    return tuple(int(part) for part in match.groups())


def main() -> int:
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} VERSION", file=sys.stderr)
        return 2

    upstream = sys.argv[1].removeprefix("v")
    try:
        incoming_key = version_key(upstream)
    except ValueError:
        print(f"Refusing unsupported or non-stable version: {upstream}", file=sys.stderr)
        return 2

    current = (ROOT / "upstream_version").read_text(encoding="utf-8").strip()
    if current == upstream:
        print(f"OpenClaw {upstream} is already pinned")
        return 0
    try:
        current_key = version_key(current)
    except ValueError:
        print(f"Current pinned version is invalid: {current}", file=sys.stderr)
        return 2
    if incoming_key < current_key:
        print(f"Refusing to downgrade OpenClaw {current} -> {upstream}", file=sys.stderr)
        return 2

    package = f"{upstream}.1"
    replace_once(ROOT / "Dockerfile", r'^ARG BUILD_FROM="[^\"]+"$', f'ARG BUILD_FROM="ghcr.io/openclaw/openclaw:{upstream}"')
    replace_once(ROOT / "Dockerfile", r'^ARG OPENCLAW_VERSION="[^\"]+"$', f'ARG OPENCLAW_VERSION="{upstream}"')
    replace_once(ROOT / "Dockerfile", r'^ARG BUILD_VERSION="[^\"]+"$', f'ARG BUILD_VERSION="{package}"')
    replace_once(ROOT / "build.yaml", r'^(  amd64: )\S+$', rf'\g<1>ghcr.io/openclaw/openclaw:{upstream}')
    replace_once(ROOT / "build.yaml", r'^(  aarch64: )\S+$', rf'\g<1>ghcr.io/openclaw/openclaw:{upstream}')
    replace_once(ROOT / "config.yaml", r'^version: "[^\"]+"$', f'version: "{package}"')
    (ROOT / "upstream_version").write_text(f"{upstream}\n", encoding="utf-8")

    changelog = ROOT / "CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8")
    if not existing.startswith("# Changelog\n\n"):
        raise RuntimeError("Unexpected CHANGELOG.md header")
    date = dt.datetime.now(dt.UTC).date().isoformat()
    entry = (
        f"## {package} - {date}\n\n"
        f"- Update the official OpenClaw image from `{current}` to `{upstream}`.\n"
        "- Reset the Home Assistant package revision to `1`.\n\n"
    )
    changelog.write_text(
        "# Changelog\n\n" + entry + existing[len("# Changelog\n\n"):],
        encoding="utf-8",
    )
    print(f"Updated OpenClaw {current} -> {upstream}; app version {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
