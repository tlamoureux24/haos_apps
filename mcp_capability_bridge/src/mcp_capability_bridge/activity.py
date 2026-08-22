"""Bounded, persistent and payload-free operational activity."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from pathlib import Path
from time import monotonic

from mcp_capability_bridge.database import connect


class ActivityJournal:
    def __init__(self, path: Path | None = None, limit: int = 500):
        self._path = path
        self._limit = max(1, min(limit, 5000))
        self._events: deque[dict[str, object]] = deque(maxlen=self._limit)

    def record(self, *, event: str, status: str, source: str, client: str = "—", tool: str = "—", adapter: str = "—", duration_ms: int | None = None) -> None:
        row: dict[str, object] = {
            "occurred_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "event": event,
            "status": status,
            "source": source or "—",
            "client": client,
            "tool": tool,
            "adapter": adapter,
        }
        if duration_ms is not None:
            row["duration_ms"] = max(0, duration_ms)
        if self._path is None:
            self._events.appendleft(row)
            return
        with connect(self._path) as database:
            database.execute(
                "INSERT INTO activity_events(occurred_at,event,status,source,client,tool,adapter,duration_ms) VALUES(?,?,?,?,?,?,?,?)",
                (row["occurred_at"], row["event"], row["status"], row["source"], row["client"], row["tool"], row["adapter"], row.get("duration_ms")),
            )
            database.execute(
                "DELETE FROM activity_events WHERE id NOT IN (SELECT id FROM activity_events ORDER BY id DESC LIMIT ?)",
                (self._limit,),
            )

    def list(self, limit: int = 100) -> list[dict[str, object]]:
        bounded = max(1, min(limit, 200))
        if self._path is None:
            return list(self._events)[:bounded]
        with connect(self._path) as database:
            rows = database.execute(
                "SELECT occurred_at,event,status,source,client,tool,adapter,duration_ms FROM activity_events ORDER BY id DESC LIMIT ?",
                (bounded,),
            ).fetchall()
        return [{key: row[key] for key in row.keys() if row[key] is not None} for row in rows]

    @staticmethod
    def timer() -> float:
        return monotonic()

    @staticmethod
    def elapsed_ms(started: float) -> int:
        return round((monotonic() - started) * 1000)
