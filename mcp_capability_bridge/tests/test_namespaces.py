from __future__ import annotations

import asyncio
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from mcp_capability_bridge.contracts import AdapterRegistry, Capability, validate_schema
from mcp_capability_bridge.database import initialize
from mcp_capability_bridge.main import build_runtime_state
from mcp_capability_bridge.mcp_api import SessionHub
from mcp_capability_bridge.security import SecretBox, load_or_create_key, token_lookup
from mcp_capability_bridge.settings import Settings


class FakeAdapter:
    type_key = "test_adapter"
    display_name = "Test adapter"

    def validate_target(self, configuration, secret):
        if set(configuration) != {"prefix"} or not isinstance(configuration["prefix"], str):
            raise ValueError("invalid_target")
        if secret is not None and not secret:
            raise ValueError("invalid_secret")

    def capabilities(self, configuration):
        return (
            Capability(
                "read",
                f"test_{configuration['prefix']}_read",
                "Return a bounded test value.",
                {"type": "object", "properties": {"value": {"type": "string", "maxLength": 20}}, "required": ["value"], "additionalProperties": False},
            ),
        )

    async def invoke(self, capability_id, configuration, secret, arguments):
        return {"value": arguments["value"], "secret_present": secret is not None}


class NamespaceStoreTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.path = Path(self.directory.name)
        settings = Settings(self.path, "info", "127.0.0.1")
        initialize(settings.database_path)
        self.state = build_runtime_state(settings, AdapterRegistry((FakeAdapter(),)))
        self.store = self.state.store

    def tearDown(self):
        self.directory.cleanup()

    def test_credentials_are_256_bit_indexed_one_way_and_restart_persistent(self):
        first, issued = self.store.create_namespace("client_one", "Client one")
        self.assertEqual(len(issued.token.split("_", 3)[3]), 43)
        self.assertEqual(token_lookup(issued.token), (first["id"], issued.credential_id))
        self.assertIsNone(token_lookup("not-a-token"))
        authenticated = self.store.authenticate(issued.token)
        self.assertEqual(authenticated.namespace_id, first["id"])
        database_bytes = (self.path / "mcp_capability_bridge.db").read_bytes()
        self.assertNotIn(issued.token.encode(), database_bytes)
        self.assertNotIn(issued.token.rsplit("_", 1)[1].encode(), database_bytes)
        restarted = build_runtime_state(Settings(self.path, "info", "127.0.0.1"), AdapterRegistry((FakeAdapter(),)))
        self.assertEqual(restarted.store.authenticate(issued.token).namespace_id, first["id"])

    def test_rotation_revoke_archive_and_isolation(self):
        first, old = self.store.create_namespace("client_one", "Client one")
        second, other = self.store.create_namespace("client_two", "Client two")
        rotated = self.store.rotate(first["id"])
        with self.assertRaises(PermissionError):
            self.store.authenticate(old.token)
        self.assertEqual(self.store.authenticate(rotated.token).namespace_id, first["id"])
        self.assertEqual(self.store.authenticate(other.token).namespace_id, second["id"])
        self.store.revoke(first["id"])
        with self.assertRaises(PermissionError):
            self.store.authenticate(rotated.token)
        self.assertEqual(self.store.authenticate(other.token).namespace_id, second["id"])
        with self.assertRaises(ValueError):
            self.store.rotate(first["id"])
        self.store.archive(first["id"])
        self.assertEqual([item["id"] for item in self.store.list_namespaces()], [second["id"]])
        self.assertEqual(len(self.store.list_namespaces(include_archived=True)), 2)

    def test_archive_requires_revocation(self):
        namespace, _ = self.store.create_namespace("client_one", "Client one")
        with self.assertRaisesRegex(ValueError, "namespace_must_be_revoked"):
            self.store.archive(namespace["id"])

    def test_cross_namespace_publication_and_dispatch_resolution(self):
        first, _ = self.store.create_namespace("client_one", "Client one")
        second, _ = self.store.create_namespace("client_two", "Client two")
        target = self.store.create_target("fixture", "Fixture", "test_adapter", {"prefix": "fixture"}, b"private-test-secret")
        before = first["inventory_revision"]
        revision = self.store.publish(first["id"], target["id"], "read")
        self.assertEqual(revision, before + 1)
        self.assertEqual([item.capability.name for item in self.store.visible_capabilities(first["id"])], ["test_fixture_read"])
        self.assertEqual(self.store.visible_capabilities(second["id"]), [])
        with self.assertRaisesRegex(KeyError, "capability_not_available"):
            self.store.resolve(second["id"], "test_fixture_read")
        resolved = self.store.resolve(first["id"], "test_fixture_read")
        self.assertEqual(self.store.secret_box.decrypt(resolved.encrypted_secret), b"private-test-secret")
        database_bytes = (self.path / "mcp_capability_bridge.db").read_bytes()
        self.assertNotIn(b"private-test-secret", database_bytes)
        self.assertNotEqual(self.store.publication_fingerprint(first["id"]), self.store.publication_fingerprint(second["id"]))
        self.assertEqual(self.store.unpublish(first["id"], "test_fixture_read"), revision + 1)

    def test_runtime_counters_are_shared_with_admin_state(self):
        async def scenario():
            async with self.state.counters.operation("namespace", "target"):
                self.assertEqual(self.state.counters.snapshot()["active_operations"], 1)
                with self.assertRaisesRegex(RuntimeError, "target_in_use"):
                    self.state.counters.ensure_target_mutable("target")
            self.assertEqual(self.state.counters.snapshot()["active_operations"], 0)
            self.state.counters.ensure_target_mutable("target")
        asyncio.run(scenario())

    def test_namespace_emergency_cancellation_stops_inflight_operation(self):
        async def scenario():
            entered = asyncio.Event()

            async def operation():
                async with self.state.counters.operation("namespace", "target"):
                    entered.set()
                    await asyncio.Event().wait()

            task = asyncio.create_task(operation())
            await entered.wait()
            await self.state.counters.cancel_namespace("namespace")
            self.assertTrue(task.cancelled())
            self.assertEqual(self.state.counters.snapshot()["active_operations"], 0)
        asyncio.run(scenario())


