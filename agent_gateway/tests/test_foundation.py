from __future__ import annotations

import os
import asyncio
import base64
import json
import sqlite3
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from agent_gateway.database import database_ready, initialize_database
from agent_gateway.admin_ui import ADMIN_CSS, ADMIN_JS
from agent_gateway.control_plane import AuthorizationError, MAX_INCIDENT_SUBJECTS, ControlPlane, TaskExecutionActiveError, validate_json_contract
from agent_gateway.connectors import (
    ConnectorSchemaRejected,
    connector_display_endpoint,
    validate_discovered_tool_schema,
    validate_streamable_http_url,
)
from agent_gateway.http_api import (
    admin_check_connector,
    admin_create_connector,
    admin_rotate_connector_secret,
    admin_set_connector_enabled,
    admin_update_connector,
)
from agent_gateway.json_contracts import validate_json_schema
from agent_gateway.mcp_api import capability_result_content
from agent_gateway.policy import decide, validate_actions
from agent_gateway.redaction import redact
from agent_gateway.security import issue_credential, load_or_create_pepper, parse_and_verify_token
from agent_gateway.settings import load_settings
from agent_gateway.surfaces import exposed_paths


class SettingsTests(unittest.TestCase):
    def test_defaults_to_public_surface(self) -> None:
        with patch.dict(os.environ, {}, clear=True):
            settings = load_settings()
        self.assertEqual(settings.surface, "public")

    def test_rejects_unknown_surface(self) -> None:
        with patch.dict(os.environ, {"AGENT_GATEWAY_SURFACE": "both"}, clear=True):
            with self.assertRaises(RuntimeError):
                load_settings()


class InternationalizationTests(unittest.TestCase):
    def test_admin_interface_supports_french_and_english(self) -> None:
        self.assertIn("navigator.language", ADMIN_JS)
        self.assertIn("agw-language", ADMIN_JS)
        self.assertIn("MutationObserver", ADMIN_JS)
        self.assertIn("'Vue d’ensemble':'Overview'", ADMIN_JS)
        self.assertIn("'Connecteurs MCP':'MCP connectors'", ADMIN_JS)
        self.assertIn("'Audit et rétention':'Audit and retention'", ADMIN_JS)
        self.assertIn("en-GB", ADMIN_JS)


class AdministrationInterfaceTests(unittest.TestCase):
    def test_root_reserves_a_stable_scrollbar_gutter(self) -> None:
        self.assertIn("html{scrollbar-gutter:stable}", ADMIN_CSS)

    def test_navigation_and_bounded_polling_use_targeted_view_loaders(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_gateway"
            / "main.py"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "const viewLoaders={overview:refresh,'identities-view':loadIdentities,"
            "events:loadEvents,tasks:loadTaskComposer,triggers:loadMappings,"
            "schedules:loadSchedules,jobs:loadJobs,reports:loadReports,"
            "connectors:loadConnectors,audit:loadAuditPage}",
            ADMIN_JS,
        )
        self.assertIn(
            "const autoRefreshIntervals={overview:10000,events:10000,jobs:5000,"
            "reports:10000,audit:10000}",
            ADMIN_JS,
        )
        self.assertNotIn("loadOperationalViews", ADMIN_JS)
        self.assertIn("document.visibilityState!=='visible'", ADMIN_JS)
        self.assertIn("!drawerShell.hidden", ADMIN_JS)
        self.assertIn("#${view} details[open]", ADMIN_JS)
        self.assertIn("viewRefreshes.has(view)", ADMIN_JS)
        self.assertIn("if(document.visibilityState==='visible')refreshActiveView()", ADMIN_JS)
        for view in ("overview", "events", "jobs", "reports", "audit"):
            self.assertIn(f'data-freshness="{view}"', main_source)
        self.assertIn("Actualisé à l’instant", ADMIN_JS)
        self.assertIn("Actualisé il y a ${seconds} s", ADMIN_JS)
        self.assertIn("Updated just now", ADMIN_JS)
        self.assertIn("Updated ${seconds}s ago", ADMIN_JS)

    def test_identity_administration_uses_a_dedicated_accessible_drawer(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_gateway"
            / "main.py"
        ).read_text(encoding="utf-8")

        self.assertIn('class="site-header"', main_source)
        self.assertIn('class="nav-scroll"', main_source)
        self.assertIn('data-view="identities-view"', main_source)
        self.assertIn('id="identity-create-open"', main_source)
        self.assertIn('role="dialog" aria-modal="true"', main_source)
        self.assertIn('aria-labelledby="drawer-title"', main_source)

    def test_identity_credential_requires_acknowledgement_or_confirmation(self) -> None:
        self.assertIn("credentialBox.classList.contains('show')&&!force", ADMIN_JS)
        self.assertIn("if(!confirm(warning))return false", ADMIN_JS)
        self.assertIn("document.querySelector('#credential-dismiss').onclick", ADMIN_JS)
        self.assertIn("restoreTarget?.focus()", ADMIN_JS)
        self.assertIn("event.key==='Escape'", ADMIN_JS)
        self.assertIn("document.body.classList.add('drawer-open')", ADMIN_JS)

    def test_operational_cockpit_and_configuration_drawers_are_wired(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_gateway"
            / "main.py"
        ).read_text(encoding="utf-8")

        for metric in (
            "metric-connectors",
            "metric-triggers",
            "metric-schedules",
            "metric-active-jobs",
            "metric-incidents",
            "metric-audit",
        ):
            self.assertIn(f'id="{metric}"', main_source)
        for form in (
            "task-create",
            "mapping-create",
            "schedule-create",
            "connector-create",
            "retention-form",
        ):
            self.assertIn(f"'{form}'", ADMIN_JS)
        self.assertIn("drawer.classList.toggle('wide'", ADMIN_JS)

    def test_task_drawer_contains_the_optional_fixed_argument_editor(self) -> None:
        for contract in (
            "fixed_arguments_v1",
            "Restreindre cet outil",
            "fixed_ordinary",
            "fixed_sensitive",
            "example_arguments",
            "parseArgumentValue",
        ):
            self.assertIn(contract, ADMIN_JS)
        self.assertIn("taskInputSchema", ADMIN_JS)
        self.assertIn("renderArgumentSummary", ADMIN_JS)

    def test_connector_cards_render_bilingual_schema_rejection_reasons(self) -> None:
        for contract in (
            "connectorErrorPresentation",
            "connector.last_error_code",
            "unsupported_json_schema_keyword",
            "Schéma MCP refusé — mot-clé JSON Schema non pris en charge",
            "MCP schema rejected — unsupported JSON Schema keyword",
            "Code :",
        ):
            self.assertIn(contract, ADMIN_JS)

    def test_connector_editing_and_secret_rotation_are_separate_bilingual_actions(self) -> None:
        main_source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_gateway"
            / "main.py"
        ).read_text(encoding="utf-8")
        for contract in (
            'id="connector-edit"',
            'id="connector-rotate-secret"',
            'autocomplete="new-password"',
            "/admin/api/v1/connectors/update",
            "/admin/api/v1/connectors/rotate-secret",
        ):
            self.assertIn(contract, main_source + ADMIN_JS)
        self.assertIn("The current secret is retained automatically and is never displayed.", ADMIN_JS)
        self.assertIn("The existing secret cannot be displayed.", ADMIN_JS)
        self.assertIn("url:url||null", ADMIN_JS)
        self.assertNotIn("connector.bearer_token", ADMIN_JS)


class AdministrationStatusTests(unittest.TestCase):
    def test_cockpit_status_distinguishes_unavailable_and_disabled_resources(self) -> None:
        source = (
            Path(__file__).resolve().parents[1]
            / "src"
            / "agent_gateway"
            / "http_api.py"
        ).read_text(encoding="utf-8")

        for key in (
            '"unavailable"',
            '"disabled"',
            '"archived"',
            '"triggers"',
            '"schedules"',
            '"suspended"',
            '"audit"',
        ):
            self.assertIn(key, source)


