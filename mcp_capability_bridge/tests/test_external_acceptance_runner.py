from __future__ import annotations

import importlib.util
import asyncio
import threading
import time
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock,patch

import httpx

RUNNER_PATH=Path(__file__).resolve().parents[1]/"acceptance"/"lot3b_external"/"runner.py"
SPEC=importlib.util.spec_from_file_location("mcb_lot3b_external_runner",RUNNER_PATH)
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)


class ExternalAcceptanceRunnerTests(unittest.TestCase):
    def test_fixture_exposes_observable_cookie_isolation_state(self):
        server=runner.ThreadingHTTPServer(("127.0.0.1",0),runner.FixtureHandler)
        thread=threading.Thread(target=server.serve_forever,daemon=True);thread.start()
        try:
            with httpx.Client() as client:
                first=client.get(f"http://127.0.0.1:{server.server_port}/").text
                second=client.get(f"http://127.0.0.1:{server.server_port}/").text
            self.assertIn("Cookie state: fresh",first);self.assertIn("Cookie state: reused",second)
        finally:
            server.shutdown();server.server_close();thread.join()

    def test_result_parser_extracts_stable_error_without_payload_logging(self):
        failure=SimpleNamespace(isError=True,content=[SimpleNamespace(text='{"error":{"code":"invalid_web_session","effect_possible":false}}')])
        self.assertEqual(runner.error_code(failure),"invalid_web_session")


class ExternalAcceptanceKeepaliveTests(unittest.IsolatedAsyncioTestCase):
    async def test_human_pause_keeps_the_control_session_active(self):
        def delayed_input(_):time.sleep(0.04);return ""
        with patch.object(runner,"KEEPALIVE_SECONDS",0.01),patch.object(runner,"snapshot",new=AsyncMock()) as snapshot_call,patch("builtins.input",side_effect=delayed_input):
            await runner.interactive_pause("pause",[("url","token","prefix","handle")])
        self.assertGreaterEqual(snapshot_call.await_count,1)


if __name__=="__main__":unittest.main()
