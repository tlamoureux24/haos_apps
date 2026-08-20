from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_execution_plane.database import initialize
from agent_execution_plane.execution import ExecutionOutcome
from agent_execution_plane.lifecycle import LifecycleBusy, LifecycleStore
from agent_execution_plane.admin_ui import ADMIN_JS


class StandaloneLifecycleTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.database=Path(self.temp.name)/"aep.db";initialize(self.database);self.store=LifecycleStore(self.database)
    def tearDown(self):self.temp.cleanup()

    def test_credential_create_rotate_revoke_restart_and_one_way_storage(self):
        self.assertFalse(self.store.credential_configured());self.assertEqual(self.store.authenticate("anything"),"not_configured")
        first=self.store.create_credential();self.assertGreaterEqual(len(first),40);self.assertEqual(self.store.authenticate(first),"accepted");self.assertEqual(self.store.authenticate("wrong"),"rejected")
        with sqlite3.connect(self.database) as db: persisted=db.execute("SELECT value FROM settings WHERE key='standalone_credential_verifier'").fetchone()[0]
        self.assertTrue(persisted.startswith("opaque_sha256$"));self.assertNotIn(first,persisted);self.assertNotIn(first,self.database.read_bytes().decode(errors="ignore"))
        for _ in range(100): self.assertEqual(self.store.authenticate(first),"accepted")
        restarted=LifecycleStore(self.database);self.assertEqual(restarted.authenticate(first),"accepted")
        second=restarted.create_credential(rotate=True);self.assertEqual(restarted.authenticate(first),"rejected");self.assertEqual(restarted.authenticate(second),"accepted")
        self.assertTrue(restarted.revoke_credential());self.assertEqual(restarted.authenticate(second),"not_configured")
        self.assertIn("tokenOnce",ADMIN_JS);self.assertIn("navigator.clipboard.writeText",ADMIN_JS);self.assertNotIn("localStorage.setItem('standalone",ADMIN_JS);self.assertNotIn("sessionStorage",ADMIN_JS)
        self.assertIn("function clearStandaloneToken()",ADMIN_JS);self.assertIn("if(view!=='api')clearStandaloneToken()",ADMIN_JS)
        self.assertIn("id=\"hide-token\"",ADMIN_JS);self.assertIn("document.getElementById('hide-token').onclick=clearStandaloneToken",ADMIN_JS)
        self.assertEqual(ADMIN_JS.count("setInterval("),1);self.assertIn("clearInterval(viewTimer)",ADMIN_JS);self.assertIn("refreshView(view);viewTimer=setInterval",ADMIN_JS);self.assertNotIn("setTimeout(loadOAuthAccount",ADMIN_JS)

    def test_atomic_single_slot_active_pending_ack_and_stale_abandon(self):
        barrier=threading.Barrier(2)
        def reserve(value):
            barrier.wait()
            try:self.store.reserve(value);return "accepted"
            except LifecycleBusy as exc:return str(exc)
        with ThreadPoolExecutor(max_workers=2) as pool: results=list(pool.map(reserve,["one","two"]))
        self.assertEqual(results.count("accepted"),1);self.assertEqual(results.count("busy_active"),1)
        execution_id=self.store.state()["execution_id"]
        pending=self.store.complete(execution_id,ExecutionOutcome(True,result={"answer":42},model_id="safe-model"));self.assertEqual(pending["outcome"]["result"],{"answer":42})
        self.assertNotIn("result",self.store.overview()["outcome"])
        with self.assertRaisesRegex(LifecycleBusy,"busy_pending_result"):self.store.reserve("next")
        self.assertFalse(self.store.abandon("stale-id"));self.assertEqual(self.store.state()["execution_id"],execution_id)
        self.assertEqual(self.store.ack(execution_id),"acknowledged");self.assertEqual(self.store.ack(execution_id),"not_found");self.assertEqual(self.store.state(),{"state":"idle"})

    def test_restart_recovery_never_replays_and_preserves_pending_exactly(self):
        self.store.reserve("active-id");self.assertEqual(LifecycleStore(self.database).recover_interrupted(),"active-id")
        state=self.store.state();self.assertEqual(state["execution_id"],"active-id");self.assertEqual(state["outcome"]["error_code"],"execution_interrupted")
        self.assertEqual(self.store.ack("active-id"),"acknowledged")
        self.store.reserve("pending-id");self.store.complete("pending-id",ExecutionOutcome(True,result={"exact":[1,2,3]},model_id="m",mcp_effect_possible=False))
        before=self.store.execution("pending-id")[1];self.assertIsNone(LifecycleStore(self.database).recover_interrupted());after=LifecycleStore(self.database).execution("pending-id")[1]
        self.assertEqual(before,after);self.assertEqual(LifecycleStore(self.database).ack("pending-id"),"acknowledged")

    def test_successful_null_result_survives_restart_exactly(self):
        self.store.reserve("null-result-id");self.store.complete("null-result-id",ExecutionOutcome(True,result=None,model_id="m"))
        before=self.store.execution("null-result-id")[1];self.assertIn("result",before["outcome"]);self.assertIsNone(before["outcome"]["result"])
        restarted=LifecycleStore(self.database);self.assertIsNone(restarted.recover_interrupted());self.assertEqual(restarted.execution("null-result-id")[1],before)

    def test_execution_material_is_not_persisted_except_pending_final_result(self):
        canaries=["OBJECTIVE-CANARY","INPUT-CANARY","MCP-BEARER-CANARY","DESCRIPTION-CANARY","ARGUMENT-CANARY","TOOL-RESULT-CANARY","REASONING-CANARY"]
        self.store.reserve("canary-execution")
        before=self.database.read_bytes().decode(errors="ignore");self.assertTrue(all(value not in before for value in canaries))
        self.store.complete("canary-execution",ExecutionOutcome(True,result="FINAL-RESULT-CANARY"))
        with sqlite3.connect(self.database) as db: pending="\n".join(db.iterdump())
        self.assertIn("FINAL-RESULT-CANARY",pending);self.assertTrue(all(value not in pending for value in canaries))
        self.store.ack("canary-execution")
        with sqlite3.connect(self.database) as db: after="\n".join(db.iterdump())
        self.assertNotIn("FINAL-RESULT-CANARY",after)

    def test_http_mcp_loggers_do_not_emit_request_urls_or_headers_at_info(self):
        config=Path(__file__).parents[1].joinpath("src/agent_execution_plane/uvicorn_logging.json").read_text()
        for logger in ('"httpx"','"httpcore"','"mcp"'):self.assertIn(logger,config)
        self.assertGreaterEqual(config.count('"level": "WARNING"'),3)


if __name__=="__main__":unittest.main()
