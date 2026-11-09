#!/usr/bin/env python3
"""Claude Remote Ingress status page and operational activity journal.

The journal answers "what has this App been doing?" with safe metadata only:
event codes, a status and a few whitelisted numeric/short fields. It never
stores prompts, MCP URLs, tool arguments or results, credentials or session
links.

Subcommands:
  serve              HTTP server for the Ingress page (behind nginx)
  event CODE [...]   append one journal entry
  status KEY=VALUE   merge values into the status file read by the page
"""

from __future__ import annotations

import argparse
import contextlib
import datetime as dt
import fcntl
import json
import os
import pathlib
import re
import sys
import threading
import time
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PRODUCT = "Claude Remote"
DATA = pathlib.Path(os.environ.get("CLAUDE_REMOTE_DATA", "/data"))
JOURNAL = DATA / "activity.jsonl"
LOCK = DATA / "activity.lock"
STATUS = DATA / "status.json"
RETENTION_DAYS = 30
RETENTION_ENTRIES = 10_000
PAGE_SIZE = 50
PRUNE_INTERVAL_S = 3600

EVENTS = {
    "app_started": "lifecycle",
    "app_stopping": "lifecycle",
    "mcp_configured": "mcp",
    "mcp_not_configured": "mcp",
    "mcp_reachable": "mcp",
    "mcp_unreachable": "mcp",
    "login_required": "account",
    "login_detected": "account",
    "setup_required": "remote_control",
    "setup_completed": "remote_control",
    "remote_control_started": "remote_control",
    "remote_control_exited": "remote_control",
    "remote_control_restart_scheduled": "remote_control",
}
STATUSES = ("ok", "info", "warning", "error")
# Only these detail keys are ever stored, and only short safe values.
DETAIL_KEYS = ("exit_code", "delay_s", "version", "http_status")
DETAIL_VALUE = re.compile(r"^[A-Za-z0-9._-]{1,32}$")
STATUS_KEYS = {
    "claude_version": DETAIL_VALUE,
    "logged_in": re.compile(r"^(true|false)$"),
    "remote_control": re.compile(r"^(starting|waiting_login|waiting_setup|running|restarting)$"),
    "mcp": re.compile(r"^(configured|not_configured)$"),
    "mcp_reachable": re.compile(r"^(true|false|unknown)$"),
}


def now() -> dt.datetime:
    return dt.datetime.now().astimezone()


def log(level: str, message: str) -> None:
    stamp = now().isoformat(timespec="seconds")
    print(f"{stamp} [{PRODUCT}] {level}: {message}", file=sys.stderr, flush=True)


@contextlib.contextmanager
def locked():
    DATA.mkdir(parents=True, exist_ok=True)
    with open(LOCK, "a", encoding="utf-8") as handle:
        fcntl.flock(handle, fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle, fcntl.LOCK_UN)


def read_entries() -> list[dict[str, object]]:
    entries = []
    try:
        lines = JOURNAL.read_text(encoding="utf-8").splitlines()
    except FileNotFoundError:
        return entries
    for line in lines:
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(entry, dict) and entry.get("event") in EVENTS:
            entries.append(entry)
    return entries


def prune_locked() -> int:
    entries = read_entries()
    cutoff = now() - dt.timedelta(days=RETENTION_DAYS)
    kept = []
    for entry in entries:
        try:
            stamp = dt.datetime.fromisoformat(str(entry.get("ts")))
        except ValueError:
            continue
        if stamp.tzinfo is not None and stamp >= cutoff:
            kept.append(entry)
    kept = kept[-RETENTION_ENTRIES:]
    if len(kept) != len(entries):
        temporary = JOURNAL.with_suffix(".tmp")
        temporary.write_text(
            "".join(json.dumps(entry, separators=(",", ":")) + "\n" for entry in kept),
            encoding="utf-8",
        )
        os.chmod(temporary, 0o600)
        os.replace(temporary, JOURNAL)
    return len(entries) - len(kept)


