#!/usr/bin/env python3
"""Inventory installed Chromium package executables and verify AppArmor ix coverage."""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

PACKAGES=("chromium","chromium-common","chromium-angle","chromium-chromedriver")


def inventory()->list[str]:
    paths:set[str]=set()
    for package in PACKAGES:
        output=subprocess.check_output(["apk","info","-L",package],text=True,stderr=subprocess.DEVNULL)
        for raw in output.splitlines():
            path=Path("/"+raw.lstrip("/"))
            if path.is_file() and os.access(path,os.X_OK) and ".so" not in path.name:paths.add(str(path.resolve()))
    return sorted(paths)


def validate(inventory_path:Path,apparmor_path:Path)->None:
    paths=[line.strip() for line in inventory_path.read_text().splitlines() if line.strip()]
    if not paths:raise RuntimeError("empty browser executable inventory")
    profile=apparmor_path.read_text()
    missing=[path for path in paths if not re.search(rf"^\s*{re.escape(path)}\s+ix,$",profile,re.MULTILINE)]
    if missing:raise RuntimeError("Browser executables missing AppArmor ix coverage: "+", ".join(missing))


if __name__=="__main__":
    if len(sys.argv)==2 and sys.argv[1]=="inventory":print("\n".join(inventory()))
    elif len(sys.argv)==4 and sys.argv[1]=="validate":validate(Path(sys.argv[2]),Path(sys.argv[3]))
    else:raise SystemExit("usage: validate_browser_inventory.py inventory | validate INVENTORY APPARMOR")
