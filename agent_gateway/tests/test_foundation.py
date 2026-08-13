from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

from agent_gateway.database import database_ready, initialize_database
from agent_gateway.admin_ui import ADMIN_JS
from agent_gateway.control_plane import ControlPlane, TaskExecutionActiveError, validate_json_contract
from agent_gateway.connectors import connector_display_endpoint, validate_streamable_http_url
from agent_gateway.policy import decide, validate_actions
from agent_gateway.redaction import redact
from agent_gateway.security import issue_credential, load_or_create_pepper, parse_and_verify_token
from agent_gateway.settings import load_settings
from agent_gateway.surfaces import exposed_paths


class SettingsTests(unittest.TestCase):
    def test_defaults_to_public_surface(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
        self.assertEqual(settings.surface, "public")

    def test_rejects_unknown_surface(self) -> None:
        with patch.dict(os.environ, {"AGENT_GATEWAY_SURFACE": "both"}, clear=True):
            with self.assertRaises(RuntimeError):
                load_settings()


class InternationalizationTests(unittest.TestCase):
    def test_admin_interface_supports_french_and_english(self) -> None:
        self.assertIn("navigator.language", ADMIN_JS)
        self.assertIn("agw-language", ADMIN_JS)
        self.assertIn("MutationObserver", ADMIN_JS)
        self.assertIn("'Vue d’ensemble':'Overview'", ADMIN_JS)
        self.assertIn("'Connecteurs MCP':'MCP connectors'", ADMIN_JS)
        self.assertIn("'Audit et rétention':'Audit and retention'", ADMIN_JS)
        self.assertIn("en-GB", ADMIN_JS)


class ConnectorContractTests(unittest.TestCase):
    def test_accepts_generic_streamable_http_endpoint(self) -> None:
        url = "https://mcp.example.test:8443/custom/path?tenant=one"
        self.assertEqual(validate_streamable_http_url(url), url)
        self.assertEqual(connector_display_endpoint(url), "https://mcp.example.test:8443")

    def test_rejects_embedded_credentials_and_fragments(self) -> None:
        for url in (
            "https://user:secret@mcp.example.test/mcp",
            "https://mcp.example.test/mcp#secret",
            "file:///tmp/server",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_streamable_http_url(url)

    def test_rejects_invalid_ingress_proxy_ip(self) -> None:
        with patch.dict(
            os.environ,
            {"AGENT_GATEWAY_INGRESS_PROXY_IP": "not-an-ip"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                load_settings()

    def test_accepts_configured_intake_rate_limit(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_GATEWAY_INTAKE_RATE_LIMIT": "42"}, clear=True
        ):
            settings = load_settings()
        self.assertEqual(settings.intake_rate_limit_per_minute, 42)

    def test_rejects_out_of_range_intake_rate_limit(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_GATEWAY_INTAKE_RATE_LIMIT": "0"}, clear=True
        ):
            with self.assertRaises(RuntimeError):
                load_settings()

class DatabaseReadinessTests(unittest.TestCase):
    def test_missing_database_is_not_ready(self) -> None:
        self.assertFalse(database_ready(Path("/definitely/missing/database.db")))

    def test_expected_schema_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            initialize_database(path)
            self.assertTrue(database_ready(path))
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM task_definitions").fetchone()[0],
                    0,
                )

    def test_incompatible_existing_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE gateway_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO gateway_metadata VALUES('application', 'agent_gateway');
                """
            )
            connection.close()
            with self.assertRaisesRegex(RuntimeError, "remove_app_data"):
                initialize_database(path)
            self.assertFalse(database_ready(path))

    def test_generation_six_is_upgraded_without_data_loss(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            initialize_database(path)
            with sqlite3.connect(path) as connection:
                connection.execute("DROP TABLE event_mappings")
                connection.execute("DROP TABLE schedules")
                connection.execute("UPDATE gateway_metadata SET value='6' WHERE key='schema_generation'")
            initialize_database(path)
            self.assertTrue(database_ready(path))
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM schedules").fetchone()[0], 0)
                self.assertEqual(connection.execute("SELECT count(*) FROM event_mappings").fetchone()[0], 0)


class PublicSurfaceTests(unittest.TestCase):
    def test_public_root_is_not_exposed(self) -> None:
        paths = set(exposed_paths("public"))
        self.assertNotIn("/", paths)
        self.assertEqual(
            paths,
            {
                "/api/v1/events",
                "/api/v1/jobs",
                "/api/v1/reports",
                "/api/v1/permissions/effective",
                "/health/live",
                "/health/ready",
            },
        )

    def test_admin_root_is_exposed(self) -> None:
        self.assertIn("/", exposed_paths("admin"))


class CredentialTests(unittest.TestCase):
    def test_configured_pepper_avoids_persistent_file_access(self) -> None:
        expected = bytes(range(32))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inaccessible" / "credential-pepper"
            with patch.dict(os.environ, {"AGENT_GATEWAY_CREDENTIAL_PEPPER_HEX": expected.hex()}):
                self.assertEqual(load_or_create_pepper(path), expected)
            self.assertFalse(path.exists())

    def test_token_round_trip_and_wrong_pepper_denial(self) -> None:
        issued = issue_credential(b"a" * 32)
        self.assertEqual(
            parse_and_verify_token(issued.token, b"a" * 32, issued.verifier),
            issued.credential_id,
        )
        self.assertIsNone(parse_and_verify_token(issued.token, b"b" * 32, issued.verifier))

    def test_malformed_token_is_denied(self) -> None:
        self.assertIsNone(parse_and_verify_token("not-a-token", b"a" * 32, "0" * 64))

    def test_concurrent_pepper_creation_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "credential-pepper"
            with ThreadPoolExecutor(max_workers=8) as executor:
                peppers = list(executor.map(lambda _: load_or_create_pepper(path), range(32)))
            self.assertEqual(len(set(peppers)), 1)
            self.assertEqual(len(peppers[0]), 32)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class PolicyTests(unittest.TestCase):
    def test_policy_is_deny_by_default(self) -> None:
        self.assertFalse(decide("events.read", ()).allowed)
        self.assertEqual(decide("events.read", ()).reason_code, "not_granted")

    def test_policy_accepts_only_known_actions(self) -> None:
        self.assertEqual(validate_actions(["jobs.read", "jobs.read"]), ("jobs.read",))
        with self.assertRaises(ValueError):
            validate_actions(["shell.execute"])


class RedactionTests(unittest.TestCase):
    def test_nested_secrets_and_tokens_are_redacted(self) -> None:
        issued = issue_credential(b"a" * 32)
        value = {
            "safe": [{"api_key": "canary"}, f"prefix {issued.token} suffix"],
            "authorization": "Bearer canary",
        }
        redacted = redact(value)
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["safe"][0]["api_key"], "[REDACTED]")
        self.assertNotIn(issued.token, redacted["safe"][1])


class TaskReportContractTests(unittest.TestCase):
    def test_generic_report_shape_is_validated(self) -> None:
        schema = {
            "type": "object",
            "required": ["result"],
            "additionalProperties": False,
            "properties": {"result": {"type": "string", "minLength": 1}},
        }
        validate_json_contract({"result": "healthy"}, schema)
        with self.assertRaisesRegex(ValueError, "required"):
            validate_json_contract({}, schema)
        with self.assertRaisesRegex(ValueError, "additional_property"):
            validate_json_contract({"result": "healthy", "unexpected": True}, schema)


class TaskCompositionTests(unittest.TestCase):
    def test_task_dependencies_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                    (connector_id, "Example MCP", "streamable_http", "protected", "https://mcp.example.test", "2026-08-13T00:00:00Z", "2026-08-13T00:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                    (connector_id, "inspect", "Inspect", '{"type":"object","properties":{"slug":{"type":"string","minLength":1}}}', "a" * 64, "2026-08-13T00:00:00Z"),
                )
            task_id = control_plane.create_task(
                "Inspect service",
                "inspect_service",
                "Inspect the selected service.",
                3,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "test-task",
            )
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["id"], task_id)
            self.assertEqual(task["status"], "ready")
            self.assertEqual(len(task["tools"]), 1)
            self.assertRegex(task["tools"][0]["namespaced_name"], r"^task_[0-9a-f]{12}__inspect__[0-9a-f]{12}$")
            self.assertEqual(control_plane.delete_connector(connector_id, "test-delete"), "in_use")
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE connector_tools SET schema_fingerprint=? WHERE connector_id=? AND name='inspect'",
                    ("b" * 64, connector_id),
                )
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["status"], "unavailable")
            self.assertIn("tool_schema_changed:Example MCP.inspect", task["dependency_failures"])
            self.assertTrue(control_plane.set_task_enabled(task_id, False, "test-pause"))
            self.assertEqual(control_plane.list_tasks()[0]["status"], "disabled")
            self.assertTrue(control_plane.set_task_enabled(task_id, True, "test-resume"))
            self.assertEqual(control_plane.delete_task(task_id, "test-delete-task"), "deleted")
            self.assertEqual(control_plane.list_tasks(), [])
            self.assertEqual(control_plane.delete_task(task_id, "test-delete-missing"), "not_found")
            manual_task_id = control_plane.create_task(
                "Manual inspection",
                "manual_inspection",
                "Inspect on demand.",
                1,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "test-manual-task",
            )
            manual_job_id = control_plane.enqueue_manual_task(manual_task_id, {}, "test-manual-run")
            self.assertEqual(control_plane.get_job(manual_job_id)["state"], "queued")
            self.assertIsNone(control_plane.get_job(manual_job_id)["event_id"])
            with self.assertRaisesRegex(TaskExecutionActiveError, "task_execution_active"):
                control_plane.enqueue_manual_task(manual_task_id, {}, "test-manual-duplicate")
            self.assertEqual(control_plane.list_tasks()[0]["active_job_count"], 1)
            self.assertEqual(control_plane.delete_task(manual_task_id, "test-delete-used"), "in_use")

    def test_task_requires_a_ready_connector_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            with self.assertRaisesRegex(ValueError, "requires_tool"):
                control_plane.create_task("Empty", "empty", "No tools", 1, [], "test")

    def test_archiving_preserves_history_and_restores_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                    (connector_id, "Example MCP", "streamable_http", "protected", "https://mcp.example.test", "2026-08-13T00:00:00Z", "2026-08-13T00:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                    (connector_id, "inspect", "Inspect", '{"type":"object"}', "a" * 64, "2026-08-13T00:00:00Z"),
                )
            task_id = control_plane.create_task("Inspect", "inspect", "Inspect.", 1, [{"connector_id": connector_id, "tool_name": "inspect"}], "test-task")
            job_id = control_plane.enqueue_manual_task(task_id, {}, "test-run")
            with self.assertRaisesRegex(ValueError, "task_execution_active"):
                control_plane.set_task_archived(task_id, True, "test-active-archive")
            with self.assertRaisesRegex(ValueError, "connector_execution_active"):
                control_plane.set_connector_archived(connector_id, True, "test-active-connector-archive")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job_id,))
            self.assertTrue(control_plane.set_task_archived(task_id, True, "test-archive"))
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["status"], "archived")
            self.assertIsNotNone(task["archived_at"])
            self.assertEqual(control_plane.get_job(job_id)["state"], "cancelled")
            self.assertTrue(control_plane.set_task_archived(task_id, False, "test-restore"))
            self.assertEqual(control_plane.list_tasks()[0]["status"], "disabled")
            self.assertTrue(control_plane.set_connector_archived(connector_id, True, "test-connector-archive"))
            connector = control_plane.list_connectors()[0]
            self.assertFalse(connector["enabled"])
            self.assertIsNotNone(connector["archived_at"])
            self.assertTrue(control_plane.set_connector_archived(connector_id, False, "test-connector-restore"))
            connector = control_plane.list_connectors()[0]
            self.assertFalse(connector["enabled"])
            self.assertIsNone(connector["archived_at"])
            metrics = control_plane.status_counts()
            self.assertEqual(metrics["events_24h"], 0)
            self.assertEqual(metrics["failed_jobs_24h"], 0)

    def test_due_schedule_queues_once_and_skips_an_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)", (connector_id,"Example MCP","streamable_http","protected","https://mcp.example.test","2026-08-13T00:00:00Z","2026-08-13T00:00:00Z"))
                connection.execute("INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)", (connector_id,"inspect","Inspect",'{"type":"object"}',"a"*64,"2026-08-13T00:00:00Z"))
            task_id = control_plane.create_task("Inspect", "inspect", "Inspect.", 1, [{"connector_id":connector_id,"tool_name":"inspect"}], "test-task")
            schedule_id = control_plane.create_schedule("Every hour", task_id, "interval", 60, None, None, None, "test-schedule")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE schedules SET next_run_at='2000-01-01T00:00:00Z' WHERE id=?", (schedule_id,))
            self.assertEqual(control_plane.run_due_schedules(), 1)
            self.assertEqual(control_plane.list_schedules()[0]["last_outcome"], "queued")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE schedules SET next_run_at='2000-01-01T00:00:00Z' WHERE id=?", (schedule_id,))
            self.assertEqual(control_plane.run_due_schedules(), 1)
            self.assertEqual(control_plane.list_schedules()[0]["last_outcome"], "skipped_active")
            self.assertEqual(len(control_plane.list_jobs()), 1)

    def test_calendar_schedule_next_occurrence_uses_iana_timezone(self) -> None:
        reference = datetime.fromisoformat("2026-08-13T08:00:00+00:00")
        self.assertEqual(
            ControlPlane._next_schedule_run("daily", 1440, "11:30", None, "Europe/Paris", reference),
            "2026-08-13T09:30:00.000Z",
        )
        self.assertEqual(
            ControlPlane._next_schedule_run("weekly", 10080, "09:00", 0, "Europe/Paris", reference),
            "2026-08-17T07:00:00.000Z",
        )
        with self.assertRaisesRegex(ValueError, "invalid_timezone"):
            ControlPlane._next_schedule_run("daily", 1440, "09:00", None, "Mars/Olympus", reference)
        with self.assertRaisesRegex(ValueError, "invalid_schedule"):
            ControlPlane._next_schedule_run("weekly", 10080, "09:00", None, "Europe/Paris", reference)

    def test_retention_removes_only_expired_terminal_data_and_keeps_audit_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            old = "2000-01-01T00:00:00.000Z"
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO identities(id,display_name,identity_type,status,created_at) VALUES('10000000-0000-0000-0000-000000000001','Source','event_source','active',?)", (old,))
                connection.execute("INSERT INTO policy_documents(id,name,created_at) VALUES('policy','policy',?)", (old,))
                connection.execute("INSERT INTO policy_revisions(id,policy_id,schema_version,document_json,created_at) VALUES('revision','policy',1,'{}',?)", (old,))
                connection.execute("INSERT INTO task_definitions(id,name,display_name,enabled,created_at) VALUES('task','task','Task',1,?)", (old,))
                connection.execute("INSERT INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES('task-revision','task',1,'Task','{}','{}',1,?)", (old,))
                connection.execute("INSERT INTO events(id,source_identity_id,idempotency_key,schema_version,event_type,occurred_at,received_at,payload_json) VALUES('event','10000000-0000-0000-0000-000000000001','key',1,'test.event',?,?, '{}')", (old, old))
                connection.execute("INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES('old-job','event','task','completed','revision','task-revision','{}',?,?)", (old, old))
                connection.execute("INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES('active-job',NULL,'task','queued','revision','task-revision','{}',?,?)", (old, old))
                connection.execute("INSERT INTO reports(id,job_id,schema_version,report_json,created_at) VALUES('report','old-job',1,'{}',?)", (old,))
                connection.execute("INSERT INTO job_attempts(id,job_id,attempt_number,identity_id,lease_verifier,leased_at,lease_expires_at,max_expires_at,finished_at,outcome) VALUES('attempt','old-job',1,'10000000-0000-0000-0000-000000000001','x',?,?,?,?, 'completed')", (old, old, old, old))
            control_plane.record_audit(actor_identity_id=None, credential_id=None, action="test", decision="recorded", reason_code="test", correlation_id="test")
            self.assertEqual(control_plane.retention_status()["preview"]["jobs"], 1)
            deleted = control_plane.run_retention("test-retention")
            self.assertEqual(deleted, {"jobs": 1, "reports": 1, "attempts": 1, "orphan_events": 1})
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT id FROM jobs").fetchall(), [("active-job",)])
            self.assertTrue(control_plane.verify_audit_chain()["valid"])


if __name__ == "__main__":
    unittest.main()
