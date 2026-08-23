from __future__ import annotations

import os
import asyncio
import sqlite3
import tempfile
import unittest
from contextlib import closing
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx

from mcp_capability_bridge import __version__
from mcp_capability_bridge.activity import ActivityJournal
from mcp_capability_bridge.admin_ui import ADMIN_CSS, ADMIN_JS
from mcp_capability_bridge.database import database_ready, initialize
from mcp_capability_bridge.ingress import cookie_secure
from mcp_capability_bridge.main import admin_page, build_runtime_state, create_apps
from mcp_capability_bridge.runtime import load_log_configuration
from mcp_capability_bridge.settings import Settings, load_settings


class SettingsTests(unittest.TestCase):
    def test_csrf_cookie_matches_browser_facing_ingress_scheme(self) -> None:
        http = SimpleNamespace(headers={}, url=SimpleNamespace(scheme="http"))
        forwarded_https = SimpleNamespace(headers={"x-forwarded-proto": "https, http"}, url=SimpleNamespace(scheme="http"))
        self.assertFalse(cookie_secure(http))
        self.assertTrue(cookie_secure(forwarded_https))

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
            self.assertEqual(tables, {"schema_info", "namespaces", "targets", "publications", "activity_events"})

    def test_ready_is_false_before_initialization(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            self.assertFalse(database_ready(Path(directory) / "missing.db"))

    def test_unknown_generation_is_refused_without_mutating_it(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.db"
            with sqlite3.connect(path) as database:
                database.execute(
                    "CREATE TABLE schema_info(singleton INTEGER PRIMARY KEY, generation INTEGER NOT NULL)"
                )
                database.execute(
                    "INSERT INTO schema_info(singleton, generation) VALUES(1, 99)"
                )
            with self.assertRaisesRegex(RuntimeError, "Unsupported database generation: 99"):
                initialize(path)
            with closing(sqlite3.connect(path)) as database:
                generation = database.execute(
                    "SELECT generation FROM schema_info WHERE singleton=1"
                ).fetchone()[0]
                tables = {
                    row[0]
                    for row in database.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
            self.assertEqual(generation, 99)
            self.assertEqual(tables, {"schema_info"})

    def test_generation_one_initialization_adds_activity_table_to_existing_database(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.db"
            with closing(sqlite3.connect(path)) as database:
                database.execute(
                    "CREATE TABLE schema_info(singleton INTEGER PRIMARY KEY, generation INTEGER NOT NULL)"
                )
                database.execute(
                    "INSERT INTO schema_info(singleton, generation) VALUES(1, 1)"
                )
            initialize(path)
            with closing(sqlite3.connect(path)) as database:
                table = database.execute(
                    "SELECT name FROM sqlite_master WHERE type='table' AND name='activity_events'"
                ).fetchone()
            self.assertEqual(table, ("activity_events",))


class ActivityJournalTests(unittest.TestCase):
    def test_journal_is_bounded_and_contains_only_explicit_safe_metadata(self) -> None:
        journal = ActivityJournal(limit=2)
        journal.record(event="tool_call", status="success", source="192.0.2.10", client="client_a", tool="ssh_uptime", adapter="ssh", duration_ms=12)
        journal.record(event="authentication", status="refused", source="192.0.2.11")
        journal.record(event="tool_call", status="failure", source="192.0.2.12", client="client_b", tool="web_open", adapter="web")
        rows = journal.list()
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0]["source"], "192.0.2.12")
        serialized = str(rows).lower()
        for forbidden in ("credential", "authorization", "arguments", "result", "payload"):
            self.assertNotIn(forbidden, serialized)

    def test_journal_is_persistent_across_instances_and_remains_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "bridge.db"
            initialize(path)
            journal = ActivityJournal(path, limit=2)
            journal.record(event="first", status="success", source="system")
            journal.record(
                event="second",
                status="failure",
                source="192.0.2.1",
                tool="web_open",
                adapter="web",
            )
            journal.record(event="third", status="success", source="system")

            restarted = ActivityJournal(path, limit=2)
            self.assertEqual(
                [row["event"] for row in restarted.list()],
                ["third", "second"],
            )
            with closing(sqlite3.connect(path)) as database:
                count = database.execute(
                    "SELECT COUNT(*) FROM activity_events"
                ).fetchone()[0]
            self.assertEqual(count, 2)

    def test_runtime_lifecycle_records_started_ready_and_stopped(self) -> None:
        async def scenario() -> None:
            with tempfile.TemporaryDirectory() as directory:
                settings = Settings(Path(directory), "info", "127.0.0.1")
                initialize(settings.database_path)
                state = build_runtime_state(settings)
                _, public = create_apps(state)
                async with public.router.lifespan_context(public):
                    self.assertEqual(
                        [row["event"] for row in reversed(state.activity.list())],
                        ["app_started", "app_ready"],
                    )
                self.assertEqual(state.activity.list()[0]["event"], "app_stopped")

        asyncio.run(scenario())


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

    def test_refused_authentication_is_visible_as_safe_activity(self) -> None:
        async def scenario() -> None:
            secret = "Bearer must-never-appear"
            refused = await self.request(self.public, "POST", "/mcp", headers={"Authorization": secret})
            self.assertEqual(refused.status_code, 401)
            activity = await self.request(self.admin, "GET", "/admin/api/v1/activity", headers={"X-Ingress-Path": "/api/hassio_ingress/test"})
            self.assertEqual(activity.status_code, 200)
            row = activity.json()["events"][0]
            self.assertEqual((row["event"], row["status"]), ("authentication", "refused"))
            self.assertNotIn("must-never-appear", activity.text)

        asyncio.run(scenario())

    def test_admin_requires_ingress_context_and_exposes_no_mcp(self) -> None:
        async def scenario() -> None:
            self.assertEqual((await self.request(self.admin, "GET", "/")).status_code, 403)
            headers = {"X-Ingress-Path": "/api/hassio_ingress/test"}
            page = await self.request(self.admin, "GET", "/", headers=headers)
            self.assertEqual(page.status_code, 200)
            self.assertNotIn("; Secure", page.headers["set-cookie"])
            secure_page = await self.request(
                self.admin, "GET", "/", headers={**headers, "X-Forwarded-Proto": "https"},
            )
            self.assertIn("; Secure", secure_page.headers["set-cookie"])
            self.assertIn("MCP Capability Bridge <b>v1.1.6</b>", page.text)
            self.assertIn('/api/hassio_ingress/test/admin/assets/admin.css', page.text)
            self.assertNotIn('name="key"', page.text)
            status = (await self.request(self.admin, "GET", "/admin/api/v1/status", headers=headers)).json()
            self.assertEqual(status["public_surface"], "authenticated_mcp")
            self.assertEqual(status["adapters"], [{"type_key": "ssh", "display_name": "SSH"}, {"type_key": "web", "display_name": "Web"}])
            self.assertEqual(status["target_summary"], {"enabled": 0, "disabled": 0})
            self.assertEqual(status["runtime"], {"active_operations": 0, "active_namespaces": 0, "active_targets": 0, "active_sessions": 0})
            for element_id in ("namespace-count", "target-count", "publication-count", "adapter-count", "operation-count", "busy-client-count", "busy-target-count", "session-count"):
                self.assertIn(f'id="{element_id}"', page.text)
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
                json={"display_name": "Client one"},
            )
            self.assertEqual(created.status_code, 201)
            self.assertEqual(created.json()["namespace"]["key"], "client_one")
            token = created.json()["token"]
            listed = await self.request(self.admin, "GET", "/admin/api/v1/namespaces", headers={"X-Ingress-Path": ingress})
            self.assertNotIn(token, listed.text)
            self.assertNotIn("credential_verifier", listed.text)
        asyncio.run(scenario())

    def test_web_target_requires_confirmed_resolution_and_publishes_read_only_tools(self) -> None:
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
            self.assertEqual(target["key"], "web_test")
            listed = next(item for item in self.state.store.list_targets() if item["id"] == target["id"])
            self.assertEqual([item["id"] for item in listed["capabilities"]], ["open", "snapshot", "wait", "navigate", "click", "fill", "select", "press", "close"])
            configuration = self.state.store.get_target_configuration(target["id"])
            self.assertEqual(configuration["navigation_origins"], ["https://app.internal"])
            self.assertEqual(configuration["resource_origins"], ["https://app.internal"])
            self.assertEqual(configuration["authentication_origins"], [])
            self.assertEqual(configuration["websocket_origins"], [])

        asyncio.run(scenario())


class AdministrationUiTests(unittest.TestCase):
    def test_certificate_regeneration_uses_neutral_secondary_button(self) -> None:
        self.assertIn(".secondary{background:var(--surface2);font-weight:700}", ADMIN_CSS)
        self.assertIn('id="certificate-regenerate" class="secondary"', ADMIN_JS)

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
        self.assertIn("serviceOperational:'Service opérationnel'", ADMIN_JS)
        self.assertIn("serviceOperational:'Service operational'", ADMIN_JS)
        self.assertNotIn("scopeAdapters", ADMIN_JS)

    def test_operational_ui_status_activity_and_drawer_reset(self) -> None:
        for contract in (
            "serviceOperational", "serviceUnavailable", "loadActivity",
            "stopDynamicTimers", "activityTimer=setInterval(loadActivity,5000)",
            "f.reset();f.querySelector('.message').textContent=''",
            "activityCategory", "activityDetail", 'class="activity-state',
        ):
            self.assertIn(contract, ADMIN_JS)
        self.assertNotIn("status-open", ADMIN_JS)
        self.assertIn(".service-state", ADMIN_CSS)
        self.assertIn(".activity-code", ADMIN_CSS)
        self.assertIn(".activity-state", ADMIN_CSS)
        self.assertIn("table{width:100%", ADMIN_CSS)
        self.assertIn("serviceDegraded:'Service dégradé'", ADMIN_JS)
        self.assertIn("listenerNotStarted:'Listener non démarré'", ADMIN_JS)
        self.assertIn("confirm(tr('confirmCertificateRegeneration'))", ADMIN_JS)
        self.assertIn(".service-state.degraded", ADMIN_CSS)
        page = admin_page("")
        self.assertIn('data-i18n="category"', page)
        self.assertNotIn('data-i18n="adapter"></th>', page)

    def test_lot_two_ui_preserves_namespaces_and_adds_bounded_ssh_forms(self) -> None:
        for contract in ("createClient", "credentialOnce", "data-rotate", "data-revoke", "data-archive", "show-archived"):
            self.assertIn(contract, ADMIN_JS)
        for contract in ("target-form", "capability-form", "publication-form", "scanHostKey", "effectCapable"):
            self.assertIn(contract, ADMIN_JS)
        for contract in ("web-target-form", "web-resolve", "data-test-web", "webResolutionId"):
            self.assertIn(contract, ADMIN_JS)
        self.assertNotIn('name="key"', ADMIN_JS)
        self.assertNotIn("key:f.key.value", ADMIN_JS)

    def test_ssh_capability_view_excludes_generated_web_capabilities(self) -> None:
        self.assertIn("targets.filter(t=>t.adapter_type==='ssh').flatMap", ADMIN_JS)
        self.assertIn("f.target_id.innerHTML=targets.filter(t=>t.enabled)", ADMIN_JS)


class RuntimeTopologyTests(unittest.TestCase):
    def test_application_logger_follows_configured_level(self) -> None:
        for level in ("debug", "info", "warning", "error"):
            with self.subTest(level=level):
                logger = load_log_configuration(level)["loggers"]["mcp_capability_bridge"]
                self.assertEqual(logger["level"], level.upper())
                self.assertEqual(logger["handlers"], ["default"])
                self.assertFalse(logger["propagate"])

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
