from __future__ import annotations

import importlib.metadata
import json
import os
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

from agent_execution_plane.admin_ui import ADMIN_CSS, ADMIN_JS
from agent_execution_plane.codex_runtime import CODEX_VERSION, CONFIG, CodexRuntime, CodexRuntimeError, child_environment, ensure_codex_home
from agent_execution_plane.database import initialize
from agent_execution_plane.models import Candidate, ModelStore
from agent_execution_plane.execution import Capability

FAKE_SERVER = Path(__file__).with_name("fake_codex_app_server.py")


class CodexOAuthTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.observation = self.root / "observed.jsonl"

    def tearDown(self):
        self.temp.cleanup()

    def runtime(self, *, connected=False):
        environment = {"AEP_FAKE_OBSERVATION": str(self.observation), "OPENAI_API_KEY": "forbidden", "CODEX_API_KEY": "forbidden", "CODEX_ACCESS_TOKEN": "forbidden"}
        if connected:
            environment["AEP_FAKE_CONNECTED"] = "1"
        return CodexRuntime(self.root / "codex-home", command=(sys.executable, str(FAKE_SERVER)), environment=environment)

    def observations(self):
        return [json.loads(line) for line in self.observation.read_text(encoding="utf-8").splitlines()]

    def test_isolated_home_config_and_child_environment(self):
        home = self.root / "codex-home"
        ensure_codex_home(home)
        self.assertEqual(home.stat().st_mode & 0o777, 0o700)
        self.assertEqual((home / "config.toml").stat().st_mode & 0o777, 0o600)
        self.assertEqual((home / "config.toml").read_text(encoding="utf-8"), CONFIG)
        environment = child_environment(home, {"OPENAI_API_KEY": "x", "CODEX_API_KEY": "y", "CODEX_ACCESS_TOKEN": "z", "SAFE": "yes"})
        self.assertEqual(environment["CODEX_HOME"], str(home)); self.assertEqual(environment["SAFE"], "yes")
        self.assertFalse(set(environment) & {"OPENAI_API_KEY", "CODEX_API_KEY", "CODEX_ACCESS_TOKEN"})
        self.assertIn('web_search = "live"\n\n[features]', CONFIG); self.assertNotIn('web_search = false', CONFIG)

    def test_device_login_account_catalogue_and_logout(self):
        runtime = self.runtime()
        self.assertEqual(runtime.account(), {"status": "disconnected"})
        login = runtime.login_start(); self.assertEqual(login["status"], "pending"); self.assertEqual(login["user_code"], "ABCD-EFGH")
        runtime.login_cancel(); runtime.close()
        connected = self.runtime(connected=True)
        account = connected.account(); self.assertEqual(account, {"status": "connected", "plan_type": "plus"}); self.assertNotIn("email", account)
        self.assertEqual(connected.models(), [{"id": "gpt-test", "display_name": "GPT Test"}])
        connected.logout(); self.assertEqual(connected.account(), {"status": "disconnected"}); connected.close()
        observed = self.observations()
        self.assertTrue(all(not item["forbidden_env"] for item in observed))
        self.assertTrue(all(item["codex_home"] == str(self.root / "codex-home") for item in observed))
        self.assertFalse(any(item["method"].startswith(("thread/", "turn/", "item/")) for item in observed))

    def test_oauth_model_persistence_validation_rollback_and_no_secret_fields(self):
        database = self.root / "aep.db"; initialize(database)
        runtime = self.runtime(connected=True); store = ModelStore(database, self.root / "private", runtime)
        candidate = Candidate("ChatGPT", "openai_chatgpt_oauth", None, "gpt-test", None, False, True, 5)
        model, result = store.save(candidate); self.assertEqual(result.state, "available"); self.assertIsNone(model["base_url"]); self.assertFalse(model["credential_configured"])
        changed, failed = store.save(Candidate("Rejected", "openai_chatgpt_oauth", None, "missing", None, False, True, 9), model["id"])
        self.assertIsNone(changed); self.assertEqual(failed.code, "runtime_or_model_incompatible"); self.assertEqual(store.list()[0]["display_name"], "ChatGPT")
        with closing(sqlite3.connect(database)) as db:
            row = db.execute("SELECT base_url,encrypted_credential FROM models").fetchone()
            activity = json.dumps(db.execute("SELECT * FROM activity").fetchall())
        self.assertEqual(row, (None, None)); self.assertNotIn("must-not-leak", activity)
        runtime.close()
        restarted = ModelStore(database, self.root / "private", self.runtime(connected=True)); self.assertEqual(restarted.list()[0]["provider_model"], "gpt-test"); restarted.codex_runtime.close()
        with self.assertRaises(ValueError): store.save(Candidate("Bad", "openai_chatgpt_oauth", "https://api.openai.com", "gpt-test", None, False, True, 5))
        with self.assertRaises(ValueError): store.save(Candidate("Bad", "openai_chatgpt_oauth", None, "gpt-test", "sk-forbidden", True, True, 5))

    def test_two_oauth_models_survive_edit_reload_and_reorder(self):
        database = self.root / "aep.db"; initialize(database)
        runtime = CodexRuntime(self.root / "codex-home", command=(sys.executable, str(FAKE_SERVER)), environment={"AEP_FAKE_OBSERVATION": str(self.observation), "AEP_FAKE_CONNECTED": "1", "AEP_FAKE_MODELS": "gpt-5.6-sol,gpt-5.5"})
        store = ModelStore(database, self.root / "private", runtime)
        first, _ = store.save(Candidate("GPT-5.6-Sol", "openai_chatgpt_oauth", None, "gpt-5.6-sol", None, False, True, 5), None)
        self.assertTrue(first["id"]); self.assertEqual(first["priority"], 1); self.assertEqual(len(store.list()), 1)
        edited, _ = store.save(Candidate("GPT-5.6-Sol", "openai_chatgpt_oauth", None, "gpt-5.6-sol", None, False, True, 7), first["id"])
        self.assertEqual(edited["id"], first["id"]); self.assertEqual(len(store.list()), 1)
        second, _ = store.save(Candidate("GPT-5.5", "openai_chatgpt_oauth", None, "gpt-5.5", None, False, True, 5), None)
        rows = store.list(); self.assertEqual(len(rows), 2); self.assertNotEqual(first["id"], second["id"])
        self.assertEqual([(row["display_name"], row["priority"]) for row in rows], [("GPT-5.6-Sol", 1), ("GPT-5.5", 2)])
        runtime.close()
        reloaded_runtime = CodexRuntime(self.root / "reloaded-codex-home", command=(sys.executable, str(FAKE_SERVER)), environment={"AEP_FAKE_OBSERVATION": str(self.observation), "AEP_FAKE_CONNECTED": "1", "AEP_FAKE_MODELS": "gpt-5.6-sol,gpt-5.5"})
        reloaded = ModelStore(database, self.root / "private", reloaded_runtime)
        self.assertEqual({row["provider_model"] for row in reloaded.list()}, {"gpt-5.6-sol", "gpt-5.5"})
        reloaded.reorder([second["id"], first["id"]]); reordered = reloaded.list()
        self.assertEqual([(row["id"], row["priority"]) for row in reordered], [(second["id"], 1), (first["id"], 2)])
        self.assertEqual({row["provider_model"] for row in reordered}, {"gpt-5.6-sol", "gpt-5.5"}); reloaded_runtime.close()

    def test_health_and_validation_never_start_inference(self):
        database = self.root / "aep.db"; initialize(database)
        runtime = self.runtime(connected=True); store = ModelStore(database, self.root / "private", runtime)
        store.save(Candidate("ChatGPT", "openai_chatgpt_oauth", None, "gpt-test", None, False, True, 5)); store.refresh_health(); runtime.close()
        methods = [item["method"] for item in self.observations()]
        self.assertTrue(set(methods) <= {"initialize", "account/read", "model/list"})

    def test_runtime_packages_are_exactly_pinned_and_real_binary_handshakes(self):
        self.assertEqual(CODEX_VERSION, "0.144.4")
        self.assertEqual(importlib.metadata.version("openai-codex"), CODEX_VERSION)
        self.assertEqual(importlib.metadata.version("openai-codex-cli-bin"), CODEX_VERSION)
        runtime = CodexRuntime(self.root / "real-codex-home")
        runtime.smoke(); runtime.close()

    def test_bilingual_ui_exposes_oauth_without_api_key_field(self):
        self.assertIn("openai_chatgpt_oauth", ADMIN_JS)
        self.assertIn("Compte OpenAI / ChatGPT", ADMIN_JS); self.assertIn("OpenAI / ChatGPT account", ADMIN_JS)
        self.assertIn("Aucun modèle configuré.", ADMIN_JS); self.assertIn("No model configured.", ADMIN_JS)
        self.assertIn("provider:'Fournisseur'", ADMIN_JS); self.assertIn("tr(m.provider_family)", ADMIN_JS)
        self.assertIn("credential:oauth?null", ADMIN_JS); self.assertIn("base_url:oauth?null", ADMIN_JS)
        self.assertIn("form.reset();form.id.value=model?.id??''", ADMIN_JS)
        self.assertIn("data={id:f.id.value||null", ADMIN_JS)
        self.assertGreaterEqual(ADMIN_JS.count("${m.in_use?'disabled':''}"),3)
        self.assertIn(".primary:disabled,.secondary:disabled,.danger:disabled",ADMIN_CSS)
        self.assertIn("model_in_use:'Ce modèle est en cours d’utilisation.'",ADMIN_JS);self.assertIn("model_in_use:'This model is currently in use.'",ADMIN_JS)
        self.assertIn("if(!response.ok)actionMessage.textContent=tr((await response.json()).error.code)",ADMIN_JS)
        self.assertIn('id="model-drawer-panel"', ADMIN_JS); self.assertNotIn('id="model-dialog"', ADMIN_JS)
        self.assertIn("openDrawer(tr(model?'edit':'addModel'),'model-drawer-panel',trigger)", ADMIN_JS)
        self.assertIn("document.querySelector('.drawer-overlay').onclick=closeDrawer", ADMIN_JS)
        self.assertIn("if(event.key==='Escape')", ADMIN_JS); self.assertIn("restoreTarget?.focus()", ADMIN_JS)
        self.assertIn('.drawer{position:absolute;inset:0 0 0 auto', ADMIN_CSS); self.assertIn('@media(max-width:560px){.drawer{width:100vw}', ADMIN_CSS)
        self.assertIn("chatgptDeviceCode", Path(__file__).parents[1].joinpath("src/agent_execution_plane/codex_runtime.py").read_text(encoding="utf-8"))

    def test_execution_wrapper_routes_only_dynamic_tools_and_denies_commands(self):
        async def scenario():
            environment={"AEP_FAKE_OBSERVATION":str(self.observation),"AEP_FAKE_EXECUTION":"1","OPENAI_API_KEY":"forbidden"}
            runtime=CodexRuntime(self.root/'codex-home',command=(sys.executable,str(FAKE_SERVER)),environment=environment);calls=[]
            async def dispatch(call):calls.append(call);return {'accepted':call.arguments['value']}
            reply=await runtime.execute_turn('gpt-test',[{'role':'user','content':'source'}],(Capability('source_tool','source',{'type':'object'}),),None,10,dispatch)
            self.assertEqual(reply.content,'done');self.assertEqual([(c.name,c.arguments) for c in calls],[('source_tool',{'value':4})])
        import asyncio;asyncio.run(scenario())
        observed=self.observations();start=next(x for x in observed if x['method']=='thread/start')['params']
        self.assertTrue(start['ephemeral']);self.assertEqual(start['environments'],[]);self.assertEqual(start['instructionSources'],[]);self.assertEqual([x['name'] for x in start['dynamicTools']],['source_tool'])
        denial=next(x for x in observed if x['method']=='observed_denial')['response'];self.assertEqual(denial['error']['message'],'unattended_request_denied')


if __name__ == "__main__": unittest.main()
