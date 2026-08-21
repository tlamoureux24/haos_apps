"""Generation-one metadata-only persistence."""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from pathlib import Path

SCHEMA_VERSION = 1


@contextmanager
def connect(path: Path):
    connection = sqlite3.connect(path)
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
