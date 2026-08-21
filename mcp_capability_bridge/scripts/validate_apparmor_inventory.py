#!/usr/bin/env python3
"""Compare observed runtime executables with targeted AppArmor ix/rix rules."""

from __future__ import annotations

import fnmatch
import pathlib
import re
import sys


def executable_rules(profile: str) -> list[str]:
    rules = []
    for line in profile.splitlines():
        match = re.match(r'^\s*(?:"([^"]+)"|(\S+))\s+(?:r?ix),\s*$', line)
        if match:
            rules.append(match.group(1) or match.group(2))
    return rules


def covered(path: str, rules: list[str]) -> bool:
    return any(fnmatch.fnmatchcase(path, rule) for rule in rules)


def main() -> int:
    if len(sys.argv) != 3:
        raise SystemExit("usage: validate_apparmor_inventory.py PROFILE INVENTORY")
    profile = pathlib.Path(sys.argv[1]).read_text(encoding="utf-8")
    observed = {line.strip() for line in pathlib.Path(sys.argv[2]).read_text(encoding="utf-8").splitlines() if line.strip()}
    missing = sorted(path for path in observed if not covered(path, executable_rules(profile)))
    if missing:
        raise RuntimeError("Observed executables missing AppArmor ix/rix coverage:\n" + "\n".join(missing))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