class ConnectorContractTests(unittest.TestCase):
    def test_accepts_generic_streamable_http_endpoint(self) -> None:
        url = "https://mcp.example.test:8443/custom/path?tenant=one"
        self.assertEqual(validate_streamable_http_url(url), url)
        self.assertEqual(connector_display_endpoint(url), "https://mcp.example.test:8443")

    def test_rejects_embedded_credentials_and_fragments(self) -> None:
        for url in (
            "https://user:secret@mcp.example.test/mcp",
            "https://mcp.example.test/mcp#secret",
            "file:///tmp/server",
        ):
            with self.subTest(url=url), self.assertRaises(ValueError):
                validate_streamable_http_url(url)

    def test_rejects_invalid_ingress_proxy_ip(self) -> None:
        with patch.dict(
            os.environ,
            {"AGENT_GATEWAY_INGRESS_PROXY_IP": "not-an-ip"},
            clear=True,
        ):
            with self.assertRaises(RuntimeError):
                load_settings()

    def test_accepts_configured_intake_rate_limit(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_GATEWAY_INTAKE_RATE_LIMIT": "42"}, clear=True
        ):
            settings = load_settings()
        self.assertEqual(settings.intake_rate_limit_per_minute, 42)

    def test_rejects_out_of_range_intake_rate_limit(self) -> None:
        with patch.dict(
            os.environ, {"AGENT_GATEWAY_INTAKE_RATE_LIMIT": "0"}, clear=True
        ):
            with self.assertRaises(RuntimeError):
                load_settings()

    def test_discovery_wraps_schema_rejections_with_safe_tool_context(self) -> None:
        cases = (
            ({"type": "object", "customConstraint": True}, "unsupported_json_schema_keyword"),
            ({"$schema": "http://json-schema.org/draft-07/schema#"}, "unsupported_json_schema_dialect"),
            ({"type": "string", "format": "private-format"}, "unsupported_json_schema_format"),
            ({"$ref": "https://example.test/schema.json"}, "unsupported_external_json_schema_reference"),
            ({"type": "not-a-type"}, "invalid_json_schema"),
            ({"description": "x" * (16 * 1024)}, "upstream_tool_schema_too_large"),
        )
        for schema, code in cases:
            with self.subTest(code=code), self.assertRaises(ConnectorSchemaRejected) as raised:
                validate_discovered_tool_schema("inspect", schema)
            self.assertEqual(raised.exception.code, code)
            self.assertEqual(raised.exception.tool_name, "inspect")


