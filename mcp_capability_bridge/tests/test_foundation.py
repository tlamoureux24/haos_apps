from __future__ import annotations

import os
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx

from mcp_capability_bridge import __version__
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.database import database_ready, initialize
from mcp_capability_bridge.main import build_runtime_state, create_apps
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
    def test_generation_one_contains_only_lot_one_configuration(self) -> None:
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
            self.assertEqual(tables, {"schema_info", "namespaces", "targets", "publications"})

    def test_ready_is_false_before_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(database_ready(Path(directory) / "missing.db"))


class SurfaceTests(unittest.TestCase):
    def setUp(self) -> None:
        self.directory = tempfile.TemporaryDirectory()
        self.settings = Settings(Path(self.directory.name), "info", "127.0.0.1")
        initialize(self.settings.database_path)
        self.state = build_runtime_state(self.settings)
        self.admin, self.public = create_apps(self.state)

    def tearDown(self) -> None:
        self.directory.cleanup()

    async def request(self, app, method: str, path: str, **kwargs) -> httpx.Response:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://testserver") as client:
            return await client.request(method, path, **kwargs)

    def test_public_surface_is_health_plus_authenticated_mcp(self) -> None:
        async def scenario() -> None:
            self.assertEqual((await self.request(self.public, "GET", "/health/live")).json(), {"status": "live"})
            ready = await self.request(self.public, "GET", "/health/ready")
            self.assertEqual(ready.status_code, 200)
            self.assertEqual(ready.json(), {"status": "ready", "version": __version__})
            for path in ("/", "/admin/api/v1/status"):
                self.assertEqual((await self.request(self.public, "GET", path)).status_code, 404)
            self.assertEqual((await self.request(self.public, "GET", "/mcp")).status_code, 401)
        asyncio.run(scenario())

    def test_admin_requires_ingress_context_and_exposes_no_mcp(self) -> None:
        async def scenario() -> None:
            self.assertEqual((await self.request(self.admin, "GET", "/")).status_code, 403)
            headers = {"X-Ingress-Path": "/api/hassio_ingress/test"}
            page = await self.request(self.admin, "GET", "/", headers=headers)
            self.assertEqual(page.status_code, 200)
            self.assertIn("MCP Capability Bridge <b>v0.4.0</b>", page.text)
            self.assertIn('/api/hassio_ingress/test/admin/assets/admin.css', page.text)
            status = (await self.request(self.admin, "GET", "/admin/api/v1/status", headers=headers)).json()
            self.assertEqual(status["public_surface"], "authenticated_mcp")
            self.assertEqual(status["adapters"], [{"type_key": "ssh", "display_name": "SSH"}, {"type_key": "web", "display_name": "Web"}])
            self.assertEqual((await self.request(self.admin, "GET", "/mcp", headers=headers)).status_code, 404)
        asyncio.run(scenario())

    def test_admin_namespace_secret_is_returned_once_and_never_listed(self) -> None:
        async def scenario() -> None:
            ingress = "/api/hassio_ingress/test"
            headers = {
                "X-Ingress-Path": ingress,
                "Cookie": f"mcb_csrf={self.state.csrf_token}",
                "X-CSRF-Token": self.state.csrf_token,
            }
            created = await self.request(
                self.admin, "POST", "/admin/api/v1/namespaces", headers=headers,
                json={"key": "client_one", "display_name": "Client one"},
            )
            self.assertEqual(created.status_code, 201)
            token = created.json()["token"]
            listed = await self.request(self.admin, "GET", "/admin/api/v1/namespaces", headers={"X-Ingress-Path": ingress})
            self.assertNotIn(token, listed.text)
            self.assertNotIn("credential_verifier", listed.text)
        asyncio.run(scenario())

    def test_web_target_requires_confirmed_resolution_and_publishes_no_tool(self) -> None:
        async def scenario() -> None:
            ingress = "/api/hassio_ingress/test"
            headers = {
                "X-Ingress-Path": ingress,
                "Cookie": f"mcb_csrf={self.state.csrf_token}",
                "X-CSRF-Token": self.state.csrf_token,
            }
            with patch(
                "mcp_capability_bridge.main.resolve_host",
                new=AsyncMock(return_value=("10.0.0.8",)),
            ):
                resolved = await self.request(
                    self.admin,
                    "POST",
                    "/admin/api/v1/web/resolve",
                    headers=headers,
                    json={"base_url": "https://app.internal/path"},
                )
            self.assertEqual(resolved.status_code, 200)
            created = await self.request(
                self.admin,
                "POST",
                "/admin/api/v1/web/targets",
                headers=headers,
                json={
                    "resolution_id": resolved.json()["resolution_id"],
                    "key": "web_test",
                    "display_name": "Web test",
                    "base_url": "https://app.internal/path",
                    "verify_tls": True,
                    "inactivity_seconds": 300,
                    "absolute_seconds": 1800,
                },
            )
            self.assertEqual(created.status_code, 201)
            target = created.json()["target"]
            self.assertEqual(target["adapter_type"], "web")
            listed = next(item for item in self.state.store.list_targets() if item["id"] == target["id"])
            self.assertEqual(listed["capabilities"], [])
            configuration = self.state.store.get_target_configuration(target["id"])
            self.assertEqual(configuration["navigation_origins"], ["https://app.internal"])
            self.assertEqual(configuration["resource_origins"], ["https://app.internal"])
            self.assertEqual(configuration["authentication_origins"], [])
            self.assertEqual(configuration["websocket_origins"], [])

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
            "Vue d’ensemble", "Overview", "e.key==='Escape'",
            "returnFocus?.focus()", "e.key!=='Tab'",
            "function clearSecrets()", "clearSecrets();scanId='';shell.hidden=true",
        ):
            self.assertIn(contract, ADMIN_JS)

    def test_lot_two_ui_preserves_namespaces_and_adds_bounded_ssh_forms(self) -> None:
        for contract in ("createClient", "credentialOnce", "data-rotate", "data-revoke", "data-archive", "show-archived"):
            self.assertIn(contract, ADMIN_JS)
        for contract in ("target-form", "capability-form", "publication-form", "scanHostKey", "effectCapable"):
            self.assertIn(contract, ADMIN_JS)
        for contract in ("web-target-form", "web-resolve", "data-test-web", "webResolutionId"):
            self.assertIn(contract, ADMIN_JS)


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
