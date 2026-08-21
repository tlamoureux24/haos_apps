from __future__ import annotations

import asyncio
import socket
import sys
import tempfile
import unittest
from pathlib import Path

import httpx
import uvicorn

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "agent_control_plane" / "src"))

from agent_control_plane.connectors import discover_streamable_http, invoke_streamable_http
from mcp_capability_bridge.contracts import AdapterRegistry, Capability
from mcp_capability_bridge.database import initialize
from mcp_capability_bridge.main import build_runtime_state, create_apps
from mcp_capability_bridge.settings import Settings


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
        self.state = build_runtime_state(settings, AdapterRegistry((ContractAdapter(),)))
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


if __name__ == "__main__":
    unittest.main()
