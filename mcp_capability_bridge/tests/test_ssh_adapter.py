from __future__ import annotations

import asyncio
import json
import logging
import shlex
import tempfile
import unittest
from pathlib import Path

import asyncssh
import httpx

from mcp_capability_bridge.ssh_adapter import (
    SSHAdapter,
    SSHCallError,
    build_command,
    quote_posix_token,
    scan_host_key,
    validate_ssh_capability,
)
from mcp_capability_bridge.contracts import AdapterRegistry
from mcp_capability_bridge.database import initialize
from mcp_capability_bridge.main import build_runtime_state, create_apps
from mcp_capability_bridge.settings import Settings


def capability(**overrides):
    value = {
        "id": "overview",
        "key": "overview",
        "display_name": "Overview",
        "description": "Return a harmless fixture value.",
        "executable": "/usr/bin/fixture",
        "template": [{"literal": "show"}, {"parameter": "value"}],
        "input_schema": {
            "type": "object",
            "properties": {"value": {"type": "string", "maxLength": 4096}},
            "required": ["value"],
            "additionalProperties": False,
        },
        "timeout_seconds": 3,
        "stdout_limit": 64,
        "stderr_limit": 32,
        "enabled": True,
        "effect_capable": False,
    }
    value.update(overrides)
    return value


class FixtureServer(asyncssh.SSHServer):
    def __init__(self, fixture):
        self.fixture = fixture

    def connection_made(self, conn):
        self.fixture.connections += 1

    def begin_auth(self, username):
        return True

    def password_auth_supported(self):
        return True

    def validate_password(self, username, password):
        return username == "bridge" and password == self.fixture.password

    def public_key_auth_supported(self):
        return True

    def validate_public_key(self, username, key):
        return username == "bridge" and self.fixture.client_key is not None and key.export_public_key() == self.fixture.client_key.export_public_key()


class SSHFixture:
    def __init__(self):
        self.password = "bridge-secret"
        self.client_key = None
        self.connections = 0
        self.commands = []
        self.server = None
        self.host_key = asyncssh.generate_private_key("ssh-ed25519")

    async def start(self):
        async def process(process):
            self.commands.append(process.command)
            if "sleep" in process.command:
                await asyncio.sleep(10)
            process.stdout.write(self.password + "X" * 200)
            process.stderr.write(self.password + "E" * 100)
            process.exit(0)

        self.server = await asyncssh.create_server(
            lambda: FixtureServer(self),
            "127.0.0.1",
            0,
            server_host_keys=[self.host_key],
            process_factory=process,
        )
        return self

    @property
    def port(self):
        return self.server.get_port()

    def configuration(self, item=None):
        public = self.host_key.export_public_key("openssh").decode().strip()
        return {
            "host": "127.0.0.1",
            "port": self.port,
            "username": "bridge",
            "host_public_key": public,
            "host_fingerprint": self.host_key.get_fingerprint("sha256"),
            "capabilities": [item or capability()],
        }

    async def stop(self):
        self.server.close()
        await self.server.wait_closed()


class SSHContractTests(unittest.TestCase):
    def test_asyncssh_payload_logging_is_disabled(self):
        self.assertGreaterEqual(logging.getLogger("asyncssh").getEffectiveLevel(), logging.WARNING)

    def test_token_template_quotes_hostile_input_as_one_posix_argument(self):
        hostile = "$(touch /tmp/no) ; ' quoted\nnext"
        command = build_command("/usr/bin/fixture", [{"literal": "show"}, {"parameter": "value"}], {"value": hostile})
        self.assertEqual(shlex.split(command), ["/usr/bin/fixture", "show", hostile])
        self.assertEqual(command.split(" ", 1)[0], "'/usr/bin/fixture'")
        with self.assertRaisesRegex(ValueError, "invalid_command_token"):
            quote_posix_token("bad\x00token")
        with self.assertRaisesRegex(ValueError, "invalid_command_token"):
            quote_posix_token("bad\x01token")

    def test_capability_contract_rejects_unbounded_or_caller_command_heads(self):
        validate_ssh_capability(capability())
        for invalid in (
            capability(executable="relative-command"),
            capability(template=[{"command": "value"}]),
            capability(input_schema={"type": "object", "properties": {"nested": {"type": "object"}}, "additionalProperties": False}),
        ):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                validate_ssh_capability(invalid)


