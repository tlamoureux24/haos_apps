from __future__ import annotations

import asyncio
import json
import shlex
import socket
import sys
import tempfile
import unittest
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_control_plane" / "src"))

from agent_control_plane.connectors import ConnectorCertificateMismatch, discover_streamable_http, invoke_streamable_http
from mcp_capability_bridge.contracts import AdapterRegistry, Capability
from mcp_capability_bridge.database import initialize
from mcp_capability_bridge.main import build_runtime_state, create_apps
from mcp_capability_bridge.settings import Settings
from mcp_capability_bridge.ssh_adapter import SSHAdapter
from mcp_capability_bridge.tls import prepare_certificate
from mcp_capability_bridge.web_adapter import WebAdapter
from test_ssh_adapter import SSHFixture, capability


class ContractAdapter:
    type_key = "contract_test"
    display_name = "Contract test"

    def validate_target(self, configuration, secret):
        if configuration != {"key": "fixture"}:
            raise ValueError("invalid_target")

    def capabilities(self, configuration):
        return (Capability("overview", "test_fixture_overview", "Return contract-test data.", {"type": "object", "properties": {"value": {"type": "string", "maxLength": 20}}, "required": ["value"], "additionalProperties": False}),)

    async def invoke(self, capability_id, configuration, secret, arguments):
        return {"received": arguments["value"]}


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


class AcpContractIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.directory = tempfile.TemporaryDirectory()
        settings = Settings(Path(self.directory.name), "error", "127.0.0.1")
        initialize(settings.database_path)
        self.state = build_runtime_state(settings, AdapterRegistry((ContractAdapter(), SSHAdapter(), WebAdapter())))
        _, public = create_apps(self.state)
        self.port = available_port()
        self.server = uvicorn.Server(uvicorn.Config(public, host="127.0.0.1", port=self.port, log_level="error", access_log=False))
        self.task = asyncio.create_task(self.server.serve())
        for _ in range(100):
            if self.server.started:
                break
            if self.task.done():
                self.task.result()
            await asyncio.sleep(0.02)
        self.assertTrue(self.server.started)
        self.url = f"http://127.0.0.1:{self.port}/mcp"

    async def asyncTearDown(self):
        self.server.should_exit = True
        await self.task
        self.directory.cleanup()

    async def test_current_acp_discovers_isolated_empty_and_published_inventories(self):
        first, first_token = self.state.store.create_namespace("acp_client", "ACP client")
        _, second_token = self.state.store.create_namespace("other_client", "Other client")
        self.assertEqual(await discover_streamable_http(self.url, first_token.token), [])
        target = self.state.store.create_target("fixture", "Fixture", "contract_test", {"key": "fixture"}, b"test-secret")
        self.state.store.publish(first["id"], target["id"], "overview")
        inventory = await discover_streamable_http(self.url, first_token.token)
        self.assertEqual([tool["name"] for tool in inventory], ["test_fixture_overview"])
        self.assertEqual(await discover_streamable_http(self.url, second_token.token), [])
        result = await invoke_streamable_http(self.url, first_token.token, "test_fixture_overview", {"value": "ok"})
        self.assertFalse(result["isError"])
        text = result["content"][0]["text"]
        self.assertIn('"received":"ok"', text)
        denied = await invoke_streamable_http(self.url, second_token.token, "test_fixture_overview", {"value": "blocked"})
        self.assertTrue(denied["isError"])
        self.assertNotIn("blocked", str(denied))
        rotated = self.state.store.rotate(first["id"])
        async with httpx.AsyncClient() as client:
            rejected = await client.get(self.url, headers={"Authorization": f"Bearer {first_token.token}"})
        self.assertEqual(rejected.status_code, 401)
        rotated_inventory = await discover_streamable_http(self.url, rotated.token)
        self.assertEqual([tool["name"] for tool in rotated_inventory], ["test_fixture_overview"])

    async def test_current_acp_discovers_and_calls_real_bounded_ssh_tool(self):
        fixture = await SSHFixture().start()
        try:
            namespace, issued = self.state.store.create_namespace("ssh_acp", "SSH ACP")
            secret = json.dumps({"mode": "password", "password": fixture.password}).encode()
            target = self.state.store.create_target("ssh_fixture", "SSH fixture", "ssh", fixture.configuration(capability()), secret)
            self.state.store.publish(namespace["id"], target["id"], "overview")
            inventory = await discover_streamable_http(self.url, issued.token)
            self.assertEqual([tool["name"] for tool in inventory], ["ssh_overview"])
            result = await invoke_streamable_http(self.url, issued.token, "ssh_overview", {"value": "through-acp"})
            self.assertFalse(result["isError"])
            self.assertEqual(shlex.split(fixture.commands[-1]), ["/usr/bin/fixture", "show", "through-acp"])
            self.assertNotIn(fixture.password, str(result))
        finally:
            await fixture.stop()

    async def test_current_acp_accepts_all_interactive_web_tool_schemas(self):
        namespace, issued = self.state.store.create_namespace("web_acp", "Web ACP")
        configuration = {"base_url":"https://web.internal/","resolved_addresses":["10.0.0.8"],"navigation_origins":["https://web.internal"],"authentication_origins":[],"resource_origins":["https://web.internal"],"websocket_origins":[],"verify_tls":True,"inactivity_seconds":300,"absolute_seconds":1800,"authentication":{"mode":"none"}}
        target = self.state.store.create_target("web_fixture", "Web fixture", "web", configuration, None)
        for capability_id in ("open","snapshot","wait","navigate","click","fill","select","press","close"):
            self.state.store.publish(namespace["id"], target["id"], capability_id)
        inventory = await discover_streamable_http(self.url, issued.token)
        self.assertEqual({tool["name"] for tool in inventory},{f"web_web_fixture_{name}" for name in ("open","snapshot","wait","navigate","click","fill","select","press","close")})

    async def test_z_current_acp_rejects_wrong_pin_and_recovers(self):
        _, public = create_apps(self.state)
        certificate = prepare_certificate(Path(self.directory.name), "self_generated")
        tls_port = available_port()
        tls_server = uvicorn.Server(uvicorn.Config(
            public, host="127.0.0.1", port=tls_port, log_level="error", access_log=False,
            ssl_certfile=str(certificate.certfile), ssl_keyfile=str(certificate.keyfile),
        ))
        tls_task = asyncio.create_task(tls_server.serve())
        for _ in range(100):
            if tls_server.started:
                break
            if tls_task.done():
                tls_task.result()
            await asyncio.sleep(0.02)
        self.assertTrue(tls_server.started)
        try:
            url = f"https://127.0.0.1:{tls_port}/mcp"
            namespace, issued = self.state.store.create_namespace("tls_acp", "TLS ACP")
            target = self.state.store.create_target("tls_fixture", "TLS fixture", "contract_test", {"key": "fixture"}, b"secret")
            self.state.store.publish(namespace["id"], target["id"], "overview")
            inventory = await discover_streamable_http(url, issued.token, certificate.fingerprint_sha256)
            self.assertEqual([tool["name"] for tool in inventory], ["test_fixture_overview"])
            result = await invoke_streamable_http(url, issued.token, "test_fixture_overview", {"value": "pinned"}, certificate.fingerprint_sha256)
            self.assertFalse(result["isError"])
            self.assertIn('"received":"pinned"', result["content"][0]["text"])
            with self.assertRaisesRegex(ConnectorCertificateMismatch, "certificate_sha256_mismatch"):
                await discover_streamable_http(url, issued.token, "0" * 64)
            recovered = await discover_streamable_http(url, issued.token, certificate.fingerprint_sha256)
            self.assertEqual([tool["name"] for tool in recovered], ["test_fixture_overview"])
        finally:
            tls_server.should_exit = True
            await tls_task


if __name__ == "__main__":
    unittest.main()
