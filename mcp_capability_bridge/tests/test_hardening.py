from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path

import httpx

from mcp_capability_bridge.database import initialize
from mcp_capability_bridge.main import RequestBodyLimitMiddleware, build_runtime_state, create_apps
from mcp_capability_bridge.runtime_state import RuntimeCapacityError, RuntimeCounters
from mcp_capability_bridge.settings import Settings


class RuntimeCapacityTests(unittest.IsolatedAsyncioTestCase):
    async def test_limits_fail_immediately_without_queuing(self) -> None:
        counters = RuntimeCounters(global_limit=2, namespace_limit=1, adapter_limit=2, target_limit=2)
        entered = asyncio.Event()
        release = asyncio.Event()

        async def hold() -> None:
            async with counters.operation("client-a", "target-a", "ssh"):
                entered.set()
                await release.wait()

        task = asyncio.create_task(hold())
        await entered.wait()
        with self.assertRaisesRegex(RuntimeCapacityError, "namespace_busy"):
            async with counters.operation("client-a", "target-b", "ssh"):
                self.fail("capacity refusal must not queue")
        release.set()
        await task
        self.assertEqual(counters.snapshot()["active_operations"], 0)

    async def test_shutdown_refuses_new_work_and_cancels_active_operation(self) -> None:
        counters = RuntimeCounters()
        entered = asyncio.Event()

        async def hold() -> None:
            async with counters.operation("client-a", "target-a", "web"):
                entered.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(hold())
        await entered.wait()
        await counters.shutdown()
        self.assertTrue(task.cancelled())
        with self.assertRaisesRegex(RuntimeCapacityError, "runtime_stopping"):
            async with counters.operation("client-b", "target-b", "ssh"):
                self.fail("shutdown must refuse new work")


class RequestLimitTests(unittest.IsolatedAsyncioTestCase):
    async def test_malformed_authenticated_mcp_request_is_bounded_and_runtime_recovers(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), "info", "127.0.0.1")
            initialize(settings.database_path)
            state = build_runtime_state(settings)
            _, public = create_apps(state)
            _, credential = state.store.create_namespace("client", "Client")
            transport = httpx.ASGITransport(app=public)
            headers = {
                "Authorization": f"Bearer {credential.token}",
                "Accept": "application/json, text/event-stream",
                "Content-Type": "application/json",
            }
            async with public.router.lifespan_context(public):
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    malformed = await client.post("/mcp", headers=headers, content=b'{"jsonrpc":')
                    ready = await client.get("/health/ready")
            self.assertIn(malformed.status_code, {400, 422})
            self.assertLessEqual(len(malformed.content), 4096)
            self.assertEqual(ready.status_code, 200)

    async def test_declared_oversized_mcp_body_is_refused_before_authentication(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            settings = Settings(Path(directory), "info", "127.0.0.1")
            initialize(settings.database_path)
            _, public = create_apps(build_runtime_state(settings))
            transport = httpx.ASGITransport(app=public)
            async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/mcp", content=b"x" * (256 * 1024 + 1))
            self.assertEqual(response.status_code, 413)
            self.assertEqual(response.json(), {"error": {"code": "request_too_large"}})

    async def test_chunked_oversized_body_is_refused_without_calling_downstream(self) -> None:
        called = False

        async def downstream(scope, receive, send):
            nonlocal called
            called = True

        middleware = RequestBodyLimitMiddleware(downstream, limit=4)
        chunks = iter(
            (
                {"type": "http.request", "body": b"123", "more_body": True},
                {"type": "http.request", "body": b"45", "more_body": False},
            )
        )
        sent = []

        async def receive():
            return next(chunks)

        async def send(message):
            sent.append(message)

        await middleware(
            {"type": "http", "method": "POST", "path": "/mcp", "headers": []},
            receive,
            send,
        )
        self.assertFalse(called)
        self.assertEqual(sent[0]["status"], 413)
