"""Generic MCP source boundary for Agent Control Plane jobs and leases."""

from __future__ import annotations

import asyncio
import json
import logging
import secrets
import sqlite3
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from agent_execution_plane.database import now_iso, record_activity
from agent_execution_plane.execution import Capability, ExecutionFailure, ExecutionOutcome, ExecutionRequest
from agent_execution_plane.lifecycle import LifecycleBusy, LifecycleStore
from agent_execution_plane.security import decrypt, encrypt

ACP_URL_KEY="acp_mcp_url"
ACP_CREDENTIAL_KEY="acp_mcp_credential"
ACP_STATUS_KEY="acp_connectivity"
ACP_TELEMETRY_KEY="acp_telemetry"
LIFECYCLE_TOOLS={"jobs_claim_v1","jobs_heartbeat_v1","jobs_complete_v1","jobs_fail_v1"}
LIFECYCLE_INPUTS={
    "jobs_claim_v1":{},
    "jobs_heartbeat_v1":{"job_id":"string","lease_token":"string"},
    "jobs_complete_v1":{"job_id":"string","lease_token":"string","completion_key":"string","report":"object"},
    "jobs_fail_v1":{"job_id":"string","lease_token":"string","completion_key":"string","reason":"string","retryable":"boolean"},
}
logger=logging.getLogger(__name__)


def _timestamp(value: str) -> float:
    return datetime.fromisoformat(value.replace("Z","+00:00")).timestamp()


def _valid_lifecycle_schema(name:str,schema:dict[str,Any])->bool:
    expected=LIFECYCLE_INPUTS[name]
    properties=schema.get("properties");required=schema.get("required",[])
    if schema.get("type")!="object" or not isinstance(properties,dict) or not isinstance(required,list) or set(properties)!=set(expected) or set(required)!=set(expected):return False
    return all(isinstance(properties[field],dict) and properties[field].get("type")==kind for field,kind in expected.items())


