"""Authoritative in-process operation counters and concurrency limits."""

from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager


class RuntimeCounters:
    def __init__(self, global_limit: int = 8, namespace_limit: int = 2, adapter_limit: int = 4):
        self._global = asyncio.Semaphore(global_limit)
        self._namespace_limit = namespace_limit
        self._namespace_semaphores: dict[str, asyncio.Semaphore] = {}
        self._adapter_limit = adapter_limit
        self._adapter_semaphores: dict[str, asyncio.Semaphore] = {}
        self._active_namespaces: Counter[str] = Counter()
        self._active_targets: Counter[str] = Counter()
        self._namespace_tasks: dict[str, set[asyncio.Task]] = {}

    @asynccontextmanager
    async def operation(self, namespace_id: str, target_id: str, adapter_type: str = "core"):
        namespace = self._namespace_semaphores.setdefault(namespace_id, asyncio.Semaphore(self._namespace_limit))
        adapter = self._adapter_semaphores.setdefault(adapter_type, asyncio.Semaphore(self._adapter_limit))
        async with self._global, namespace, adapter:
            task = asyncio.current_task()
            if task is None:
                raise RuntimeError("operation_task_missing")
            self._namespace_tasks.setdefault(namespace_id, set()).add(task)
            self._active_namespaces[namespace_id] += 1
            self._active_targets[target_id] += 1
            try:
                yield
            finally:
                self._active_namespaces[namespace_id] -= 1
                self._active_targets[target_id] -= 1
                self._namespace_tasks[namespace_id].discard(task)

    def snapshot(self) -> dict[str, object]:
        return {
            "active_operations": sum(self._active_targets.values()),
            "active_namespaces": sum(value > 0 for value in self._active_namespaces.values()),
            "active_targets": sum(value > 0 for value in self._active_targets.values()),
            "active_sessions": 0,
        }

    def ensure_target_mutable(self, target_id: str) -> None:
        if self._active_targets[target_id] > 0:
            raise RuntimeError("target_in_use")

    def target_in_use(self, target_id: str) -> bool:
        return self._active_targets[target_id] > 0

    async def cancel_namespace(self, namespace_id: str) -> None:
        current = asyncio.current_task()
        tasks = [task for task in self._namespace_tasks.get(namespace_id, ()) if task is not current and not task.done()]
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
