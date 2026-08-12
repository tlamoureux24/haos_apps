from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from importlib import import_module
from pathlib import Path
from unittest.mock import patch

from agent_gateway.database import database_ready
from agent_gateway.settings import load_settings


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
                INSERT INTO alembic_version VALUES('0001_foundation');
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
        with patch.dict(os.environ, {"AGENT_GATEWAY_SURFACE": "public"}):
            module = import_module("agent_gateway.main")
        exposed_paths = {route.path for route in module.app.routes}
        self.assertNotIn("/", exposed_paths)
        self.assertEqual(exposed_paths, {"/health/live", "/health/ready"})


if __name__ == "__main__":
    unittest.main()
