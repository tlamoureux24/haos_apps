#!/usr/bin/env python3
"""Update tracked runtimes and bump the experimental App patch version."""

from __future__ import annotations

import argparse
import pathlib
import re


ROOT = pathlib.Path(__file__).resolve().parents[1]


def replace_one(path: pathlib.Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one replacement in {path}: {pattern}")
    path.write_text(updated, encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--code-server", required=True)
    parser.add_argument("--codex", required=True)
    parser.add_argument("--ha-cli", required=True)
    args = parser.parse_args()

    for value in (args.code_server, args.codex, args.ha_cli):
        if not re.fullmatch(r"\d+\.\d+\.\d+", value):
            raise RuntimeError(f"Unsupported upstream version: {value}")

    config = ROOT / "config.yaml"
    current_text = config.read_text(encoding="utf-8")
    match = re.search(r'^version: "(0\.1\.)(\d+)"$', current_text, re.MULTILINE)
    if not match:
        raise RuntimeError("Expected an experimental 0.1.x App version")
    next_version = f"{match.group(1)}{int(match.group(2)) + 1}"

    dockerfile = ROOT / "Dockerfile"
    replace_one(dockerfile, r'^ARG BUILD_VERSION="[^"]+"$', f'ARG BUILD_VERSION="{next_version}"')
    replace_one(dockerfile, r'^ARG CODE_SERVER_VERSION="[^"]+"$', f'ARG CODE_SERVER_VERSION="{args.code_server}"')
    replace_one(dockerfile, r'^ARG CODEX_VERSION="[^"]+"$', f'ARG CODEX_VERSION="{args.codex}"')
    replace_one(dockerfile, r'^ARG HA_CLI_VERSION="[^"]+"$', f'ARG HA_CLI_VERSION="{args.ha_cli}"')
    replace_one(config, r'^version: "[^"]+"$', f'version: "{next_version}"')

    versions = ROOT / "upstream_versions"
    replace_one(versions, r'^code-server=.*$', f'code-server={args.code_server}')
    replace_one(versions, r'^codex=.*$', f'codex={args.codex}')
    replace_one(versions, r'^ha-cli=.*$', f'ha-cli={args.ha_cli}')

    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    entry = (
        f"\n## {next_version}\n\n"
        f"- Update code-server to {args.code_server}.\n"
        f"- Update Codex CLI to {args.codex}.\n"
        f"- Update Home Assistant CLI to {args.ha_cli}.\n"
    )
    changelog.write_text(text.replace("# Changelog\n", "# Changelog\n" + entry, 1), encoding="utf-8")
    print(next_version)


if __name__ == "__main__":
    main()
