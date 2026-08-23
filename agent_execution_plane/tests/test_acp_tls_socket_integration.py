from __future__ import annotations

import asyncio
import socket
import sqlite3
import sys
import tempfile
import unittest
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path

import uvicorn

REPOSITORY_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPOSITORY_ROOT / "agent_control_plane" / "src"))

from agent_control_plane.control_plane import ControlPlane
from agent_control_plane.database import initialize_database
from agent_control_plane.mcp_api import create_mcp
from agent_control_plane.tls import generate_certificate, inspect_certificate
from agent_execution_plane.acp import AcpBoundary, AcpStore
from agent_execution_plane.database import initialize
from agent_execution_plane.execution import ExecutionOutcome
from agent_execution_plane.lifecycle import LifecycleStore
from agent_execution_plane.mcp_client import session_factory
from agent_execution_plane.security import load_or_create_key


def available_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class Models:
    def execution_models(self):
        return [{"id": "deterministic-test-model", "timeout_minutes": 1}]


class Engine:
    def __init__(self):
        self.requests = []

    async def execute(self, request):
        self.requests.append(request)
        return ExecutionOutcome(True, result={"schema_version": 1, "summary": "TLS lifecycle complete", "findings": []})


class AcpTlsSocketIntegrationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        root = Path(self.temporary.name)
        self.acp_database = root / "acp.db"
        initialize_database(self.acp_database)
        self.control_plane = ControlPlane(self.acp_database, root / "acp-private")
        identity = self.control_plane.create_identity(
            "TLS AEP worker", "client", ["jobs.claim", "jobs.heartbeat", "jobs.complete", "jobs.fail"], "tls-worker"
        )
        self.credential = identity.credential.token
        self.worker = self.control_plane.authenticate(self.credential)
        self.aep_database = root / "aep.db"
        initialize(self.aep_database)
        self.store = AcpStore(self.aep_database, load_or_create_key(root / "aep-key"))
        self.lifecycle = LifecycleStore(self.aep_database)
        certfile, keyfile = generate_certificate(root / "tls", "localhost")
        self.certificate = inspect_certificate("self_generated", certfile, keyfile)
        self.port = available_port()
        application = create_mcp(self.control_plane).streamable_http_app()
        self.server = uvicorn.Server(uvicorn.Config(
            application, host="127.0.0.1", port=self.port, log_level="error", access_log=False,
            ssl_certfile=str(certfile), ssl_keyfile=str(keyfile),
        ))
        self.server_task = asyncio.create_task(self.server.serve())
        for _ in range(100):
            if self.server.started:
                break
            if self.server_task.done():
                self.server_task.result()
            await asyncio.sleep(0.02)
        self.assertTrue(self.server.started)

    async def asyncTearDown(self):
        self.server.should_exit = True
        await self.server_task
        self.temporary.cleanup()

    def queue_job(self):
        stamp = now_iso()
        with closing(sqlite3.connect(self.acp_database)) as database:
            database.execute("INSERT INTO task_definitions(id,name,display_name,enabled,created_at) VALUES('task','tls-task','TLS task',1,?)", (stamp,))
            database.execute(
                "INSERT INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES('revision','task',1,'Exercise TLS lifecycle','{}',?,1,?)",
                ('{"type":"object","required":["schema_version","summary","findings"]}', stamp),
            )
            database.execute(
                "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES('tls-job',NULL,'tls-task','queued',?,'revision','{}',?,?)",
                (self.worker.policy_revision_id, stamp, stamp),
            )
            database.commit()

    def boundary(self, engine):
        return AcpBoundary(self.store, self.lifecycle, engine, Models(), session_factory, self.aep_database, poll_interval=0.01)

    async def test_pinned_https_claim_completion_and_report(self):
        self.queue_job()
        engine = Engine()
        boundary = self.boundary(engine)
        url = f"https://127.0.0.1:{self.port}/mcp"
        await boundary.configure(url, self.credential, True, self.certificate.fingerprint_sha256)
        await boundary.step()
        self.assertEqual(len(engine.requests), 1)
        self.assertEqual(self.lifecycle.state(), {"state": "idle"})
        with closing(sqlite3.connect(self.acp_database)) as database:
            self.assertEqual(database.execute("SELECT state FROM jobs WHERE id='tls-job'").fetchone()[0], "completed")
            report = database.execute("SELECT report_json FROM reports WHERE job_id='tls-job'").fetchone()[0]
        self.assertIn("TLS lifecycle complete", report)

    async def test_wrong_pin_is_rejected_cleanly(self):
        boundary = self.boundary(Engine())
        with self.assertRaisesRegex(RuntimeError, "certificate_sha256_mismatch"):
            await boundary.configure(
                f"https://127.0.0.1:{self.port}/mcp", self.credential, True, "0" * 64,
            )

if __name__ == "__main__":
    unittest.main()
