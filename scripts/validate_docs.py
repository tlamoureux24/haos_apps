#!/usr/bin/env python3
"""Validate repository Markdown without building any Home Assistant App."""

from __future__ import annotations

import re
import subprocess
from pathlib import Path
from urllib.parse import unquote


ROOT = Path(__file__).resolve().parents[1]
LINK = re.compile(r"!?(?:\[[^\]]*\])\(([^)]+)\)")
STALE_RELEASE_LABELS = (
    re.compile(r"^Current release:\s*\*\*[0-9]+\.[0-9]+\.[0-9]+", re.MULTILINE),
    re.compile(r"^Version actuelle\s*:\s*\*\*[0-9]+\.[0-9]+\.[0-9]+", re.MULTILINE),
)
USER_DOCS = {
    ROOT / app / name
    for app in ("agent_control_plane", "agent_execution_plane", "mcp_capability_bridge")
    for name in ("README.md", "README.fr.md", "DOCS.md")
}


def markdown_files() -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "*.md"], cwd=ROOT, check=True,
        text=True, capture_output=True,
    )
    return [ROOT / line for line in result.stdout.splitlines() if line]


def local_target(document: Path, raw_target: str) -> Path | None:
    target = raw_target.strip()
    if target.startswith("<") and target.endswith(">"):
        target = target[1:-1]
    if not target or target.startswith(("#", "http://", "https://", "mailto:")):
        return None
    target = unquote(target.split("#", 1)[0].split("?", 1)[0])
    if not target:
        return None
    return (document.parent / target).resolve()


def main() -> None:
    errors: list[str] = []
    documents = markdown_files()
    for document in documents:
        try:
            content = document.read_text(encoding="utf-8")
        except UnicodeDecodeError as error:
            errors.append(f"{document.relative_to(ROOT)}: invalid UTF-8: {error}")
            continue
        for match in LINK.finditer(content):
            target = local_target(document, match.group(1))
            if target is None:
                continue
            try:
                target.relative_to(ROOT)
            except ValueError:
                errors.append(
                    f"{document.relative_to(ROOT)}: local link leaves repository: {match.group(1)}"
                )
                continue
            if not target.exists():
                errors.append(
                    f"{document.relative_to(ROOT)}: missing local link target: {match.group(1)}"
                )
        if document in USER_DOCS:
            for pattern in STALE_RELEASE_LABELS:
                if pattern.search(content):
                    errors.append(
                        f"{document.relative_to(ROOT)}: current App version must come from config.yaml"
                    )
    if errors:
        raise SystemExit("Documentation validation failed:\n- " + "\n- ".join(errors))
    print(f"Validated {len(documents)} Markdown files and local link targets")


if __name__ == "__main__":
    main()
