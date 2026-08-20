from __future__ import annotations

import asyncio
import socket
import tempfile
import threading
import unittest
from pathlib import Path

import httpx
import uvicorn
from mcp.server.fastmcp import FastMCP
from starlette.applications import Starlette
from starlette.routing import Route

from agent_execution_plane.database import initialize, list_activity
from agent_execution_plane.execution import ExecutionEngine, ExecutionOutcome, ProviderReply, ToolCall
from agent_execution_plane.lifecycle import LifecycleStore
from agent_execution_plane.mcp_client import session_factory
from agent_execution_plane.standalone import StandaloneBoundary


class Store:
    def execution_models(self):return [{"id":"model-priority-1","timeout_minutes":1}]
    def begin_use(self,_):pass
    def end_use(self,_):pass


class Provider:
    def __init__(self,capture):self.capture=capture;self.turns=0
    async def turn(self,messages,tools,result_schema,remaining,dispatch):
        self.capture.append(tuple(tool.name for tool in tools));self.turns+=1
        if tools and self.turns==1:return ProviderReply(tool_calls=(ToolCall("call-1",tools[0].name,{"value":7}),),assistant_message={"role":"assistant","content":""})
        return ProviderReply({"answer":"done","tool_result_seen":any(getattr(item,"result",None)=={"observed":7} for item in messages)})


