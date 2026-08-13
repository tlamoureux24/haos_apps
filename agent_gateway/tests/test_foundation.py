from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import patch

from agent_gateway.database import database_ready, initialize_database
from agent_gateway.control_plane import validate_json_contract
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


if __name__ == "__main__":
    unittest.main()
