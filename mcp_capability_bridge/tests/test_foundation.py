from __future__ import annotations

import os
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import patch

import httpx

from mcp_capability_bridge import __version__
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.database import database_ready, initialize
from mcp_capability_bridge.main import RuntimeState, create_apps
from mcp_capability_bridge.settings import Settings, load_settings


class SettingsTests(unittest.TestCase):
    def test_defaults_are_two_fixed_internal_listeners(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
        self.assertEqual((settings.public_port, settings.admin_port), (8098, 8099))
        self.assertEqual(settings.log_level, "info")

    def test_rejects_invalid_log_level_and_proxy_ip(self) -> None:
        for environment in (
            {"MCP_CAPABILITY_BRIDGE_LOG_LEVEL": "trace"},
            {"MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP": "not-an-ip"},
        ):
            with self.subTest(environment=environment), patch.dict(os.environ, environment, clear=True):
                with self.assertRaises(RuntimeError):
                    load_settings()


class DatabaseTests(unittest.TestCase):
    def test_generation_one_contains_metadata_only(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.db"
            initialize(path)
            self.assertTrue(database_ready(path))
            with closing(sqlite3.connect(path)) as database:
                tables = {
                    row[0] for row in database.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(tables, {"schema_info"})

    def test_ready_is_false_before_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(database_ready(Path(directory) / "missing.db"))


class SurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.directory.name), "info", "127.0.0.1")
        initialize(self.settings.database_path)
        self.admin, self.public = create_apps(RuntimeState(self.settings))

    def tearDown(self) -> None:
        self.directory.cleanup()

    async def request(self, app, method: str, path: str, **kwargs) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    def test_public_surface_is_health_only(self) -> None:
        async def scenario() -> None:
            self.assertEqual((await self.request(self.public, "GET", "/health/live")).json(), {"status": "live"})
            ready = await self.request(self.public, "GET", "/health/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(ready.json(), {"status": "ready", "version": __version__})
            for path in ("/", "/admin/api/v1/status", "/mcp"):
                self.assertEqual((await self.request(self.public, "GET", path)).status_code, 404)
        asyncio.run(scenario())

    def test_admin_requires_ingress_context_and_exposes_no_mcp(self) -> None:
        async def scenario() -> None:
            self.assertEqual((await self.request(self.admin, "GET", "/")).status_code, 403)
            headers = {"X-Ingress-Path": "/api/hassio_ingress/test"}
            page = await self.request(self.admin, "GET", "/", headers=headers)
            self.assertEqual(page.status_code, 200)
            self.assertIn("MCP Capability Bridge <b>v0.1.0</b>", page.text)
            self.assertIn('/api/hassio_ingress/test/admin/assets/admin.css', page.text)
            status = (await self.request(self.admin, "GET", "/admin/api/v1/status", headers=headers)).json()
            self.assertEqual(status["public_surface"], "health_only")
            self.assertEqual((await self.request(self.admin, "GET", "/mcp", headers=headers)).status_code, 404)
        asyncio.run(scenario())


class AdministrationUiTests(unittest.TestCase):
    def test_shared_suite_conventions_are_present(self) -> None:
        for contract in (
            ":root{color-scheme:light;scrollbar-gutter:stable",
            "html[data-theme=dark]",
            ".pagehead",
            ".drawer-shell",
            "@media(max-width:560px)",
        ):
            self.assertIn(contract, ADMIN_CSS)
        for contract in (
            "navigator.language", "mcb-language", "mcb-theme",
            "Vue d’ensemble", "Overview", "event.key==='Escape'",
            "returnFocus?.focus()", "event.key!=='Tab'",
        ):
            self.assertIn(contract, ADMIN_JS)

    def test_lot_zero_does_not_claim_unimplemented_features(self) -> None:
        self.assertIn("No MCP endpoint, client, credential, target or adapter", ADMIN_JS)
        self.assertNotIn("fetch(`${base}/mcp", ADMIN_JS)


class RuntimeTopologyTests(unittest.TestCase):
    def test_launcher_starts_one_python_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        launcher = (root / "run.sh").read_text(encoding="utf-8")
        runtime = (root / "src/mcp_capability_bridge/runtime.py").read_text(encoding="utf-8")
        self.assertEqual(launcher.count("python3 -m mcp_capability_bridge.runtime"), 1)
        self.assertNotIn("python3 -m uvicorn", launcher)
        self.assertIn("asyncio.gather", runtime)
        self.assertIn("ManagedServer", runtime)
        self.assertIn("server.should_exit = True", runtime)


if __name__ == "__main__":
    unittest.main()
