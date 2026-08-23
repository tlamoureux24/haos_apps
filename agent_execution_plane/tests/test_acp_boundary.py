from __future__ import annotations

import asyncio
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

from agent_execution_plane.acp import AcpBoundary, AcpStore, LIFECYCLE_INPUTS, LIFECYCLE_TOOLS
from agent_execution_plane.database import initialize
from agent_execution_plane.execution import Capability, ExecutionOutcome
from agent_execution_plane.lifecycle import LifecycleStore
from agent_execution_plane.security import load_or_create_key


class Models:
    def __init__(self,available=True):self.available=available
    def execution_models(self):return [{"id":"model","timeout_minutes":1}] if self.available else []


class Engine:
    def __init__(self):self.requests=[]
    async def execute(self,request):self.requests.append(request);return ExecutionOutcome(True,result={"schema_version":1,"summary":"done","findings":[]})


class Session:
    def __init__(self,owner):self.owner=owner
    async def __aenter__(self):
        if self.owner.connect_delay:await asyncio.sleep(self.owner.connect_delay)
        if self.owner.connect_pin_error:raise RuntimeError("certificate_sha256_mismatch")
        return self
    async def __aexit__(self,*_):pass
    async def list_tools(self,cursor=None):
        tools=[Capability(name,"",{"type":"object","properties":{field:{"type":kind} for field,kind in LIFECYCLE_INPUTS[name].items()},"required":list(LIFECYCLE_INPUTS[name])}) for name in sorted(LIFECYCLE_TOOLS)]
        if self.owner.incompatible:tools=tools[:-1]
        if self.owner.bad_schema:tools[-1]=Capability(tools[-1].name,"",{"type":"object","properties":{}})
        tools += [Capability("virtual.read","governed",{"type":"object","properties":{"value":{"type":"integer"}},"required":["value"]}),Capability("unrelated","",{})]
        return tools,None
    async def call_tool(self,name,arguments):
        self.owner.calls.append((name,arguments))
        if name=="jobs_claim_v1":
            if self.owner.hang_claim:
                try:await self.owner.claim_gate.wait()
                finally:self.owner.cancelled_claims+=1
            if self.owner.claim_error:raise RuntimeError("temporary")
            if self.owner.pin_error:raise RuntimeError("certificate_sha256_mismatch")
            if self.owner.claimed:return {"claimed":False}
            self.owner.claimed=True
            return {"claimed":True,"job":{"id":"job-1","objective":"objective","input":{"safe":True},"allowed_capabilities":[{"name":"virtual.read","input_schema":{"type":"object","properties":{"value":{"type":"integer"}},"required":["value"]}}],"required_report_schema":{"type":"object","required":["schema_version","summary","findings"]}},"lease_token":"LEASE-SECRET","lease_expires_at":self.owner.expiry}
        if name=="jobs_complete_v1" and self.owner.fail_delivery:
            self.owner.fail_delivery=False;raise RuntimeError("temporary")
        if name=="jobs_heartbeat_v1":
            if self.owner.heartbeat_failures:self.owner.heartbeat_failures-=1;raise RuntimeError("temporary")
            return {"job_id":"job-1","lease_expires_at":self.owner.expiry}
        return {"state":"accepted"}


class Factory:
    def __init__(self):
        self.calls=[];self.claimed=False;self.fail_delivery=False;self.heartbeat_failures=0;self.incompatible=False;self.bad_schema=False;self.connect_delay=0;self.connect_pin_error=False;self.claim_error=False;self.pin_error=False;self.hang_claim=False;self.claim_gate=asyncio.Event();self.cancelled_claims=0
        self.expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat().replace("+00:00","Z")
    def __call__(self,_):return Session(self)


class AcpBoundaryTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.database=self.root/"aep.db";initialize(self.database)
        self.store=AcpStore(self.database,load_or_create_key(self.root/"key"));self.lifecycle=LifecycleStore(self.database);self.engine=Engine();self.models=Models();self.factory=Factory()
        self.boundary=AcpBoundary(self.store,self.lifecycle,self.engine,self.models,self.factory,self.database,poll_interval=.01,heartbeat_interval=60)
    async def asyncTearDown(self):self.temp.cleanup()

    async def configure(self):await self.boundary.configure("https://acp.invalid/mcp","WORKER-SECRET",True)
    async def wait_until(self,predicate):
        for _ in range(100):
            if predicate():return
            await asyncio.sleep(.005)
        self.fail("condition_not_reached")

    async def test_configuration_is_validate_before_save_encrypted_and_optional(self):
        self.assertFalse(self.boundary.state()["configured"])
        with self.assertRaisesRegex(ValueError,"acp_credential_required"):await self.boundary.configure("https://acp.invalid/mcp",None,True)
        self.factory.incompatible=True
        with self.assertRaisesRegex(ValueError,"incompatible_acp_contract"):await self.boundary.configure("https://acp.invalid/mcp","WORKER-SECRET",True)
        self.assertIsNone(self.store.configuration());self.factory.incompatible=False;self.factory.bad_schema=True
        with self.assertRaisesRegex(ValueError,"incompatible_acp_contract"):await self.boundary.configure("https://acp.invalid/mcp","WORKER-SECRET",True)
        self.assertIsNone(self.store.configuration());self.factory.bad_schema=False
        await self.configure();public=self.store.configuration();self.assertEqual(public,{"url":"https://acp.invalid/mcp","credential_configured":True,"certificate_sha256":""})
        self.assertNotIn("WORKER-SECRET",self.database.read_bytes().decode(errors="ignore"));self.assertEqual(self.boundary.state()["connectivity"],"connected")

    async def test_configuration_timeout_is_bounded_and_does_not_persist(self):
        self.factory.connect_delay=.1;self.boundary.validation_timeout=.01
        with self.assertRaisesRegex(RuntimeError,"acp_validation_timeout"):
            await self.boundary.configure("https://acp.invalid/mcp","WORKER-SECRET",True)
        self.assertIsNone(self.store.configuration());self.assertFalse(self.boundary.state()["configured"])

    async def test_claim_maps_exact_envelope_excludes_lifecycle_and_delivers_once(self):
        await self.configure();await self.boundary.step()
        self.assertEqual(len(self.engine.requests),1);request=self.engine.requests[0]
        self.assertEqual((request.source_reference,request.objective,request.input),("job-1","objective",{"safe":True}))
        self.assertEqual([tool.name for tool in request.capabilities],["virtual.read"]);self.assertFalse(LIFECYCLE_TOOLS & {tool.name for tool in request.capabilities})
        self.assertEqual(self.lifecycle.state(),{"state":"idle"});self.assertIsNone(self.store.metadata())
        completion=[call for call in self.factory.calls if call[0]=="jobs_complete_v1"]
        self.assertEqual(len(completion),1);self.assertEqual(completion[0][1]["report"]["summary"],"done")
        telemetry=self.boundary.state()["telemetry"]
        self.assertEqual((telemetry["available_jobs"],telemetry["successful_polls"]),(1,1));self.assertIsNotNone(telemetry["last_poll_success_at"]);self.assertIsNotNone(telemetry["last_response_at"]);self.assertIsNone(telemetry["last_error_code"])

    async def test_empty_poll_and_error_telemetry_are_durable_and_safe(self):
        await self.configure();self.factory.claimed=True;await self.boundary.step()
        telemetry=AcpStore(self.database,self.store.key).telemetry();self.assertEqual((telemetry["available_jobs"],telemetry["successful_polls"]),(0,1))
        self.factory.claim_error=True;runner=asyncio.create_task(self.boundary.run());await asyncio.sleep(.03);self.boundary._stop.set();runner.cancel();await asyncio.gather(runner,return_exceptions=True)
        telemetry=AcpStore(self.database,self.store.key).telemetry();self.assertEqual(telemetry["last_error_code"],"acp_unavailable");self.assertIsNotNone(telemetry["last_error_at"])
        persisted=self.database.read_bytes().decode(errors="ignore");self.assertNotIn("WORKER-SECRET",persisted);self.assertNotIn("temporary",persisted)

    async def test_runtime_certificate_rotation_is_reported_precisely(self):
        await self.configure();self.factory.pin_error=True
        runner=asyncio.create_task(self.boundary.run());await asyncio.sleep(.03);self.boundary._stop.set();runner.cancel();await asyncio.gather(runner,return_exceptions=True)
        state=self.boundary.state()
        self.assertEqual(state["connectivity"],"unavailable")
        self.assertEqual(state["telemetry"]["last_error_code"],"certificate_sha256_mismatch")
        self.assertTrue(state["configured"])

    async def test_idle_healthcheck_detects_certificate_rotation_without_models(self):
        await self.configure();self.models.available=False;self.factory.connect_pin_error=True;self.boundary._next_healthcheck=0
        runner=asyncio.create_task(self.boundary.run());await asyncio.sleep(.03);self.boundary._stop.set();runner.cancel();await asyncio.gather(runner,return_exceptions=True)
        state=self.boundary.state()
        self.assertEqual(state["connectivity"],"unavailable")
        self.assertEqual(state["telemetry"]["last_error_code"],"certificate_sha256_mismatch")
        self.assertEqual(state["telemetry"]["successful_polls"],0)
        self.assertTrue(state["configured"])

    async def test_stalled_claim_times_out_and_polling_recovers_without_restart(self):
        await self.configure();self.factory.hang_claim=True;self.boundary.request_timeout=.01
        await self.boundary.start();await self.wait_until(lambda:self.factory.cancelled_claims>=1)
        self.assertGreaterEqual(self.factory.cancelled_claims,1);self.assertEqual(self.boundary.state()["telemetry"]["last_error_code"],"acp_request_timeout")
        self.factory.hang_claim=False;self.factory.claimed=True;await self.wait_until(lambda:self.boundary.state()["telemetry"]["successful_polls"]>=1);await self.boundary.stop()
        telemetry=self.boundary.state()["telemetry"]
        self.assertGreaterEqual(telemetry["successful_polls"],1);self.assertEqual(telemetry["last_error_code"],None);self.assertEqual(self.boundary.state()["connectivity"],"connected")

    async def test_supervisor_restarts_an_interrupted_polling_worker(self):
        await self.configure();self.factory.claimed=True;await self.boundary.start();await self.wait_until(lambda:self.boundary.state()["telemetry"]["successful_polls"]>=1)
        first=self.boundary._worker;polls=self.boundary.state()["telemetry"]["successful_polls"];first.cancel();await self.wait_until(lambda:self.boundary._worker is not None and self.boundary._worker is not first and self.boundary.state()["telemetry"]["successful_polls"]>polls)
        self.assertIsNotNone(self.boundary._worker);self.assertIsNot(first,self.boundary._worker);self.assertGreater(self.boundary.state()["telemetry"]["successful_polls"],polls)
        await self.boundary.stop()

    async def test_pending_delivery_retries_after_restart_without_rerunning_model(self):
        await self.configure();self.factory.fail_delivery=True
        with self.assertRaises(RuntimeError):await self.boundary.step()
        self.assertEqual(len(self.engine.requests),1);self.assertEqual(self.lifecycle.state()["state"],"pending_result")
        persisted=self.database.read_bytes().decode(errors="ignore")
        self.assertNotIn("WORKER-SECRET",persisted);self.assertNotIn("LEASE-SECRET",persisted)
        self.assertNotIn("objective",persisted);self.assertNotIn('{"safe":true}',persisted.replace(" ",""))
        restarted_engine=Engine();restarted=AcpBoundary(self.store,self.lifecycle,restarted_engine,self.models,self.factory,self.database)
        await restarted.step();self.assertEqual(restarted_engine.requests,[]);self.assertEqual(self.lifecycle.state(),{"state":"idle"})

    async def test_zero_models_and_busy_slot_do_not_claim(self):
        await self.configure();self.models.available=False;await self.boundary.step();self.assertFalse(self.factory.claimed)
        self.models.available=True;self.lifecycle.reserve("standalone");await self.boundary.step();self.assertFalse(self.factory.claimed)

    async def test_restart_active_is_failed_not_replayed(self):
        await self.configure();self.store.reserve_claim("acp-execution","job-1","LEASE-SECRET",self.factory.expiry,"completion")
        restarted_engine=Engine();restarted=AcpBoundary(self.store,self.lifecycle,restarted_engine,self.models,self.factory,self.database)
        await restarted.step();self.assertEqual(restarted_engine.requests,[]);self.assertEqual(self.lifecycle.state(),{"state":"idle"})
        self.assertTrue(any(name=="jobs_fail_v1" and args["reason"]=="execution_interrupted" for name,args in self.factory.calls))

    async def test_restart_with_expired_lease_clears_local_slot_without_remote_failure(self):
        await self.configure();expired=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat().replace("+00:00","Z")
        self.store.reserve_claim("acp-execution","job-1","LEASE-SECRET",expired,"completion")
        await self.boundary.step()
        self.assertEqual(self.lifecycle.state(),{"state":"idle"});self.assertIsNone(self.store.metadata())
        self.assertFalse(any(name=="jobs_fail_v1" for name,_ in self.factory.calls))

    async def test_heartbeat_transient_failure_recovers_before_expiry(self):
        await self.configure();self.factory.heartbeat_failures=1;self.boundary.heartbeat_interval=.01
        lease={"expires":(datetime.now(timezone.utc)+timedelta(seconds=.2)).isoformat().replace("+00:00","Z"),"lost":False}
        self.factory.expiry=(datetime.now(timezone.utc)+timedelta(minutes=5)).isoformat().replace("+00:00","Z")
        task=asyncio.create_task(self.boundary._heartbeat("job-1","LEASE-SECRET",lease,self.store.configuration(include_credential=True)))
        await asyncio.sleep(.04);task.cancel();await asyncio.gather(task,return_exceptions=True)
        self.assertGreaterEqual(sum(name=="jobs_heartbeat_v1" for name,_ in self.factory.calls),2);self.assertEqual(lease["expires"],self.factory.expiry)

    async def test_expired_lease_stops_without_heartbeat_call(self):
        await self.configure();lease={"expires":(datetime.now(timezone.utc)+timedelta(seconds=.01)).isoformat().replace("+00:00","Z"),"lost":False}
        with self.assertRaisesRegex(RuntimeError,"lease_expired"):
            await self.boundary._heartbeat("job-1","LEASE-SECRET",lease,self.store.configuration(include_credential=True))
        self.assertFalse(any(name=="jobs_heartbeat_v1" for name,_ in self.factory.calls))

    async def test_second_consecutive_heartbeat_error_is_not_tolerated(self):
        await self.configure();self.factory.heartbeat_failures=2;self.boundary.heartbeat_interval=.01
        lease={"expires":(datetime.now(timezone.utc)+timedelta(seconds=1)).isoformat().replace("+00:00","Z"),"lost":False}
        with self.assertRaisesRegex(RuntimeError,"temporary"):
            await self.boundary._heartbeat("job-1","LEASE-SECRET",lease,self.store.configuration(include_credential=True))
        self.assertEqual(sum(name=="jobs_heartbeat_v1" for name,_ in self.factory.calls),2)


if __name__=="__main__":unittest.main()
