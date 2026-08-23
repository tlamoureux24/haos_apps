from __future__ import annotations

import sqlite3
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_execution_plane.admin_ui import ADMIN_CSS, ADMIN_JS

from agent_execution_plane.database import MAX_ACTIVITY_ENTRIES, database_ready, initialize, list_activity, prune, record_activity


class FoundationTests(unittest.TestCase):
    def test_root_reserves_stable_scrollbar_gutter_without_changing_app_width(self):
        self.assertIn(':root{color-scheme:light;scrollbar-gutter:stable;',ADMIN_CSS)
        self.assertIn('.app{max-width:1840px',ADMIN_CSS)

    def test_activity_freshness_and_overview_lifecycle_ui(self):
        main_source = Path(__file__).parents[1].joinpath("src/agent_execution_plane/main.py").read_text(encoding="utf-8")
        self.assertIn('data-freshness="activity"', main_source)
        for text in ("Actualisé à l’instant", "Actualisé il y a ${seconds} s", "Actualisé il y a ${minutes} min"):
            self.assertIn(text, ADMIN_JS)
        self.assertIn("viewRefreshes=new Map()", ADMIN_JS); self.assertIn("document.visibilityState!=='visible'", ADMIN_JS)
        self.assertIn("`${tr('lifecycleState')}: ${tr(lifecycle)}`", ADMIN_JS)
        self.assertNotIn("`${tr('standaloneState')}: ${tr(configured?'configured':'notConfigured')}`", ADMIN_JS)

    def test_overview_exposes_real_model_resource_metrics(self):
        main_source = Path(__file__).parents[1].joinpath("src/agent_execution_plane/main.py").read_text(encoding="utf-8")
        for element_id in ("available-model-count", "enabled-model-count", "used-model-count", "provider-family-count"):
            self.assertIn(f'id="{element_id}"', main_source)
        for expression in ("m.provider_state==='available'", "m=>m.enabled", "m=>m.in_use", "new Set(models.map(m=>m.provider_family)).size"):
            self.assertIn(expression, ADMIN_JS)
        self.assertIn("loadAcp(),loadModels()", ADMIN_JS)

    def test_service_badge_uses_real_admin_status_and_has_failure_state(self):
        main_source = Path(__file__).parents[1].joinpath("src/agent_execution_plane/main.py").read_text(encoding="utf-8")
        self.assertIn('Route("/admin/api/v1/status", admin_status)', main_source)
        self.assertIn("available = database_ready(settings.database_path)", main_source)
        self.assertIn("loadServiceStatus", ADMIN_JS)
        self.assertIn("/admin/api/v1/status", ADMIN_JS)
        self.assertIn("response.ok&&data.status==='ready'", ADMIN_JS)
        self.assertIn("serviceUnavailable:'Service indisponible'", ADMIN_JS)
        self.assertIn("serviceUnavailable:'Service unavailable'", ADMIN_JS)
        self.assertIn(".health.unavailable", ADMIN_CSS)

    def test_control_plane_configuration_has_page_action_and_explicit_feedback(self):
        main_source=Path(__file__).parents[1].joinpath("src/agent_execution_plane/main.py").read_text(encoding="utf-8")
        self.assertIn('id="acp-edit" class="page-action"',ADMIN_JS)
        self.assertIn('id="acp-drawer-panel"',ADMIN_JS)
        self.assertIn("openDrawer(tr(acpData?.configured?'editConnection':'configureConnection'),'acp-drawer-panel',trigger)",ADMIN_JS)
        self.assertIn('id="acp-overview-state"',main_source);self.assertIn('id="acp-overview-detail"',main_source)
        self.assertIn("lastPollSuccess",ADMIN_JS);self.assertIn("lastAcpResponse",ADMIN_JS);self.assertIn("availableJobs",ADMIN_JS);self.assertIn("successfulPolls",ADMIN_JS);self.assertIn("lastError",ADMIN_JS)
        self.assertIn("singleAcpHelp",ADMIN_JS)
        self.assertIn("acp_validation_pending",ADMIN_JS)
        self.assertIn("acp_validation_timeout",ADMIN_JS)
        self.assertIn("acp_request_failed",ADMIN_JS)
        self.assertIn("button.disabled=true",ADMIN_JS)
        self.assertIn("finally{button.disabled=false}",ADMIN_JS)
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = Path(self.temp.name) / "agent_execution_plane.db"
        initialize(self.database)

    def tearDown(self): self.temp.cleanup()

    def test_generation_one_empty_business_schema(self):
        self.assertTrue(database_ready(self.database))
        with closing(sqlite3.connect(self.database)) as db:
            tables = {row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertIn("schema_info", tables); self.assertIn("activity", tables); self.assertIn("models", tables)
        self.assertTrue({"settings", "pending_result", "active_execution", "model_usage"} <= tables)
        self.assertFalse(tables & {"jobs", "executions"})

    def test_042_upgrade_is_additive_and_preserves_models_and_activity(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("DROP TABLE pending_result");db.execute("DROP TABLE active_execution");db.execute("DROP TABLE settings")
            db.execute("INSERT INTO activity(occurred_at,event_code,category,status) VALUES('now','legacy_activity','system','success')")
            db.execute("INSERT INTO models VALUES('legacy-model','Legacy','ollama_compatible','http://localhost:11434','reasoner',NULL,1,1,5,'available',NULL,NULL,'now','now')");db.commit()
        initialize(self.database)
        with closing(sqlite3.connect(self.database)) as db:
            self.assertEqual(db.execute("SELECT id,priority FROM models").fetchall(),[("legacy-model",1)])
            self.assertEqual(db.execute("SELECT event_code FROM activity").fetchall(),[("legacy_activity",)])
            tables={row[0] for row in db.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertTrue({"settings","active_execution","pending_result"} <= tables)

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

    def test_generation_one_models_shape_preserves_pre_oauth_rows(self):
        with closing(sqlite3.connect(self.database)) as db:
            db.execute("DROP TABLE models")
            db.execute("CREATE TABLE models (id TEXT PRIMARY KEY,display_name TEXT NOT NULL,provider_family TEXT NOT NULL CHECK(provider_family IN ('ollama_compatible','openai_compatible')),base_url TEXT NOT NULL,provider_model TEXT NOT NULL,encrypted_credential BLOB,enabled INTEGER NOT NULL,priority INTEGER NOT NULL UNIQUE,timeout_minutes REAL NOT NULL,technical_state TEXT NOT NULL,diagnostic_code TEXT,checked_at TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL)")
            db.execute("INSERT INTO models VALUES('legacy','Legacy','ollama_compatible','http://localhost:11434','old',NULL,1,1,5,'available',NULL,NULL,'now','now')")
            db.commit()
        initialize(self.database)
        with closing(sqlite3.connect(self.database)) as db:
            row = db.execute("SELECT id,base_url FROM models").fetchone()
            schema = db.execute("SELECT sql FROM sqlite_master WHERE name='models'").fetchone()[0]
        self.assertEqual(row, ("legacy", "http://localhost:11434")); self.assertIn("openai_chatgpt_oauth", schema)

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
