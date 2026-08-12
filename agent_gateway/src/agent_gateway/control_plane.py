"""Transactional control-plane services shared by every transport."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from uuid import uuid4

from agent_gateway.database import connect
from agent_gateway.policy import decide, validate_actions
from agent_gateway.redaction import redact
from agent_gateway.security import (
    IssuedCredential,
    issue_credential,
    load_or_create_pepper,
    parse_and_verify_token,
    token_credential_id,
)


GENESIS_HASH = "0" * 64
ALLOWED_IDENTITY_TYPES = frozenset({"client", "event_source", "scheduler"})
ALLOWED_TASKS = frozenset({"gatus_readonly_diagnostic"})


def utc_now() -> str:
    return datetime.now(UTC).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def canonical_json(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


@dataclass(frozen=True)
class AuthenticatedIdentity:
    identity_id: str
    credential_id: str
    identity_type: str
    display_name: str
    actions: tuple[str, ...]
    policy_revision_id: str


@dataclass(frozen=True)
class CreatedIdentity:
    identity_id: str
    policy_revision_id: str
    credential: IssuedCredential


@dataclass(frozen=True)
class IntakeResult:
    event_id: str
    job_id: str
    duplicate: bool


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class QueueFullError(RuntimeError):
    pass


class ControlPlane:
    def __init__(self, database_path: Path, private_dir: Path, queue_limit: int = 1000):
        self.database_path = database_path
        self.pepper = load_or_create_pepper(private_dir / "credential-pepper")
        self.queue_limit = queue_limit

    def create_identity(
        self,
        display_name: str,
        identity_type: str,
        actions: list[str],
        correlation_id: str,
    ) -> CreatedIdentity:
        name = display_name.strip()
        if not name or len(name) > 120:
            raise ValueError("Display name must contain 1 to 120 characters")
        if identity_type not in ALLOWED_IDENTITY_TYPES:
            raise ValueError("Unknown identity type")
        normalized_actions = validate_actions(actions)
        now = utc_now()
        identity_id = str(uuid4())
        policy_id = str(uuid4())
        revision_id = str(uuid4())
        credential = issue_credential(self.pepper)
        policy = {
            "schema_version": 1,
            "allow": {"gateway_actions": list(normalized_actions), "capabilities": []},
            "deny": {"gateway_actions": [], "capabilities": []},
            "limits": {"max_concurrent_jobs": 1},
        }
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO identities(id,display_name,identity_type,status,created_at) VALUES(?,?,?,?,?)",
                (identity_id, name, identity_type, "active", now),
            )
            connection.execute(
                "INSERT INTO credentials(id,identity_id,verifier,created_at) VALUES(?,?,?,?)",
                (credential.credential_id, identity_id, credential.verifier, now),
            )
            connection.execute(
                "INSERT INTO policy_documents(id,name,created_at) VALUES(?,?,?)",
                (policy_id, f"identity-{identity_id}", now),
            )
            connection.execute(
                "INSERT INTO policy_revisions(id,policy_id,schema_version,document_json,created_at) VALUES(?,?,?,?,?)",
                (revision_id, policy_id, 1, canonical_json(policy), now),
            )
            connection.execute(
                "INSERT INTO policy_bindings(identity_id,policy_revision_id,bound_at) VALUES(?,?,?)",
                (identity_id, revision_id, now),
            )
            self._append_audit(
                connection,
                actor_identity_id=None,
                credential_id=None,
                action="identities.create",
                target_type="identity",
                target_id=identity_id,
                decision="allowed",
                reason_code="ingress_admin",
                correlation_id=correlation_id,
                metadata={"identity_type": identity_type, "actions": list(normalized_actions)},
            )
        return CreatedIdentity(identity_id, revision_id, credential)

    def authenticate(self, token: str) -> AuthenticatedIdentity:
        credential_id = token_credential_id(token)
        if credential_id is None:
            raise AuthenticationError("invalid_credential")
        now = utc_now()
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT c.id AS credential_id,c.verifier,c.expires_at,c.revoked_at,
                       i.id AS identity_id,i.identity_type,i.display_name,i.status,
                       p.id AS policy_revision_id,p.schema_version,p.document_json
                FROM credentials c
                JOIN identities i ON i.id=c.identity_id
                JOIN policy_bindings b ON b.identity_id=i.id
                JOIN policy_revisions p ON p.id=b.policy_revision_id
                WHERE c.id=?
                """,
                (credential_id,),
            ).fetchone()
            if row is None or row["status"] != "active" or row["revoked_at"] is not None:
                raise AuthenticationError("invalid_credential")
            if row["expires_at"] is not None and row["expires_at"] <= now:
                raise AuthenticationError("expired_credential")
            if parse_and_verify_token(token, self.pepper, row["verifier"]) != credential_id:
                raise AuthenticationError("invalid_credential")
            if row["schema_version"] != 1:
                raise AuthenticationError("unsupported_policy")
            policy = json.loads(row["document_json"])
            actions = validate_actions(policy.get("allow", {}).get("gateway_actions", []))
            connection.execute("UPDATE credentials SET last_used_at=? WHERE id=?", (now, credential_id))
        return AuthenticatedIdentity(
            identity_id=row["identity_id"],
            credential_id=credential_id,
            identity_type=row["identity_type"],
            display_name=row["display_name"],
            actions=actions,
            policy_revision_id=row["policy_revision_id"],
        )

    def authorize(self, identity: AuthenticatedIdentity, action: str) -> None:
        decision = decide(action, identity.actions)
        if not decision.allowed:
            raise AuthorizationError(decision.reason_code)

    def record_audit(
        self,
        *,
        actor_identity_id: str | None,
        credential_id: str | None,
        action: str,
        decision: str,
        reason_code: str,
        correlation_id: str,
        metadata: object | None = None,
    ) -> None:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            self._append_audit(
                connection,
                actor_identity_id=actor_identity_id,
                credential_id=credential_id,
                action=action,
                target_type=None,
                target_id=None,
                decision=decision,
                reason_code=reason_code,
                correlation_id=correlation_id,
                metadata=metadata or {},
            )

    def ingest_event(
        self,
        identity: AuthenticatedIdentity,
        idempotency_key: str,
        event: dict[str, object],
        correlation_id: str,
    ) -> IntakeResult:
        self.authorize(identity, "events.create")
        if not idempotency_key or len(idempotency_key) > 160:
            raise ValueError("Idempotency key must contain 1 to 160 characters")
        task_name = str(event.get("requested_task", ""))
        if task_name not in ALLOWED_TASKS:
            raise ValueError("Unknown requested task")
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT e.id AS event_id,j.id AS job_id FROM events e JOIN jobs j ON j.event_id=e.id WHERE e.source_identity_id=? AND e.idempotency_key=?",
                (identity.identity_id, idempotency_key),
            ).fetchone()
            if existing:
                return IntakeResult(existing["event_id"], existing["job_id"], True)
            queued = connection.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('queued','leased')"
            ).fetchone()[0]
            if queued >= self.queue_limit:
                raise QueueFullError("queue_full")
            event_id = str(uuid4())
            job_id = str(uuid4())
            payload = canonical_json(redact(event))
            connection.execute(
                "INSERT INTO events(id,source_identity_id,idempotency_key,schema_version,event_type,occurred_at,received_at,payload_json) VALUES(?,?,?,?,?,?,?,?)",
                (
                    event_id,
                    identity.identity_id,
                    idempotency_key,
                    int(event["schema_version"]),
                    str(event["event_type"]),
                    str(event["occurred_at"]),
                    now,
                    payload,
                ),
            )
            connection.execute(
                "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,input_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?)",
                (job_id, event_id, task_name, "queued", identity.policy_revision_id, payload, now, now),
            )
            self._append_audit(
                connection,
                actor_identity_id=identity.identity_id,
                credential_id=identity.credential_id,
                action="events.create",
                target_type="event",
                target_id=event_id,
                decision="allowed",
                reason_code="accepted",
                correlation_id=correlation_id,
                metadata={"job_id": job_id, "event_type": event["event_type"]},
            )
        return IntakeResult(event_id, job_id, False)

    def _append_audit(
        self,
        connection: sqlite3.Connection,
        *,
        actor_identity_id: str | None,
        credential_id: str | None,
        action: str,
        target_type: str | None,
        target_id: str | None,
        decision: str,
        reason_code: str,
        correlation_id: str,
        metadata: object,
    ) -> None:
        previous = connection.execute(
            "SELECT entry_hash FROM audit_entries ORDER BY sequence DESC LIMIT 1"
        ).fetchone()
        previous_hash = previous[0] if previous else GENESIS_HASH
        entry_id = str(uuid4())
        occurred_at = utc_now()
        safe_metadata = canonical_json(redact(metadata))
        material = canonical_json(
            {
                "id": entry_id,
                "occurred_at": occurred_at,
                "actor_identity_id": actor_identity_id,
                "credential_id": credential_id,
                "action": action,
                "target_type": target_type,
                "target_id": target_id,
                "decision": decision,
                "reason_code": reason_code,
                "correlation_id": correlation_id,
                "metadata_json": safe_metadata,
                "previous_hash": previous_hash,
            }
        )
        entry_hash = hmac.new(self.pepper, material.encode("utf-8"), hashlib.sha256).hexdigest()
        connection.execute(
            """
            INSERT INTO audit_entries(
              id,occurred_at,actor_identity_id,credential_id,action,target_type,target_id,
              decision,reason_code,correlation_id,metadata_json,previous_hash,entry_hash
            ) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                entry_id,
                occurred_at,
                actor_identity_id,
                credential_id,
                action,
                target_type,
                target_id,
                decision,
                reason_code,
                correlation_id,
                safe_metadata,
                previous_hash,
                entry_hash,
            ),
        )
