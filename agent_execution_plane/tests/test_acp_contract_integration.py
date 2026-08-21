from __future__ import annotations

import asyncio
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timedelta, timezone
from pathlib import Path

REPOSITORY_ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(REPOSITORY_ROOT/"agent_control_plane"/"src"))

from agent_control_plane.control_plane import ControlPlane
from agent_control_plane.database import initialize_database
from agent_control_plane.mcp_api import create_mcp
from agent_execution_plane.acp import AcpBoundary, AcpStore, LIFECYCLE_TOOLS
from agent_execution_plane.database import initialize
from agent_execution_plane.execution import Capability, ExecutionOutcome
from agent_execution_plane.lifecycle import LifecycleStore
from agent_execution_plane.security import load_or_create_key


def now_iso():return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00","Z")


class Models:
    def execution_models(self):return [{"id":"model","timeout_minutes":1}]


class Engine:
    def __init__(self,outcome):self.outcome=outcome;self.requests=[]
    async def execute(self,request):self.requests.append(request);return self.outcome


class CurrentAcpSession:
    def __init__(self,factory):self.factory=factory
    async def __aenter__(self):return self
    async def __aexit__(self,*_):pass
    async def list_tools(self,cursor=None):
        tools=self.factory.server._tool_manager.list_tools()
        return [Capability(tool.name,tool.description or "",dict(tool.parameters)) for tool in tools],None
    async def call_tool(self,name,args):
        cp=self.factory.control_plane;worker=self.factory.worker
        if name=="jobs_claim_v1":
            lease=cp.claim_job(worker,"aep-contract-claim")
            return {"claimed":False} if lease is None else {"claimed":True,"job":lease.job,"lease_token":lease.lease_token,"lease_expires_at":lease.lease_expires_at}
        if name=="jobs_heartbeat_v1":
            if self.factory.heartbeat_network_failures:
                self.factory.heartbeat_network_failures-=1;raise RuntimeError("network_lost")
            return {"job_id":args["job_id"],"lease_expires_at":cp.heartbeat_job(worker,args["job_id"],args["lease_token"],"aep-contract-heartbeat")}
        if name=="jobs_complete_v1":
            report_id=cp.complete_job(worker,args["job_id"],args["lease_token"],args["completion_key"],args["report"],"aep-contract-complete")
            return {"job_id":args["job_id"],"state":"completed","report_id":report_id}
        if name=="jobs_fail_v1":
            state=cp.fail_job(worker,args["job_id"],args["lease_token"],args["completion_key"],args["reason"],args["retryable"],"aep-contract-fail")
            if self.factory.lose_fail_response:
                self.factory.lose_fail_response=False;raise RuntimeError("response_lost")
            return {"job_id":args["job_id"],"state":state}
        raise AssertionError(name)


class CurrentAcpFactory:
    def __init__(self,control_plane,worker):
        self.control_plane=control_plane;self.worker=worker;self.server=create_mcp(control_plane)
        self.lose_fail_response=False;self.heartbeat_network_failures=0
    def __call__(self,_):return CurrentAcpSession(self)


class CurrentAcpContractTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp=tempfile.TemporaryDirectory();root=Path(self.temp.name)
        self.acp_database=root/"acp.db";initialize_database(self.acp_database)
        self.control_plane=ControlPlane(self.acp_database,root/"acp-private")
        created=self.control_plane.create_identity("AEP worker","client",["jobs.claim","jobs.heartbeat","jobs.complete","jobs.fail"],"contract-worker")
        self.worker=self.control_plane.authenticate(created.credential.token)
        self.aep_database=root/"aep.db";initialize(self.aep_database)
        self.store=AcpStore(self.aep_database,load_or_create_key(root/"aep-key"));self.lifecycle=LifecycleStore(self.aep_database)
        self.factory=CurrentAcpFactory(self.control_plane,self.worker);self.models=Models()

    async def asyncTearDown(self):self.temp.cleanup()

    def queue_job(self,job_id="job-1",max_attempts=3):
        stamp=now_iso()
        with closing(sqlite3.connect(self.acp_database)) as db:
            db.execute("INSERT OR IGNORE INTO task_definitions(id,name,display_name,enabled,created_at) VALUES('task','task','Task',1,?)",(stamp,))
            db.execute("INSERT OR IGNORE INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES('revision','task',1,'Objective','{}',?, ?,?)",('{"type":"object","required":["schema_version","summary","findings"]}',max_attempts,stamp))
            db.execute("INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES(?,NULL,'task','queued',?,'revision','{}',?,?)",(job_id,self.worker.policy_revision_id,stamp,stamp))
            db.commit()

    def boundary(self,engine,heartbeat_interval=.01):
        return AcpBoundary(self.store,self.lifecycle,engine,self.models,self.factory,self.aep_database,poll_interval=.01,heartbeat_interval=heartbeat_interval)

    async def configure(self,boundary):await boundary.configure("https://acp.invalid/mcp","WORKER-SECRET",True)

    async def test_current_acp_lifecycle_schemas_validate(self):
        boundary=self.boundary(Engine(ExecutionOutcome(True,result={})))
        await self.configure(boundary)
        inventory={tool.name:tool.parameters for tool in self.factory.server._tool_manager.list_tools()}
        self.assertTrue(LIFECYCLE_TOOLS.issubset(inventory));self.assertTrue(self.store.configuration()["credential_configured"])

    async def test_lost_fail_response_retries_idempotently_without_model_replay(self):
        self.queue_job();engine=Engine(ExecutionOutcome(False,error_code="execution_failed"));boundary=self.boundary(engine)
        await self.configure(boundary);self.factory.lose_fail_response=True
        with self.assertRaisesRegex(RuntimeError,"response_lost"):await boundary.step()
        self.assertEqual(len(engine.requests),1);self.assertEqual(self.lifecycle.state()["state"],"pending_result")
        restarted_engine=Engine(ExecutionOutcome(True,result={}));await self.boundary(restarted_engine).step()
        self.assertEqual(restarted_engine.requests,[]);self.assertEqual(self.lifecycle.state(),{"state":"idle"})
        with closing(sqlite3.connect(self.acp_database)) as db:
            self.assertEqual(db.execute("SELECT state FROM jobs WHERE id='job-1'").fetchone()[0],"failed")
            self.assertEqual(db.execute("SELECT count(*) FROM job_attempts WHERE job_id='job-1' AND outcome='failed'").fetchone()[0],1)

    async def test_restart_after_expired_lease_releases_slot_and_reclaims_without_replay(self):
        self.queue_job();lease=self.control_plane.claim_job(self.worker,"initial-claim");self.assertIsNotNone(lease)
        expired=(datetime.now(timezone.utc)-timedelta(seconds=1)).isoformat().replace("+00:00","Z")
        with closing(sqlite3.connect(self.acp_database)) as db:db.execute("UPDATE job_attempts SET lease_expires_at=? WHERE job_id='job-1'",(expired,));db.commit()
        self.store.reserve_claim("interrupted","job-1",lease.lease_token,expired,"interrupted-key")
        engine=Engine(ExecutionOutcome(True,result={"schema_version":1,"summary":"recovered","findings":[]}));boundary=self.boundary(engine)
        await self.configure(boundary);await boundary.step()
        self.assertEqual(engine.requests,[]);self.assertEqual(self.lifecycle.state(),{"state":"idle"})
        await boundary.step();self.assertEqual(len(engine.requests),1);self.assertEqual(self.lifecycle.state(),{"state":"idle"})
        with closing(sqlite3.connect(self.acp_database)) as db:
            attempts=db.execute("SELECT attempt_number,outcome,failure_reason FROM job_attempts WHERE job_id='job-1' ORDER BY attempt_number").fetchall()
        self.assertEqual(attempts,[(1,"failed","lease_expired"),(2,"completed",None)])

    async def test_one_transient_heartbeat_error_recovers_against_current_acp(self):
        self.queue_job();lease=self.control_plane.claim_job(self.worker,"heartbeat-claim");self.factory.heartbeat_network_failures=1
        boundary=self.boundary(Engine(ExecutionOutcome(True,result={})),heartbeat_interval=.01);await self.configure(boundary)
        state={"expires":lease.lease_expires_at,"lost":False};task=asyncio.create_task(boundary._heartbeat("job-1",lease.lease_token,state,self.store.configuration(include_credential=True)))
        await asyncio.sleep(.04);task.cancel();await asyncio.gather(task,return_exceptions=True)
        self.assertEqual(self.factory.heartbeat_network_failures,0);self.assertGreater(state["expires"],lease.lease_expires_at)


if __name__=="__main__":unittest.main()
