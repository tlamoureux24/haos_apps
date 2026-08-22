"""Bounded, non-persistent and payload-free operational activity."""

from __future__ import annotations

from collections import deque
from datetime import datetime
from time import monotonic


class ActivityJournal:
    def __init__(self, limit: int = 500):
        self._events: deque[dict[str, object]] = deque(maxlen=limit)

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
        self._events.appendleft(row)

    def list(self, limit: int = 100) -> list[dict[str, object]]:
        return list(self._events)[: max(1, min(limit, 200))]

    @staticmethod
    def timer() -> float:
        return monotonic()

    @staticmethod
    def elapsed_ms(started: float) -> int:
        return round((monotonic() - started) * 1000)
