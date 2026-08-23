from __future__ import annotations

import asyncio
import unittest
from pathlib import Path

import uvicorn

from agent_control_plane.connectors import ConnectorCertificateMismatch, discover_streamable_http, invoke_streamable_http
from test_acp_contract import AcpContractIntegrationTests, available_port
from mcp_capability_bridge.main import create_apps
from mcp_capability_bridge.tls import prepare_certificate


class PinnedAcpContractIntegrationTests(AcpContractIntegrationTests):
    async def test_current_acp_rejects_wrong_pin_and_recovers(self):
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
