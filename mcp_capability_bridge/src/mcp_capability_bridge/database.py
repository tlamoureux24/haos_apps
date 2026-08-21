"""Generation-one metadata-only persistence."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path, timeout=10)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA secure_delete=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as database:
        database.executescript("""
            CREATE TABLE IF NOT EXISTS schema_info (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                generation INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO schema_info(singleton, generation) VALUES (1, 1);
            CREATE TABLE IF NOT EXISTS namespaces (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                status TEXT NOT NULL CHECK(status IN ('active','revoked','archived')),
                credential_id TEXT NOT NULL UNIQUE,
                credential_verifier TEXT NOT NULL,
                credential_generation INTEGER NOT NULL CHECK(credential_generation > 0),
                inventory_revision INTEGER NOT NULL CHECK(inventory_revision > 0),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                revoked_at TEXT,
                archived_at TEXT
            );
            CREATE INDEX IF NOT EXISTS namespaces_status ON namespaces(status, created_at);
            CREATE TABLE IF NOT EXISTS targets (
                id TEXT PRIMARY KEY,
                key TEXT NOT NULL UNIQUE,
                display_name TEXT NOT NULL,
                adapter_type TEXT NOT NULL,
                configuration_json TEXT NOT NULL,
                encrypted_secret BLOB,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                technical_state TEXT NOT NULL CHECK(technical_state IN ('valid','invalid','unchecked')),
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS publications (
                namespace_id TEXT NOT NULL REFERENCES namespaces(id) ON DELETE CASCADE,
                target_id TEXT NOT NULL REFERENCES targets(id) ON DELETE CASCADE,
                capability_id TEXT NOT NULL,
                published_name TEXT NOT NULL,
                created_at TEXT NOT NULL,
                PRIMARY KEY(namespace_id, published_name),
                UNIQUE(namespace_id, target_id, capability_id)
            );
        """)
        generation = database.execute(
            "SELECT generation FROM schema_info WHERE singleton = 1"
        ).fetchone()[0]
        if generation != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported database generation: {generation}")


def database_ready(path: Path) -> bool:
    try:
        with connect(path) as database:
            row = database.execute(
                "SELECT generation FROM schema_info WHERE singleton = 1"
            ).fetchone()
        return row is not None and row[0] == SCHEMA_VERSION
    except (OSError, sqlite3.Error, TypeError):
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "initialize":
        raise SystemExit("usage: python -m mcp_capability_bridge.database initialize")
    from mcp_capability_bridge.settings import load_settings

    initialize(load_settings().database_path)