class AcpStore:
    def __init__(self,database:Path,key:bytes):self.database=database;self.key=key
    @contextmanager
    def _open(self):
        db=sqlite3.connect(self.database,timeout=10);db.row_factory=sqlite3.Row
        try:yield db
        finally:db.close()
    def configuration(self,*,include_credential=False):
        with self._open() as db:rows={r["key"]:r["value"] for r in db.execute("SELECT key,value FROM settings WHERE key IN (?,?)",(ACP_URL_KEY,ACP_CREDENTIAL_KEY))}
        if ACP_URL_KEY not in rows:return None
        result={"url":rows[ACP_URL_KEY],"credential_configured":ACP_CREDENTIAL_KEY in rows}
        if include_credential:result["credential"]=decrypt(self.key,rows.get(ACP_CREDENTIAL_KEY).encode() if rows.get(ACP_CREDENTIAL_KEY) else None)
        return result
    def save_configuration(self,url:str,credential:str|None,replace:bool):
        current=self.configuration(include_credential=True);token=credential if replace or not current else current.get("credential")
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE");stamp=now_iso()
            db.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(ACP_URL_KEY,url,stamp))
            if token is not None:db.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(ACP_CREDENTIAL_KEY,encrypt(self.key,token).decode(),stamp))
            elif replace:db.execute("DELETE FROM settings WHERE key=?",(ACP_CREDENTIAL_KEY,))
            db.commit()
    def delete_configuration(self):
        with self._open() as db:db.execute("DELETE FROM settings WHERE key IN (?,?)",(ACP_URL_KEY,ACP_CREDENTIAL_KEY));db.commit()
    def connectivity(self):
        with self._open() as db:row=db.execute("SELECT value FROM settings WHERE key=?",(ACP_STATUS_KEY,)).fetchone()
        return row["value"] if row else "not_configured"
    def set_connectivity(self,value):
        with self._open() as db:db.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(ACP_STATUS_KEY,value,now_iso()));db.commit()
    def telemetry(self):
        with self._open() as db:row=db.execute("SELECT value FROM settings WHERE key=?",(ACP_TELEMETRY_KEY,)).fetchone()
        defaults={"last_poll_success_at":None,"last_response_at":None,"available_jobs":None,"successful_polls":0,"last_error_at":None,"last_error_code":None}
        if not row:return defaults
        try:value=json.loads(row["value"])
        except (TypeError,json.JSONDecodeError):return defaults
        if not isinstance(value,dict):return defaults
        return {**defaults,**{key:value.get(key) for key in defaults}}
    def _update_telemetry(self,updates,*,increment_polls=False):
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE");row=db.execute("SELECT value FROM settings WHERE key=?",(ACP_TELEMETRY_KEY,)).fetchone()
            try:value=json.loads(row["value"]) if row else {}
            except (TypeError,json.JSONDecodeError):value={}
            if not isinstance(value,dict):value={}
            value.update(updates)
            if increment_polls:
                try:polls=int(value.get("successful_polls",0))
                except (TypeError,ValueError):polls=0
                value["successful_polls"]=polls+1
            stamp=now_iso();db.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at",(ACP_TELEMETRY_KEY,json.dumps(value,separators=(",",":"),sort_keys=True),stamp));db.commit()
    def reset_telemetry(self):
        stamp=now_iso();self._update_telemetry({"last_poll_success_at":None,"last_response_at":stamp,"available_jobs":None,"successful_polls":0,"last_error_at":None,"last_error_code":None})
    def record_response(self):self._update_telemetry({"last_response_at":now_iso()})
    def record_poll(self,available_jobs):
        stamp=now_iso();self._update_telemetry({"last_poll_success_at":stamp,"last_response_at":stamp,"available_jobs":available_jobs,"last_error_at":None,"last_error_code":None},increment_polls=True)
    def record_error(self,code):self._update_telemetry({"last_error_at":now_iso(),"last_error_code":code})
    def reserve_claim(self,execution_id,job_id,lease_token,lease_expires_at,completion_key):
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            if db.execute("SELECT 1 FROM active_execution UNION ALL SELECT 1 FROM pending_result LIMIT 1").fetchone():raise LifecycleBusy("busy")
            db.execute("INSERT INTO active_execution VALUES(1,?,'acp',?)",(execution_id,now_iso()))
            db.execute("INSERT INTO acp_execution VALUES(1,?,?,?,?,?,'active')",(execution_id,job_id,encrypt(self.key,lease_token),lease_expires_at,completion_key));db.commit()
    def metadata(self):
        with self._open() as db:row=db.execute("SELECT * FROM acp_execution WHERE singleton=1").fetchone()
        if not row:return None
        result=dict(row);result["lease_token"]=decrypt(self.key,result.pop("encrypted_lease_token"));return result
    def pending(self,execution_id):
        with self._open() as db:db.execute("UPDATE acp_execution SET phase='pending' WHERE execution_id=?",(execution_id,));db.commit()
    def update_expiry(self,value):
        with self._open() as db:db.execute("UPDATE acp_execution SET lease_expires_at=? WHERE singleton=1",(value,));db.commit()
    def clear(self):
        with self._open() as db:db.execute("DELETE FROM acp_execution WHERE singleton=1");db.commit()


