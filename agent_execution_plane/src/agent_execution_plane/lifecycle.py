"""Durable single-slot lifecycle and standalone credential state."""

from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from dataclasses import asdict
from pathlib import Path
from typing import Any

from agent_execution_plane.database import now_iso
from agent_execution_plane.execution import ExecutionOutcome, canonical
from agent_execution_plane.security import credential_verifier, generate_opaque_credential, verify_credential

MAX_RESULT_BYTES = 4 * 1024 * 1024
VERIFIER_KEY = "standalone_credential_verifier"


class LifecycleBusy(RuntimeError):
    pass


class LifecycleStore:
    def __init__(self, database: Path):
        self.database = database

    @contextmanager
    def _open(self):
        db = sqlite3.connect(self.database, timeout=10)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA secure_delete=ON")
        try:
            yield db
            db.commit()
        except BaseException:
            db.rollback()
            raise
        finally:
            db.close()

    def credential_configured(self) -> bool:
        with self._open() as db:
            return db.execute("SELECT 1 FROM settings WHERE key=?", (VERIFIER_KEY,)).fetchone() is not None

    def create_credential(self, *, rotate: bool = False) -> str:
        token = generate_opaque_credential(); verifier = credential_verifier(token); timestamp = now_iso()
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            exists = db.execute("SELECT 1 FROM settings WHERE key=?", (VERIFIER_KEY,)).fetchone() is not None
            if exists and not rotate: raise ValueError("credential_already_configured")
            if not exists and rotate: raise ValueError("credential_not_configured")
            db.execute("INSERT INTO settings(key,value,updated_at) VALUES(?,?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value,updated_at=excluded.updated_at", (VERIFIER_KEY, verifier, timestamp))
            db.commit()
        return token

    def revoke_credential(self) -> bool:
        with self._open() as db:
            return bool(db.execute("DELETE FROM settings WHERE key=?", (VERIFIER_KEY,)).rowcount)

    def authenticate(self, token: str) -> str:
        with self._open() as db:
            row = db.execute("SELECT value FROM settings WHERE key=?", (VERIFIER_KEY,)).fetchone()
        if row is None: return "not_configured"
        if len(token) > 256: return "rejected"
        return "accepted" if verify_credential(token, row["value"]) else "rejected"

    def reserve(self, execution_id: str, source_kind: str = "standalone") -> dict[str, Any]:
        timestamp = now_iso()
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT execution_id FROM active_execution WHERE singleton=1").fetchone()
            pending = db.execute("SELECT execution_id FROM pending_result WHERE singleton=1").fetchone()
            if active: raise LifecycleBusy("busy_active")
            if pending: raise LifecycleBusy("busy_pending_result")
            db.execute("INSERT INTO active_execution(singleton,execution_id,source_kind,started_at) VALUES(1,?,?,?)", (execution_id, source_kind, timestamp))
            db.commit()
        return {"execution_id": execution_id, "source_kind": source_kind, "started_at": timestamp}

    def complete(self, execution_id: str, outcome: ExecutionOutcome) -> dict[str, Any]:
        value = {key: item for key, item in asdict(outcome).items() if item is not None or (key == "result" and outcome.success)}
        encoded = canonical(value)
        api_document={"execution_id":execution_id,"status":"result_available","outcome":value}
        if len(canonical(api_document).encode()) > MAX_RESULT_BYTES: value = {"success": False, "error_code": "result_limit", "mcp_effect_possible": outcome.mcp_effect_possible}; encoded = canonical(value)
        timestamp = now_iso()
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            active = db.execute("SELECT source_kind FROM active_execution WHERE singleton=1 AND execution_id=?", (execution_id,)).fetchone()
            if active is None: raise KeyError("execution_not_active")
            if db.execute("SELECT 1 FROM pending_result WHERE singleton=1").fetchone(): raise LifecycleBusy("busy_pending_result")
            db.execute("INSERT INTO pending_result(singleton,execution_id,source_kind,outcome_json,completed_at) VALUES(1,?,?,?,?)", (execution_id, active["source_kind"], encoded, timestamp))
            db.execute("DELETE FROM active_execution WHERE singleton=1 AND execution_id=?", (execution_id,))
            db.commit()
        return {"execution_id": execution_id, "source_kind": active["source_kind"], "outcome": value, "completed_at": timestamp}

    def recover_interrupted(self) -> str | None:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT execution_id FROM pending_result WHERE singleton=1").fetchone()
            if pending: db.commit(); return None
            active = db.execute("SELECT execution_id,source_kind FROM active_execution WHERE singleton=1").fetchone()
            if active is None: db.commit(); return None
            if active["source_kind"] != "standalone": db.commit(); return None
            outcome = canonical({"success": False, "error_code": "execution_interrupted", "mcp_effect_possible": True})
            db.execute("INSERT INTO pending_result(singleton,execution_id,source_kind,outcome_json,completed_at) VALUES(1,?,?,?,?)", (active["execution_id"], active["source_kind"], outcome, now_iso()))
            db.execute("DELETE FROM active_execution WHERE singleton=1")
            db.commit(); return str(active["execution_id"])

    def state(self) -> dict[str, Any]:
        with self._open() as db:
            active = db.execute("SELECT execution_id,source_kind,started_at FROM active_execution WHERE singleton=1").fetchone()
            pending = db.execute("SELECT execution_id,source_kind,outcome_json,completed_at FROM pending_result WHERE singleton=1").fetchone()
        if active: return {"state": "active", **dict(active)}
        if pending:
            outcome = json.loads(pending["outcome_json"])
            return {"state": "pending_result", "execution_id": pending["execution_id"], "source_kind": pending["source_kind"], "completed_at": pending["completed_at"], "outcome": outcome}
        return {"state": "idle"}

    def execution(self, execution_id: str) -> tuple[str, dict[str, Any] | None]:
        state = self.state()
        if state.get("execution_id") != execution_id: return "not_found", None
        if state["state"] == "active": return "running", {"execution_id": execution_id, "status": "running"}
        return "result_available", {"execution_id": execution_id, "status": "result_available", "outcome": state["outcome"]}

    def overview(self) -> dict[str, Any]:
        state=self.state()
        if state["state"] != "pending_result": return state
        outcome=state["outcome"]
        state["outcome"]={key:outcome[key] for key in ("success","error_code","model_id","mcp_effect_possible") if key in outcome}
        return state

    def ack(self, execution_id: str) -> str:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            pending = db.execute("SELECT execution_id FROM pending_result WHERE singleton=1").fetchone()
            active = db.execute("SELECT execution_id FROM active_execution WHERE singleton=1").fetchone()
            if pending and pending["execution_id"] == execution_id:
                db.execute("DELETE FROM pending_result WHERE singleton=1 AND execution_id=?", (execution_id,)); db.commit(); return "acknowledged"
            db.commit()
        if active and active["execution_id"] == execution_id: return "result_not_available"
        return "not_found"

    def abandon(self, execution_id: str) -> bool:
        with self._open() as db:
            db.execute("BEGIN IMMEDIATE")
            removed = db.execute("DELETE FROM pending_result WHERE singleton=1 AND execution_id=?", (execution_id,)).rowcount
            db.commit(); return bool(removed)