class StandaloneApiTests(unittest.IsolatedAsyncioTestCase):
    @classmethod
    def setUpClass(cls):
        cls.calls=[];cls.mcp=FastMCP("standalone-test",stateless_http=True,json_response=True)
        async def requested(value:int):cls.calls.append(("requested",value));return {"observed":value}
        async def unrelated(secret:str):cls.calls.append(("unrelated",secret));return {"forbidden":True}
        cls.mcp.add_tool(requested,name="requested",description="requested description");cls.mcp.add_tool(unrelated,name="unrelated",description="unrelated description")
        sock=socket.socket();sock.bind(("127.0.0.1",0));cls.port=sock.getsockname()[1];sock.close()
        cls.server=uvicorn.Server(uvicorn.Config(cls.mcp.streamable_http_app(),host="127.0.0.1",port=cls.port,log_level="error"));cls.thread=threading.Thread(target=cls.server.run,daemon=True);cls.thread.start()
        for _ in range(100):
            if cls.server.started:break
            threading.Event().wait(.02)
    @classmethod
    def tearDownClass(cls):cls.server.should_exit=True;cls.thread.join(5)

    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.database=Path(self.temp.name)/"aep.db";initialize(self.database);self.lifecycle=LifecycleStore(self.database);self.capture=[]
        inventory=await self.mcp.list_tools();requested=next(tool for tool in inventory if tool.name=="requested")
        self.tool={"name":"requested","description":requested.description or "","input_schema":requested.inputSchema}
        engine=ExecutionEngine(Store(),lambda _:Provider(self.capture),session_factory);self.boundary=StandaloneBoundary(self.lifecycle,engine,self.database)
        app=Starlette(routes=[Route("/api/v1/execute",self.boundary.submit,methods=["POST"]),Route("/api/v1/executions/{execution_id}",self.boundary.get),Route("/api/v1/executions/{execution_id}/ack",self.boundary.ack,methods=["POST"])])
        self.client=httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://aep");self.token=self.lifecycle.create_credential();self.auth={"Authorization":f"Bearer {self.token}"}
    async def asyncTearDown(self):await self.client.aclose();self.temp.cleanup();type(self).calls=[]
    def payload(self,tools=None):return {"objective":"OBJECTIVE-CANARY","input":{"value":"INPUT-CANARY"},"mcp":{"url":f"http://127.0.0.1:{self.port}/mcp","bearer_token":"MCP-BEARER-CANARY","tools":self.tool if False else ([self.tool] if tools is None else tools)},"result_schema":{"type":"object","properties":{"answer":{"type":"string"},"tool_result_seen":{"type":"boolean"}},"required":["answer","tool_result_seen"]}}
    async def wait_result(self,execution_id):
        for _ in range(200):
            response=await self.client.get(f"/api/v1/executions/{execution_id}",headers=self.auth)
            if response.json().get("status")=="result_available":return response
            await asyncio.sleep(.01)
        self.fail("result not available")

    async def test_auth_contract_exact_envelope_full_get_ack_flow(self):
        self.lifecycle.revoke_credential();response=await self.client.post("/api/v1/execute",json=self.payload(),headers=self.auth);self.assertEqual((response.status_code,response.json()["error"]["code"]),(503,"credential_not_configured"))
        self.token=self.lifecycle.create_credential();self.auth={"Authorization":f"Bearer {self.token}"};wrong=await self.client.post("/api/v1/execute",json=self.payload(),headers={"Authorization":"Bearer wrong"});self.assertEqual(wrong.status_code,401)
        accepted=await self.client.post("/api/v1/execute",json=self.payload(),headers=self.auth);self.assertEqual(accepted.status_code,202);execution_id=accepted.json()["execution_id"];self.assertGreaterEqual(len(execution_id),30)
        self.assertIn(self.lifecycle.state()["state"],{"active","pending_result"})
        result=await self.wait_result(execution_id);again=await self.client.get(f"/api/v1/executions/{execution_id}",headers=self.auth);self.assertEqual(result.json(),again.json());self.assertEqual(result.json()["outcome"]["result"],{"answer":"done","tool_result_seen":True})
        self.assertEqual(type(self).calls,[("requested",7)]);self.assertTrue(self.capture);self.assertTrue(all(names==("requested",) for names in self.capture));self.assertNotIn("unrelated",sum((list(names) for names in self.capture),[]))
        busy=await self.client.post("/api/v1/execute",json=self.payload(),headers=self.auth);self.assertEqual((busy.status_code,busy.json()["error"]["code"]),(409,"busy_pending_result"))
        acknowledged=await self.client.post(f"/api/v1/executions/{execution_id}/ack",headers=self.auth);self.assertEqual(acknowledged.json()["status"],"acknowledged")
        self.assertEqual((await self.client.get(f"/api/v1/executions/{execution_id}",headers=self.auth)).status_code,404)
        second=await self.client.post("/api/v1/execute",json=self.payload(tools=[]),headers=self.auth);self.assertEqual(second.status_code,202);await self.wait_result(second.json()["execution_id"]);self.assertEqual(self.capture[-1],())

    async def test_invalid_contract_bounds_and_no_model_selection(self):
        invalid=self.payload();invalid["model_id"]="caller-choice";response=await self.client.post("/api/v1/execute",json=invalid,headers=self.auth);self.assertEqual((response.status_code,response.json()["error"]["code"]),(422,"invalid_execution_contract"))
        malformed=await self.client.post("/api/v1/execute",content=b"{",headers={**self.auth,"Content-Type":"application/json"});self.assertEqual((malformed.status_code,malformed.json()["error"]["code"]),(400,"malformed_json"))
        non_object=await self.client.post("/api/v1/execute",json=[],headers=self.auth);self.assertEqual((non_object.status_code,non_object.json()["error"]["code"]),(422,"invalid_execution_contract"))
        oversized=await self.client.post("/api/v1/execute",content=b"x"*(4*1024*1024+1),headers=self.auth);self.assertEqual((oversized.status_code,oversized.json()["error"]["code"]),(413,"body_too_large"))
        too_many=self.payload(tools=[{"name":f"t{i}","description":"","input_schema":{}} for i in range(129)]);response=await self.client.post("/api/v1/execute",json=too_many,headers=self.auth);self.assertEqual(response.status_code,422)

    async def test_activity_and_database_never_disclose_execution_secrets(self):
        accepted=await self.client.post("/api/v1/execute",json=self.payload(),headers=self.auth);execution_id=accepted.json()["execution_id"];await self.wait_result(execution_id)
        serialized=self.database.read_bytes().decode(errors="ignore")+str(list_activity(self.database))
        for canary in ("OBJECTIVE-CANARY","INPUT-CANARY","MCP-BEARER-CANARY","requested description"):
            self.assertNotIn(canary,serialized)

    async def test_active_busy_is_immediate_and_concurrent_submit_has_one_winner(self):
        class BlockingEngine:
            def __init__(self):self.gate=asyncio.Event();self.calls=0
            async def execute(self,_):self.calls+=1;await self.gate.wait();return ExecutionOutcome(True,result="done")
        engine=BlockingEngine();boundary=StandaloneBoundary(self.lifecycle,engine,self.database)
        app=Starlette(routes=[Route("/api/v1/execute",boundary.submit,methods=["POST"])])
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://aep") as client:
            first,second=await asyncio.gather(client.post("/api/v1/execute",json=self.payload(tools=[]),headers=self.auth),client.post("/api/v1/execute",json=self.payload(tools=[]),headers=self.auth))
            self.assertEqual(sorted([first.status_code,second.status_code]),[202,409]);loser=first if first.status_code==409 else second;self.assertEqual(loser.json()["error"]["code"],"busy_active");self.assertEqual(engine.calls,1)
            engine.gate.set();await asyncio.sleep(.05)

    async def test_post_accept_engine_failures_become_exact_pending_outcomes(self):
        failures=[("provider_failure",False),("mcp_failure",True),("result_schema_invalid",False),("result_schema_invalid",True),("attempt_timeout",False),("attempt_timeout",True)]
        for index,(code,effect) in enumerate(failures):
            class OutcomeEngine:
                async def execute(self,_):return ExecutionOutcome(False,error_code=code,model_id="model-priority-1",mcp_effect_possible=effect)
            boundary=StandaloneBoundary(self.lifecycle,OutcomeEngine(),self.database);app=Starlette(routes=[Route("/api/v1/execute",boundary.submit,methods=["POST"]),Route("/api/v1/executions/{execution_id}",boundary.get)])
            async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url="http://aep") as client:
                accepted=await client.post("/api/v1/execute",json=self.payload(tools=[]),headers=self.auth);self.assertEqual(accepted.status_code,202);execution_id=accepted.json()["execution_id"]
                for _ in range(50):
                    result=await client.get(f"/api/v1/executions/{execution_id}",headers=self.auth)
                    if result.json().get("status")=="result_available":break
                    await asyncio.sleep(.01)
                self.assertEqual(result.json()["outcome"],{"success":False,"error_code":code,"model_id":"model-priority-1","mcp_effect_possible":effect})
            self.assertEqual(self.lifecycle.ack(execution_id),"acknowledged",index)


if __name__=="__main__":unittest.main()
