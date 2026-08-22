from __future__ import annotations

import base64
import importlib.util
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace

import httpx

RUNNER_PATH=Path(__file__).resolve().parents[1]/"acceptance"/"lot3c_external"/"runner.py"
SPEC=importlib.util.spec_from_file_location("mcb_lot3c_external_runner",RUNNER_PATH)
runner=importlib.util.module_from_spec(SPEC);SPEC.loader.exec_module(runner)


class Lot3CAcceptanceRunnerTests(unittest.TestCase):
    def test_reader_and_admin_fixture_enforce_different_real_authority(self):
        runner.State.admin_effects=runner.State.reader_denials=0
        external="http://127.0.0.1:9"
        reader=runner.ThreadingHTTPServer(("127.0.0.1",0),runner.handler("reader",external))
        admin=runner.ThreadingHTTPServer(("127.0.0.1",0),runner.handler("admin",external))
        threads=[threading.Thread(target=item.serve_forever,daemon=True) for item in (reader,admin)]
        for thread in threads:thread.start()
        try:
            reader_auth="Basic "+base64.b64encode(b"reader:reader-secret").decode()
            admin_auth="Basic "+base64.b64encode(b"admin:admin-secret").decode()
            with httpx.Client() as client:
                self.assertEqual(client.post(f"http://127.0.0.1:{reader.server_port}/effect",headers={"Authorization":reader_auth}).status_code,403)
                self.assertEqual(client.post(f"http://127.0.0.1:{admin.server_port}/effect",headers={"Authorization":admin_auth}).status_code,204)
            self.assertEqual((runner.State.reader_denials,runner.State.admin_effects),(1,1))
        finally:
            for server in (reader,admin):server.shutdown();server.server_close()
            for thread in threads:thread.join()

    def test_error_parser_extracts_stable_code_without_payload_output(self):
        result=SimpleNamespace(isError=True,content=[SimpleNamespace(text='{"error":{"code":"stale_reference","effect_possible":false}}')])
        self.assertEqual(runner.error_code(result),"stale_reference")


if __name__=="__main__":unittest.main()