class ConnectorDiscoveryVisibilityTests(unittest.TestCase):
    @staticmethod
    async def _inline_threadpool(function, *args, **kwargs):
        return function(*args, **kwargs)

    def _run(self, handler, request):
        with patch(
            "agent_gateway.http_api.run_in_threadpool", new=self._inline_threadpool
        ):
            return asyncio.run(handler(request))

    class Request:
        def __init__(self, control_plane: ControlPlane, payload: dict[str, object]) -> None:
            self.state = SimpleNamespace(correlation_id="test-correlation")
            self.app = SimpleNamespace(state=SimpleNamespace(control_plane=control_plane))
            self.cookies = {"agw_csrf": "csrf"}
            self.headers = {"content-type": "application/json", "x-csrf-token": "csrf"}
            self._body = json.dumps(payload).encode()

        async def body(self) -> bytes:
            return self._body

    def _connector(self, root: Path) -> tuple[ControlPlane, str]:
        root.mkdir(parents=True, exist_ok=True)
        database_path = root / "gateway.db"
        initialize_database(database_path)
        control_plane = ControlPlane(database_path, root / "private")
        connector_id = control_plane.create_connector(
            "Test MCP",
            "https://mcp.example.test/mcp",
            "super-secret-bearer-token",
            [{"name": "inspect", "description": "Inspect", "input_schema": {"type": "object"}, "schema_fingerprint": "a" * 64}],
            "setup",
        )
        return control_plane, connector_id

    def test_network_failure_remains_unreachable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control_plane, connector_id = self._connector(Path(directory))
            request = self.Request(control_plane, {"connector_id": connector_id})
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(side_effect=OSError("network failed")),
            ):
                response = self._run(admin_check_connector, request)
            self.assertEqual(response.status_code, 503)
            self.assertEqual(json.loads(response.body)["error"]["code"], "connector_unreachable")
            connector = control_plane.list_connectors()[0]
            self.assertEqual(connector["status"], "unreachable")
            self.assertEqual(connector["last_error_code"], "connection_failed")

    def test_schema_rejections_remain_precise_in_admin_api_and_persistence(self) -> None:
        codes = (
            "unsupported_json_schema_keyword",
            "unsupported_json_schema_dialect",
            "unsupported_json_schema_format",
            "unsupported_external_json_schema_reference",
            "invalid_json_schema",
            "upstream_tool_schema_too_large",
        )
        for code in codes:
            with self.subTest(code=code), tempfile.TemporaryDirectory() as directory:
                control_plane, connector_id = self._connector(Path(directory))
                request = self.Request(control_plane, {"connector_id": connector_id})
                rejection = ConnectorSchemaRejected(code, "inspect")
                with self.assertLogs("agent_gateway.connectors", level="WARNING") as logs, patch(
                    "agent_gateway.http_api.discover_streamable_http",
                    new=AsyncMock(side_effect=rejection),
                ):
                    response = self._run(admin_check_connector, request)
                self.assertEqual(response.status_code, 422)
                self.assertEqual(json.loads(response.body)["error"]["code"], code)
                connector = control_plane.list_connectors()[0]
                self.assertEqual(connector["status"], "invalid")
                self.assertEqual(connector["last_error_code"], code)
                logged = "\n".join(logs.output)
                self.assertIn(f"error={code}", logged)
                self.assertIn("tool='inspect'", logged)
                self.assertNotIn("super-secret-bearer-token", logged)
                self.assertNotIn("inputSchema", logged)

    def test_creation_and_reactivation_return_precise_schema_error(self) -> None:
        rejection = ConnectorSchemaRejected("unsupported_json_schema_keyword", "inspect")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            database_path = root / "gateway.db"
            initialize_database(database_path)
            control_plane = ControlPlane(database_path, root / "private")
            create = self.Request(
                control_plane,
                {
                    "display_name": "Rejected MCP",
                    "url": "https://mcp.example.test/mcp",
                    "bearer_token": "creation-secret-token",
                },
            )
            with self.assertLogs("agent_gateway.connectors", level="WARNING") as logs, patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(side_effect=rejection),
            ):
                response = self._run(admin_create_connector, create)
            self.assertEqual(response.status_code, 422)
            self.assertEqual(
                json.loads(response.body)["error"]["code"],
                "unsupported_json_schema_keyword",
            )
            self.assertEqual(control_plane.list_connectors(), [])
            self.assertNotIn("creation-secret-token", "\n".join(logs.output))

            control_plane, connector_id = self._connector(root / "existing")
            control_plane.set_connector_enabled(connector_id, False, "disable")
            enable = self.Request(control_plane, {"connector_id": connector_id, "enabled": True})
            with self.assertLogs("agent_gateway.connectors", level="WARNING") as enable_logs, patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(side_effect=rejection),
            ):
                response = self._run(admin_set_connector_enabled, enable)
            self.assertEqual(response.status_code, 422)
            connector = control_plane.list_connectors()[0]
            self.assertFalse(connector["enabled"])
            self.assertEqual(connector["status"], "invalid")
            self.assertEqual(connector["last_error_code"], "unsupported_json_schema_keyword")
            self.assertNotIn("super-secret-bearer-token", "\n".join(enable_logs.output))

    def test_ordinary_edit_preserves_secret_and_name_only_skips_discovery(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control_plane, connector_id = self._connector(Path(directory))
            with sqlite3.connect(control_plane.database_path) as connection:
                protected_before = connection.execute(
                    "SELECT protected_config FROM connectors WHERE id=?", (connector_id,)
                ).fetchone()[0]
            request = self.Request(
                control_plane,
                {"connector_id": connector_id, "display_name": "Renamed MCP", "url": None},
            )
            with patch(
                "agent_gateway.http_api.discover_streamable_http", new=AsyncMock()
            ) as discover:
                response = self._run(admin_update_connector, request)
            self.assertEqual(response.status_code, 200)
            discover.assert_not_awaited()
            self.assertEqual(
                control_plane.connector_connection_config(connector_id),
                ("https://mcp.example.test/mcp", "super-secret-bearer-token"),
            )
            with sqlite3.connect(control_plane.database_path) as connection:
                protected_after = connection.execute(
                    "SELECT protected_config FROM connectors WHERE id=?", (connector_id,)
                ).fetchone()[0]
            self.assertEqual(protected_before, protected_after)
            connector = control_plane.list_connectors()[0]
            self.assertEqual(connector["display_name"], "Renamed MCP")
            self.assertTrue(connector["has_secret"])
            serialized = json.dumps(connector) + response.body.decode()
            self.assertNotIn("super-secret-bearer-token", serialized)
            self.assertTrue(control_plane.verify_audit_chain()["valid"])

            no_secret_id = control_plane.create_connector(
                "No secret MCP",
                "https://open.example.test/mcp",
                "",
                [],
                "no-secret",
            )
            no_secret = next(
                item for item in control_plane.list_connectors() if item["id"] == no_secret_id
            )
            self.assertFalse(no_secret["has_secret"])

    def test_secret_rotation_replaces_gateway_copy_without_disclosure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control_plane, connector_id = self._connector(Path(directory))
            old_secret = "super-secret-bearer-token"
            new_secret = "new-rotated-secret-token"
            stale_url, stale_secret, stale_protected = control_plane.connector_change_config(
                connector_id
            )
            inventory = [
                {
                    "name": "inspect",
                    "description": "Inspect",
                    "input_schema": {"type": "object"},
                    "schema_fingerprint": "a" * 64,
                }
            ]
            request = self.Request(
                control_plane,
                {"connector_id": connector_id, "bearer_token": new_secret},
            )
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(return_value=inventory),
            ) as discover:
                response = self._run(admin_rotate_connector_secret, request)
            self.assertEqual(response.status_code, 200)
            discover.assert_awaited_once_with("https://mcp.example.test/mcp", new_secret)
            self.assertEqual(
                control_plane.connector_connection_config(connector_id),
                ("https://mcp.example.test/mcp", new_secret),
            )
            check = self.Request(control_plane, {"connector_id": connector_id})
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(return_value=inventory),
            ) as rediscover:
                check_response = self._run(admin_check_connector, check)
            self.assertEqual(check_response.status_code, 200)
            rediscover.assert_awaited_once_with(
                "https://mcp.example.test/mcp", new_secret
            )
            public_objects = json.dumps(
                {
                    "response": json.loads(response.body),
                    "connectors": control_plane.list_connectors(),
                    "audit": control_plane.list_audit_entries(),
                    "tasks": control_plane.list_tasks(),
                }
            )
            self.assertNotIn(old_secret, public_objects)
            self.assertNotIn(new_secret, public_objects)
            with sqlite3.connect(control_plane.database_path) as connection:
                database_text = " ".join(
                    str(value)
                    for row in connection.iterdump()
                    for value in (row,)
                )
            self.assertNotIn(old_secret, database_text)
            self.assertNotIn(new_secret, database_text)
            empty_rotation = self.Request(
                control_plane, {"connector_id": connector_id, "bearer_token": ""}
            )
            empty_response = self._run(admin_rotate_connector_secret, empty_rotation)
            self.assertEqual(empty_response.status_code, 422)
            self.assertEqual(control_plane.connector_connection_config(connector_id)[1], new_secret)
            with self.assertRaisesRegex(ValueError, "connector_changed"):
                control_plane.update_connector(
                    connector_id,
                    "Stale endpoint edit",
                    "https://stale.example.test/mcp",
                    stale_secret,
                    stale_protected,
                    True,
                    inventory,
                    None,
                    "stale-update",
                )
            self.assertEqual(stale_url, "https://mcp.example.test/mcp")
            self.assertEqual(control_plane.connector_connection_config(connector_id)[1], new_secret)
            self.assertTrue(control_plane.verify_audit_chain()["valid"])

    def test_endpoint_and_rotation_failures_are_persisted_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control_plane, connector_id = self._connector(Path(directory))
            task_id = control_plane.create_task(
                "Inspect",
                "inspect",
                "Inspect the service.",
                1,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "task",
            )
            update = self.Request(
                control_plane,
                {
                    "connector_id": connector_id,
                    "display_name": "Moved MCP",
                    "url": "https://moved.example.test/mcp",
                },
            )
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(side_effect=OSError("private network detail")),
            ):
                response = self._run(admin_update_connector, update)
            self.assertEqual(response.status_code, 503)
            connector = control_plane.list_connectors()[0]
            self.assertEqual(connector["status"], "unreachable")
            self.assertEqual(connector["last_error_code"], "connection_failed")
            self.assertEqual(connector["tool_count"], 1)
            self.assertEqual(control_plane.list_tasks()[0]["status"], "unavailable")
            self.assertEqual(
                control_plane.connector_connection_config(connector_id),
                ("https://moved.example.test/mcp", "super-secret-bearer-token"),
            )

            new_secret = "rejected-new-secret"
            rotate = self.Request(
                control_plane,
                {"connector_id": connector_id, "bearer_token": new_secret},
            )
            rejection = ConnectorSchemaRejected(
                "unsupported_json_schema_keyword", "inspect"
            )
            with self.assertLogs("agent_gateway.connectors", level="WARNING") as logs, patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(side_effect=rejection),
            ):
                response = self._run(admin_rotate_connector_secret, rotate)
            self.assertEqual(response.status_code, 422)
            connector = control_plane.list_connectors()[0]
            self.assertEqual(connector["status"], "invalid")
            self.assertEqual(
                connector["last_error_code"], "unsupported_json_schema_keyword"
            )
            self.assertEqual(
                control_plane.connector_connection_config(connector_id)[1],
                "super-secret-bearer-token",
            )
            self.assertNotIn(new_secret, "\n".join(logs.output))

            inventory = [
                {
                    "name": "inspect",
                    "description": "Inspect",
                    "input_schema": {"type": "object"},
                    "schema_fingerprint": "a" * 64,
                }
            ]
            check = self.Request(control_plane, {"connector_id": connector_id})
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(return_value=inventory),
            ):
                response = self._run(admin_check_connector, check)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(control_plane.list_tasks()[0]["id"], task_id)
            self.assertEqual(control_plane.list_tasks()[0]["status"], "ready")
            changed_inventory = [{**inventory[0], "schema_fingerprint": "b" * 64}]
            changed = self.Request(
                control_plane,
                {
                    "connector_id": connector_id,
                    "display_name": "Moved again MCP",
                    "url": "https://moved-again.example.test/mcp",
                },
            )
            with patch(
                "agent_gateway.http_api.discover_streamable_http",
                new=AsyncMock(return_value=changed_inventory),
            ):
                response = self._run(admin_update_connector, changed)
            self.assertEqual(response.status_code, 200)
            self.assertEqual(control_plane.list_connectors()[0]["status"], "ready")
            self.assertEqual(control_plane.list_tasks()[0]["status"], "unavailable")
            self.assertIn(
                "tool_schema_changed:Moved again MCP.inspect",
                control_plane.list_tasks()[0]["dependency_failures"],
            )
            audit_text = json.dumps(control_plane.list_audit_entries())
            self.assertNotIn("super-secret-bearer-token", audit_text)
            self.assertNotIn(new_secret, audit_text)
            self.assertTrue(control_plane.verify_audit_chain()["valid"])

    def test_endpoint_change_and_rotation_are_blocked_during_active_execution(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            control_plane, connector_id = self._connector(Path(directory))
            task_id = control_plane.create_task(
                "Inspect",
                "inspect",
                "Inspect the service.",
                1,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "task",
            )
            control_plane.enqueue_manual_task(task_id, {}, "run")
            rotate = self.Request(
                control_plane,
                {
                    "connector_id": connector_id,
                    "bearer_token": "RECOGNIZABLE-REFUSED-NEW-SECRET",
                },
            )
            refused_endpoint = "https://RECOGNIZABLE-REFUSED-ENDPOINT.example.test/mcp"
            update = self.Request(
                control_plane,
                {
                    "connector_id": connector_id,
                    "display_name": "Test MCP",
                    "url": refused_endpoint,
                },
            )
            with patch(
                "agent_gateway.http_api.discover_streamable_http", new=AsyncMock()
            ) as discover:
                rename = self.Request(
                    control_plane,
                    {
                        "connector_id": connector_id,
                        "display_name": "Renamed during execution",
                        "url": None,
                    },
                )
                rename_response = self._run(admin_update_connector, rename)
                connector_before = control_plane.list_connectors()[0]
                config_before = control_plane.connector_connection_config(connector_id)
                tools_before = control_plane.list_connector_tools(connector_id)
                update_response = self._run(admin_update_connector, update)
                rotate_response = self._run(admin_rotate_connector_secret, rotate)
            self.assertEqual(rename_response.status_code, 200)
            self.assertEqual(update_response.status_code, 409)
            self.assertEqual(rotate_response.status_code, 409)
            self.assertEqual(
                json.loads(update_response.body)["error"]["code"],
                "connector_execution_active",
            )
            self.assertEqual(
                json.loads(rotate_response.body)["error"]["code"],
                "connector_execution_active",
            )
            discover.assert_not_awaited()
            self.assertEqual(
                control_plane.connector_connection_config(connector_id),
                config_before,
            )
            self.assertEqual(control_plane.list_connectors()[0], connector_before)
            self.assertEqual(control_plane.list_connector_tools(connector_id), tools_before)
            denials = [
                entry
                for entry in control_plane.list_audit_entries()
                if entry["decision"] == "denied"
                and entry["reason_code"] == "connector_execution_active"
            ]
            self.assertEqual(
                {entry["action"] for entry in denials},
                {"connectors.update", "connectors.secret_rotate"},
            )
            audit_text = json.dumps(denials)
            self.assertNotIn(refused_endpoint, audit_text)
            self.assertNotIn("RECOGNIZABLE-REFUSED-NEW-SECRET", audit_text)
            self.assertTrue(control_plane.verify_audit_chain()["valid"])

class DatabaseReadinessTests(unittest.TestCase):
    def test_missing_database_is_not_ready(self) -> None:
        self.assertFalse(database_ready(Path("/definitely/missing/database.db")))

    def test_expected_schema_is_ready(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            initialize_database(path)
            self.assertTrue(database_ready(path))
            with sqlite3.connect(path) as connection:
                self.assertEqual(
                    connection.execute("SELECT count(*) FROM task_definitions").fetchone()[0],
                    0,
                )

    def test_incompatible_existing_schema_is_rejected(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            connection = sqlite3.connect(path)
            connection.executescript(
                """
                CREATE TABLE gateway_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
                INSERT INTO gateway_metadata VALUES('application', 'agent_gateway');
                """
            )
            connection.close()
            with self.assertRaisesRegex(RuntimeError, "remove_app_data"):
                initialize_database(path)
            self.assertFalse(database_ready(path))

    def test_old_generation_requires_clean_reinstall(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "gateway.db"
            initialize_database(path)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE gateway_metadata SET value='13' WHERE key='schema_generation'")
            with self.assertRaisesRegex(RuntimeError, "remove_app_data"):
                initialize_database(path)
            self.assertFalse(database_ready(path))


class PublicSurfaceTests(unittest.TestCase):
    def test_public_root_is_not_exposed(self) -> None:
        paths = set(exposed_paths("public"))
        self.assertNotIn("/", paths)
        self.assertEqual(
            paths,
            {
                "/api/v1/events",
                "/api/v1/jobs",
                "/api/v1/reports",
                "/api/v1/permissions/effective",
                "/health/live",
                "/health/ready",
            },
        )

    def test_admin_root_is_exposed(self) -> None:
        self.assertIn("/", exposed_paths("admin"))


class CredentialTests(unittest.TestCase):
    def test_configured_pepper_avoids_persistent_file_access(self) -> None:
        expected = bytes(range(32))
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "inaccessible" / "credential-pepper"
            with patch.dict(os.environ, {"AGENT_GATEWAY_CREDENTIAL_PEPPER_HEX": expected.hex()}):
                self.assertEqual(load_or_create_pepper(path), expected)
            self.assertFalse(path.exists())

    def test_token_round_trip_and_wrong_pepper_denial(self) -> None:
        issued = issue_credential(b"a" * 32)
        self.assertEqual(
            parse_and_verify_token(issued.token, b"a" * 32, issued.verifier),
            issued.credential_id,
        )
        self.assertIsNone(parse_and_verify_token(issued.token, b"b" * 32, issued.verifier))

    def test_malformed_token_is_denied(self) -> None:
        self.assertIsNone(parse_and_verify_token("not-a-token", b"a" * 32, "0" * 64))

    def test_concurrent_pepper_creation_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "private" / "credential-pepper"
            with ThreadPoolExecutor(max_workers=8) as executor:
                peppers = list(executor.map(lambda _: load_or_create_pepper(path), range(32)))
            self.assertEqual(len(set(peppers)), 1)
            self.assertEqual(len(peppers[0]), 32)
            self.assertEqual(path.stat().st_mode & 0o777, 0o600)


class PolicyTests(unittest.TestCase):
    def test_policy_is_deny_by_default(self) -> None:
        self.assertFalse(decide("events.read", ()).allowed)
        self.assertEqual(decide("events.read", ()).reason_code, "not_granted")

    def test_policy_accepts_only_known_actions(self) -> None:
        self.assertEqual(validate_actions(["jobs.read", "jobs.read"]), ("jobs.read",))
        with self.assertRaises(ValueError):
            validate_actions(["shell.execute"])


class RedactionTests(unittest.TestCase):
    def test_nested_secrets_and_tokens_are_redacted(self) -> None:
        issued = issue_credential(b"a" * 32)
        value = {
            "safe": [{"api_key": "canary"}, f"prefix {issued.token} suffix"],
            "authorization": "Bearer canary",
        }
        redacted = redact(value)
        self.assertEqual(redacted["authorization"], "[REDACTED]")
        self.assertEqual(redacted["safe"][0]["api_key"], "[REDACTED]")
        self.assertNotIn(issued.token, redacted["safe"][1])

    def test_transient_sensitive_values_are_redacted_by_value(self) -> None:
        secret = "SECRET-FIXED-8264"
        ordinary = "recette-fixed-args"
        result = {
            "content": [
                {"type": "text", "text": f"source={secret}; slug={ordinary}"},
            ],
            "structuredContent": {
                "innocent": {"requested_source": secret},
                "ordinary": ordinary,
                f"echo-{secret}": "key is also protected",
            },
        }
        content = capability_result_content(result, [secret])
        serialized = content[0].text
        self.assertNotIn(secret, serialized)
        self.assertIn("[REDACTED]", serialized)
        self.assertIn(ordinary, serialized)

    def test_non_string_sensitive_json_values_are_redacted_conservatively(self) -> None:
        result = {
            "nested": {"innocent": {"scope": ["private", 7]}},
            "echoed_leaf": 7,
            "unrelated_boolean": True,
        }
        redacted = redact(result, [{"scope": ["private", 7]}])
        self.assertEqual(redacted["nested"]["innocent"], "[REDACTED]")
        self.assertEqual(redacted["echoed_leaf"], "[REDACTED]")
        self.assertIs(redacted["unrelated_boolean"], True)

    def test_text_key_from_sensitive_object_is_redacted_when_echoed_as_value(self) -> None:
        secret_key = "private-scope-name"
        result = {"structuredContent": {"innocent": secret_key}}
        redacted = redact(result, [{secret_key: "ordinary-looking-value"}])
        self.assertEqual(redacted["structuredContent"]["innocent"], "[REDACTED]")
        self.assertNotIn(secret_key, json.dumps(redacted))


class TaskReportContractTests(unittest.TestCase):
    def test_generic_report_shape_is_validated(self) -> None:
        schema = {
            "type": "object",
            "required": ["result"],
            "additionalProperties": False,
            "properties": {"result": {"type": "string", "minLength": 1}},
        }
        validate_json_contract({"result": "healthy"}, schema)
        with self.assertRaisesRegex(ValueError, "required"):
            validate_json_contract({}, schema)
        with self.assertRaisesRegex(ValueError, "additional_property"):
            validate_json_contract({"result": "healthy", "unexpected": True}, schema)

    def test_common_mcp_json_schema_constraints_are_enforced(self) -> None:
        schema = {
            "type": "object",
            "required": ["mode", "target", "count", "label", "occurred_at", "tags"],
            "additionalProperties": False,
            "properties": {
                "mode": {"enum": ["inspect", "status"]},
                "target": {"const": "gatus"},
                "count": {"type": "integer", "minimum": 1, "maximum": 10},
                "label": {"type": "string", "pattern": "^safe-[a-z]+$"},
                "occurred_at": {"type": "string", "format": "date-time"},
                "tags": {"type": "array", "items": {"type": "string"}, "minItems": 1, "uniqueItems": True},
            },
        }
        valid = {
            "mode": "inspect",
            "target": "gatus",
            "count": 5,
            "label": "safe-test",
            "occurred_at": "2026-08-15T10:00:00+02:00",
            "tags": ["icmp"],
        }
        validate_json_contract(valid, schema)
        for key, invalid, keyword in (
            ("mode", "delete", "enum"),
            ("target", "another", "const"),
            ("count", 0, "minimum"),
            ("count", 11, "maximum"),
            ("label", "unsafe", "pattern"),
            ("occurred_at", "not-a-date", "format"),
            ("tags", [], "min_items"),
            ("tags", ["icmp", "icmp"], "uniqueItems"),
        ):
            payload = {**valid, key: invalid}
            with self.subTest(keyword=keyword), self.assertRaisesRegex(ValueError, keyword):
                validate_json_contract(payload, schema)

    def test_compositions_and_local_references_are_applied(self) -> None:
        schema = {
            "$defs": {"name": {"type": "string", "pattern": "^[a-z]+$"}},
            "type": "object",
            "properties": {
                "name": {"anyOf": [{"$ref": "#/$defs/name"}, {"type": "null"}]}
            },
            "required": ["name"],
            "additionalProperties": False,
        }
        validate_json_contract({"name": "gatus"}, schema)
        validate_json_contract({"name": None}, schema)
        with self.assertRaisesRegex(ValueError, "anyOf"):
            validate_json_contract({"name": "Gatus"}, schema)

    def test_unknown_keywords_dialects_formats_and_external_refs_fail_closed(self) -> None:
        for schema, reason in (
            ({"type": "string", "customConstraint": True}, "keyword"),
            ({"$schema": "http://json-schema.org/draft-07/schema#", "type": "string"}, "dialect"),
            ({"type": "string", "format": "private-format"}, "format"),
            ({"$ref": "https://example.test/schema.json"}, "reference"),
        ):
            with self.subTest(reason=reason), self.assertRaisesRegex(ValueError, reason):
                validate_json_schema(schema)


class TaskCompositionTests(unittest.TestCase):
    def test_fixed_arguments_are_hidden_injected_and_independent_per_connector(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            schema = {
                "type": "object",
                "required": ["addon", "action", "token", "limit", "label"],
                "additionalProperties": False,
                "properties": {
                    "addon": {"type": "string", "const": "gatus"},
                    "action": {"type": "string", "enum": ["inspect"]},
                    "token": {"type": "string", "pattern": "^secret-[a-z]+$"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 10},
                    "label": {"type": "string", "pattern": "^safe-[a-z]+$"},
                },
            }
            restricted_connector = "10000000-0000-0000-0000-000000000001"
            standard_connector = "10000000-0000-0000-0000-000000000002"
            with sqlite3.connect(path) as connection:
                for connector_id, name in (
                    (restricted_connector, "Restricted MCP"),
                    (standard_connector, "Standard MCP"),
                ):
                    connection.execute(
                        "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                        (connector_id, name, "streamable_http", "protected", "https://example.test", "2026-08-15T00:00:00Z", "2026-08-15T00:00:00Z"),
                    )
                    connection.execute(
                        "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                        (connector_id, "manage", "Manage one resource", json.dumps(schema), "a" * 64, "2026-08-15T00:00:00Z"),
                    )
            secret = "secret-fixedvalue"
            class FakeFernet:
                def encrypt(self, value: bytes) -> bytes:
                    return base64.urlsafe_b64encode(value)

                def decrypt(self, value: bytes) -> bytes:
                    return base64.urlsafe_b64decode(value)

            with patch("agent_gateway.fixed_arguments.connector_fernet", return_value=FakeFernet()):
                task_id = control_plane.create_task(
                    "Scoped management",
                    "scoped_management",
                    "Manage only the configured resource.",
                    1,
                    [
                        {
                            "connector_id": restricted_connector,
                            "tool_name": "manage",
                            "argument_mode": "fixed_arguments_v1",
                            "example_arguments": {
                                "addon": "gatus",
                                "action": "inspect",
                                "token": secret,
                                "limit": 5,
                                "label": "safe-test",
                            },
                            "argument_rules": {
                                "addon": "fixed_ordinary",
                                "action": "editable",
                                "token": "fixed_sensitive",
                                "limit": "fixed_ordinary",
                                "label": "editable",
                            },
                        },
                        {"connector_id": standard_connector, "tool_name": "manage"},
                    ],
                    "task-create",
                )
            task = control_plane.list_tasks()[0]
            restricted = next(tool for tool in task["tools"] if tool["connector_id"] == restricted_connector)
            standard = next(tool for tool in task["tools"] if tool["connector_id"] == standard_connector)
            self.assertEqual(restricted["argument_exposure"]["fixed"]["addon"]["value"], "gatus")
            self.assertEqual(
                restricted["argument_exposure"]["fixed"]["token"],
                {"classification": "sensitive", "protected": True},
            )
            self.assertEqual(standard["argument_exposure"]["mode"], "standard")
            with sqlite3.connect(path) as connection:
                stored = connection.execute(
                    "SELECT constraints_json FROM task_tool_selections WHERE connector_id=?",
                    (restricted_connector,),
                ).fetchone()[0]
            self.assertNotIn(secret, stored)
            self.assertIn('"gatus"', stored)

            job_id = control_plane.enqueue_manual_task(task_id, {}, "task-run")
            created = control_plane.create_identity(
                "Worker", "client", ["jobs.claim", "jobs.heartbeat", "jobs.complete", "jobs.fail"], "worker"
            )
            worker = control_plane.authenticate(created.credential.token)
            advertised = control_plane.next_queued_capabilities(worker)
            schemas = {item["name"]: item["input_schema"] for item in advertised}
            self.assertEqual(
                schemas[restricted["namespaced_name"]],
                {
                    "type": "object",
                    "required": ["action", "label"],
                    "additionalProperties": False,
                    "properties": {
                        "action": {"type": "string", "enum": ["inspect"]},
                        "label": {"type": "string", "pattern": "^safe-[a-z]+$"},
                    },
                },
            )
            self.assertEqual(schemas[standard["namespaced_name"]], schema)
            lease = control_plane.claim_job(worker, "claim")
            self.assertIsNotNone(lease)
            self.assertEqual(lease.job["id"], job_id)
            with self.assertRaisesRegex(ValueError, "invalid_capability_arguments"):
                control_plane.resolve_active_capability(
                    worker,
                    restricted["namespaced_name"],
                    {"action": "inspect", "label": "safe-test", "addon": "another"},
                    "override",
                )
            sensitive_override = "ATTACKER-SENSITIVE-OVERRIDE"
            with self.assertRaisesRegex(ValueError, "invalid_capability_arguments"):
                control_plane.resolve_active_capability(
                    worker,
                    restricted["namespaced_name"],
                    {"action": "inspect", "label": "safe-test", "token": sensitive_override},
                    "override-sensitive",
                )
            with self.assertRaisesRegex(AuthorizationError, "capability_not_available"):
                control_plane.resolve_active_capability(
                    worker,
                    "missing_virtual_capability",
                    {},
                    "capability-unavailable",
                )
            for capability, arguments in (
                (standard["namespaced_name"], {"addon": "other", "action": "inspect", "token": secret, "limit": 5, "label": "safe-test"}),
                (standard["namespaced_name"], {"addon": "gatus", "action": "delete", "token": secret, "limit": 5, "label": "safe-test"}),
                (standard["namespaced_name"], {"addon": "gatus", "action": "inspect", "token": secret, "limit": 11, "label": "safe-test"}),
                (standard["namespaced_name"], {"addon": "gatus", "action": "inspect", "token": secret, "limit": 5, "label": "unsafe"}),
                (restricted["namespaced_name"], {"action": "delete", "label": "safe-test"}),
                (restricted["namespaced_name"], {"action": "inspect", "label": "unsafe"}),
            ):
                with self.subTest(capability=capability, arguments=arguments), patch(
                    "agent_gateway.control_plane.reveal_connector_config"
                ) as reveal:
                    with self.assertRaisesRegex(ValueError, "invalid_capability_arguments"):
                        control_plane.resolve_active_capability(worker, capability, arguments, "invalid")
                    reveal.assert_not_called()
            with patch("agent_gateway.fixed_arguments.connector_fernet", return_value=FakeFernet()), patch(
                "agent_gateway.control_plane.reveal_connector_config",
                return_value=("https://restricted.example.test/mcp", ""),
            ):
                resolved = control_plane.resolve_active_capability(
                    worker,
                    restricted["namespaced_name"],
                    {"action": "inspect", "label": "safe-test"},
                    "invoke",
                )
            self.assertEqual(
                resolved["arguments"],
                {
                    "addon": "gatus",
                    "action": "inspect",
                    "token": secret,
                    "limit": 5,
                    "label": "safe-test",
                },
            )
            self.assertEqual(resolved["sensitive_values"], [secret])
            original_constraints = json.loads(stored)
            for fixed_name, invalid_value in (("addon", "other"), ("limit", 11)):
                tampered = json.loads(json.dumps(original_constraints))
                tampered["fixed_ordinary"][fixed_name] = invalid_value
                with sqlite3.connect(path) as connection:
                    connection.execute(
                        "UPDATE task_tool_selections SET constraints_json=? WHERE connector_id=?",
                        (json.dumps(tampered), restricted_connector),
                    )
                with self.subTest(merged=fixed_name), patch(
                    "agent_gateway.fixed_arguments.connector_fernet", return_value=FakeFernet()
                ), patch("agent_gateway.control_plane.reveal_connector_config") as reveal:
                    with self.assertRaisesRegex(ValueError, "invalid_capability_arguments"):
                        control_plane.resolve_active_capability(
                            worker,
                            restricted["namespaced_name"],
                            {"action": "inspect", "label": "safe-test"},
                            "tampered",
                        )
                    reveal.assert_not_called()
            audit_entries = control_plane.list_audit_entries(limit=10_000)
            denials = {
                entry["correlation_id"]: entry
                for entry in audit_entries
                if entry["decision"] == "denied"
            }
            self.assertEqual(denials["override"]["reason_code"], "invalid_capability_arguments")
            self.assertEqual(
                denials["override-sensitive"]["reason_code"],
                "invalid_capability_arguments",
            )
            self.assertEqual(
                denials["capability-unavailable"]["reason_code"],
                "capability_not_available",
            )
            serialized_audit = json.dumps(audit_entries)
            self.assertNotIn(secret, serialized_audit)
            self.assertNotIn(sensitive_override, serialized_audit)
            self.assertTrue(control_plane.verify_audit_chain()["valid"])

    def test_fixed_arguments_reject_invalid_examples_and_schema_changes_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                    (connector_id, "Example MCP", "streamable_http", "protected", "https://example.test", "2026-08-15T00:00:00Z", "2026-08-15T00:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                    (connector_id, "inspect", "Inspect", json.dumps({
                        "type": "object",
                        "required": ["target"],
                        "additionalProperties": False,
                        "properties": {"target": {"type": "string"}, "verbose": {"type": "boolean"}},
                    }), "a" * 64, "2026-08-15T00:00:00Z"),
                )
            selection = {
                "connector_id": connector_id,
                "tool_name": "inspect",
                "argument_mode": "fixed_arguments_v1",
                "example_arguments": {},
                "argument_rules": {"target": "fixed_ordinary"},
            }
            with self.assertRaises(ValueError):
                control_plane.create_task("Invalid", "invalid", "Invalid.", 1, [selection], "invalid")
            selection["example_arguments"] = {"target": "service"}
            task_id = control_plane.create_task("Valid", "valid", "Valid.", 1, [selection], "valid")
            control_plane.enqueue_manual_task(task_id, {}, "run")
            worker_created = control_plane.create_identity("Worker", "client", ["jobs.claim"], "worker")
            worker = control_plane.authenticate(worker_created.credential.token)
            self.assertEqual(len(control_plane.next_queued_capabilities(worker)), 1)
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE connector_tools SET schema_fingerprint=? WHERE connector_id=? AND name='inspect'",
                    ("b" * 64, connector_id),
                )
            self.assertEqual(control_plane.next_queued_capabilities(worker), [])

    def test_task_dependencies_fail_closed(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                    (connector_id, "Example MCP", "streamable_http", "protected", "https://mcp.example.test", "2026-08-13T00:00:00Z", "2026-08-13T00:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                    (connector_id, "inspect", "Inspect", '{"type":"object","properties":{"slug":{"type":"string","minLength":1}}}', "a" * 64, "2026-08-13T00:00:00Z"),
                )
            task_id = control_plane.create_task(
                "Inspect service",
                "inspect_service",
                "Inspect the selected service.",
                3,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "test-task",
            )
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["id"], task_id)
            self.assertEqual(task["status"], "ready")
            self.assertEqual(len(task["tools"]), 1)
            self.assertRegex(task["tools"][0]["namespaced_name"], r"^task_[0-9a-f]{12}__inspect__[0-9a-f]{12}$")
            self.assertEqual(control_plane.delete_connector(connector_id, "test-delete"), "in_use")
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "UPDATE connector_tools SET schema_fingerprint=? WHERE connector_id=? AND name='inspect'",
                    ("b" * 64, connector_id),
                )
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["status"], "unavailable")
            self.assertIn("tool_schema_changed:Example MCP.inspect", task["dependency_failures"])
            self.assertTrue(control_plane.set_task_enabled(task_id, False, "test-pause"))
            self.assertEqual(control_plane.list_tasks()[0]["status"], "disabled")
            self.assertTrue(control_plane.set_task_enabled(task_id, True, "test-resume"))
            self.assertEqual(control_plane.delete_task(task_id, "test-delete-task"), "deleted")
            self.assertEqual(control_plane.list_tasks(), [])
            self.assertEqual(control_plane.delete_task(task_id, "test-delete-missing"), "not_found")
            manual_task_id = control_plane.create_task(
                "Manual inspection",
                "manual_inspection",
                "Inspect on demand.",
                1,
                [{"connector_id": connector_id, "tool_name": "inspect"}],
                "test-manual-task",
            )
            manual_job_id = control_plane.enqueue_manual_task(manual_task_id, {}, "test-manual-run")
            self.assertEqual(control_plane.get_job(manual_job_id)["state"], "queued")
            self.assertIsNone(control_plane.get_job(manual_job_id)["event_id"])
            with self.assertRaisesRegex(TaskExecutionActiveError, "task_execution_active"):
                control_plane.enqueue_manual_task(manual_task_id, {}, "test-manual-duplicate")
            self.assertEqual(control_plane.list_tasks()[0]["active_job_count"], 1)
            self.assertEqual(control_plane.delete_task(manual_task_id, "test-delete-used"), "in_use")

    def test_task_requires_a_ready_connector_tool(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            with self.assertRaisesRegex(ValueError, "requires_tool"):
                control_plane.create_task("Empty", "empty", "No tools", 1, [], "test")

    def test_archiving_preserves_history_and_restores_disabled(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute(
                    "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                    (connector_id, "Example MCP", "streamable_http", "protected", "https://mcp.example.test", "2026-08-13T00:00:00Z", "2026-08-13T00:00:00Z"),
                )
                connection.execute(
                    "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                    (connector_id, "inspect", "Inspect", '{"type":"object"}', "a" * 64, "2026-08-13T00:00:00Z"),
                )
            task_id = control_plane.create_task("Inspect", "inspect", "Inspect.", 1, [{"connector_id": connector_id, "tool_name": "inspect"}], "test-task")
            job_id = control_plane.enqueue_manual_task(task_id, {}, "test-run")
            with self.assertRaisesRegex(ValueError, "task_execution_active"):
                control_plane.set_task_archived(task_id, True, "test-active-archive")
            with self.assertRaisesRegex(ValueError, "connector_execution_active"):
                control_plane.set_connector_archived(connector_id, True, "test-active-connector-archive")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE jobs SET state='cancelled' WHERE id=?", (job_id,))
            self.assertTrue(control_plane.set_task_archived(task_id, True, "test-archive"))
            task = control_plane.list_tasks()[0]
            self.assertEqual(task["status"], "archived")
            self.assertIsNotNone(task["archived_at"])
            self.assertEqual(control_plane.get_job(job_id)["state"], "cancelled")
            self.assertTrue(control_plane.set_task_archived(task_id, False, "test-restore"))
            self.assertEqual(control_plane.list_tasks()[0]["status"], "disabled")
            self.assertTrue(control_plane.set_connector_archived(connector_id, True, "test-connector-archive"))
            connector = control_plane.list_connectors()[0]
            self.assertFalse(connector["enabled"])
            self.assertIsNotNone(connector["archived_at"])
            self.assertTrue(control_plane.set_connector_archived(connector_id, False, "test-connector-restore"))
            connector = control_plane.list_connectors()[0]
            self.assertFalse(connector["enabled"])
            self.assertIsNone(connector["archived_at"])
            metrics = control_plane.status_counts()
            self.assertEqual(metrics["events_24h"], 0)
            self.assertEqual(metrics["reports_24h"], 0)
            self.assertEqual(metrics["failed_jobs_24h"], 0)
            self.assertEqual(metrics["event_mappings"], 0)
            self.assertEqual(metrics["active_event_mappings"], 0)
            self.assertEqual(metrics["schedules"], 0)
            self.assertEqual(metrics["active_schedules"], 0)

    def test_due_schedule_queues_once_and_skips_an_active_task(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            connector_id = "10000000-0000-0000-0000-000000000001"
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)", (connector_id,"Example MCP","streamable_http","protected","https://mcp.example.test","2026-08-13T00:00:00Z","2026-08-13T00:00:00Z"))
                connection.execute("INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)", (connector_id,"inspect","Inspect",'{"type":"object"}',"a"*64,"2026-08-13T00:00:00Z"))
            task_id = control_plane.create_task("Inspect", "inspect", "Inspect.", 1, [{"connector_id":connector_id,"tool_name":"inspect"}], "test-task")
            schedule_id = control_plane.create_schedule("Every hour", task_id, "interval", 60, None, None, None, "test-schedule")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE schedules SET next_run_at='2000-01-01T00:00:00Z' WHERE id=?", (schedule_id,))
            self.assertEqual(control_plane.run_due_schedules(), 1)
            self.assertEqual(control_plane.list_schedules()[0]["last_outcome"], "queued")
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE schedules SET next_run_at='2000-01-01T00:00:00Z' WHERE id=?", (schedule_id,))
            self.assertEqual(control_plane.run_due_schedules(), 1)
            self.assertEqual(control_plane.list_schedules()[0]["last_outcome"], "skipped_active")
            self.assertEqual(len(control_plane.list_jobs()), 1)

    def test_calendar_schedule_next_occurrence_uses_iana_timezone(self) -> None:
        reference = datetime.fromisoformat("2026-08-13T08:00:00+00:00")
        self.assertEqual(
            ControlPlane._next_schedule_run("daily", 1440, "11:30", None, "Europe/Paris", reference),
            "2026-08-13T09:30:00.000Z",
        )
        self.assertEqual(
            ControlPlane._next_schedule_run("weekly", 10080, "09:00", 0, "Europe/Paris", reference),
            "2026-08-17T07:00:00.000Z",
        )
        with self.assertRaisesRegex(ValueError, "invalid_timezone"):
            ControlPlane._next_schedule_run("daily", 1440, "09:00", None, "Mars/Olympus", reference)
        with self.assertRaisesRegex(ValueError, "invalid_schedule"):
            ControlPlane._next_schedule_run("weekly", 10080, "09:00", None, "Europe/Paris", reference)

    def test_retention_removes_only_expired_terminal_data_and_keeps_audit_valid(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            old = "2000-01-01T00:00:00.000Z"
            with sqlite3.connect(path) as connection:
                connection.execute("INSERT INTO identities(id,display_name,identity_type,status,created_at) VALUES('10000000-0000-0000-0000-000000000001','Source','event_source','active',?)", (old,))
                connection.execute("INSERT INTO policy_documents(id,name,created_at) VALUES('policy','policy',?)", (old,))
                connection.execute("INSERT INTO policy_revisions(id,policy_id,schema_version,document_json,created_at) VALUES('revision','policy',1,'{}',?)", (old,))
                connection.execute("INSERT INTO task_definitions(id,name,display_name,enabled,created_at) VALUES('task','task','Task',1,?)", (old,))
                connection.execute("INSERT INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES('task-revision','task',1,'Task','{}','{}',1,?)", (old,))
                connection.execute("INSERT INTO events(id,source_identity_id,idempotency_key,schema_version,event_type,occurred_at,received_at,payload_json) VALUES('event','10000000-0000-0000-0000-000000000001','key',1,'test.event',?,?, '{}')", (old, old))
                connection.execute("INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES('old-job','event','task','completed','revision','task-revision','{}',?,?)", (old, old))
                connection.execute("INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES('active-job',NULL,'task','queued','revision','task-revision','{}',?,?)", (old, old))
                connection.execute("INSERT INTO reports(id,job_id,schema_version,report_json,created_at) VALUES('report','old-job',1,'{}',?)", (old,))
                connection.execute("INSERT INTO job_attempts(id,job_id,attempt_number,identity_id,lease_verifier,leased_at,lease_expires_at,max_expires_at,finished_at,outcome) VALUES('attempt','old-job',1,'10000000-0000-0000-0000-000000000001','x',?,?,?,?, 'completed')", (old, old, old, old))
            control_plane.record_audit(actor_identity_id=None, credential_id=None, action="test", decision="recorded", reason_code="test", correlation_id="test")
            self.assertEqual(control_plane.retention_status()["preview"]["jobs"], 1)
            deleted = control_plane.run_retention("test-retention")
            self.assertEqual(deleted, {"jobs": 1, "reports": 1, "attempts": 1, "orphan_events": 1})
            with sqlite3.connect(path) as connection:
                self.assertEqual(connection.execute("SELECT id FROM jobs").fetchall(), [("active-job",)])
            self.assertTrue(control_plane.verify_audit_chain()["valid"])


class AuditVerificationCheckpointTests(unittest.TestCase):
    @staticmethod
    def _record(control_plane: ControlPlane, suffix: str) -> None:
        control_plane.record_audit(
            actor_identity_id=None,
            credential_id=None,
            action=f"test.{suffix}",
            decision="recorded",
            reason_code="test",
            correlation_id=suffix,
        )

    def test_cockpit_and_retention_status_never_run_a_full_verification(self) -> None:
        http_source = (
            Path(__file__).resolve().parents[1] / "src" / "agent_gateway" / "http_api.py"
        ).read_text(encoding="utf-8")
        admin_status_source = http_source.split("async def admin_status", 1)[1].split(
            "async def admin_list_identities", 1
        )[0]
        self.assertNotIn("verify_audit_chain", admin_status_source)
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            control_plane.maintain_audit_verification(force_full=True)
            with patch.object(control_plane, "verify_audit_chain", side_effect=AssertionError("unbounded read")):
                self.assertTrue(control_plane.audit_status()["valid"])
                self.assertTrue(control_plane.retention_status()["audit"]["valid"])

    def test_incremental_verification_revalidates_anchor_and_advances_only_over_new_entries(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            initial = control_plane.maintain_audit_verification(force_full=True)
            self.assertEqual(initial["state"], "valid")
            full_verified_at = initial["full_verified_at"]
            self._record(control_plane, "two")
            pending = control_plane.audit_status()
            self.assertEqual(pending["state"], "pending")
            self.assertEqual(pending["pending_entries"], 1)
            with patch.object(control_plane, "verify_audit_chain", side_effect=AssertionError("full scan")):
                current = control_plane.maintain_audit_verification()
            self.assertEqual(current["state"], "valid")
            self.assertEqual(current["verified_entries"], 2)
            self.assertEqual(current["full_verified_at"], full_verified_at)

    def test_anchor_failure_runs_full_verification_and_preserves_last_valid_checkpoint(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            control_plane.maintain_audit_verification(force_full=True)
            with sqlite3.connect(path) as connection:
                checkpoint_before = connection.execute(
                    "SELECT value FROM gateway_metadata WHERE key='audit_valid_checkpoint'"
                ).fetchone()[0]
                connection.execute("UPDATE audit_entries SET metadata_json='{\"tampered\":true}' WHERE sequence=1")
            with patch.object(control_plane, "verify_audit_chain", wraps=control_plane.verify_audit_chain) as full:
                status = control_plane.maintain_audit_verification()
            self.assertEqual(full.call_count, 1)
            self.assertEqual(status["state"], "invalid")
            self.assertFalse(status["valid"])
            with sqlite3.connect(path) as connection:
                checkpoint_after = connection.execute(
                    "SELECT value FROM gateway_metadata WHERE key='audit_valid_checkpoint'"
                ).fetchone()[0]
            self.assertEqual(checkpoint_after, checkpoint_before)

    def test_invalid_state_stays_quiet_until_an_authorized_full_verification(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            control_plane.maintain_audit_verification(force_full=True)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE audit_entries SET action='tampered' WHERE sequence=1")
            self.assertEqual(control_plane.maintain_audit_verification()["state"], "invalid")
            self._record(control_plane, "two")
            with patch.object(control_plane, "verify_audit_chain", side_effect=AssertionError("unexpected periodic full scan")):
                status = control_plane.maintain_audit_verification()
            self.assertEqual(status["state"], "invalid")
            with patch.object(control_plane, "verify_audit_chain", wraps=control_plane.verify_audit_chain) as full:
                status = control_plane.maintain_audit_verification(force_full=True)
            self.assertEqual(full.call_count, 1)
            self.assertEqual(status["state"], "invalid")

    def test_interrupted_verification_is_resumed_by_the_periodic_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            control_plane.maintain_audit_verification(force_full=True)
            control_plane._store_audit_verification_state("verifying", reason="interrupted")
            with patch.object(control_plane, "verify_audit_chain", wraps=control_plane.verify_audit_chain) as full:
                status = control_plane.maintain_audit_verification()
            self.assertEqual(full.call_count, 1)
            self.assertEqual(status["state"], "valid")

    def test_invalid_state_is_rechecked_at_the_full_verification_deadline(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            control_plane.maintain_audit_verification(force_full=True)
            with sqlite3.connect(path) as connection:
                connection.execute("UPDATE audit_entries SET action='tampered' WHERE sequence=1")
            self.assertEqual(control_plane.maintain_audit_verification()["state"], "invalid")
            with sqlite3.connect(path) as connection:
                checkpoint = json.loads(connection.execute(
                    "SELECT value FROM gateway_metadata WHERE key='audit_valid_checkpoint'"
                ).fetchone()[0])
                checkpoint["full_verified_at"] = "2000-01-01T00:00:00.000Z"
                checkpoint = control_plane._sign_audit_checkpoint(checkpoint)
                connection.execute(
                    "UPDATE gateway_metadata SET value=? WHERE key='audit_valid_checkpoint'",
                    (json.dumps(checkpoint),),
                )
            with patch.object(control_plane, "verify_audit_chain", wraps=control_plane.verify_audit_chain) as full:
                status = control_plane.maintain_audit_verification()
            self.assertEqual(full.call_count, 1)
            self.assertEqual(status["state"], "invalid")

    def test_checkpoint_metadata_tampering_cannot_define_an_incremental_trust_anchor(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = root / "gateway.db"
            initialize_database(path)
            control_plane = ControlPlane(path, root / "private")
            self._record(control_plane, "one")
            control_plane.maintain_audit_verification(force_full=True)
            with sqlite3.connect(path) as connection:
                checkpoint = json.loads(connection.execute(
                    "SELECT value FROM gateway_metadata WHERE key='audit_valid_checkpoint'"
                ).fetchone()[0])
                checkpoint["sequence"] = 0
                checkpoint["entry_hash"] = "0" * 64
                connection.execute(
                    "UPDATE gateway_metadata SET value=? WHERE key='audit_valid_checkpoint'",
                    (json.dumps(checkpoint),),
                )
            self.assertEqual(control_plane.audit_status()["state"], "checkpoint_inconsistent")
            with patch.object(control_plane, "verify_audit_chain", wraps=control_plane.verify_audit_chain) as full:
                status = control_plane.maintain_audit_verification()
            self.assertEqual(full.call_count, 1)
            self.assertEqual(status["state"], "valid")
            self.assertEqual(status["verified_entries"], 1)


class MultiSubjectIncidentTests(unittest.TestCase):
    def _setup(self, root: Path) -> tuple[ControlPlane, object, str]:
        path = root / "gateway.db"
        initialize_database(path)
        control_plane = ControlPlane(path, root / "private", intake_rate_limit_per_minute=600)
        connector_id = "10000000-0000-0000-0000-000000000001"
        with sqlite3.connect(path) as connection:
            connection.execute(
                "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
                (connector_id, "Example MCP", "streamable_http", "protected", "https://mcp.example.test", "2026-08-13T00:00:00Z", "2026-08-13T00:00:00Z"),
            )
            connection.execute(
                "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                (connector_id, "inspect", "Inspect", '{"type":"object"}', "a" * 64, "2026-08-13T00:00:00Z"),
            )
        task_id = control_plane.create_task("Incident", "incident", "Inspect incident.", 3, [{"connector_id": connector_id, "tool_name": "inspect"}], "test-task")
        created = control_plane.create_identity("Event source", "event_source", ["events.create"], "test-source")
        identity = control_plane.authenticate(created.credential.token)
        mapping_id = control_plane.create_event_mapping(
            "Aggregate alerts", identity.identity_id, "service.alert", task_id, 0, 1,
            "service.recovered", "attributes", "aggregate_by_subject", "test-mapping",
        )
        return control_plane, identity, mapping_id

    @staticmethod
    def _event(event_type: str, subject: str, status: str = "unavailable") -> dict[str, object]:
        return {
            "schema_version": 1,
            "event_type": event_type,
            "occurred_at": "2026-08-14T08:00:00Z",
            "subject": {"entity_id": subject},
            "attributes": {"status": status},
        }

    def test_recovery_removes_only_its_subject_and_promotes_one_aggregate_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, mapping_id = self._setup(root)
            for name in ("camera_1", "camera_2", "camera_3"):
                result = control_plane.ingest_event(identity, f"alert-{name}", self._event("service.alert", name), f"alert-{name}")
                self.assertIn(result.outcome, {"grace_started", "grace_subject_added"})
            unknown = control_plane.ingest_event(identity, "recover-unknown", self._event("service.recovered", "camera_9", "available"), "recover-unknown")
            self.assertEqual(unknown.outcome, "recovery_subject_unknown")
            for name in ("camera_1", "camera_2"):
                recovered = control_plane.ingest_event(identity, f"recover-{name}", self._event("service.recovered", name, "available"), f"recover-{name}")
                self.assertEqual(recovered.outcome, "subject_recovered")
            mapping = control_plane.list_event_mappings()[0]
            self.assertEqual(mapping["active_subject_count"], 1)
            with sqlite3.connect(root / "gateway.db") as connection:
                connection.execute("UPDATE event_incidents SET due_at='2000-01-01T00:00:00.000Z',next_attempt_at='2000-01-01T00:00:00.000Z' WHERE mapping_id=?", (mapping_id,))
            self.assertEqual(control_plane.run_due_event_triggers(), 1)
            jobs = control_plane.list_jobs()
            self.assertEqual(len(jobs), 1)
            job = control_plane.get_job(jobs[0]["id"])
            self.assertEqual(job["input"]["kind"], "aggregated_event_incident")
            self.assertEqual(job["input"]["subjects"], [{"attributes": {"status": "unavailable"}, "subject": {"entity_id": "camera_3"}}])
            self.assertEqual(len(control_plane.list_events()), 6)

    def test_all_subjects_recover_without_job_and_repeated_alert_updates_member(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, _ = self._setup(root)
            started = control_plane.ingest_event(identity, "alert-1", self._event("service.alert", "camera_1"), "alert-1")
            due_at = control_plane.list_event_mappings()[0]["pending_due_at"]
            repeated = control_plane.ingest_event(identity, "alert-2", self._event("service.alert", "camera_1", "still_unavailable"), "alert-2")
            self.assertEqual(repeated.outcome, "grace_subject_updated")
            self.assertEqual(control_plane.list_event_mappings()[0]["pending_due_at"], due_at)
            recovered = control_plane.ingest_event(identity, "recover-1", self._event("service.recovered", "camera_1", "available"), "recover-1")
            self.assertEqual(recovered.outcome, "incident_resolved")
            self.assertIsNone(control_plane.list_event_mappings()[0]["incident_id"])
            self.assertEqual(control_plane.run_due_event_triggers(), 0)
            self.assertEqual(control_plane.list_jobs(), [])
            self.assertEqual(started.outcome, "grace_started")

    def test_concurrent_due_promotion_creates_exactly_one_job(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, mapping_id = self._setup(root)
            control_plane.ingest_event(identity, "alert", self._event("service.alert", "camera_1"), "alert")
            with sqlite3.connect(root / "gateway.db") as connection:
                connection.execute("UPDATE event_incidents SET due_at='2000-01-01T00:00:00.000Z',next_attempt_at='2000-01-01T00:00:00.000Z' WHERE mapping_id=?", (mapping_id,))
            with ThreadPoolExecutor(max_workers=8) as executor:
                results = list(executor.map(lambda _: control_plane.run_due_event_triggers(), range(8)))
            self.assertEqual(sum(results), 1)
            self.assertEqual(len(control_plane.list_jobs()), 1)

    def test_concurrent_alerts_keep_one_member_per_subject(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, _ = self._setup(root)
            subjects = [f"camera_{index % 8}" for index in range(32)]
            with ThreadPoolExecutor(max_workers=8) as executor:
                list(executor.map(
                    lambda item: control_plane.ingest_event(identity, f"alert-{item[0]}", self._event("service.alert", item[1]), f"alert-{item[0]}"),
                    enumerate(subjects),
                ))
            mapping = control_plane.list_event_mappings()[0]
            self.assertEqual(mapping["active_subject_count"], 8)
            with sqlite3.connect(root / "gateway.db") as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM event_incident_subjects").fetchone()[0], 8)
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 32)

    def test_recovery_promotion_race_is_atomic(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, mapping_id = self._setup(root)
            for name in ("camera_1", "camera_2"):
                control_plane.ingest_event(identity, f"alert-{name}", self._event("service.alert", name), f"alert-{name}")
            with sqlite3.connect(root / "gateway.db") as connection:
                connection.execute("UPDATE event_incidents SET due_at='2000-01-01T00:00:00.000Z',next_attempt_at='2000-01-01T00:00:00.000Z' WHERE mapping_id=?", (mapping_id,))
            with ThreadPoolExecutor(max_workers=2) as executor:
                future_recovery = executor.submit(control_plane.ingest_event, identity, "recover-camera-1", self._event("service.recovered", "camera_1", "available"), "recover-camera-1")
                future_promotion = executor.submit(control_plane.run_due_event_triggers)
                recovery = future_recovery.result()
                future_promotion.result()
            self.assertIn(recovery.outcome, {"subject_recovered", "recovery_recorded"})
            self.assertEqual(len(control_plane.list_jobs()), 1)
            self.assertIsNone(control_plane.list_event_mappings()[0]["incident_id"])
            subjects = {item["subject"]["entity_id"] for item in control_plane.get_job(control_plane.list_jobs()[0]["id"])["input"]["subjects"]}
            self.assertIn(subjects, ({"camera_2"}, {"camera_1", "camera_2"}))

    def test_alert_recovery_race_keeps_a_consistent_incident(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, _ = self._setup(root)
            with ThreadPoolExecutor(max_workers=2) as executor:
                alert = executor.submit(
                    control_plane.ingest_event,
                    identity,
                    "race-alert",
                    self._event("service.alert", "camera_1"),
                    "race-alert",
                )
                recovery = executor.submit(
                    control_plane.ingest_event,
                    identity,
                    "race-recovery",
                    self._event("service.recovered", "camera_1", "available"),
                    "race-recovery",
                )
                outcomes = {alert.result().outcome, recovery.result().outcome}
            self.assertIn("grace_started", outcomes)
            self.assertTrue(outcomes & {"incident_resolved", "recovery_recorded"})
            mapping = control_plane.list_event_mappings()[0]
            self.assertIn(mapping["active_subject_count"], (0, 1))
            self.assertEqual(mapping["incident_id"] is None, mapping["active_subject_count"] == 0)
            with sqlite3.connect(root / "gateway.db") as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], 2)

    def test_aggregate_subject_is_required_and_bounded(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, _ = self._setup(root)
            missing = self._event("service.alert", "camera_1")
            missing["subject"] = {}
            with self.assertRaisesRegex(ValueError, "aggregate_subject_required"):
                control_plane.ingest_event(identity, "missing", missing, "missing")
            oversized = self._event("service.alert", "camera_1")
            oversized["subject"] = {"entity_id": "x" * 5000}
            rejected = control_plane.ingest_event(identity, "oversized", oversized, "oversized")
            self.assertEqual(rejected.outcome, "aggregate_subject_too_large")
            for index in range(MAX_INCIDENT_SUBJECTS):
                control_plane.ingest_event(identity, f"bounded-{index}", self._event("service.alert", f"camera_{index}"), f"bounded-{index}")
            overflow = control_plane.ingest_event(identity, "bounded-overflow", self._event("service.alert", "camera_overflow"), "bounded-overflow")
            self.assertEqual(overflow.outcome, "incident_subject_limit")
            self.assertEqual(control_plane.list_event_mappings()[0]["active_subject_count"], MAX_INCIDENT_SUBJECTS)
            with sqlite3.connect(root / "gateway.db") as connection:
                self.assertEqual(connection.execute("SELECT count(*) FROM events").fetchone()[0], MAX_INCIDENT_SUBJECTS + 2)

    def test_unpromotable_incident_becomes_visible_and_retryable(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            control_plane, identity, mapping_id = self._setup(root)
            control_plane.ingest_event(identity, "alert", self._event("service.alert", "camera_1"), "alert")
            task_id = control_plane.list_tasks()[0]["id"]
            control_plane.enqueue_manual_task(task_id, {}, "manual-blocker")
            for _ in range(10):
                with sqlite3.connect(root / "gateway.db") as connection:
                    connection.execute("UPDATE event_incidents SET due_at='2000-01-01T00:00:00.000Z',next_attempt_at='2000-01-01T00:00:00.000Z' WHERE mapping_id=?", (mapping_id,))
                control_plane.run_due_event_triggers()
            mapping = control_plane.list_event_mappings()[0]
            self.assertEqual(mapping["incident_state"], "blocked")
            self.assertEqual(mapping["last_block_reason"], "task_execution_active")
            self.assertTrue(control_plane.retry_event_incident(mapping_id, "retry"))
            mapping = control_plane.list_event_mappings()[0]
            self.assertEqual(mapping["incident_state"], "pending")
            self.assertEqual(mapping["promotion_attempts"], 0)


if __name__ == "__main__":
    unittest.main()
