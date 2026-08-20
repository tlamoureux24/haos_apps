from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_execution_plane.database import MAX_ACTIVITY_ENTRIES, database_ready, initialize, list_activity, prune, record_activity


class FoundationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "agent_execution_plane.db"
        initialize(self.database)

    def tearDown(self): self.temp.cleanup()

    def test_generation_one_empty_business_schema(self):
        self.assertTrue(database_ready(self.database))
        with closing(sqlite3.connect(self.database)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("schema_info", tables); self.assertIn("activity", tables)
        self.assertFalse(tables & {"models", "jobs", "executions", "pending_result", "active_execution"})

    def test_activity_is_safe_and_persistent(self):
        record_activity(self.database, "app_ready", "system", "success")
        initialize(self.database)
        entry = list_activity(self.database)["entries"][0]
        self.assertEqual(entry["event_code"], "app_ready")
        self.assertRegex(entry["occurred_at"], r"(?:Z|[+-]\d\d:\d\d)$")
        self.assertEqual(set(entry), {"occurred_at", "event_code", "category", "status", "source_ip"})

    def test_clean_stop_event_is_persistent(self):
        record_activity(self.database, "app_stopped", "system", "success")
        initialize(self.database)
        entries = list_activity(self.database)["entries"]
        self.assertEqual(entries[0]["event_code"], "app_stopped")
        self.assertEqual(entries[0]["status"], "success")

    def test_retention_prunes_age_and_count(self):
        old = (datetime.now(timezone.utc) - timedelta(days=31)).isoformat()
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("INSERT INTO activity(occurred_at,event_code,category,status) VALUES(?,?,?,?)", (old, "old", "system", "success"))
            db.executemany("INSERT INTO activity(occurred_at,event_code,category,status) VALUES(?,?,?,?)", [(datetime.now(timezone.utc).isoformat(), f"safe_{i}", "system", "success") for i in range(MAX_ACTIVITY_ENTRIES + 5)])
            db.commit()
        prune(self.database)
        result = list_activity(self.database)
        self.assertEqual(result["total"], MAX_ACTIVITY_ENTRIES)
        self.assertNotIn("old", {entry["event_code"] for entry in result["entries"]})

    def test_pagination_is_bounded(self):
        for index in range(4): record_activity(self.database, f"safe_{index}", "system", "success")
        result = list_activity(self.database, limit=2, offset=1)
        self.assertEqual(len(result["entries"]), 2); self.assertEqual(result["total"], 4)


if __name__ == "__main__": unittest.main()
