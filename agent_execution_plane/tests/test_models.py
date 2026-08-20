from __future__ import annotations

import json
import sqlite3
import tempfile
import threading
import unittest
from contextlib import closing
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

from agent_execution_plane.database import initialize
from agent_execution_plane.models import Candidate, ModelStore


class FakeProvider(BaseHTTPRequestHandler):
    model_exists = True
    ollama_tools = True
    probe_tools = True
    show_calls = 0
    models_calls = 0
    chat_calls = 0
    authorizations = []

    def log_message(self, *_): pass
    def _send(self, value, status=200):
        body = json.dumps(value).encode(); self.send_response(status); self.send_header("Content-Type", "application/json"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)
    def do_GET(self):
        type(self).authorizations.append(self.headers.get("Authorization"))
        type(self).models_calls += 1
        self._send({"data": [{"id": "reasoner"}] if type(self).model_exists else []})
    def do_POST(self):
        type(self).authorizations.append(self.headers.get("Authorization"))
        length = int(self.headers.get("content-length", 0)); json.loads(self.rfile.read(length) or b"{}")
        if self.path == "/api/show":
            type(self).show_calls += 1; self._send({"capabilities": ["tools"] if type(self).ollama_tools else ["completion"]})
        else:
            type(self).chat_calls += 1
            calls = [{"function": {"name": "capability_probe", "arguments": "{}"}}] if type(self).probe_tools else []
            self._send({"choices": [{"message": {"tool_calls": calls}}]})


class ModelTests(unittest.TestCase):
    def setUp(self):
        FakeProvider.model_exists=True; FakeProvider.ollama_tools=True; FakeProvider.probe_tools=True; FakeProvider.show_calls=FakeProvider.models_calls=FakeProvider.chat_calls=0; FakeProvider.authorizations=[]
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), FakeProvider); self.thread = threading.Thread(target=self.server.serve_forever, daemon=True); self.thread.start()
        self.temp = tempfile.TemporaryDirectory(); root = Path(self.temp.name); self.database=root/"aep.db"; initialize(self.database); self.store=ModelStore(self.database, root/"private"); self.url=f"http://127.0.0.1:{self.server.server_port}"
    def tearDown(self): self.server.shutdown(); self.server.server_close(); self.temp.cleanup()
    def candidate(self, family="ollama_compatible", name="Primary", credential="super-secret", timeout=5, replace_credential=True):
        return Candidate(name, family, self.url, "reasoner", credential, replace_credential, True, timeout)

    def test_ollama_creation_encrypts_and_never_returns_secret(self):
        model, result = self.store.save(self.candidate())
        self.assertEqual(result.state, "available"); self.assertEqual(FakeProvider.show_calls, 1); self.assertNotIn("super-secret", json.dumps(model))
        with closing(sqlite3.connect(self.database)) as db: encrypted=db.execute("SELECT encrypted_credential FROM models").fetchone()[0]
        self.assertNotIn(b"super-secret", encrypted); self.assertEqual((Path(self.temp.name)/"private/provider-key").stat().st_mode & 0o777, 0o600)

    def test_openai_explicit_probe_and_rollback(self):
        model, _ = self.store.save(self.candidate("openai_compatible")); self.assertEqual(FakeProvider.chat_calls, 1)
        FakeProvider.probe_tools=False
        changed, result = self.store.save(self.candidate("openai_compatible", "Rejected", credential=None, timeout=9), model["id"])
        self.assertIsNone(changed); self.assertEqual(result.state, "incompatible")
        stored=self.store.list()[0]; self.assertEqual(stored["display_name"], "Primary"); self.assertEqual(stored["timeout_minutes"], 5)

    def test_edit_keeps_credential_unless_explicitly_replaced(self):
        model, _ = self.store.save(self.candidate())
        retained, _ = self.store.save(self.candidate(name="Retained", credential=None, replace_credential=False), model["id"])
        self.assertTrue(retained["credential_configured"])
        replaced, _ = self.store.save(self.candidate(name="Replaced", credential="new-secret"), model["id"])
        self.assertTrue(replaced["credential_configured"])
        self.assertEqual(FakeProvider.authorizations, ["Bearer super-secret", "Bearer super-secret", "Bearer new-secret"])
        with closing(sqlite3.connect(self.database)) as db:
            activity = db.execute("SELECT event_code FROM activity ORDER BY id").fetchall()
            serialized = json.dumps(activity)
        self.assertIn("model_credential_replaced", serialized)
        self.assertNotIn("new-secret", serialized)

    def test_priority_enabled_and_unbounded_positive_timeout(self):
        first,_=self.store.save(self.candidate(name="First",timeout=1_000_000)); second,_=self.store.save(self.candidate(name="Second"))
        self.store.reorder([second["id"],first["id"]]); self.assertEqual([m["display_name"] for m in self.store.list()],["Second","First"])
        self.store.set_enabled(first["id"],False); disabled=next(m for m in self.store.list() if m["id"]==first["id"]); self.assertEqual(disabled["technical_state"],"disabled")
        with self.assertRaises(ValueError): self.store.save(self.candidate(timeout=0))

    def test_startup_health_never_infers_and_unreachable_does_not_raise(self):
        model,_=self.store.save(self.candidate("openai_compatible")); FakeProvider.chat_calls=0
        self.store.refresh_health(); self.assertEqual(FakeProvider.chat_calls,0); self.assertEqual(self.store.list()[0]["provider_state"],"unverified")
        self.server.shutdown(); self.server.server_close(); self.store.refresh_health(); self.assertEqual(self.store.list()[0]["provider_state"],"unavailable")

    def test_known_incompatible_ollama_is_not_saved(self):
        FakeProvider.ollama_tools=False; model,result=self.store.save(self.candidate()); self.assertIsNone(model); self.assertEqual(result.state,"incompatible"); self.assertEqual(self.store.list(),[])

    def test_in_use_locks_technical_changes_disable_and_delete_but_not_priority(self):
        first,_=self.store.save(self.candidate(name='First'));second,_=self.store.save(self.candidate(name='Second'))
        self.store.begin_use(first['id']);self.assertTrue(self.store.list()[0]['in_use'])
        with self.assertRaisesRegex(RuntimeError,'model_in_use'):self.store.delete(first['id'])
        with self.assertRaisesRegex(RuntimeError,'model_in_use'):self.store.set_enabled(first['id'],False)
        with self.assertRaisesRegex(RuntimeError,'model_in_use'):self.store.save(self.candidate(name='Changed'),first['id'])
        self.store.reorder([second['id'],first['id']]);self.assertEqual(self.store.list()[1]['id'],first['id'])
        self.store.end_use(first['id']);self.assertFalse(self.store.list()[1]['in_use'])


if __name__ == "__main__": unittest.main()