class AcpBoundary:
    def __init__(self,store:AcpStore,lifecycle:LifecycleStore,engine,model_store,mcp_factory,database:Path,*,poll_interval=1.0,heartbeat_interval=60.0,validation_timeout=15.0,request_timeout=15.0):
        self.store=store;self.lifecycle=lifecycle;self.engine=engine;self.model_store=model_store;self.mcp_factory=mcp_factory;self.database=database
        self.poll_interval=poll_interval;self.heartbeat_interval=heartbeat_interval;self.validation_timeout=validation_timeout;self.request_timeout=request_timeout;self._stop=asyncio.Event();self._runner=None;self._worker=None;self.connectivity="not_configured"
    def state(self):
        config=self.store.configuration();meta=self.store.metadata()
        return {"configured":config is not None,"credential_configured":bool(config and config["credential_configured"]),"connectivity":self.store.connectivity(),"delivery":meta["phase"] if meta else None,"telemetry":self.store.telemetry()}
    def _request(self,config,capabilities=(),guard=None,job=None):
        return ExecutionRequest("boundary","boundary",str((job or {}).get("objective","boundary")),(job or {}).get("input",{}),config["url"],config.get("credential"),tuple(capabilities),(job or {}).get("required_report_schema"),guard)
    async def _call(self,name,args,config=None,*,record_response=True):
        config=config or self.store.configuration(include_credential=True)
        if not config:raise RuntimeError("acp_not_configured")
        async def exchange():
            async with self.mcp_factory(self._request(config)) as session:return await session.call_tool(name,args)
        try:result=await asyncio.wait_for(exchange(),timeout=self.request_timeout)
        except asyncio.TimeoutError as exc:raise RuntimeError("acp_request_timeout") from exc
        if record_response:self.store.record_response()
        return result
    async def validate_configuration(self,url,credential):
        parsed=urlparse(url)
        if parsed.scheme not in {"http","https"} or not parsed.netloc or parsed.username or parsed.password:raise ValueError("invalid_acp_url")
        config={"url":url,"credential":credential}
        async with self.mcp_factory(self._request(config)) as session:
            inventory={};cursor=None
            while True:
                page,cursor=await session.list_tools(cursor);inventory.update((tool.name,tool.input_schema) for tool in page)
                if cursor is None:break
        if not all(name in inventory and _valid_lifecycle_schema(name,inventory[name]) for name in LIFECYCLE_TOOLS):raise ValueError("incompatible_acp_contract")
    async def configure(self,url,credential,replace):
        current=self.store.configuration(include_credential=True);effective=credential if replace or not current else current.get("credential")
        if not effective:raise ValueError("acp_credential_required")
        try:await asyncio.wait_for(self.validate_configuration(url,effective),timeout=self.validation_timeout)
        except asyncio.TimeoutError as exc:raise RuntimeError("acp_validation_timeout") from exc
        except ValueError:raise
        except Exception as exc:raise RuntimeError("acp_unavailable") from exc
        self.store.save_configuration(url,credential,replace);self.store.reset_telemetry();self.connectivity="connected";self.store.set_connectivity("connected")
    async def start(self):
        if self._runner and not self._runner.done():return
        self._stop.clear();self._runner=asyncio.create_task(self._supervise(),name="aep-acp-boundary-supervisor")
    async def stop(self):
        self._stop.set()
        if self._runner:self._runner.cancel();await asyncio.gather(self._runner,return_exceptions=True)
        self._runner=None;self._worker=None
    def _record_worker_failure(self,code,exc):
        changed=self.store.connectivity()!="unavailable" or self.store.telemetry().get("last_error_code")!=code
        self.connectivity="unavailable";self.store.set_connectivity("unavailable");self.store.record_error(code)
        if changed:logger.warning("AEP_ACP_WORKER state=retrying code=%s cause=%s",code,type(exc).__name__)
    async def _supervise(self):
        while not self._stop.is_set():
            self._worker=asyncio.create_task(self.run(),name="aep-acp-boundary-worker")
            try:await self._worker
            except asyncio.CancelledError as exc:
                if self._stop.is_set():raise
                self._record_worker_failure("acp_worker_interrupted",exc)
            except Exception as exc:self._record_worker_failure("acp_worker_failed",exc)
            finally:self._worker=None
            if not self._stop.is_set():await asyncio.sleep(self.poll_interval)
    async def run(self):
        while not self._stop.is_set():
            try:await self.step()
            except asyncio.CancelledError:raise
            except Exception as exc:
                code="acp_request_timeout" if str(exc)=="acp_request_timeout" else "acp_unavailable"
                self._record_worker_failure(code,exc)
            await asyncio.sleep(self.poll_interval)
    async def step(self):
        config=self.store.configuration(include_credential=True)
        if not config:self.connectivity="not_configured";self.store.set_connectivity("not_configured");return
        meta=self.store.metadata()
        if meta:
            if meta["phase"]=="pending":await self._deliver(meta)
            else:await self._reconcile_interrupted(meta)
            return
        if self.lifecycle.state()["state"]!="idle" or not self.model_store.execution_models():return
        claim=await self._call("jobs_claim_v1",{},config,record_response=False);self.connectivity="connected";self.store.set_connectivity("connected")
        self.store.record_poll(1 if isinstance(claim,dict) and claim.get("claimed") else 0)
        if not isinstance(claim,dict) or not claim.get("claimed"):return
        await self._accept_claim(claim,config)
    def _claim_contract(self,claim):
        job=claim.get("job");token=claim.get("lease_token");expires=claim.get("lease_expires_at")
        if not isinstance(job,dict) or not isinstance(job.get("id"),str) or not isinstance(job.get("objective"),str) or "input" not in job or not isinstance(token,str) or not isinstance(expires,str):raise ValueError("invalid_acp_claim")
        raw=job.get("allowed_capabilities");schema=job.get("required_report_schema")
        if not isinstance(raw,list) or not isinstance(schema,dict):raise ValueError("invalid_acp_claim")
        capabilities=[]
        for item in raw:
            if not isinstance(item,dict) or set(item)!={"name","input_schema"} or not isinstance(item["name"],str) or item["name"] in LIFECYCLE_TOOLS or not isinstance(item["input_schema"],dict):raise ValueError("invalid_acp_claim")
            capabilities.append(Capability(item["name"],"",item["input_schema"]))
        return job,token,expires,tuple(capabilities),schema
    async def _accept_claim(self,claim,config):
        job,token,expires,capabilities,schema=self._claim_contract(claim);execution_id="acp-"+secrets.token_urlsafe(18);completion_key=secrets.token_urlsafe(24)
        try:self.store.reserve_claim(execution_id,job["id"],token,expires,completion_key)
        except LifecycleBusy:
            await self._call("jobs_fail_v1",{"job_id":job["id"],"lease_token":token,"completion_key":completion_key,"reason":"aep_busy","retryable":True},config);return
        record_activity(self.database,"acp_job_claimed","execution","success")
        lease={"expires":expires,"lost":False}
        async def guard():
            if lease["lost"] or datetime.now(timezone.utc).timestamp()>=_timestamp(lease["expires"]):raise ExecutionFailure("source_lease_lost")
        request=ExecutionRequest(execution_id,job["id"],job["objective"],job["input"],config["url"],config.get("credential"),capabilities,schema,guard)
        execute=asyncio.create_task(self.engine.execute(request));heartbeat=asyncio.create_task(self._heartbeat(job["id"],token,lease,config))
        done,_=await asyncio.wait({execute,heartbeat},return_when=asyncio.FIRST_COMPLETED)
        if heartbeat in done and heartbeat.exception():lease["lost"]=True;execute.cancel();await asyncio.gather(execute,return_exceptions=True);outcome=ExecutionOutcome(False,error_code="source_lease_lost",mcp_effect_possible=True)
        else:
            outcome=await execute;heartbeat.cancel();await asyncio.gather(heartbeat,return_exceptions=True)
        self.lifecycle.complete(execution_id,outcome);self.store.pending(execution_id);record_activity(self.database,"acp_result_pending_delivery","execution","success" if outcome.success else "failure")
        await self._deliver(self.store.metadata())
    async def _heartbeat(self,job_id,token,lease,config):
        transient_failures=0
        while True:
            remaining=_timestamp(lease["expires"])-datetime.now(timezone.utc).timestamp()
            await asyncio.sleep(max(0,min(self.heartbeat_interval,remaining)))
            if datetime.now(timezone.utc).timestamp()>=_timestamp(lease["expires"]):raise RuntimeError("lease_expired")
            try:
                result=await self._call("jobs_heartbeat_v1",{"job_id":job_id,"lease_token":token},config)
                lease["expires"]=result["lease_expires_at"];self.store.update_expiry(lease["expires"])
                transient_failures=0
            except Exception:
                transient_failures+=1
                if transient_failures>1 or datetime.now(timezone.utc).timestamp()>=_timestamp(lease["expires"]):raise
    async def _deliver(self,meta):
        state=self.lifecycle.state();outcome=state.get("outcome") if state.get("execution_id")==meta["execution_id"] else None
        if not outcome:return
        if outcome.get("success"):
            await self._call("jobs_complete_v1",{"job_id":meta["job_id"],"lease_token":meta["lease_token"],"completion_key":meta["completion_key"],"report":outcome.get("result")})
        else:
            await self._call("jobs_fail_v1",{"job_id":meta["job_id"],"lease_token":meta["lease_token"],"completion_key":meta["completion_key"],"reason":outcome.get("error_code","execution_failed"),"retryable":False})
        self.lifecycle.ack(meta["execution_id"]);self.store.clear();self.connectivity="connected";self.store.set_connectivity("connected");record_activity(self.database,"acp_result_delivered","execution","success")
    async def _reconcile_interrupted(self,meta):
        if datetime.now(timezone.utc).timestamp()<_timestamp(meta["lease_expires_at"]):
            try:await self._call("jobs_fail_v1",{"job_id":meta["job_id"],"lease_token":meta["lease_token"],"completion_key":meta["completion_key"],"reason":"execution_interrupted","retryable":True})
            except Exception:
                if datetime.now(timezone.utc).timestamp()<_timestamp(meta["lease_expires_at"]):raise
        self.lifecycle.clear_active(meta["execution_id"]);self.store.clear();record_activity(self.database,"acp_interruption_reconciled","execution","success")
    def abandon(self,execution_id):
        meta=self.store.metadata()
        if meta and meta["execution_id"]==execution_id:self.store.clear()
