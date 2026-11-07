#!/usr/bin/env python3
"""Update the pinned stable NPM version, image digest and package metadata."""

from __future__ import annotations

import datetime as dt
import pathlib
import re
import sys


ROOT = pathlib.Path(__file__).resolve().parents[1]
SEMVER = re.compile(r"^(\d+)\.(\d+)\.(\d+)$")
DIGEST = re.compile(r"^sha256:[0-9a-f]{64}$")
DIGEST_ARG = re.compile(r'^ARG NPM_DIGEST="(?:@(sha256:[0-9a-f]{64}))?"$', re.MULTILINE)

# Exit code used when an already pinned upstream tag now resolves to another
# image. Released tags must not change silently: this needs a human decision.
EXIT_DIGEST_DRIFT = 3


def replace_once(path: pathlib.Path, pattern: str, replacement: str) -> None:
    content = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, content, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected exactly one matching field in {path}")
    path.write_text(updated, encoding="utf-8")


def pinned_digest() -> str:
    matches = DIGEST_ARG.findall((ROOT / "Dockerfile").read_text(encoding="utf-8"))
    if len(matches) != 1:
        raise RuntimeError("Expected exactly one valid ARG NPM_DIGEST in Dockerfile")
    return matches[0]


def add_changelog_entry(package: str, lines: list[str]) -> None:
    changelog = ROOT / "CHANGELOG.md"
    existing = changelog.read_text(encoding="utf-8")
    if not existing.startswith("# Changelog\n\n"):
        raise RuntimeError("Unexpected CHANGELOG.md header")
    date = dt.datetime.now(dt.UTC).date().isoformat()
    entry = f"## {package} - {date}\n\n" + "".join(f"- {line}\n" for line in lines) + "\n"
    changelog.write_text("# Changelog\n\n" + entry + existing[len("# Changelog\n\n"):], encoding="utf-8")


def write_package(upstream: str, package: str, digest: str) -> None:
    replace_once(ROOT / "Dockerfile", r'^ARG NPM_VERSION="[^"]+"$', f'ARG NPM_VERSION="{upstream}"')
    replace_once(ROOT / "Dockerfile", r'^ARG NPM_DIGEST="[^"]*"$', f'ARG NPM_DIGEST="@{digest}"')
    replace_once(ROOT / "Dockerfile", r'^ARG BUILD_VERSION="[^"]+"$', f'ARG BUILD_VERSION="{package}"')
    replace_once(ROOT / "config.yaml", r'^version: "[^"]+"$', f'version: "{package}"')
    (ROOT / "upstream_version").write_text(f"{upstream}\n", encoding="utf-8")


def main() -> int:
    if len(sys.argv) != 3:
        print(f"Usage: {sys.argv[0]} VERSION sha256:DIGEST", file=sys.stderr)
        return 2

    upstream = sys.argv[1].removeprefix("v")
    digest = sys.argv[2].removeprefix("@")
    if not SEMVER.fullmatch(upstream):
        print(f"Refusing non-stable semantic version: {upstream}", file=sys.stderr)
        return 2
    if not DIGEST.fullmatch(digest):
        print(f"Refusing invalid image digest: {digest}", file=sys.stderr)
        return 2

    current = (ROOT / "upstream_version").read_text(encoding="utf-8").strip()
    if not SEMVER.fullmatch(current):
        print(f"Current pinned version is invalid: {current}", file=sys.stderr)
        return 2
    current_digest = pinned_digest()
    current_parts = tuple(int(part) for part in current.split("."))
    upstream_parts = tuple(int(part) for part in upstream.split("."))
    if upstream_parts < current_parts:
        print(f"Refusing to downgrade NPM {current} -> {upstream}", file=sys.stderr)
        return 2

    if upstream == current:
        if current_digest == digest:
            print(f"NPM {upstream} is already pinned to {digest}")
            return 0
        if current_digest:
            print(
                f"Upstream tag {upstream} moved from {current_digest} to {digest}; "
                "refusing to follow it automatically",
                file=sys.stderr,
            )
            return EXIT_DIGEST_DRIFT

        # First digest pin of the current version: same upstream image, new
        # package revision so Home Assistant receives the rebuilt wrapper.
        config = (ROOT / "config.yaml").read_text(encoding="utf-8")
        revision = re.search(rf'^version: "{re.escape(current)}-(\d+)"$', config, flags=re.MULTILINE)
        if revision is None:
            raise RuntimeError("Cannot read the current package revision")
        package = f"{upstream}-{int(revision.group(1)) + 1}"
        write_package(upstream, package, digest)
        add_changelog_entry(
            package,
            [
                f"Pin the official Nginx Proxy Manager `{upstream}` image by its "
                f"multi-architecture digest `{digest}`.",
                "The upstream image content is unchanged.",
            ],
        )
        print(f"Pinned NPM {upstream} to {digest}; app version {package}")
        return 0

    package = f"{upstream}-1"
    write_package(upstream, package, digest)
    add_changelog_entry(
        package,
        [
            f"Update the official Nginx Proxy Manager image from `{current}` to `{upstream}`.",
            f"Pin the image by its multi-architecture digest `{digest}`.",
            "Reset the Home Assistant package revision to `1`.",
        ],
    )
    print(f"Updated NPM {current} -> {upstream} ({digest}); app version {package}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
