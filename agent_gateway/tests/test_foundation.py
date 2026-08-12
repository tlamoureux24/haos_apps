from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from agent_gateway.database import database_ready
from agent_gateway.policy import decide, validate_actions
from agent_gateway.redaction import redact
from agent_gateway.security import issue_credential, parse_and_verify_token
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


class DatabaseReadinessTests(unittest.TestCase):
    def test_missing_database_is_not_ready(self) -> None:
        self.assertFalse(database_ready(Path("/definitely/missing/database.db")))

    def test_expected_schema_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY);
                INSERT INTO alembic_version VALUES('0002_control_plane');
                CREATE TABLE gateway_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO gateway_metadata VALUES('application', 'agent_gateway');
                """
            )
            connection.close()
            self.assertTrue(database_ready(path))

    def test_unknown_revision_is_not_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE alembic_version(version_num TEXT PRIMARY KEY);
                INSERT INTO alembic_version VALUES('future');
                CREATE TABLE gateway_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO gateway_metadata VALUES('application', 'agent_gateway');
                """
            )
            connection.close()
            self.assertFalse(database_ready(path))


class PublicSurfaceTests(unittest.TestCase):
    def test_public_root_is_not_exposed(self) -> None:
        paths = set(exposed_paths("public"))
        self.assertNotIn("/", paths)
        self.assertEqual(paths, {"/health/live", "/health/ready"})

    def test_admin_root_is_exposed(self) -> None:
        self.assertIn("/", exposed_paths("admin"))


class CredentialTests(unittest.TestCase):
    def test_token_round_trip_and_wrong_pepper_denial(self) -> None:
        issued = issue_credential(b"a" * 32)
        self.assertEqual(
            parse_and_verify_token(issued.token, b"a" * 32, issued.verifier),
            issued.credential_id,
        )
        self.assertIsNone(parse_and_verify_token(issued.token, b"b" * 32, issued.verifier))

    def test_malformed_token_is_denied(self) -> None:
        self.assertIsNone(parse_and_verify_token("not-a-token", b"a" * 32, "0" * 64))


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


if __name__ == "__main__":
    unittest.main()
