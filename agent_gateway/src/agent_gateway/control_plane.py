"""Transactional control-plane services shared by every transport."""

from __future__ import annotations

import hashlib
import hmac
import json
import sqlite3
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from agent_gateway.connectors import (
    connector_display_endpoint,
    protect_connector_config,
    reveal_connector_config,
    validate_streamable_http_url,
)
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


def validate_json_contract(value: object, schema: dict[str, object], path: str = "report") -> None:
    """Validate the bounded JSON Schema subset produced by task definitions."""
    expected = schema.get("type")
    if expected is None and ("properties" in schema or "required" in schema):
        expected = "object"
    type_checks = {
        "object": lambda item: isinstance(item, dict),
        "array": lambda item: isinstance(item, list),
        "string": lambda item: isinstance(item, str),
        "integer": lambda item: isinstance(item, int) and not isinstance(item, bool),
        "number": lambda item: isinstance(item, (int, float)) and not isinstance(item, bool),
        "boolean": lambda item: isinstance(item, bool),
        "null": lambda item: item is None,
    }
    if expected is not None:
        check = type_checks.get(str(expected))
        if check is None or not check(value):
            raise ValueError(f"invalid_contract:{path}:type")
    if isinstance(value, dict):
        required = schema.get("required", [])
        properties = schema.get("properties", {})
        if not isinstance(required, list) or any(not isinstance(key, str) for key in required) or not isinstance(properties, dict):
            raise ValueError("invalid_stored_report_schema")
        if any(key not in value for key in required):
            raise ValueError(f"invalid_contract:{path}:required")
        if schema.get("additionalProperties") is False and any(key not in properties for key in value):
            raise ValueError(f"invalid_contract:{path}:additional_property")
        for key, child in value.items():
            child_schema = properties.get(key)
            if child_schema is not None:
                if not isinstance(child_schema, dict):
                    raise ValueError("invalid_stored_report_schema")
                validate_json_contract(child, child_schema, f"{path}.{key}")
    if isinstance(value, list):
        maximum = schema.get("maxItems")
        if maximum is not None and len(value) > int(maximum):
            raise ValueError(f"invalid_contract:{path}:max_items")
        item_schema = schema.get("items")
        if item_schema is not None:
            if not isinstance(item_schema, dict):
                raise ValueError("invalid_stored_report_schema")
            for index, child in enumerate(value):
                validate_json_contract(child, item_schema, f"{path}[{index}]")
    if isinstance(value, str):
        minimum = schema.get("minLength")
        maximum = schema.get("maxLength")
        if minimum is not None and len(value) < int(minimum):
            raise ValueError(f"invalid_contract:{path}:min_length")
        if maximum is not None and len(value) > int(maximum):
            raise ValueError(f"invalid_contract:{path}:max_length")


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


@dataclass(frozen=True)
class LeaseResult:
    job: dict[str, object]
    lease_token: str
    lease_expires_at: str


class AuthenticationError(RuntimeError):
    pass


class AuthorizationError(RuntimeError):
    def __init__(self, reason_code: str):
        super().__init__(reason_code)
        self.reason_code = reason_code


class QueueFullError(RuntimeError):
    pass


class RateLimitExceeded(RuntimeError):
    pass


class LeaseError(RuntimeError):
    pass