class SecurityAndContractTests(unittest.TestCase):
    def test_private_keys_are_separate_atomic_and_mode_600(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            pepper = load_or_create_key(root / "pepper")
            target = load_or_create_key(root / "target")
            self.assertNotEqual(pepper, target)
            self.assertEqual((root / "pepper").stat().st_mode & 0o777, 0o600)
            self.assertEqual((root / "target").stat().st_mode & 0o777, 0o600)
            box = SecretBox(target)
            envelope = box.encrypt(b"secret")
            self.assertNotIn(b"secret", envelope)
            self.assertEqual(box.decrypt(envelope), b"secret")

    def test_schema_and_tool_contract_match_acp_bounds(self):
        schema = {"type": "object", "properties": {"value": {"type": "string", "maxLength": 20}}, "additionalProperties": False}
        self.assertIsInstance(validate_schema(schema), str)
        with self.assertRaises(ValueError):
            validate_schema({"type": "object", "properties": {}, "additionalProperties": True})
        with self.assertRaises(ValueError):
            validate_schema({"type": "object", "properties": {}, "unknown": True, "additionalProperties": False})
        with self.assertRaisesRegex(ValueError, "unsupported_json_schema_format"):
            validate_schema({"type": "object", "properties": {"value": {"type": "string", "format": "private-format"}}, "additionalProperties": False})

    def test_tool_list_change_notification_is_namespace_scoped(self):
        class Session:
            def __init__(self):
                self.calls = 0

            async def send_tool_list_changed(self):
                self.calls += 1

        async def scenario():
            hub = SessionHub()
            first, second = Session(), Session()
            hub.observe("one", first)
            hub.observe("two", second)
            await hub.tools_changed("one")
            self.assertEqual((first.calls, second.calls), (1, 0))
        asyncio.run(scenario())


if __name__ == "__main__":
    unittest.main()
