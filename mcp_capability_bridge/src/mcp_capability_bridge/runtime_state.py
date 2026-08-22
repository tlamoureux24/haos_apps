"""Authoritative in-process operation counters and concurrency limits."""

from __future__ import annotations

import asyncio
from collections import Counter
from contextlib import asynccontextmanager


class RuntimeCapacityError(RuntimeError):
    """Stable fail-fast capacity or shutdown refusal."""


class RuntimeCounters:
    def __init__(self, global_limit: int = 8, namespace_limit: int = 2, adapter_limit: int = 4, target_limit: int = 2):
        self._global_limit = global_limit
        self._namespace_limit = namespace_limit
        self._adapter_limit = adapter_limit
        self._target_limit = target_limit
        self._active_global = 0
        self._active_namespaces: Counter[str] = Counter()
        self._active_adapters: Counter[str] = Counter()
        self._active_targets: Counter[str] = Counter()
        self._namespace_tasks: dict[str, set[asyncio.Task]] = {}
        self._closing = False

    @asynccontextmanager
    async def operation(self, namespace_id: str, target_id: str, adapter_type: str = "core"):
        if self._closing:
            raise RuntimeCapacityError("runtime_stopping")
        if self._active_global >= self._global_limit:
            raise RuntimeCapacityError("bridge_busy")
        if self._active_namespaces[namespace_id] >= self._namespace_limit:
            raise RuntimeCapacityError("namespace_busy")
        if self._active_adapters[adapter_type] >= self._adapter_limit:
            raise RuntimeCapacityError("adapter_busy")
        if self._active_targets[target_id] >= self._target_limit:
            raise RuntimeCapacityError("target_busy")
        task = asyncio.current_task()
        if task is None:
            raise RuntimeError("operation_task_missing")
        self._namespace_tasks.setdefault(namespace_id, set()).add(task)
        self._active_global += 1
        self._active_namespaces[namespace_id] += 1
        self._active_adapters[adapter_type] += 1
        self._active_targets[target_id] += 1
        try:
            yield
        finally:
            self._active_global -= 1
            self._active_namespaces[namespace_id] -= 1
            self._active_adapters[adapter_type] -= 1
            self._active_targets[target_id] -= 1
            self._namespace_tasks[namespace_id].discard(task)

    def snapshot(self) -> dict[str, object]:
        return {
            "active_operations": self._active_global,
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
        await self._cancel(tasks)

    async def shutdown(self) -> None:
        self._closing = True
        current = asyncio.current_task()
        tasks = {
            task
            for owned in self._namespace_tasks.values()
            for task in owned
            if task is not current and not task.done()
        }
        await self._cancel(list(tasks))

    @staticmethod
    async def _cancel(tasks: list[asyncio.Task]) -> None:
        for task in tasks:
            task.cancel()
        if not tasks:
            return
        done, pending = await asyncio.wait(tasks, timeout=10)
        for task in pending:
            task.cancel()
        for task in done:
            try:
                task.result()
            except BaseException:
                pass