class SSHRuntimeTests(unittest.TestCase):
    def test_repeated_calls_use_fresh_connections_and_leave_no_tasks(self):
        async def scenario():
            fixture = await SSHFixture().start()
            try:
                adapter = SSHAdapter()
                secret = json.dumps(
                    {"mode": "password", "password": fixture.password}
                ).encode()
                before = fixture.connections
                for index in range(20):
                    result = await adapter.invoke(
                        "overview",
                        fixture.configuration(),
                        secret,
                        {"value": str(index)},
                    )
                    self.assertEqual(result["exit_status"], 0)
                self.assertEqual(fixture.connections, before + 20)
                self.assertFalse(
                    any("_drain" in repr(task.get_coro()) for task in asyncio.all_tasks())
                )
            finally:
                await fixture.stop()

        asyncio.run(scenario())

    def test_admin_enrollment_capability_publication_and_in_use_guard(self):
        async def scenario():
            fixture = await SSHFixture().start()
            directory = tempfile.TemporaryDirectory()
            try:
                settings = Settings(Path(directory.name), "error", "127.0.0.1")
                initialize(settings.database_path)
                state = build_runtime_state(settings, AdapterRegistry((SSHAdapter(),)))
                admin, _ = create_apps(state)
                transport = httpx.ASGITransport(app=admin)
                headers = {"X-Ingress-Path": "/api/hassio_ingress/test", "Cookie": f"mcb_csrf={state.csrf_token}", "X-CSRF-Token": state.csrf_token}
                async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
                    scan = await client.post("/admin/api/v1/ssh/scan", headers=headers, json={"host": "127.0.0.1", "port": fixture.port})
                    self.assertEqual(scan.status_code, 200)
                    created = await client.post("/admin/api/v1/targets", headers=headers, json={"scan_id": scan.json()["scan_id"], "display_name": "Fixture", "username": "bridge", "auth_mode": "password", "password": fixture.password})
                    self.assertEqual(created.status_code, 201)
                    self.assertEqual(created.json()["target"]["key"], "fixture")
                    self.assertNotIn(fixture.password, created.text)
                    target_id = created.json()["target"]["id"]
                    generated = capability(id="", display_name="État général")
                    generated.pop("key")
                    saved = await client.post("/admin/api/v1/ssh/capabilities/save", headers=headers, json={"target_id": target_id, "capability": generated})
                    self.assertEqual(saved.status_code, 200)
                    target = (await client.get(f"/admin/api/v1/targets/detail/{target_id}", headers=headers)).json()["target"]
                    capability_id = target["configuration"]["capabilities"][0]["id"]
                    self.assertEqual(target["configuration"]["capabilities"][0]["key"], "etat_general")
                    renamed = dict(target["configuration"]["capabilities"][0])
                    renamed.pop("key")
                    renamed["display_name"] = "État renommé"
                    edited = await client.post("/admin/api/v1/ssh/capabilities/save", headers=headers, json={"target_id": target_id, "capability": renamed})
                    self.assertEqual(edited.status_code, 200)
                    target = (await client.get(f"/admin/api/v1/targets/detail/{target_id}", headers=headers)).json()["target"]
                    self.assertEqual(target["configuration"]["capabilities"][0]["key"], "etat_general")
                    namespace, _ = state.store.create_namespace("client", "Client")
                    published = await client.post("/admin/api/v1/publications/publish", headers=headers, json={"namespace_id": namespace["id"], "target_id": target_id, "capability_id": capability_id})
                    self.assertEqual(published.status_code, 200)
                    revision = published.json()["inventory_revision"]
                    async with state.counters.operation(namespace["id"], target_id, "ssh"):
                        blocked = await client.post("/admin/api/v1/targets/disable", headers=headers, json={"id": target_id})
                        self.assertEqual(blocked.status_code, 409)
                        self.assertEqual(blocked.json()["error"]["code"], "target_in_use")
                    deleted = await client.post("/admin/api/v1/ssh/capabilities/delete", headers=headers, json={"target_id": target_id, "capability_id": capability_id})
                    self.assertEqual(deleted.status_code, 200)
                    self.assertGreater(state.store.get_namespace(namespace["id"])["inventory_revision"], revision)
                    self.assertEqual(state.store.list_publications(), [])
            finally:
                directory.cleanup()
                await fixture.stop()
        asyncio.run(scenario())

    def test_scan_password_pin_bounds_redaction_and_fresh_connections(self):
        async def scenario():
            fixture = await SSHFixture().start()
            try:
                scan = await scan_host_key("127.0.0.1", fixture.port)
                self.assertEqual(scan.fingerprint, fixture.host_key.get_fingerprint("sha256"))
                enrollment_connections = fixture.connections
                adapter = SSHAdapter()
                secret = json.dumps({"mode": "password", "password": fixture.password}).encode()
                first = await adapter.invoke("overview", fixture.configuration(), secret, {"value": "one"})
                second = await adapter.invoke("overview", fixture.configuration(), secret, {"value": "two"})
                self.assertEqual(fixture.connections, enrollment_connections + 2)
                self.assertEqual(shlex.split(fixture.commands[0]), ["/usr/bin/fixture", "show", "one"])
                self.assertTrue(first["stdout_truncated"])
                self.assertTrue(first["stderr_truncated"])
                self.assertGreater(first["stdout_bytes"], 64)
                self.assertGreater(first["stderr_bytes"], 32)
                self.assertNotIn(fixture.password, json.dumps((first, second)))
                changed = fixture.configuration()
                other = asyncssh.generate_private_key("ssh-ed25519")
                changed["host_public_key"] = other.export_public_key("openssh").decode().strip()
                changed["host_fingerprint"] = other.get_fingerprint("sha256")
                with self.assertRaisesRegex(SSHCallError, "ssh_transport_failed"):
                    await adapter.invoke("overview", changed, secret, {"value": "blocked"})
                self.assertEqual(len(fixture.commands), 2)
                with tempfile.TemporaryDirectory() as directory:
                    settings = Settings(Path(directory), "error", "127.0.0.1")
                    initialize(settings.database_path)
                    state = build_runtime_state(settings, AdapterRegistry((SSHAdapter(),)))
                    target = state.store.create_target("ssh_fixture", "SSH fixture", "ssh", fixture.configuration(), secret)
                    persisted = settings.database_path.read_bytes()
                    self.assertNotIn(fixture.password.encode(), persisted)
                    restarted = build_runtime_state(settings, AdapterRegistry((SSHAdapter(),)))
                    resolved = restarted.store.get_target_configuration(target["id"])
                    self.assertEqual(resolved["host_fingerprint"], fixture.host_key.get_fingerprint("sha256"))
            finally:
                await fixture.stop()
        asyncio.run(scenario())

    def test_private_key_authentication_and_timeout_cleanup(self):
        async def scenario():
            fixture = await SSHFixture().start()
            try:
                fixture.client_key = asyncssh.generate_private_key("ssh-ed25519")
                private_key = fixture.client_key.export_private_key("openssh").decode()
                secret = json.dumps({"mode": "private_key", "private_key": private_key, "passphrase": ""}).encode()
                result = await SSHAdapter().invoke("overview", fixture.configuration(), secret, {"value": "key"})
                self.assertEqual(result["exit_status"], 0)
                slow = capability(template=[{"literal": "sleep"}], timeout_seconds=1)
                with self.assertRaisesRegex(SSHCallError, "ssh_timeout") as raised:
                    await SSHAdapter().invoke("overview", fixture.configuration(slow), secret, {})
                self.assertTrue(raised.exception.effect_possible)
                cancellable = capability(template=[{"literal": "sleep"}], timeout_seconds=3)
                command_count = len(fixture.commands)
                task = asyncio.create_task(SSHAdapter().invoke("overview", fixture.configuration(cancellable), secret, {}))
                while len(fixture.commands) == command_count:
                    await asyncio.sleep(0.01)
                task.cancel()
                with self.assertRaises(asyncio.CancelledError):
                    await task
                await asyncio.sleep(0)
                self.assertFalse(any(not task.done() and "_drain" in repr(task.get_coro()) for task in asyncio.all_tasks()))
            finally:
                await fixture.stop()
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