def add_event(code: str, status: str, details: dict[str, str]) -> None:
    if code not in EVENTS:
        raise SystemExit(f"Unknown event code: {code}")
    if status not in STATUSES:
        raise SystemExit(f"Unknown status: {status}")
    entry: dict[str, object] = {
        "ts": now().isoformat(timespec="seconds"),
        "event": code,
        "category": EVENTS[code],
        "status": status,
    }
    safe = {
        key: value
        for key, value in details.items()
        if key in DETAIL_KEYS and DETAIL_VALUE.fullmatch(value)
    }
    if safe:
        entry["details"] = safe
    with locked():
        with open(JOURNAL, "a", encoding="utf-8") as handle:
            handle.write(json.dumps(entry, separators=(",", ":")) + "\n")
        os.chmod(JOURNAL, 0o600)
        if len(read_entries()) > RETENTION_ENTRIES:
            prune_locked()


def read_status() -> dict[str, object]:
    try:
        status = json.loads(STATUS.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError):
        status = {}
    return status if isinstance(status, dict) else {}


def update_status(pairs: dict[str, str]) -> None:
    with locked():
        status = read_status()
        for key, value in pairs.items():
            pattern = STATUS_KEYS.get(key)
            if pattern is None or not pattern.fullmatch(value):
                raise SystemExit(f"Refused status value for {key}")
            status[key] = value
        status["updated_at"] = now().isoformat(timespec="seconds")
        temporary = STATUS.with_suffix(".tmp")
        temporary.write_text(json.dumps(status), encoding="utf-8")
        os.chmod(temporary, 0o644)
        os.replace(temporary, STATUS)


PAGE = (pathlib.Path(__file__).resolve().parent / "ingress_ui.html")


class Handler(BaseHTTPRequestHandler):
    server_version = "ClaudeRemote"
    sys_version = ""

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        return

    def send_json(self, payload: object) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "application/json")
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self) -> None:  # noqa: N802
        url = urlparse(self.path)
        if url.path == "/":
            body = PAGE.read_bytes()
            self.send_response(HTTPStatus.OK)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        elif url.path == "/healthz":
            self.send_json({"ok": True})
        elif url.path == "/api/status":
            status = read_status()
            status["app_version"] = os.environ.get("BUILD_VERSION", "")
            self.send_json(status)
        elif url.path == "/api/activity":
            query = parse_qs(url.query)
            try:
                page = max(0, int(query.get("page", ["0"])[0]))
            except ValueError:
                page = 0
            category = query.get("category", [""])[0]
            entries = list(reversed(read_entries()))
            if category:
                entries = [entry for entry in entries if entry.get("category") == category]
            start = page * PAGE_SIZE
            self.send_json({
                "entries": entries[start:start + PAGE_SIZE],
                "page": page,
                "pages": max(1, -(-len(entries) // PAGE_SIZE)),
                "total": len(entries),
            })
        else:
            self.send_error(HTTPStatus.NOT_FOUND)


def pruner() -> None:
    while True:
        try:
            with locked():
                removed = prune_locked()
            if removed:
                log("INFO", f"Pruned {removed} activity journal entries")
        except OSError as error:
            log("WARNING", f"Activity journal pruning failed: {error.__class__.__name__}")
        time.sleep(PRUNE_INTERVAL_S)


def serve(port: int) -> None:
    threading.Thread(target=pruner, daemon=True).start()
    server = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    log("INFO", f"Ingress status page listening on 127.0.0.1:{port}")
    server.serve_forever()


def key_values(values: list[str]) -> dict[str, str]:
    pairs = {}
    for item in values:
        key, separator, value = item.partition("=")
        if not separator:
            raise SystemExit(f"Expected KEY=VALUE, got {item!r}")
        pairs[key] = value
    return pairs


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    serve_cmd = commands.add_parser("serve")
    serve_cmd.add_argument("--port", type=int, default=8100)
    event_cmd = commands.add_parser("event")
    event_cmd.add_argument("code")
    event_cmd.add_argument("--status", default="info")
    event_cmd.add_argument("details", nargs="*")
    status_cmd = commands.add_parser("status")
    status_cmd.add_argument("pairs", nargs="+")
    args = parser.parse_args()

    if args.command == "serve":
        serve(args.port)
    elif args.command == "event":
        add_event(args.code, args.status, key_values(args.details))
    elif args.command == "status":
        update_status(key_values(args.pairs))


if __name__ == "__main__":
    main()
