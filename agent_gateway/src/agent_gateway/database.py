"""Small database health boundary used during the foundation phase."""

from __future__ import annotations

import sqlite3
from pathlib import Path


EXPECTED_REVISION = "0003_intake_rate_limits"


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def database_ready(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            revision = connection.execute(
                "SELECT version_num FROM alembic_version"
            ).fetchone()
            application = connection.execute(
                "SELECT value FROM gateway_metadata WHERE key = 'application'"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return bool(
        integrity
        and integrity[0] == "ok"
        and revision
        and revision[0] == EXPECTED_REVISION
        and application
        and application[0] == "agent_gateway"
    )
