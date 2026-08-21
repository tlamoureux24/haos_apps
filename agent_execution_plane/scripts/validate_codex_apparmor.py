#!/usr/bin/env python3
"""Inventory Codex package executables and verify their targeted AppArmor rules."""

from __future__ import annotations

import argparse
import importlib.metadata
from pathlib import Path
import stat

CODEX_DISTRIBUTIONS = ("openai-codex", "openai-codex-cli-bin")
EXECUTABLE_MAGIC = (b"\x7fELF", b"#!")


def package_executables() -> tuple[Path, ...]:
    candidates: set[Path] = set()
    missing_mode: list[Path] = []
    for name in CODEX_DISTRIBUTIONS:
        distribution = importlib.metadata.distribution(name)
        for relative in distribution.files or ():
            path = Path(distribution.locate_file(relative)).resolve()
            if not path.is_file():
                continue
            with path.open("rb") as stream:
                magic = stream.read(4)
            executable_mode = path.stat().st_mode & (stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
            if not executable_mode and not any(magic.startswith(prefix) for prefix in EXECUTABLE_MAGIC):
                continue
            if not executable_mode:
                missing_mode.append(path)
            candidates.add(path)
    if missing_mode:
        raise RuntimeError("Codex executable lacks Unix execute permission: " + ", ".join(map(str, sorted(missing_mode))))
    return tuple(sorted(candidates))


def apparmor_path(path: Path) -> str:
    marker = "/site-packages/"
    value = str(path)
    if marker not in value:
        raise RuntimeError(f"Codex executable is outside site-packages: {value}")
    return "/usr/lib/python3*/site-packages/" + value.split(marker, 1)[1]


def validate(inventory_path: Path, apparmor_pathname: Path) -> None:
    inventory = {apparmor_path(Path(line)) for line in inventory_path.read_text(encoding="utf-8").splitlines() if line}
    rules = {
        line.strip()[:-4]
        for line in apparmor_pathname.read_text(encoding="utf-8").splitlines()
        if line.strip().startswith("/usr/lib/python3*/site-packages/codex_cli_bin/") and line.strip().endswith(" ix,")
    }
    missing = inventory - rules
    stale = rules - inventory
    if missing or stale:
        raise RuntimeError(f"Codex/AppArmor executable mismatch; missing={sorted(missing)} stale={sorted(stale)}")


def main() -> int:
    parser = argparse.ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("inventory")
    check = subparsers.add_parser("validate")
    check.add_argument("--inventory", type=Path, required=True)
    check.add_argument("--apparmor", type=Path, required=True)
    args = parser.parse_args()
    if args.command == "inventory":
        for executable in package_executables():
            print(executable)
    else:
        validate(args.inventory, args.apparmor)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