class ControlPlane:
    def __init__(
        self,
        database_path: Path,
        private_dir: Path,
        queue_limit: int = 1000,
        intake_rate_limit_per_minute: int = 30,
    ):
        self.database_path = database_path
        self.pepper = load_or_create_pepper(private_dir / "credential-pepper")
        self.queue_limit = queue_limit
        self.intake_rate_limit_per_minute = intake_rate_limit_per_minute

    def list_connectors(self) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT c.id,c.display_name,c.transport,c.display_endpoint,c.status,c.enabled,
                       c.created_at,c.updated_at,c.last_checked_at,c.last_error_code,
                       c.inventory_revision,count(t.name) AS tool_count
                FROM connectors c LEFT JOIN connector_tools t ON t.connector_id=c.id
                GROUP BY c.id ORDER BY c.display_name COLLATE NOCASE
                """
            ).fetchall()
        return [
            {
                **dict(row),
                "enabled": bool(row["enabled"]),
                "has_secret": True,
            }
            for row in rows
        ]

    def list_connector_tools(self, connector_id: str) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                "SELECT name,description,input_schema_json,schema_fingerprint,discovered_at FROM connector_tools WHERE connector_id=? ORDER BY name",
                (connector_id,),
            ).fetchall()
        return [
            {
                "name": row["name"],
                "description": row["description"],
                "input_schema": json.loads(row["input_schema_json"]),
                "schema_fingerprint": row["schema_fingerprint"],
                "discovered_at": row["discovered_at"],
            }
            for row in rows
        ]

    def list_tasks(self) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT d.id,d.name,d.display_name,d.enabled,d.created_at,r.id AS revision_id,
                       r.revision,r.objective,r.max_attempts,r.created_at AS revision_created_at
                FROM task_definitions d JOIN task_revisions r ON r.task_definition_id=d.id
                WHERE r.revision=(SELECT max(r2.revision) FROM task_revisions r2 WHERE r2.task_definition_id=d.id)
                ORDER BY d.display_name COLLATE NOCASE
                """
            ).fetchall()
            tasks: list[dict[str, object]] = []
            for row in rows:
                selections = connection.execute(
                    """
                    SELECT s.connector_id,s.tool_name,s.namespaced_name,s.schema_fingerprint,
                           c.display_name AS connector_name,c.enabled AS connector_enabled,c.status AS connector_status,
                           t.schema_fingerprint AS current_fingerprint
                    FROM task_tool_selections s
                    JOIN connectors c ON c.id=s.connector_id
                    LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                    WHERE s.task_revision_id=? ORDER BY c.display_name COLLATE NOCASE,s.tool_name
                    """,
                    (row["revision_id"],),
                ).fetchall()
                failures = []
                for selection in selections:
                    if not selection["connector_enabled"]:
                        failures.append(f"connector_disabled:{selection['connector_name']}")
                    elif selection["connector_status"] != "ready":
                        failures.append(f"connector_not_ready:{selection['connector_name']}")
                    elif selection["current_fingerprint"] is None:
                        failures.append(f"tool_missing:{selection['connector_name']}.{selection['tool_name']}")
                    elif selection["current_fingerprint"] != selection["schema_fingerprint"]:
                        failures.append(f"tool_schema_changed:{selection['connector_name']}.{selection['tool_name']}")
                status = "disabled" if not row["enabled"] else ("ready" if selections and not failures else "unavailable")
                tasks.append(
                    {
                        **dict(row),
                        "enabled": bool(row["enabled"]),
                        "status": status,
                        "dependency_failures": failures,
                        "tools": [
                            {
                                "connector_id": item["connector_id"],
                                "connector_name": item["connector_name"],
                                "tool_name": item["tool_name"],
                                "namespaced_name": item["namespaced_name"],
                            }
                            for item in selections
                        ],
                    }
                )
        return tasks

    def create_task(
        self,
        display_name: str,
        name: str,
        objective: str,
        max_attempts: int,
        selections: list[dict[str, str]],
        correlation_id: str,
    ) -> str:
        if not selections or not 1 <= max_attempts <= 10:
            raise ValueError("task_requires_tool")
        if len({(item["connector_id"], item["tool_name"]) for item in selections}) != len(selections):
            raise ValueError("duplicate_task_tool")
        task_id = str(uuid4())
        revision_id = str(uuid4())
        now = utc_now()
        report_schema = {
            "type": "object",
            "required": ["schema_version", "summary", "findings"],
            "additionalProperties": False,
            "properties": {
                "schema_version": {"type": "integer"},
                "summary": {"type": "string", "minLength": 1, "maxLength": 2000},
                "findings": {"type": "array", "maxItems": 100},
            },
        }
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            resolved = []
            for selection in selections:
                row = connection.execute(
                    """
                    SELECT c.id AS connector_id,c.status,c.enabled,t.name,t.schema_fingerprint
                    FROM connectors c JOIN connector_tools t ON t.connector_id=c.id
                    WHERE c.id=? AND t.name=?
                    """,
                    (selection["connector_id"], selection["tool_name"]),
                ).fetchone()
                if row is None or not row["enabled"] or row["status"] != "ready":
                    raise ValueError("task_connector_not_ready")
                resolved.append(row)
            connection.execute(
                "INSERT INTO task_definitions(id,name,display_name,enabled,created_at) VALUES(?,?,?,?,?)",
                (task_id, name.strip(), display_name.strip(), 1, now),
            )
            connection.execute(
                "INSERT INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES(?,?,?,?,?,?,?,?)",
                (revision_id, task_id, 1, objective.strip(), '{"type":"object"}', canonical_json(report_schema), max_attempts, now),
            )
            for row in resolved:
                digest = hashlib.sha256(f"{revision_id}:{row['connector_id']}:{row['name']}".encode()).hexdigest()[:12]
                safe_tool_name = "".join(character if character.isalnum() else "_" for character in row["name"]).strip("_")[:80] or "tool"
                virtual_name = f"task_{task_id.replace('-', '')[:12]}__{safe_tool_name}__{digest}"
                connection.execute(
                    "INSERT INTO task_tool_selections(task_revision_id,connector_id,tool_name,schema_fingerprint,namespaced_name,constraints_json) VALUES(?,?,?,?,?,?)",
                    (revision_id, row["connector_id"], row["name"], row["schema_fingerprint"], virtual_name, "{}"),
                )
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.create", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"tool_count": len(resolved)})
        return task_id

    def set_task_enabled(self, task_id: str, enabled: bool, correlation_id: str) -> bool:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute("UPDATE task_definitions SET enabled=? WHERE id=?", (int(enabled), task_id)).rowcount
            if not updated:
                return False
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.enable" if enabled else "tasks.disable", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def delete_task(self, task_id: str, correlation_id: str) -> str:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT id FROM task_definitions WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return "not_found"
            used = connection.execute("SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id WHERE r.task_definition_id=? LIMIT 1", (task_id,)).fetchone()
            if used is not None:
                return "in_use"
            revision_ids = [item[0] for item in connection.execute("SELECT id FROM task_revisions WHERE task_definition_id=?", (task_id,)).fetchall()]
            for revision_id in revision_ids:
                connection.execute("DELETE FROM task_tool_selections WHERE task_revision_id=?", (revision_id,))
            connection.execute("DELETE FROM task_revisions WHERE task_definition_id=?", (task_id,))
            connection.execute("DELETE FROM task_definitions WHERE id=?", (task_id,))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.delete", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return "deleted"

    def create_connector(
        self,
        display_name: str,
        url: str,
        bearer_token: str,
        inventory: list[dict[str, object]],
        correlation_id: str,
    ) -> str:
        name = display_name.strip()
        if not name:
            raise ValueError("invalid_connector_name")
        normalized_url = validate_streamable_http_url(url)
        connector_id = str(uuid4())
        now = utc_now()
        protected = protect_connector_config(self.pepper, normalized_url, bearer_token)
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,last_checked_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,?,1)",
                (connector_id, name, "streamable_http", protected, connector_display_endpoint(normalized_url), now, now, now),
            )
            self._replace_connector_tools(connection, connector_id, inventory, now)
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.create", target_type="connector", target_id=connector_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"display_name": name, "tool_count": len(inventory)})
        return connector_id

    def connector_connection_config(self, connector_id: str) -> tuple[str, str] | None:
        with connect(self.database_path) as connection:
            row = connection.execute("SELECT protected_config FROM connectors WHERE id=?", (connector_id,)).fetchone()
        return None if row is None else reveal_connector_config(self.pepper, row["protected_config"])

    def refresh_connector(self, connector_id: str, inventory: list[dict[str, object]] | None, error_code: str | None, correlation_id: str) -> bool:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT enabled FROM connectors WHERE id=?", (connector_id,)).fetchone()
            if row is None:
                return False
            if inventory is None:
                connection.execute("UPDATE connectors SET status='unreachable',updated_at=?,last_checked_at=?,last_error_code=? WHERE id=?", (now, now, error_code or "connection_failed", connector_id))
                reason = "unreachable"
            else:
                status = "ready" if row["enabled"] else "disabled"
                connection.execute("UPDATE connectors SET status=?,updated_at=?,last_checked_at=?,last_error_code=NULL,inventory_revision=inventory_revision+1 WHERE id=?", (status, now, now, connector_id))
                self._replace_connector_tools(connection, connector_id, inventory, now)
                reason = "inventory_refreshed"
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.check", target_type="connector", target_id=connector_id, decision="recorded", reason_code=reason, correlation_id=correlation_id, metadata={"tool_count": len(inventory or [])})
        return True

    def set_connector_enabled(self, connector_id: str, enabled: bool, correlation_id: str) -> bool:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            updated = connection.execute("UPDATE connectors SET enabled=?,status=?,updated_at=? WHERE id=?", (int(enabled), "ready" if enabled else "disabled", now, connector_id)).rowcount
            if not updated:
                return False
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.enable" if enabled else "connectors.disable", target_type="connector", target_id=connector_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def delete_connector(self, connector_id: str, correlation_id: str) -> str:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            try:
                deleted = connection.execute("DELETE FROM connectors WHERE id=?", (connector_id,)).rowcount
            except sqlite3.IntegrityError:
                return "in_use"
            if not deleted:
                return "not_found"
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.delete", target_type="connector", target_id=connector_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return "deleted"

    @staticmethod
    def _replace_connector_tools(connection: sqlite3.Connection, connector_id: str, inventory: list[dict[str, object]], now: str) -> None:
        connection.execute("DELETE FROM connector_tools WHERE connector_id=?", (connector_id,))
        for tool in inventory:
            connection.execute(
                "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
                (connector_id, str(tool["name"]), str(tool["description"]), canonical_json(tool["input_schema"]), str(tool["schema_fingerprint"]), now),
            )

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

    def list_identities(self) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT i.id,i.display_name,i.identity_type,i.status,i.created_at,
                       p.document_json,
                       count(c.id) AS credential_count,
                       max(c.last_used_at) AS last_used_at
                FROM identities i
                JOIN policy_bindings b ON b.identity_id=i.id
                JOIN policy_revisions p ON p.id=b.policy_revision_id
                LEFT JOIN credentials c ON c.identity_id=i.id AND c.revoked_at IS NULL
                GROUP BY i.id,p.id
                ORDER BY i.created_at DESC
                """
            ).fetchall()
        identities = []
        for row in rows:
            policy = json.loads(row["document_json"])
            identities.append(
                {
                    "id": row["id"],
                    "display_name": row["display_name"],
                    "identity_type": row["identity_type"],
                    "status": row["status"],
                    "created_at": row["created_at"],
                    "last_used_at": row["last_used_at"],
                    "active_credentials": row["credential_count"],
                    "gateway_actions": list(
                        validate_actions(policy.get("allow", {}).get("gateway_actions", []))
                    ),
                }
            )
        return identities

    def revoke_identity(self, identity_id: str, correlation_id: str) -> bool:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT status FROM identities WHERE id=?", (identity_id,)
            ).fetchone()
            if row is None:
                return False
            if row["status"] != "revoked":
                connection.execute(
                    "UPDATE identities SET status='revoked' WHERE id=?", (identity_id,)
                )
                connection.execute(
                    "UPDATE credentials SET revoked_at=? WHERE identity_id=? AND revoked_at IS NULL",
                    (now, identity_id),
                )
                self._append_audit(
                    connection,
                    actor_identity_id=None,
                    credential_id=None,
                    action="identities.revoke",
                    target_type="identity",
                    target_id=identity_id,
                    decision="allowed",
                    reason_code="ingress_admin",
                    correlation_id=correlation_id,
                    metadata={},
                )
        return True

    def list_events(self, limit: int = 100) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT e.id,e.event_type,e.occurred_at,e.received_at,e.payload_json,
                       i.display_name AS source_name,j.id AS job_id
                FROM events e
                JOIN identities i ON i.id=e.source_identity_id
                LEFT JOIN jobs j ON j.event_id=e.id
                ORDER BY e.received_at DESC LIMIT ?
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "event_type": row["event_type"],
                "occurred_at": row["occurred_at"],
                "received_at": row["received_at"],
                "source_name": row["source_name"],
                "job_id": row["job_id"],
                "payload": redact(json.loads(row["payload_json"])),
            }
            for row in rows
        ]

    def get_event(self, event_id: str) -> dict[str, object] | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT e.id,e.event_type,e.occurred_at,e.received_at,e.payload_json,
                       i.display_name AS source_name,j.id AS job_id
                FROM events e
                JOIN identities i ON i.id=e.source_identity_id
                LEFT JOIN jobs j ON j.event_id=e.id
                WHERE e.id=?
                """,
                (event_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "event_type": row["event_type"],
            "occurred_at": row["occurred_at"],
            "received_at": row["received_at"],
            "source_name": row["source_name"],
            "job_id": row["job_id"],
            "payload": redact(json.loads(row["payload_json"])),
        }

    def status_counts(self) -> dict[str, int]:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT
                  (SELECT count(*) FROM identities) AS identities,
                  (SELECT count(*) FROM identities WHERE status='active') AS active_identities,
                  (SELECT count(*) FROM events) AS events,
                  (SELECT count(*) FROM jobs) AS jobs,
                  (SELECT count(*) FROM reports) AS reports
                """
            ).fetchone()
        return {key: int(row[key]) for key in row.keys()}

    def list_jobs(self, limit: int = 100) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT j.id,j.event_id,j.task_name,j.state,j.created_at,j.updated_at,
                       count(DISTINCT r.id) AS report_count,count(DISTINCT a.id) AS attempt_count
                FROM jobs j LEFT JOIN reports r ON r.job_id=j.id
                LEFT JOIN job_attempts a ON a.job_id=j.id
                GROUP BY j.id ORDER BY j.created_at DESC LIMIT ?
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [dict(row) for row in rows]

    def get_job(self, job_id: str) -> dict[str, object] | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT j.id,j.event_id,j.task_name,j.state,j.task_revision_id,j.input_json,j.created_at,
                       j.updated_at,count(DISTINCT r.id) AS report_count,count(DISTINCT a.id) AS attempt_count
                FROM jobs j LEFT JOIN reports r ON r.job_id=j.id
                LEFT JOIN job_attempts a ON a.job_id=j.id
                WHERE j.id=? GROUP BY j.id
                """,
                (job_id,),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["input"] = redact(json.loads(result.pop("input_json")))
        return result

    def cancel_job(self, job_id: str, correlation_id: str) -> str:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                "SELECT state FROM jobs WHERE id=?", (job_id,)
            ).fetchone()
            if row is None:
                return "not_found"
            if row["state"] != "queued":
                return "not_cancellable"
            updated = connection.execute(
                "UPDATE jobs SET state='cancelled',updated_at=? WHERE id=? AND state='queued'",
                (now, job_id),
            ).rowcount
            if updated != 1:
                return "not_cancellable"
            self._append_audit(
                connection,
                actor_identity_id=None,
                credential_id=None,
                action="jobs.cancel",
                target_type="job",
                target_id=job_id,
                decision="allowed",
                reason_code="ingress_admin",
                correlation_id=correlation_id,
                metadata={"previous_state": "queued"},
            )
        return "cancelled"

    def claim_job(self, identity: AuthenticatedIdentity, correlation_id: str) -> LeaseResult | None:
        self.authorize(identity, "jobs.claim")
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        lease_expires = (now_dt + timedelta(minutes=5)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        max_expires = (now_dt + timedelta(minutes=30)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        token = secrets.token_urlsafe(32)
        verifier = hmac.new(self.pepper, token.encode(), hashlib.sha256).hexdigest()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            expired = connection.execute(
                "SELECT a.id,a.job_id,a.attempt_number,t.max_attempts FROM job_attempts a JOIN jobs j ON j.id=a.job_id JOIN task_revisions t ON t.id=j.task_revision_id WHERE j.state='leased' AND a.finished_at IS NULL AND a.lease_expires_at<=?",
                (now,),
            ).fetchall()
            for attempt in expired:
                next_state = "queued" if attempt["attempt_number"] < attempt["max_attempts"] else "dead_letter"
                connection.execute("UPDATE job_attempts SET finished_at=?,outcome='failed',failure_reason='lease_expired' WHERE id=?", (now, attempt["id"]))
                connection.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=? AND state='leased'", (next_state, now, attempt["job_id"]))
                self._append_audit(connection, actor_identity_id=None, credential_id=None, action="jobs.lease_expire", target_type="job", target_id=attempt["job_id"], decision="recorded", reason_code=next_state, correlation_id=correlation_id, metadata={"attempt": attempt["attempt_number"]})
            active = connection.execute(
                "SELECT count(*) FROM job_attempts WHERE identity_id=? AND finished_at IS NULL AND lease_expires_at>?",
                (identity.identity_id, now),
            ).fetchone()[0]
            if active >= 1:
                return None
            row = connection.execute(
                "SELECT id FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if row is None:
                return None
            job_id = row["id"]
            attempt_number = connection.execute(
                "SELECT count(*)+1 FROM job_attempts WHERE job_id=?", (job_id,)
            ).fetchone()[0]
            attempt_id = str(uuid4())
            connection.execute(
                "INSERT INTO job_attempts(id,job_id,attempt_number,identity_id,lease_verifier,leased_at,lease_expires_at,max_expires_at) VALUES(?,?,?,?,?,?,?,?)",
                (attempt_id, job_id, attempt_number, identity.identity_id, verifier, now, lease_expires, max_expires),
            )
            if connection.execute(
                "UPDATE jobs SET state='leased',updated_at=? WHERE id=? AND state='queued'",
                (now, job_id),
            ).rowcount != 1:
                raise LeaseError("claim_conflict")
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="jobs.claim", target_type="job", target_id=job_id, decision="allowed", reason_code="leased", correlation_id=correlation_id, metadata={"attempt": attempt_number})
        job = self.get_job(job_id)
        assert job is not None
        with connect(self.database_path) as connection:
            task = connection.execute("SELECT objective,input_schema_json,report_schema_json FROM task_revisions WHERE id=?", (job["task_revision_id"],)).fetchone()
            capabilities = connection.execute(
                """SELECT s.namespaced_name,s.connector_id,s.tool_name,t.input_schema_json
                   FROM task_tool_selections s JOIN connector_tools t
                     ON t.connector_id=s.connector_id AND t.name=s.tool_name
                   WHERE s.task_revision_id=? ORDER BY s.namespaced_name""",
                (job["task_revision_id"],),
            ).fetchall()
        job["objective"] = task["objective"]
        job["input_schema"] = json.loads(task["input_schema_json"])
        job["required_report_schema"] = json.loads(task["report_schema_json"])
        job["allowed_capabilities"] = [
            {
                "name": item["namespaced_name"],
                "connector_id": item["connector_id"],
                "tool_name": item["tool_name"],
                "input_schema": json.loads(item["input_schema_json"]),
            }
            for item in capabilities
        ]
        return LeaseResult(job, token, lease_expires)

    def active_capabilities(self, identity: AuthenticatedIdentity) -> list[dict[str, object]]:
        """Return only virtual tools bound to this identity's one active lease."""
        self.authorize(identity, "jobs.claim")
        now = utc_now()
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT s.namespaced_name,t.description,t.input_schema_json,d.display_name AS task_name
                FROM job_attempts a
                JOIN jobs j ON j.id=a.job_id
                JOIN task_revisions r ON r.id=j.task_revision_id
                JOIN task_definitions d ON d.id=r.task_definition_id
                JOIN task_tool_selections s ON s.task_revision_id=r.id
                JOIN connectors c ON c.id=s.connector_id
                JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                WHERE a.identity_id=? AND a.finished_at IS NULL AND a.lease_expires_at>?
                  AND j.state='leased' AND d.enabled=1 AND c.enabled=1 AND c.status='ready'
                  AND t.schema_fingerprint=s.schema_fingerprint
                ORDER BY s.namespaced_name
                """,
                (identity.identity_id, now),
            ).fetchall()
        return [
            {
                "name": row["namespaced_name"],
                "description": f"Capacité autorisée pour la tâche {row['task_name']}. {row['description']}",
                "input_schema": json.loads(row["input_schema_json"]),
            }
            for row in rows
        ]

    def resolve_active_capability(
        self,
        identity: AuthenticatedIdentity,
        virtual_name: str,
        arguments: dict[str, object],
        correlation_id: str,
    ) -> dict[str, object]:
        """Resolve a virtual tool through the caller's current lease, failing closed."""
        self.authorize(identity, "jobs.claim")
        if not isinstance(arguments, dict) or len(canonical_json(arguments).encode()) > 32 * 1024:
            raise ValueError("invalid_capability_arguments")
        now = utc_now()
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT j.id AS job_id,r.id AS task_revision_id,s.connector_id,s.tool_name,
                       s.schema_fingerprint,c.protected_config,t.input_schema_json,
                       c.enabled AS connector_enabled,c.status AS connector_status,
                       t.schema_fingerprint AS current_fingerprint
                FROM job_attempts a
                JOIN jobs j ON j.id=a.job_id
                JOIN task_revisions r ON r.id=j.task_revision_id
                JOIN task_definitions d ON d.id=r.task_definition_id
                JOIN task_tool_selections s ON s.task_revision_id=r.id
                JOIN connectors c ON c.id=s.connector_id
                LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                WHERE a.identity_id=? AND a.finished_at IS NULL AND a.lease_expires_at>?
                  AND j.state='leased' AND d.enabled=1 AND s.namespaced_name=?
                """,
                (identity.identity_id, now, virtual_name),
            ).fetchone()
            if (
                row is None
                or not row["connector_enabled"]
                or row["connector_status"] != "ready"
                or row["current_fingerprint"] != row["schema_fingerprint"]
            ):
                self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="capabilities.invoke", target_type="capability", target_id=virtual_name, decision="denied", reason_code="capability_not_available", correlation_id=correlation_id, metadata={})
                raise AuthorizationError("capability_not_available")
            validate_json_contract(arguments, json.loads(row["input_schema_json"]), "arguments")
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="capabilities.invoke", target_type="capability", target_id=virtual_name, decision="allowed", reason_code="upstream_call_authorized", correlation_id=correlation_id, metadata={"job_id": row["job_id"], "connector_id": row["connector_id"]})
        url, bearer_token = reveal_connector_config(self.pepper, row["protected_config"])
        return {
            "job_id": row["job_id"],
            "connector_id": row["connector_id"],
            "tool_name": row["tool_name"],
            "url": url,
            "bearer_token": bearer_token,
        }

    def record_capability_result(
        self,
        identity: AuthenticatedIdentity,
        virtual_name: str,
        job_id: str,
        connector_id: str,
        succeeded: bool,
        correlation_id: str,
    ) -> None:
        with connect(self.database_path) as connection:
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="capabilities.result", target_type="capability", target_id=virtual_name, decision="recorded", reason_code="upstream_succeeded" if succeeded else "upstream_failed", correlation_id=correlation_id, metadata={"job_id": job_id, "connector_id": connector_id})

    def _leased_attempt(self, connection, identity, job_id: str, lease_token: str):
        row = connection.execute(
            "SELECT * FROM job_attempts WHERE job_id=? AND finished_at IS NULL ORDER BY attempt_number DESC LIMIT 1",
            (job_id,),
        ).fetchone()
        now = utc_now()
        if row is None or row["identity_id"] != identity.identity_id:
            raise LeaseError("lease_not_owned")
        verifier = hmac.new(self.pepper, lease_token.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(verifier, row["lease_verifier"]):
            raise LeaseError("invalid_lease")
        if row["lease_expires_at"] <= now:
            raise LeaseError("lease_expired")
        return row

    def heartbeat_job(self, identity, job_id: str, lease_token: str, correlation_id: str) -> str:
        self.authorize(identity, "jobs.heartbeat")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._leased_attempt(connection, identity, job_id, lease_token)
            proposed = datetime.now(UTC) + timedelta(minutes=5)
            maximum = datetime.fromisoformat(attempt["max_expires_at"].replace("Z", "+00:00"))
            expires = min(proposed, maximum).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            connection.execute("UPDATE job_attempts SET lease_expires_at=? WHERE id=?", (expires, attempt["id"]))
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="jobs.heartbeat", target_type="job", target_id=job_id, decision="allowed", reason_code="lease_extended", correlation_id=correlation_id, metadata={})
        return expires

    def complete_job(self, identity, job_id: str, lease_token: str, completion_key: str, report: dict[str, object], correlation_id: str) -> str:
        self.authorize(identity, "jobs.complete")
        if not completion_key or len(completion_key) > 160 or not isinstance(report, dict) or len(canonical_json(report)) > 32 * 1024:
            raise ValueError("invalid_completion")
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute("SELECT r.id FROM reports r JOIN job_attempts a ON a.job_id=r.job_id WHERE r.job_id=? AND a.completion_key=?", (job_id, completion_key)).fetchone()
            if existing:
                return existing["id"]
            attempt = self._leased_attempt(connection, identity, job_id, lease_token)
            schema_row = connection.execute(
                "SELECT t.report_schema_json FROM jobs j JOIN task_revisions t ON t.id=j.task_revision_id WHERE j.id=?",
                (job_id,),
            ).fetchone()
            if schema_row is None:
                raise ValueError("invalid_completion")
            validate_json_contract(report, json.loads(schema_row["report_schema_json"]))
            schema_version = report.get("schema_version", 1)
            if not isinstance(schema_version, int) or isinstance(schema_version, bool):
                raise ValueError("invalid_completion")
            report_id = str(uuid4())
            connection.execute("INSERT INTO reports(id,job_id,schema_version,report_json,created_at) VALUES(?,?,?,?,?)", (report_id, job_id, schema_version, canonical_json(redact(report)), now))
            connection.execute("UPDATE job_attempts SET finished_at=?,outcome='completed',completion_key=? WHERE id=?", (now, completion_key, attempt["id"]))
            connection.execute("UPDATE jobs SET state='completed',updated_at=? WHERE id=? AND state='leased'", (now, job_id))
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="jobs.complete", target_type="job", target_id=job_id, decision="allowed", reason_code="completed", correlation_id=correlation_id, metadata={"report_id": report_id})
        return report_id

    def fail_job(self, identity, job_id: str, lease_token: str, reason: str, retryable: bool, correlation_id: str) -> str:
        self.authorize(identity, "jobs.fail")
        if not reason.strip() or len(reason) > 500:
            raise ValueError("invalid_failure_reason")
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            attempt = self._leased_attempt(connection, identity, job_id, lease_token)
            connection.execute("UPDATE job_attempts SET finished_at=?,outcome='failed',failure_reason=? WHERE id=?", (now, reason.strip(), attempt["id"]))
            maximum = connection.execute("SELECT t.max_attempts FROM jobs j JOIN task_revisions t ON t.id=j.task_revision_id WHERE j.id=?", (job_id,)).fetchone()[0]
            state = "queued" if retryable and attempt["attempt_number"] < maximum else ("dead_letter" if retryable else "failed")
            connection.execute("UPDATE jobs SET state=?,updated_at=? WHERE id=? AND state='leased'", (state, now, job_id))
            self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="jobs.fail", target_type="job", target_id=job_id, decision="allowed", reason_code=state, correlation_id=correlation_id, metadata={"reason": reason, "retryable": retryable})
        return state

    def list_reports(self, limit: int = 100) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT r.id,r.job_id,r.schema_version,r.report_json,r.created_at,
                       r.supersedes_id,j.task_name
                FROM reports r JOIN jobs j ON j.id=r.job_id
                ORDER BY r.created_at DESC LIMIT ?
                """,
                (min(max(limit, 1), 100),),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "job_id": row["job_id"],
                "schema_version": row["schema_version"],
                "created_at": row["created_at"],
                "supersedes_id": row["supersedes_id"],
                "task_name": row["task_name"],
                "report": redact(json.loads(row["report_json"])),
            }
            for row in rows
        ]

    def get_report(self, report_id: str) -> dict[str, object] | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT r.id,r.job_id,r.schema_version,r.report_json,r.created_at,
                       r.supersedes_id,j.task_name
                FROM reports r JOIN jobs j ON j.id=r.job_id WHERE r.id=?
                """,
                (report_id,),
            ).fetchone()
        if row is None:
            return None
        return {
            "id": row["id"],
            "job_id": row["job_id"],
            "schema_version": row["schema_version"],
            "created_at": row["created_at"],
            "supersedes_id": row["supersedes_id"],
            "task_name": row["task_name"],
            "report": redact(json.loads(row["report_json"])),
        }

    def list_audit_entries(self, limit: int = 200) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT a.sequence,a.id,a.occurred_at,a.action,a.target_type,a.target_id,
                       a.decision,a.reason_code,a.correlation_id,a.metadata_json,
                       a.previous_hash,a.entry_hash,i.display_name AS actor_name
                FROM audit_entries a
                LEFT JOIN identities i ON i.id=a.actor_identity_id
                ORDER BY a.sequence DESC LIMIT ?
                """,
                (min(max(limit, 1), 10_000),),
            ).fetchall()
        return [
            {
                "sequence": row["sequence"],
                "id": row["id"],
                "occurred_at": row["occurred_at"],
                "actor_name": row["actor_name"],
                "action": row["action"],
                "target_type": row["target_type"],
                "target_id": row["target_id"],
                "decision": row["decision"],
                "reason_code": row["reason_code"],
                "correlation_id": row["correlation_id"],
                "metadata": redact(json.loads(row["metadata_json"])),
                "previous_hash": row["previous_hash"],
                "entry_hash": row["entry_hash"],
            }
            for row in rows
        ]

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
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                "SELECT e.id AS event_id,j.id AS job_id FROM events e JOIN jobs j ON j.event_id=e.id WHERE e.source_identity_id=? AND e.idempotency_key=?",
                (identity.identity_id, idempotency_key),
            ).fetchone()
            if existing:
                return IntakeResult(existing["event_id"], existing["job_id"], True)
            task_revision = connection.execute(
                "SELECT r.id FROM task_revisions r JOIN task_definitions d ON d.id=r.task_definition_id WHERE d.name=? AND d.enabled=1 ORDER BY r.revision DESC LIMIT 1",
                (task_name,),
            ).fetchone()
            if task_revision is None:
                raise ValueError("Unknown or disabled requested task")
            dependencies = connection.execute(
                """
                SELECT s.connector_id,s.tool_name,s.schema_fingerprint,c.enabled,c.status,
                       t.schema_fingerprint AS current_fingerprint
                FROM task_tool_selections s JOIN connectors c ON c.id=s.connector_id
                LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                WHERE s.task_revision_id=?
                """,
                (task_revision["id"],),
            ).fetchall()
            if not dependencies or any(
                not item["enabled"]
                or item["status"] != "ready"
                or item["current_fingerprint"] != item["schema_fingerprint"]
                for item in dependencies
            ):
                raise ValueError("Requested task is unavailable")
            window_started_at = now[:16] + ":00.000Z"
            rate = connection.execute(
                "SELECT window_started_at,request_count FROM intake_rate_windows WHERE identity_id=?",
                (identity.identity_id,),
            ).fetchone()
            if rate is None or rate["window_started_at"] != window_started_at:
                connection.execute(
                    "INSERT INTO intake_rate_windows(identity_id,window_started_at,request_count) VALUES(?,?,1) ON CONFLICT(identity_id) DO UPDATE SET window_started_at=excluded.window_started_at,request_count=1",
                    (identity.identity_id, window_started_at),
                )
            elif rate["request_count"] >= self.intake_rate_limit_per_minute:
                raise RateLimitExceeded("rate_limited")
            else:
                connection.execute(
                    "UPDATE intake_rate_windows SET request_count=request_count+1 WHERE identity_id=?",
                    (identity.identity_id,),
                )
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
                "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, event_id, task_name, "queued", identity.policy_revision_id, task_revision["id"], payload, now, now),
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
