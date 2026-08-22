from __future__ import annotations

import asyncio
import base64
import os
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_capability_bridge.contracts import AdapterCallError, InvocationContext
from mcp_capability_bridge.web_sessions import WebSessionManager


class Fixture(BaseHTTPRequestHandler):
    effects = 0
    external_url = ""

    def log_message(self, *_):
        pass

    def do_GET(self):
        if self.path == "/iframe":
            body = b"<html><body><iframe src='/'></iframe></body></html>"
        elif self.path == "/popup":
            body = b"<html><body><button aria-label='Popup' onclick=\"window.open('/')\">Popup</button></body></html>"
        elif self.path == "/escape":
            body = f"<html><body><script>fetch('{type(self).external_url}')</script>safe</body></html>".encode()
        elif self.path == "/redirect":
            self.send_response(302);self.send_header("Location",type(self).external_url);self.end_headers();return
        else:
            body = b"""<!doctype html><html><body>
        <label>Name <input aria-label='Name' value='before'></label>
        <select aria-label='Mode'><option value='read'>Read</option><option value='admin'>Admin</option></select>
        <button aria-label='Apply' onclick="fetch('/effect',{method:'POST'})">Apply</button>
        <input type='password' aria-label='Forbidden password'><input type='file' aria-label='Forbidden upload'>
        <a aria-label='Forbidden download' download href='/download.bin'>Download</a>
        </body></html>"""
        self.send_response(200);self.send_header("Content-Type", "text/html");self.send_header("Content-Length", str(len(body)));self.end_headers();self.wfile.write(body)

    def do_POST(self):
        authorization = self.headers.get("Authorization", "")
        admin = "Basic " + base64.b64encode(b"admin:admin-secret").decode()
        if authorization and authorization != admin:
            self.send_response(403);self.end_headers();return
        type(self).effects += 1;self.send_response(204);self.end_headers()


class ExternalFixture(BaseHTTPRequestHandler):
    requests = 0
    def log_message(self, *_): pass
    def do_GET(self):
        type(self).requests += 1;self.send_response(204);self.end_headers()


@unittest.skipUnless(os.environ.get("MCB_RUN_BROWSER_TESTS") == "1" and Path("/usr/bin/chromium").is_file() and Path("/usr/bin/chromedriver").is_file(), "exact image Chromium runtime required")
class InteractiveChromiumTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        Fixture.effects = 0
        ExternalFixture.requests = 0
        self.external = ThreadingHTTPServer(("127.0.0.1", 0), ExternalFixture)
        self.external_thread = threading.Thread(target=self.external.serve_forever, daemon=True);self.external_thread.start()
        Fixture.external_url = f"http://127.0.0.1:{self.external.server_address[1]}/received"
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Fixture)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True);self.thread.start()
        self.temporary = tempfile.TemporaryDirectory()
        self.manager = WebSessionManager(Path(self.temporary.name))
        self.context = InvocationContext("namespace", 1, "target")
        port = self.server.server_address[1]
        origin = f"http://127.0.0.1:{port}"
        self.configuration = {"base_url":origin+"/","resolved_addresses":["127.0.0.1"],"navigation_origins":[origin],"authentication_origins":[],"resource_origins":[origin],"websocket_origins":[],"verify_tls":True,"inactivity_seconds":30,"absolute_seconds":60,"authentication":{"mode":"none"}}
        self.resolution = patch("mcp_capability_bridge.web_sessions.NetworkPolicy.verify_resolution", new=AsyncMock());self.resolution.start()

    async def asyncTearDown(self):
        await self.manager.close_all();self.resolution.stop();self.server.shutdown();self.server.server_close();self.thread.join(timeout=2);self.external.shutdown();self.external.server_close();self.external_thread.join(timeout=2);self.temporary.cleanup()

    async def test_real_chromium_fill_select_click_and_stale_reference(self):
        opened = await self.manager.open(self.context, self.configuration, None)
        sensitive = [node for node in opened["nodes"] if node.get("reference") and str(node.get("name", "")).startswith("Forbidden")]
        self.assertEqual(sensitive, [])
        by_role = {node["role"]: node for node in opened["nodes"] if "reference" in node}
        filled = await self.manager.action(self.context, opened["session"], by_role["textbox"]["reference"], "fill", "after")
        self.assertTrue(any(node["role"] == "textbox" and node["value"] == "after" for node in filled["nodes"]))
        with self.assertRaisesRegex(AdapterCallError, "stale_reference"):
            await self.manager.action(self.context, opened["session"], by_role["textbox"]["reference"], "fill", "replayed")
        combo = next(node for node in filled["nodes"] if node.get("role") == "combobox")
        selected = await self.manager.action(self.context, opened["session"], combo["reference"], "select", "admin")
        button = next(node for node in selected["nodes"] if node.get("role") == "button")
        await self.manager.action(self.context, opened["session"], button["reference"], "click")
        for _ in range(20):
            if Fixture.effects: break
            await asyncio.sleep(.05)
        self.assertEqual(Fixture.effects, 1)

    async def test_target_account_is_the_real_authority_boundary(self):
        configuration = dict(self.configuration);configuration["authentication"]={"mode":"basic"}
        reader = b'{"mode":"basic","username":"reader","password":"reader-secret"}'
        opened = await self.manager.open(self.context, configuration, reader)
        button = next(node for node in opened["nodes"] if node.get("role") == "button")
        await self.manager.action(self.context, opened["session"], button["reference"], "click")
        await asyncio.sleep(.15);self.assertEqual(Fixture.effects, 0)
        await self.manager.close(self.context, opened["session"])
        admin = b'{"mode":"basic","username":"admin","password":"admin-secret"}'
        opened = await self.manager.open(self.context, configuration, admin)
        button = next(node for node in opened["nodes"] if node.get("role") == "button")
        await self.manager.action(self.context, opened["session"], button["reference"], "click")
        for _ in range(20):
            if Fixture.effects: break
            await asyncio.sleep(.05)
        self.assertEqual(Fixture.effects, 1)

    async def test_iframe_and_popup_contexts_fail_closed(self):
        opened = await self.manager.open(self.context, self.configuration, None)
        with self.assertRaisesRegex(AdapterCallError, "browser_frame_denied") as frame:
            await self.manager.navigate(self.context, opened["session"], "/iframe")
        self.assertTrue(frame.exception.effect_possible)
        with self.assertRaisesRegex(AdapterCallError, "invalid_web_session"):
            await self.manager.snapshot(self.context, opened["session"])
        opened = await self.manager.open(self.context, self.configuration, None)
        navigated = await self.manager.navigate(self.context, opened["session"], "/popup")
        button = next(node for node in navigated["nodes"] if node.get("role") == "button")
        with self.assertRaisesRegex(AdapterCallError, "browser_popup_denied") as popup:
            await self.manager.action(self.context, opened["session"], button["reference"], "click")
        self.assertTrue(popup.exception.effect_possible)

    async def test_unapproved_resource_and_redirect_origins_never_receive_requests(self):
        opened = await self.manager.open(self.context, self.configuration, None)
        await self.manager.navigate(self.context, opened["session"], "/escape")
        await asyncio.sleep(.2);self.assertEqual(ExternalFixture.requests, 0)
        with self.assertRaises(AdapterCallError) as redirected:
            await self.manager.navigate(self.context, opened["session"], "/redirect")
        self.assertTrue(redirected.exception.effect_possible)
        self.assertEqual(ExternalFixture.requests, 0)


if __name__ == "__main__":
    unittest.main()
