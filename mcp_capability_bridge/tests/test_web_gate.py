from __future__ import annotations

import asyncio
import logging
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock,patch

from selenium.common.exceptions import WebDriverException

from mcp_capability_bridge.browser_runtime import BrowserRuntime,sanitize_diagnostic
from mcp_capability_bridge.web_adapter import NetworkPolicy,WebAdapter,origin


def configuration():
    return {"base_url":"https://app.internal/path","resolved_addresses":["10.0.0.8"],"navigation_origins":["https://app.internal"],"authentication_origins":[],"resource_origins":["https://app.internal"],"websocket_origins":[],"verify_tls":True,"inactivity_seconds":300,"absolute_seconds":1800}


class WebGateTests(unittest.IsolatedAsyncioTestCase):
    def test_third_party_browser_loggers_cannot_leak_payload_at_debug(self):
        self.assertGreaterEqual(logging.getLogger("selenium").getEffectiveLevel(),logging.WARNING)
        self.assertGreaterEqual(logging.getLogger("urllib3").getEffectiveLevel(),logging.WARNING)

    def test_browser_diagnostics_are_bounded_and_redact_sensitive_payloads(self):
        secret="opaque-secret-value"
        raw=f"GET https://user:{secret}@app.internal/private?token={secret}\nAuthorization: Bearer {secret}\n"+("x"*12000)
        sanitized=sanitize_diagnostic(raw)
        self.assertNotIn(secret,sanitized)
        self.assertNotIn("/private",sanitized)
        self.assertIn("[REDACTED_URL]",sanitized)
        self.assertIn("[TRUNCATED]",sanitized)
        self.assertLessEqual(len(sanitized),8205)

    def test_static_adapter_publishes_no_tools_and_validates_exact_contract(self):
        adapter=WebAdapter();adapter.validate_target(configuration(),None);self.assertEqual(adapter.capabilities(configuration()),())
        for bad in ("file:///etc/passwd","javascript:alert(1)","data:text/html,x"):
            with self.assertRaises(ValueError):origin(bad)
        invalid=configuration();invalid["navigation_origins"]=["https://elsewhere.internal"]
        with self.assertRaisesRegex(ValueError,"invalid_web_origins"):adapter.validate_target(invalid,None)

    async def test_policy_fails_closed_for_origin_and_dns_rebinding(self):
        policy=NetworkPolicy(configuration());policy.authorize("https://app.internal/ok","navigation_origins")
        with self.assertRaisesRegex(PermissionError,"web_origin_denied"):policy.authorize("http://app.internal/","navigation_origins")
        with patch("mcp_capability_bridge.web_adapter.resolve_host",new=AsyncMock(return_value=("10.0.0.9",))):
            with self.assertRaisesRegex(PermissionError,"web_resolution_changed"):await policy.verify_resolution()

    async def test_startup_cleanup_is_scoped_to_validated_profile_children(self):
        with tempfile.TemporaryDirectory() as temporary:
            root=Path(temporary);stale=root/"profile-stale";stale.mkdir();(stale/"state").write_text("x");unrelated=root/"keep";unrelated.mkdir();outside=root.parent/"outside-profile"
            outside.mkdir(exist_ok=True);link=root/"profile-link";link.symlink_to(outside,target_is_directory=True)
            runtime=BrowserRuntime(root);runtime.prepare()
            self.assertFalse(stale.exists());self.assertTrue(unrelated.exists());self.assertTrue(link.is_symlink());self.assertTrue(outside.exists())
            link.unlink();outside.rmdir()

    async def test_probe_is_bounded_and_shutdown_cleans_tasks(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime=BrowserRuntime(Path(temporary));runtime.prepare()
            with patch.object(NetworkPolicy,"verify_resolution",new=AsyncMock()),patch.object(runtime,"_probe_sync",return_value={"status":"reachable","origin":"https://app.internal"}):
                self.assertEqual((await runtime.probe(configuration()))["status"],"reachable")
            await runtime.close();self.assertEqual(list(Path(temporary).glob("profile-*")),[])

    async def test_webdriver_crash_is_logged_safely_and_returned_as_stable_error(self):
        with tempfile.TemporaryDirectory() as temporary:
            runtime=BrowserRuntime(Path(temporary));runtime.prepare()
            failure=WebDriverException("failed at https://app.internal/private Authorization: Bearer opaque-secret")
            with patch("mcp_capability_bridge.browser_runtime.webdriver.Chrome",side_effect=failure),self.assertLogs("mcp_capability_bridge.browser",level="DEBUG") as captured:
                with self.assertRaisesRegex(RuntimeError,"browser_session_failed"):
                    runtime._probe_sync(configuration(),NetworkPolicy(configuration()))
            logs="\n".join(captured.output)
            self.assertIn("MCB_BROWSER_DIAG session_failed",logs)
            self.assertIn("MCB_BROWSER_DIAG webdriver",logs)
            self.assertNotIn("opaque-secret",logs)
            self.assertNotIn("/private",logs)
            self.assertEqual(list(Path(temporary).glob("profile-*")),[])


if __name__=="__main__":unittest.main()
