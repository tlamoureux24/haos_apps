from __future__ import annotations

import asyncio
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

from mcp_capability_bridge.contracts import AdapterCallError, InvocationContext
from mcp_capability_bridge.web_sessions import WebSessionManager


def config(mode="none"):
    return {"base_url":"https://app.internal/","resolved_addresses":["10.0.0.8"],"navigation_origins":["https://app.internal"],"authentication_origins":[],"resource_origins":["https://app.internal"],"websocket_origins":[],"verify_tls":True,"inactivity_seconds":30,"absolute_seconds":60,"authentication":{"mode":mode}}


class FakeDriver:
    current_url="https://app.internal/home"
    window_handles=["one"]
    def __init__(self,*_,**__): self.quit_called=False;self.actions=[];self.node_name="Apply";self.element_type=""
    def set_page_load_timeout(self,_): pass
    def get(self,_): pass
    def execute_script(self,_): return 0
    def execute_cdp_cmd(self,method,args):
        if method=="Accessibility.getFullAXTree":
            return {"nodes":[{"role":{"value":"heading"},"name":{"value":"Welcome opaque-password"}},{"backendDOMNodeId":7,"role":{"value":"button"},"name":{"value":self.node_name}},{"backendDOMNodeId":8,"role":{"value":"textbox"},"name":{"value":"Name"}},{"role":{"value":"password"},"value":{"value":"opaque-password"}}]}
        if method=="DOM.resolveNode": return {"object":{"objectId":f'node-{args["backendNodeId"]}'}}
        if method=="Runtime.callFunctionOn":
            if "tag:this.tagName" in args.get("functionDeclaration",""): return {"result":{"value":{"tag":"BUTTON","type":self.element_type,"disabled":False,"readOnly":False}}}
            self.actions.append(args);return {"result":{"value":True}}
        if method=="DOM.getBoxModel": return {"model":{"content":[0,0,10,0,10,10,0,10]}}
        if method=="Input.dispatchMouseEvent":
            if args.get("type")=="mouseReleased": self.actions.append(args)
            return {}
        if method=="Input.dispatchKeyEvent": self.actions.append(args);return {}
        return {}
    def quit(self): self.quit_called=True


class WebSessionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary=tempfile.TemporaryDirectory();self.manager=WebSessionManager(Path(self.temporary.name),FakeDriver)
        self.patch=patch("mcp_capability_bridge.web_sessions.NetworkPolicy.verify_resolution",new=AsyncMock());self.patch.start()
        self.a=InvocationContext("namespace-a",1,"target");self.b=InvocationContext("namespace-b",1,"target")

    async def asyncTearDown(self):
        await self.manager.close_all();self.patch.stop();self.temporary.cleanup()

    async def test_handle_is_namespace_and_generation_bound_and_secret_is_redacted(self):
        configuration=config("basic");secret=b'{"mode":"basic","username":"reader","password":"opaque-password"}'
        opened=await self.manager.open(self.a,configuration,secret)
        self.assertNotIn("opaque-password",str(opened));self.assertEqual(opened["generation"],1)
        with self.assertRaisesRegex(AdapterCallError,"invalid_web_session"):
            await self.manager.snapshot(self.b,opened["session"])
        with self.assertRaisesRegex(AdapterCallError,"invalid_web_session"):
            await self.manager.close(self.b,opened["session"])
        with self.assertRaisesRegex(AdapterCallError,"invalid_web_session"):
            await self.manager.snapshot(InvocationContext("namespace-a",2,"target"),opened["session"])

    async def test_close_is_idempotent_and_profiles_are_disposable(self):
        first=await self.manager.open(self.a,config(),None);profiles=list(Path(self.temporary.name).glob("profile-*"));self.assertEqual(len(profiles),1)
        self.assertEqual(await self.manager.close(self.a,first["session"]),{"closed":True});self.assertFalse(profiles[0].exists())
        self.assertEqual(await self.manager.close(self.a,first["session"]),{"closed":True})
        second=await self.manager.open(self.a,config(),None);self.assertNotEqual(first["session"],second["session"])

    async def test_rotation_cleanup_is_scoped_to_owner(self):
        await self.manager.open(self.a,config(),None);opened_b=await self.manager.open(self.b,config(),None)
        await self.manager.close_namespace("namespace-a")
        self.assertEqual(self.manager.count(),1);self.assertEqual((await self.manager.snapshot(self.b,opened_b["session"]))["generation"],2)

    async def test_concurrent_session_call_fails_closed(self):
        opened=await self.manager.open(self.a,config(),None);session=await self.manager._lookup(self.a,opened["session"])
        await session.lock.acquire()
        try:
            with self.assertRaisesRegex(AdapterCallError,"web_session_busy"):
                await self.manager.snapshot(self.a,opened["session"])
        finally: session.lock.release()

    async def test_references_are_opaque_generation_bound_and_invalidated_after_action(self):
        opened=await self.manager.open(self.a,config(),None)
        button=next(node for node in opened["nodes"] if node.get("role")=="button")
        reference=button["reference"]
        result=await self.manager.action(self.a,opened["session"],reference,"click")
        self.assertGreater(result["generation"],opened["generation"])
        session=await self.manager._lookup(self.a,opened["session"])
        self.assertEqual(len(session.driver.actions),1)
        with self.assertRaisesRegex(AdapterCallError,"stale_reference"):
            await self.manager.action(self.a,opened["session"],reference,"click")
        self.assertEqual(len(session.driver.actions),1)

    async def test_semantic_replacement_fails_closed_before_effect(self):
        opened=await self.manager.open(self.a,config(),None)
        reference=next(node["reference"] for node in opened["nodes"] if node.get("role")=="button")
        session=await self.manager._lookup(self.a,opened["session"]);session.driver.node_name="Delete"
        with self.assertRaisesRegex(AdapterCallError,"stale_reference") as captured:
            await self.manager.action(self.a,opened["session"],reference,"click")
        self.assertFalse(captured.exception.effect_possible);self.assertEqual(session.driver.actions,[])

    async def test_sensitive_element_types_are_never_acted_on(self):
        opened=await self.manager.open(self.a,config(),None)
        reference=next(node["reference"] for node in opened["nodes"] if node.get("role")=="button")
        session=await self.manager._lookup(self.a,opened["session"]);session.driver.element_type="file"
        with self.assertRaisesRegex(AdapterCallError,"sensitive_web_field"):
            await self.manager.action(self.a,opened["session"],reference,"click")
        self.assertEqual(session.driver.actions,[])

    async def test_simultaneous_actions_serialize_and_execute_reference_once(self):
        opened=await self.manager.open(self.a,config(),None)
        reference=next(node["reference"] for node in opened["nodes"] if node.get("role")=="button")
        results=await asyncio.gather(
            self.manager.action(self.a,opened["session"],reference,"click"),
            self.manager.action(self.a,opened["session"],reference,"click"),
            return_exceptions=True,
        )
        self.assertEqual(sum(not isinstance(item,Exception) for item in results),1)
        failure=next(item for item in results if isinstance(item,AdapterCallError))
        self.assertEqual(failure.code,"stale_reference")
        session=await self.manager._lookup(self.a,opened["session"]);self.assertEqual(len(session.driver.actions),1)

    async def test_navigation_is_relative_and_lost_response_is_ambiguous_without_retry(self):
        opened=await self.manager.open(self.a,config(),None)
        with self.assertRaisesRegex(AdapterCallError,"invalid_web_navigation") as denied:
            await self.manager.navigate(self.a,opened["session"],"https://elsewhere.invalid/")
        self.assertFalse(denied.exception.effect_possible)
        session=await self.manager._lookup(self.a,opened["session"])
        session.driver.get=lambda _url: (_ for _ in ()).throw(RuntimeError("lost response with secret"))
        with self.assertRaisesRegex(AdapterCallError,"browser_action_ambiguous") as ambiguous:
            await self.manager.navigate(self.a,opened["session"],"/admin")
        self.assertTrue(ambiguous.exception.effect_possible)


if __name__=="__main__": unittest.main()
