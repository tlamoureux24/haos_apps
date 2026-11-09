"""Activity journal and status file behaviour of the Claude Remote Ingress page."""

from __future__ import annotations

import datetime as dt
import importlib.util
import json
import os
import pathlib
import tempfile
import unittest

SOURCE = pathlib.Path(__file__).resolve().parents[1] / "ingress_ui.py"


def load_module(data: pathlib.Path):
    os.environ["CLAUDE_REMOTE_DATA"] = str(data)
    spec = importlib.util.spec_from_file_location("ingress_ui_under_test", SOURCE)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JournalTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.data = pathlib.Path(self.tmp.name)
        self.ui = load_module(self.data)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_event_is_timestamped_and_private(self) -> None:
        self.ui.add_event("app_started", "ok", {"version": "9.9.9"})
        entry = self.ui.read_entries()[0]
        self.assertIsNotNone(dt.datetime.fromisoformat(entry["ts"]).tzinfo)
        self.assertEqual(entry["category"], "lifecycle")
        self.assertEqual(self.ui.JOURNAL.stat().st_mode & 0o777, 0o600)

    def test_secrets_and_unknown_details_are_dropped(self) -> None:
        self.ui.add_event("mcp_unreachable", "warning", {
            "http_status": "000",
            "url": "http://192.168.1.15:9583/private_secret",
            "version": "http://192.168.1.15:9583/private_secret",
            "token": "abc",
        })
        raw = self.ui.JOURNAL.read_text(encoding="utf-8")
        self.assertNotIn("private_secret", raw)
        self.assertNotIn("token", raw)
        self.assertEqual(self.ui.read_entries()[0]["details"], {"http_status": "000"})

    def test_unknown_event_is_refused(self) -> None:
        with self.assertRaises(SystemExit):
            self.ui.add_event("prompt_received", "info", {})

    def test_prune_by_age_and_count(self) -> None:
        old = (self.ui.now() - dt.timedelta(days=self.ui.RETENTION_DAYS + 1)).isoformat()
        recent = self.ui.now().isoformat()
        lines = [{"ts": old, "event": "app_started", "category": "lifecycle", "status": "ok"}]
        lines += [
            {"ts": recent, "event": "app_started", "category": "lifecycle", "status": "ok"}
            for _ in range(self.ui.RETENTION_ENTRIES + 5)
        ]
        self.ui.JOURNAL.write_text("".join(json.dumps(line) + "\n" for line in lines), encoding="utf-8")
        with self.ui.locked():
            removed = self.ui.prune_locked()
        self.assertEqual(removed, 6)
        self.assertEqual(len(self.ui.read_entries()), self.ui.RETENTION_ENTRIES)

    def test_status_accepts_known_values_only(self) -> None:
        self.ui.update_status({"remote_control": "running", "logged_in": "true"})
        status = self.ui.read_status()
        self.assertEqual(status["remote_control"], "running")
        with self.assertRaises(SystemExit):
            self.ui.update_status({"mcp": "http://192.168.1.15:9583/private_secret"})
        with self.assertRaises(SystemExit):
            self.ui.update_status({"ha_mcp_url": "x"})
        self.assertNotIn("private_secret", self.ui.STATUS.read_text(encoding="utf-8"))


if __name__ == "__main__":
    unittest.main()
