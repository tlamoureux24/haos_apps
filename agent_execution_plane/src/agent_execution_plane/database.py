"""Generation-1 persistence and bounded operational activity journal."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

SCHEMA_VERSION = 1
MAX_ACTIVITY_ENTRIES = 10_000
RETENTION_DAYS = 30


def now_iso() -> str:
    return datetime.now().astimezone().isoformat(timespec="milliseconds")


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA journal_mode=WAL")
    connection.execute("PRAGMA foreign_keys=ON")
    try:
        with connection:
            yield connection
    finally:
        connection.close()


def initialize(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS schema_info (
                singleton INTEGER PRIMARY KEY CHECK (singleton = 1),
                generation INTEGER NOT NULL
            );
            INSERT OR IGNORE INTO schema_info(singleton, generation) VALUES (1, 1);
            CREATE TABLE IF NOT EXISTS activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                occurred_at TEXT NOT NULL,
                event_code TEXT NOT NULL,
                category TEXT NOT NULL,
                status TEXT NOT NULL,
                source_ip TEXT
            );
            CREATE INDEX IF NOT EXISTS activity_occurred_at ON activity(occurred_at DESC, id DESC);
            CREATE TABLE IF NOT EXISTS models (
                id TEXT PRIMARY KEY,
                display_name TEXT NOT NULL,
                provider_family TEXT NOT NULL CHECK(provider_family IN ('ollama_compatible','openai_compatible','openai_chatgpt_oauth')),
                base_url TEXT,
                provider_model TEXT NOT NULL,
                encrypted_credential BLOB,
                enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                priority INTEGER NOT NULL UNIQUE CHECK(priority > 0),
                timeout_minutes REAL NOT NULL CHECK(timeout_minutes > 0),
                technical_state TEXT NOT NULL CHECK(technical_state IN ('available','unavailable','incompatible','unverified')),
                diagnostic_code TEXT,
                checked_at TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL,
                CHECK (
                    (provider_family = 'openai_chatgpt_oauth' AND base_url IS NULL AND encrypted_credential IS NULL)
                    OR
                    (provider_family != 'openai_chatgpt_oauth' AND base_url IS NOT NULL)
                )
            );
        """)
        models_sql = db.execute("SELECT sql FROM sqlite_master WHERE type='table' AND name='models'").fetchone()[0]
        if "openai_chatgpt_oauth" not in models_sql:
            db.executescript("""
                ALTER TABLE models RENAME TO models_before_oauth;
                CREATE TABLE models (
                    id TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL,
                    provider_family TEXT NOT NULL CHECK(provider_family IN ('ollama_compatible','openai_compatible','openai_chatgpt_oauth')),
                    base_url TEXT,
                    provider_model TEXT NOT NULL,
                    encrypted_credential BLOB,
                    enabled INTEGER NOT NULL CHECK(enabled IN (0,1)),
                    priority INTEGER NOT NULL UNIQUE CHECK(priority > 0),
                    timeout_minutes REAL NOT NULL CHECK(timeout_minutes > 0),
                    technical_state TEXT NOT NULL CHECK(technical_state IN ('available','unavailable','incompatible','unverified')),
                    diagnostic_code TEXT,
                    checked_at TEXT,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    CHECK ((provider_family = 'openai_chatgpt_oauth' AND base_url IS NULL AND encrypted_credential IS NULL) OR (provider_family != 'openai_chatgpt_oauth' AND base_url IS NOT NULL))
                );
                INSERT INTO models SELECT * FROM models_before_oauth;
                DROP TABLE models_before_oauth;
            """)
        generation = db.execute("SELECT generation FROM schema_info WHERE singleton=1").fetchone()[0]
        if generation != SCHEMA_VERSION:
            raise RuntimeError(f"Unsupported database generation: {generation}")


def prune(path: Path, *, now: datetime | None = None) -> None:
    cutoff = (now or datetime.now(timezone.utc)) - timedelta(days=RETENTION_DAYS)
    with connect(path) as db:
        db.execute("DELETE FROM activity WHERE julianday(occurred_at) < julianday(?)", (cutoff.isoformat(timespec="milliseconds"),))
        db.execute("DELETE FROM activity WHERE id NOT IN (SELECT id FROM activity ORDER BY id DESC LIMIT ?)", (MAX_ACTIVITY_ENTRIES,))


def record_activity(path: Path, event_code: str, category: str, status: str, source_ip: str | None = None) -> bool:
    try:
        with connect(path) as db:
            db.execute("INSERT INTO activity(occurred_at,event_code,category,status,source_ip) VALUES(?,?,?,?,?)", (now_iso(), event_code, category, status, source_ip))
    except sqlite3.Error:
        return False
    try:
        prune(path)
    except sqlite3.Error:
        # Retention maintenance is best effort and must not stop the application.
        pass
    return True


def list_activity(path: Path, limit: int = 100, offset: int = 0) -> dict[str, object]:
    limit = min(max(limit, 1), 100)
    offset = max(offset, 0)
    with connect(path) as db:
        total = db.execute("SELECT count(*) FROM activity").fetchone()[0]
        rows = db.execute("SELECT occurred_at,event_code,category,status,source_ip FROM activity ORDER BY id DESC LIMIT ? OFFSET ?", (limit, offset)).fetchall()
    return {"entries": [dict(row) for row in rows], "total": total, "limit": limit, "offset": offset}


def database_ready(path: Path) -> bool:
    try:
        with connect(path) as db:
            return db.execute("SELECT generation FROM schema_info WHERE singleton=1").fetchone()[0] == SCHEMA_VERSION
    except (OSError, sqlite3.Error, TypeError):
        return False


if __name__ == "__main__":
    if len(sys.argv) != 2 or sys.argv[1] != "initialize":
        raise SystemExit("usage: python -m agent_execution_plane.database initialize")
    from agent_execution_plane.settings import load_settings
    initialize(load_settings().database_path)
