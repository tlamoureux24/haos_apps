#!/usr/bin/env python3
"""Refresh Apps built on the Home Assistant base image when Alpine packages change.

Released App images are immutable, so security fixes published by Alpine or by
the Home Assistant base image only reach installed Apps through a new App
version. The base refresh workflow rebuilds each App below, compares its Alpine
package database with the published image of the current version, and calls
``bump`` for the Apps whose packages changed.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
HA_BASE = "ghcr.io/home-assistant/base:"
VERSION = re.compile(r"^(?P<prefix>\d+\.\d+\.)(?P<patch>\d+)(?:-(?P<revision>\d+))?$")
CHANGELOG_HEADER = "# Changelog\n\n"
MAX_LISTED_CHANGES = 25

# Every file that carries the App version, relative to the App directory.
# `check` fails when a version occurrence appears anywhere else, so a new
# version location cannot be missed silently by an automatic bump.
VERSION_FILES: dict[str, tuple[str, ...]] = {
    "agent_control_plane": (
        "config.yaml",
        "scripts/validate.py",
        "src/agent_control_plane/__init__.py",
    ),
    "agent_execution_plane": (
        "config.yaml",
        "scripts/validate.py",
        "src/agent_execution_plane/__init__.py",
    ),
    "claude_remote": (
        "config.yaml",
    ),
    "mcp_capability_bridge": (
        "config.yaml",
        "scripts/validate.py",
        "src/mcp_capability_bridge/__init__.py",
        "tests/test_foundation.py",
    ),
    "rsync_manager": (
        "Dockerfile",
        "config.yaml",
        "rootfs/www/index.html",
    ),
    "unifi_autoblock": (
        "config.yaml",
        "scripts/validate.py",
    ),
    "unifi_log_explorer": (
        "config.yaml",
        "scripts/validate.py",
    ),
}


def ha_base_apps() -> list[str]:
    found = []
    for dockerfile in sorted(ROOT.glob("*/Dockerfile")):
        lines = dockerfile.read_text(encoding="utf-8").splitlines()
        base = next((line.split()[1] for line in lines if line.startswith("FROM ")), "")
        if base.startswith(HA_BASE) and (dockerfile.parent / "config.yaml").is_file():
            found.append(dockerfile.parent.name)
    return found


def app_version(app: str) -> str:
    config = (ROOT / app / "config.yaml").read_text(encoding="utf-8")
    match = re.search(r'^version: "([^"]+)"$', config, re.MULTILINE)
    if match is None:
        raise SystemExit(f"{app}: cannot read version from config.yaml")
    return match[1]


def version_patterns(version: str) -> list[re.Pattern[str]]:
    """Match the version as plain text and as an escaped regular expression."""
    patterns = []
    for form in (re.escape(version), version):
        patterns.append(re.compile(rf"(?<![0-9.\\]){re.escape(form)}(?![0-9]|\\?\.[0-9])"))
    return patterns


def tracked_files(app: str) -> list[str]:
    output = subprocess.run(
        ["git", "ls-files", "--", app], cwd=ROOT, check=True, text=True, capture_output=True,
    ).stdout
    return [line[len(app) + 1:] for line in output.splitlines() if not line.endswith(".md")]


def check() -> list[str]:
    errors = []
    apps = ha_base_apps()
    for app in sorted(set(apps) - set(VERSION_FILES)):
        errors.append(f"{app}: built on the Home Assistant base but missing from VERSION_FILES")
    for app in sorted(set(VERSION_FILES) - set(apps)):
        errors.append(f"{app}: listed in VERSION_FILES but not built on the Home Assistant base")
    for app in sorted(set(apps) & set(VERSION_FILES)):
        version = app_version(app)
        if VERSION.fullmatch(version) is None:
            errors.append(f"{app}: unsupported version format {version}")
            continue
        patterns = version_patterns(version)
        holders = set()
        for name in tracked_files(app):
            try:
                text = (ROOT / app / name).read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            if any(pattern.search(text) for pattern in patterns):
                holders.add(name)
        expected = set(VERSION_FILES[app])
        for name in sorted(holders - expected):
            errors.append(f"{app}: {name} contains version {version} but is not in VERSION_FILES")
        for name in sorted(expected - holders):
            errors.append(f"{app}: {name} is in VERSION_FILES but does not contain version {version}")
    return errors


def packages(database: str) -> dict[str, str]:
    """Read name -> version from an Alpine /lib/apk/db/installed file."""
    result = {}
    for record in database.split("\n\n"):
        fields = dict(line.split(":", 1) for line in record.splitlines() if len(line) > 2 and line[1] == ":")
        if "P" in fields and "V" in fields:
            result[fields["P"]] = fields["V"]
    if not result:
        raise SystemExit("No Alpine package found in the database")
    return result


def diff(published: dict[str, str], fresh: dict[str, str]) -> list[dict[str, str]]:
    changes = []
    for name in sorted(set(published) | set(fresh)):
        before, after = published.get(name, ""), fresh.get(name, "")
        if before != after:
            changes.append({"package": name, "before": before, "after": after})
    return changes


def describe(change: dict[str, str]) -> str:
    name, before, after = change["package"], change["before"], change["after"]
    if not before:
        return f"`{name}` added (`{after}`)"
    if not after:
        return f"`{name}` removed (was `{before}`)"
    return f"`{name}` `{before}` → `{after}`"


def next_version(version: str) -> str:
    match = VERSION.fullmatch(version)
    if match is None:
        raise SystemExit(f"Unsupported version format: {version}")
    if match["revision"] is not None:
        return f"{match['prefix']}{match['patch']}-{int(match['revision']) + 1}"
    return f"{match['prefix']}{int(match['patch']) + 1}"


def changelog_entry(app: str, version: str, changes: list[dict[str, str]]) -> str:
    existing = (ROOT / app / "CHANGELOG.md").read_text(encoding="utf-8")
    dated = re.search(r"^## \S+ - \d{4}-\d{2}-\d{2}$", existing, re.MULTILINE) is not None
    heading = f"## {version}"
    if dated:
        heading += f" - {dt.datetime.now(dt.UTC).date().isoformat()}"
    lines = [
        heading,
        "",
        "- Rebuild on the current Home Assistant base image to pick up Alpine",
        "  package updates. The App code is unchanged.",
    ]
    for change in changes[:MAX_LISTED_CHANGES]:
        lines.append(f"  - {describe(change)}")
    if len(changes) > MAX_LISTED_CHANGES:
        lines.append(f"  - and {len(changes) - MAX_LISTED_CHANGES} more package changes")
    return "\n".join(lines) + "\n\n"


def bump(app: str, changes: list[dict[str, str]]) -> str:
    if app not in VERSION_FILES:
        raise SystemExit(f"{app}: not managed by the base refresh")
    if not changes:
        raise SystemExit(f"{app}: no package change to release")
    current = app_version(app)
    new = next_version(current)
    replacements = list(zip(version_patterns(current), (re.escape(new), new)))
    for name in VERSION_FILES[app]:
        path = ROOT / app / name
        text = path.read_text(encoding="utf-8")
        updated = text
        for pattern, value in replacements:
            updated = pattern.sub(value.replace("\\", "\\\\"), updated)
        if updated == text:
            raise SystemExit(f"{app}: {name} does not contain version {current}")
        path.write_text(updated, encoding="utf-8")

    changelog = ROOT / app / "CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8")
    if not existing.startswith(CHANGELOG_HEADER):
        raise SystemExit(f"{app}: unexpected CHANGELOG.md header")
    changelog.write_text(
        CHANGELOG_HEADER + changelog_entry(app, new, changes) + existing[len(CHANGELOG_HEADER):],
        encoding="utf-8",
    )
    return new


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    commands.add_parser("apps", help="print the Apps built on the Home Assistant base image")
    commands.add_parser("check", help="verify that every version location is known")
    compare = commands.add_parser("diff", help="compare two Alpine package databases")
    compare.add_argument("published", type=Path)
    compare.add_argument("fresh", type=Path)
    release = commands.add_parser("bump", help="release a new App version for package changes")
    release.add_argument("app")
    release.add_argument("changes", type=Path, help="JSON written by the diff command")
    args = parser.parse_args()

    if args.command == "apps":
        print(" ".join(ha_base_apps()))
    elif args.command == "check":
        errors = check()
        if errors:
            raise SystemExit("\n".join(errors))
        print(f"{len(VERSION_FILES)} Apps have known version locations")
    elif args.command == "diff":
        changes = diff(
            packages(args.published.read_text(encoding="utf-8")),
            packages(args.fresh.read_text(encoding="utf-8")),
        )
        json.dump(changes, sys.stdout, indent=2)
        print()
    elif args.command == "bump":
        changes = json.loads(args.changes.read_text(encoding="utf-8"))
        print(bump(args.app, changes))


if __name__ == "__main__":
    main()
