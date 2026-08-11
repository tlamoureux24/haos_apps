#!/usr/bin/env python3
"""Run OpenClaw's TTY-only OAuth device flow in a private pseudo-terminal."""

from __future__ import annotations

import os
import pty
import sys


COMMAND = [
    "node",
    "/app/dist/index.js",
    "models",
    "auth",
    "login",
    "--provider",
    "openai",
    "--device-code",
]


def main() -> int:
    print("=== ChatGPT/Codex OAuth device login ===", flush=True)
    print("The following code is short-lived; do not publish the App log.", flush=True)
    status = pty.spawn(COMMAND)
    exit_code = os.waitstatus_to_exitcode(status)
    if exit_code == 0:
        print("=== ChatGPT/Codex OAuth login succeeded ===", flush=True)
        print("Disable the OAuth device-login option and restart the App.", flush=True)
    else:
        print(
            f"ChatGPT/Codex OAuth login failed with exit code {exit_code}. "
            "Restart the App to request a fresh code.",
            file=sys.stderr,
            flush=True,
        )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
