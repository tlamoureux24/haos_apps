#!/usr/bin/env python3
"""Pin a new Claude Code release and bump the Claude Remote App patch version.

The SHA-512 digests are the npm registry integrity values of the musl platform
tarballs, converted to hex for `sha512sum -c`.
"""

from __future__ import annotations

import argparse
import base64
import json
import pathlib
import re
import urllib.request


ROOT = pathlib.Path(__file__).resolve().parents[1]
REGISTRY = "https://registry.npmjs.org/@anthropic-ai%2fclaude-code-linux-{arch}-musl/{version}"


def replace_one(path: pathlib.Path, pattern: str, replacement: str) -> None:
    text = path.read_text(encoding="utf-8")
    updated, count = re.subn(pattern, replacement, text, count=1, flags=re.MULTILINE)
    if count != 1:
        raise RuntimeError(f"Expected one replacement in {path}: {pattern}")
    path.write_text(updated, encoding="utf-8")


def musl_sha512(arch: str, version: str) -> str:
    with urllib.request.urlopen(REGISTRY.format(arch=arch, version=version), timeout=30) as response:
        metadata = json.load(response)
    integrity = metadata["dist"]["integrity"]
    if not integrity.startswith("sha512-"):
        raise RuntimeError(f"Unexpected integrity format for {arch}: {integrity[:16]}")
    return base64.b64decode(integrity[len("sha512-"):]).hex()


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--claude-code", required=True, help="Claude Code version, for example 2.1.319")
    args = parser.parse_args()
    version = args.claude_code
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise RuntimeError(f"Unsupported Claude Code version: {version}")

    digests = {"AMD64": musl_sha512("x64", version), "AARCH64": musl_sha512("arm64", version)}

    config = ROOT / "config.yaml"
    match = re.search(r'^version: "(\d+\.\d+\.)(\d+)"$', config.read_text(encoding="utf-8"), re.MULTILINE)
    if not match:
        raise RuntimeError("Expected a semantic App version in config.yaml")
    next_version = f"{match.group(1)}{int(match.group(2)) + 1}"

    dockerfile = ROOT / "Dockerfile"
    replace_one(dockerfile, r'^ARG CLAUDE_CODE_VERSION="[^"]+"$', f'ARG CLAUDE_CODE_VERSION="{version}"')
    for arch, digest in digests.items():
        replace_one(dockerfile, rf'^ARG CLAUDE_CODE_SHA512_{arch}="[^"]+"$', f'ARG CLAUDE_CODE_SHA512_{arch}="{digest}"')
    replace_one(config, r'^version: "[^"]+"$', f'version: "{next_version}"')

    changelog = ROOT / "CHANGELOG.md"
    text = changelog.read_text(encoding="utf-8")
    entry = f"\n## {next_version}\n\n- Update Claude Code to {version}.\n"
    changelog.write_text(text.replace("# Changelog\n", "# Changelog\n" + entry, 1), encoding="utf-8")
    print(next_version)


if __name__ == "__main__":
    main()
