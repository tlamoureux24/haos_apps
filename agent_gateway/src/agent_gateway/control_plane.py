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
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

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
    job_id: str | None
    duplicate: bool
    outcome: str


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


class TaskExecutionActiveError(RuntimeError):
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
                SELECT c.id,c.display_name,c.transport,c.display_endpoint,c.status,c.enabled,c.archived_at,
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
                SELECT d.id,d.name,d.display_name,d.enabled,d.archived_at,d.created_at,r.id AS revision_id,
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
                status = "archived" if row["archived_at"] else ("disabled" if not row["enabled"] else ("ready" if selections and not failures else "unavailable"))
                active_job_count = connection.execute(
                    """SELECT count(*) FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                       WHERE r.task_definition_id=? AND j.state IN ('queued','leased')""",
                    (row["id"],),
                ).fetchone()[0]
                tasks.append(
                    {
                        **dict(row),
                        "enabled": bool(row["enabled"]),
                        "status": status,
                        "active_job_count": active_job_count,
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
            updated = connection.execute("UPDATE task_definitions SET enabled=? WHERE id=? AND archived_at IS NULL", (int(enabled), task_id)).rowcount
            if not updated:
                return False
            if not enabled:
                connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id IN (SELECT id FROM event_mappings WHERE task_definition_id=?)", (task_id,))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.enable" if enabled else "tasks.disable", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def set_task_archived(self, task_id: str, archived: bool, correlation_id: str) -> bool:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT archived_at FROM task_definitions WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return False
            active = connection.execute(
                """SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                   WHERE r.task_definition_id=? AND j.state IN ('queued','leased') LIMIT 1""", (task_id,)
            ).fetchone()
            if archived and active:
                raise ValueError("task_execution_active")
            connection.execute("UPDATE task_definitions SET enabled=0,archived_at=? WHERE id=?", (now if archived else None, task_id))
            if archived:
                connection.execute("UPDATE schedules SET enabled=0,updated_at=? WHERE task_definition_id=?", (now, task_id))
                connection.execute("UPDATE event_mappings SET enabled=0,updated_at=? WHERE task_definition_id=?", (now, task_id))
                connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id IN (SELECT id FROM event_mappings WHERE task_definition_id=?)", (task_id,))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.archive" if archived else "tasks.restore", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def delete_task(self, task_id: str, correlation_id: str) -> str:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT id FROM task_definitions WHERE id=?", (task_id,)).fetchone()
            if row is None:
                return "not_found"
            used = connection.execute("SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id WHERE r.task_definition_id=? LIMIT 1", (task_id,)).fetchone()
            scheduled = connection.execute("SELECT 1 FROM schedules WHERE task_definition_id=? LIMIT 1", (task_id,)).fetchone()
            mapped = connection.execute("SELECT 1 FROM event_mappings WHERE task_definition_id=? LIMIT 1", (task_id,)).fetchone()
            if used is not None or scheduled is not None or mapped is not None:
                return "in_use"
            revision_ids = [item[0] for item in connection.execute("SELECT id FROM task_revisions WHERE task_definition_id=?", (task_id,)).fetchall()]
            for revision_id in revision_ids:
                connection.execute("DELETE FROM task_tool_selections WHERE task_revision_id=?", (revision_id,))
            connection.execute("DELETE FROM task_revisions WHERE task_definition_id=?", (task_id,))
            connection.execute("DELETE FROM task_definitions WHERE id=?", (task_id,))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="tasks.delete", target_type="task", target_id=task_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return "deleted"

    def enqueue_manual_task(
        self,
        task_id: str,
        task_input: dict[str, object],
        correlation_id: str,
        reason_code: str = "ingress_manual",
    ) -> str:
        if not isinstance(task_input, dict) or len(canonical_json(task_input).encode()) > 32 * 1024:
            raise ValueError("invalid_task_input")
        now = utc_now()
        job_id = str(uuid4())
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            task = connection.execute(
                """SELECT d.name,r.id AS revision_id,r.input_schema_json
                   FROM task_definitions d JOIN task_revisions r ON r.task_definition_id=d.id
                   WHERE d.id=? AND d.enabled=1
                     AND r.revision=(SELECT max(r2.revision) FROM task_revisions r2 WHERE r2.task_definition_id=d.id)""",
                (task_id,),
            ).fetchone()
            if task is None:
                raise ValueError("task_not_ready")
            if connection.execute(
                """SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                   WHERE r.task_definition_id=? AND j.state IN ('queued','leased') LIMIT 1""",
                (task_id,),
            ).fetchone() is not None:
                raise TaskExecutionActiveError("task_execution_active")
            dependencies = connection.execute(
                """SELECT s.schema_fingerprint,c.enabled,c.status,t.schema_fingerprint AS current_fingerprint
                   FROM task_tool_selections s JOIN connectors c ON c.id=s.connector_id
                   LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                   WHERE s.task_revision_id=?""",
                (task["revision_id"],),
            ).fetchall()
            if not dependencies or any(
                not item["enabled"]
                or item["status"] != "ready"
                or item["current_fingerprint"] != item["schema_fingerprint"]
                for item in dependencies
            ):
                raise ValueError("task_not_ready")
            validate_json_contract(task_input, json.loads(task["input_schema_json"]), "input")
            queued = connection.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','leased')").fetchone()[0]
            if queued >= self.queue_limit:
                raise QueueFullError("queue_full")
            policy_id = "system-ingress-admin-policy"
            policy_revision_id = "system-ingress-admin-policy-v1"
            connection.execute(
                "INSERT OR IGNORE INTO policy_documents(id,name,created_at) VALUES(?,?,?)",
                (policy_id, "system.ingress_admin", now),
            )
            connection.execute(
                "INSERT OR IGNORE INTO policy_revisions(id,policy_id,schema_version,document_json,created_at) VALUES(?,?,?,?,?)",
                (policy_revision_id, policy_id, 1, canonical_json({"allow": {"gateway_actions": [], "capabilities": []}, "deny": {"gateway_actions": [], "capabilities": []}}), now),
            )
            connection.execute(
                "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES(?,NULL,?,?,?,?,?,?,?)",
                (job_id, task["name"], "queued", policy_revision_id, task["revision_id"], canonical_json(redact(task_input)), now, now),
            )
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="jobs.create", target_type="job", target_id=job_id, decision="allowed", reason_code=reason_code, correlation_id=correlation_id, metadata={"task_id": task_id})
        return job_id

    def list_schedules(self) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """SELECT s.*,d.display_name AS task_display_name,d.enabled AS task_enabled
                   FROM schedules s JOIN task_definitions d ON d.id=s.task_definition_id
                   ORDER BY s.display_name COLLATE NOCASE"""
            ).fetchall()
        task_states = {item["id"]: item["status"] for item in self.list_tasks()}
        return [
            {
                **dict(row),
                "enabled": bool(row["enabled"]),
                "task_enabled": bool(row["task_enabled"]),
                "status": "paused" if not row["enabled"] else ("active" if task_states.get(row["task_definition_id"]) == "ready" else "suspended"),
            }
            for row in rows
        ]

    @staticmethod
    def _next_schedule_run(schedule_kind: str, interval_minutes: int, time_of_day: str | None, weekday: int | None, timezone: str | None, after: datetime | None = None) -> str:
        if schedule_kind not in {"interval", "daily", "weekly"} or not 1 <= interval_minutes <= 10080:
            raise ValueError("invalid_schedule")
        if schedule_kind == "interval" and any(value is not None for value in (time_of_day, weekday, timezone)):
            raise ValueError("invalid_schedule")
        if schedule_kind in {"daily", "weekly"} and (time_of_day is None or timezone is None):
            raise ValueError("invalid_schedule")
        if schedule_kind == "daily" and weekday is not None:
            raise ValueError("invalid_schedule")
        if schedule_kind == "weekly" and (weekday is None or not 0 <= weekday <= 6):
            raise ValueError("invalid_schedule")
        reference = after or datetime.now(UTC)
        if schedule_kind == "interval":
            candidate = reference + timedelta(minutes=interval_minutes)
        else:
            try:
                zone = ZoneInfo(timezone or "")
            except ZoneInfoNotFoundError as exc:
                raise ValueError("invalid_timezone") from exc
            hour, minute = (int(part) for part in (time_of_day or "").split(":"))
            local_now = reference.astimezone(zone)
            candidate = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
            if schedule_kind == "daily":
                if candidate <= local_now:
                    candidate += timedelta(days=1)
            else:
                days = ((weekday or 0) - local_now.weekday()) % 7
                candidate += timedelta(days=days)
                if candidate <= local_now:
                    candidate += timedelta(days=7)
            candidate = candidate.astimezone(UTC)
        return candidate.isoformat(timespec="milliseconds").replace("+00:00", "Z")

    def create_schedule(self, display_name: str, task_id: str, schedule_kind: str, interval_minutes: int, time_of_day: str | None, weekday: int | None, timezone: str | None, correlation_id: str) -> str:
        if not display_name.strip():
            raise ValueError("invalid_schedule")
        schedule_id, now = str(uuid4()), datetime.now(UTC)
        next_run = self._next_schedule_run(schedule_kind, interval_minutes, time_of_day, weekday, timezone, now)
        timestamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            task = connection.execute(
                """SELECT d.id,d.enabled,r.id AS revision_id FROM task_definitions d
                   JOIN task_revisions r ON r.task_definition_id=d.id WHERE d.id=?
                   AND r.revision=(SELECT max(r2.revision) FROM task_revisions r2 WHERE r2.task_definition_id=d.id)""",
                (task_id,),
            ).fetchone()
            if task is None or not task["enabled"]:
                raise ValueError("task_not_ready")
            dependencies = connection.execute(
                """SELECT s.schema_fingerprint,c.enabled,c.status,t.schema_fingerprint AS current_fingerprint
                   FROM task_tool_selections s JOIN connectors c ON c.id=s.connector_id
                   LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                   WHERE s.task_revision_id=?""",
                (task["revision_id"],),
            ).fetchall()
            if not dependencies or any(not item["enabled"] or item["status"] != "ready" or item["current_fingerprint"] != item["schema_fingerprint"] for item in dependencies):
                raise ValueError("task_not_ready")
            connection.execute(
                "INSERT INTO schedules(id,display_name,task_definition_id,interval_minutes,schedule_kind,time_of_day,weekday,timezone,enabled,next_run_at,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,1,?,?,?)",
                (schedule_id, display_name.strip(), task_id, interval_minutes, schedule_kind, time_of_day, weekday, timezone, next_run, timestamp, timestamp),
            )
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="schedules.create", target_type="schedule", target_id=schedule_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"task_id": task_id, "interval_minutes": interval_minutes})
        return schedule_id

    def update_schedule(self, schedule_id: str, display_name: str, task_id: str, schedule_kind: str, interval_minutes: int, time_of_day: str | None, weekday: int | None, timezone: str | None, correlation_id: str) -> bool:
        if not display_name.strip():
            raise ValueError("invalid_schedule")
        now_dt, now = datetime.now(UTC), utc_now()
        next_run = self._next_schedule_run(schedule_kind, interval_minutes, time_of_day, weekday, timezone, now_dt)
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM schedules WHERE id=?", (schedule_id,)).fetchone() is None:
                return False
            task = next((item for item in self.list_tasks() if item["id"] == task_id), None)
            if task is None or task["status"] != "ready":
                raise ValueError("task_not_ready")
            connection.execute("UPDATE schedules SET display_name=?,task_definition_id=?,interval_minutes=?,schedule_kind=?,time_of_day=?,weekday=?,timezone=?,next_run_at=?,last_outcome=NULL,updated_at=? WHERE id=?", (display_name.strip(), task_id, interval_minutes, schedule_kind, time_of_day, weekday, timezone, next_run, now, schedule_id))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="schedules.update", target_type="schedule", target_id=schedule_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"task_id": task_id, "schedule_kind": schedule_kind})
        return True

    def set_schedule_enabled(self, schedule_id: str, enabled: bool, correlation_id: str) -> bool:
        now_dt = datetime.now(UTC)
        now = now_dt.isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT interval_minutes,schedule_kind,time_of_day,weekday,timezone FROM schedules WHERE id=?", (schedule_id,)).fetchone()
            if row is None:
                return False
            next_run = self._next_schedule_run(row["schedule_kind"], row["interval_minutes"], row["time_of_day"], row["weekday"], row["timezone"], now_dt)
            connection.execute("UPDATE schedules SET enabled=?,next_run_at=?,updated_at=? WHERE id=?", (int(enabled), next_run, now, schedule_id))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="schedules.enable" if enabled else "schedules.disable", target_type="schedule", target_id=schedule_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def delete_schedule(self, schedule_id: str, correlation_id: str) -> bool:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("DELETE FROM schedules WHERE id=?", (schedule_id,)).rowcount != 1:
                return False
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="schedules.delete", target_type="schedule", target_id=schedule_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def run_due_schedules(self) -> int:
        now = utc_now()
        with connect(self.database_path) as connection:
            due = connection.execute("SELECT id,task_definition_id,interval_minutes,schedule_kind,time_of_day,weekday,timezone FROM schedules WHERE enabled=1 AND next_run_at<=? ORDER BY next_run_at,id LIMIT 100", (now,)).fetchall()
        for schedule in due:
            outcome = "queued"
            try:
                self.enqueue_manual_task(schedule["task_definition_id"], {}, f"schedule:{schedule['id']}:{now}", "internal_schedule")
            except TaskExecutionActiveError:
                outcome = "skipped_active"
            except QueueFullError:
                outcome = "queue_full"
            except ValueError:
                outcome = "task_unavailable"
            next_run = self._next_schedule_run(schedule["schedule_kind"], schedule["interval_minutes"], schedule["time_of_day"], schedule["weekday"], schedule["timezone"])
            with connect(self.database_path) as connection:
                connection.execute("UPDATE schedules SET next_run_at=?,last_run_at=?,last_outcome=?,updated_at=? WHERE id=?", (next_run, now, outcome, now, schedule["id"]))
        return len(due)

    def run_due_event_triggers(self) -> int:
        """Promote durable grace windows to jobs when their conditions still hold."""
        now = utc_now()
        with connect(self.database_path) as connection:
            due_ids = [row["mapping_id"] for row in connection.execute(
                "SELECT mapping_id FROM pending_event_triggers WHERE due_at<=? ORDER BY due_at,mapping_id LIMIT 100", (now,)
            ).fetchall()]
        promoted = 0
        for mapping_id in due_ids:
            with connect(self.database_path) as connection:
                connection.execute("BEGIN IMMEDIATE")
                pending = connection.execute(
                    """SELECT p.*,m.enabled,m.cooldown_minutes,m.last_triggered_at,d.id AS task_definition_id,
                              d.name AS task_name,d.enabled AS task_enabled
                       FROM pending_event_triggers p JOIN event_mappings m ON m.id=p.mapping_id
                       JOIN task_revisions r ON r.id=p.task_revision_id
                       JOIN task_definitions d ON d.id=r.task_definition_id
                       WHERE p.mapping_id=? AND p.due_at<=?""", (mapping_id, now)
                ).fetchone()
                if pending is None:
                    continue
                dependencies = connection.execute(
                    """SELECT s.schema_fingerprint,c.enabled,c.status,t.schema_fingerprint AS current_fingerprint
                       FROM task_tool_selections s JOIN connectors c ON c.id=s.connector_id
                       LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                       WHERE s.task_revision_id=?""", (pending["task_revision_id"],)
                ).fetchall()
                ready = pending["enabled"] and pending["task_enabled"] and dependencies and not any(
                    not item["enabled"] or item["status"] != "ready" or item["current_fingerprint"] != item["schema_fingerprint"]
                    for item in dependencies
                )
                active = connection.execute(
                    """SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                       WHERE r.task_definition_id=? AND j.state IN ('queued','leased') LIMIT 1""",
                    (pending["task_definition_id"],),
                ).fetchone()
                cooldown_cutoff = (datetime.now(UTC) - timedelta(minutes=pending["cooldown_minutes"])).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                cooling = pending["cooldown_minutes"] and pending["last_triggered_at"] and pending["last_triggered_at"] > cooldown_cutoff
                queued = connection.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','leased')").fetchone()[0]
                if not ready or active or cooling or queued >= self.queue_limit:
                    continue
                job_id = str(uuid4())
                connection.execute(
                    "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES(?,?,?,'queued',?,?,?,?,?)",
                    (job_id, pending["event_id"], pending["task_name"], pending["policy_revision_id"], pending["task_revision_id"], pending["input_json"], now, now),
                )
                connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id=?", (mapping_id,))
                connection.execute("UPDATE event_mappings SET last_triggered_at=?,updated_at=? WHERE id=?", (now, now, mapping_id))
                self._append_audit(connection, actor_identity_id=None, credential_id=None, action="events.grace_expire", target_type="event", target_id=pending["event_id"], decision="allowed", reason_code="accepted_after_grace", correlation_id=f"grace:{mapping_id}:{now}", metadata={"job_id": job_id, "mapping_id": mapping_id})
                promoted += 1
        return promoted

    def list_event_mappings(self) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """SELECT m.*,p.due_at AS pending_due_at,i.display_name AS source_name,i.status AS source_status,
                          d.display_name AS task_display_name,d.enabled AS task_enabled
                   FROM event_mappings m JOIN identities i ON i.id=m.source_identity_id
                   JOIN task_definitions d ON d.id=m.task_definition_id
                   LEFT JOIN pending_event_triggers p ON p.mapping_id=m.id
                   ORDER BY m.display_name COLLATE NOCASE"""
            ).fetchall()
        task_states = {item["id"]: item["status"] for item in self.list_tasks()}
        return [{**dict(row), "enabled": bool(row["enabled"]), "status": "paused" if not row["enabled"] else ("active" if row["source_status"] == "active" and task_states.get(row["task_definition_id"]) == "ready" else "suspended")} for row in rows]

    def create_event_mapping(self, display_name: str, source_identity_id: str, event_type: str, task_id: str, cooldown_minutes: int, grace_minutes: int, recovery_event_type: str | None, input_mode: str, correlation_id: str) -> str:
        mapping_id, now = str(uuid4()), utc_now()
        recovery_event_type = recovery_event_type or None
        if (not display_name.strip() or not 0 <= cooldown_minutes <= 10080
                or not 0 <= grace_minutes <= 1440 or input_mode not in {"full_event", "subject", "attributes"}
                or (grace_minutes == 0 and recovery_event_type is not None)
                or (grace_minutes > 0 and (recovery_event_type is None or recovery_event_type == event_type))):
            raise ValueError("invalid_event_mapping")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            source = connection.execute("SELECT identity_type,status FROM identities WHERE id=?", (source_identity_id,)).fetchone()
            if source is None or source["identity_type"] != "event_source" or source["status"] != "active":
                raise ValueError("invalid_event_source")
            task = next((item for item in self.list_tasks() if item["id"] == task_id), None)
            if task is None or task["status"] != "ready":
                raise ValueError("task_not_ready")
            collision = connection.execute("SELECT 1 FROM event_mappings WHERE source_identity_id=? AND (event_type IN (?,?) OR recovery_event_type IN (?,?)) LIMIT 1", (source_identity_id, event_type, recovery_event_type, event_type, recovery_event_type)).fetchone()
            if collision:
                raise ValueError("event_type_conflict")
            connection.execute("INSERT INTO event_mappings(id,display_name,source_identity_id,event_type,task_definition_id,enabled,cooldown_minutes,grace_minutes,recovery_event_type,input_mode,created_at,updated_at) VALUES(?,?,?,?,?,1,?,?,?,?,?,?)", (mapping_id, display_name.strip(), source_identity_id, event_type, task_id, cooldown_minutes, grace_minutes, recovery_event_type, input_mode, now, now))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="event_mappings.create", target_type="event_mapping", target_id=mapping_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"source_identity_id": source_identity_id, "event_type": event_type, "recovery_event_type": recovery_event_type, "task_id": task_id, "cooldown_minutes": cooldown_minutes, "grace_minutes": grace_minutes, "input_mode": input_mode})
        return mapping_id

    def update_event_mapping(self, mapping_id: str, display_name: str, source_identity_id: str, event_type: str, task_id: str, cooldown_minutes: int, grace_minutes: int, recovery_event_type: str | None, input_mode: str, correlation_id: str) -> bool:
        recovery_event_type = recovery_event_type or None
        if (not display_name.strip() or not 0 <= cooldown_minutes <= 10080
                or not 0 <= grace_minutes <= 1440 or input_mode not in {"full_event", "subject", "attributes"}
                or (grace_minutes == 0 and recovery_event_type is not None)
                or (grace_minutes > 0 and (recovery_event_type is None or recovery_event_type == event_type))):
            raise ValueError("invalid_event_mapping")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM event_mappings WHERE id=?", (mapping_id,)).fetchone() is None:
                return False
            source = connection.execute("SELECT identity_type,status FROM identities WHERE id=?", (source_identity_id,)).fetchone()
            task = next((item for item in self.list_tasks() if item["id"] == task_id), None)
            if source is None or source["identity_type"] != "event_source" or source["status"] != "active" or task is None or task["status"] != "ready":
                raise ValueError("dependency_not_ready")
            collision = connection.execute("SELECT 1 FROM event_mappings WHERE id<>? AND source_identity_id=? AND (event_type IN (?,?) OR recovery_event_type IN (?,?)) LIMIT 1", (mapping_id, source_identity_id, event_type, recovery_event_type, event_type, recovery_event_type)).fetchone()
            if collision:
                raise ValueError("event_type_conflict")
            connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id=?", (mapping_id,))
            now = utc_now()
            connection.execute("UPDATE event_mappings SET display_name=?,source_identity_id=?,event_type=?,task_definition_id=?,cooldown_minutes=?,grace_minutes=?,recovery_event_type=?,input_mode=?,last_triggered_at=NULL,updated_at=? WHERE id=?", (display_name.strip(), source_identity_id, event_type, task_id, cooldown_minutes, grace_minutes, recovery_event_type, input_mode, now, mapping_id))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="event_mappings.update", target_type="event_mapping", target_id=mapping_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"source_identity_id": source_identity_id, "event_type": event_type, "recovery_event_type": recovery_event_type, "task_id": task_id})
        return True

    def set_event_mapping_enabled(self, mapping_id: str, enabled: bool, correlation_id: str) -> bool:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("UPDATE event_mappings SET enabled=?,updated_at=? WHERE id=?", (int(enabled), utc_now(), mapping_id)).rowcount != 1:
                return False
            if not enabled:
                connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id=?", (mapping_id,))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="event_mappings.enable" if enabled else "event_mappings.disable", target_type="event_mapping", target_id=mapping_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def delete_event_mapping(self, mapping_id: str, correlation_id: str) -> bool:
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("DELETE FROM event_mappings WHERE id=?", (mapping_id,)).rowcount != 1:
                return False
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="event_mappings.delete", target_type="event_mapping", target_id=mapping_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

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
            updated = connection.execute("UPDATE connectors SET enabled=?,status=?,updated_at=? WHERE id=? AND archived_at IS NULL", (int(enabled), "ready" if enabled else "disabled", now, connector_id)).rowcount
            if not updated:
                return False
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.enable" if enabled else "connectors.disable", target_type="connector", target_id=connector_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
        return True

    def set_connector_archived(self, connector_id: str, archived: bool, correlation_id: str) -> bool:
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            if connection.execute("SELECT 1 FROM connectors WHERE id=?", (connector_id,)).fetchone() is None:
                return False
            active = connection.execute(
                """SELECT 1 FROM jobs j JOIN task_tool_selections s ON s.task_revision_id=j.task_revision_id
                   WHERE s.connector_id=? AND j.state IN ('queued','leased') LIMIT 1""",
                (connector_id,),
            ).fetchone()
            if archived and active:
                raise ValueError("connector_execution_active")
            connection.execute("UPDATE connectors SET enabled=0,status='disabled',archived_at=?,updated_at=? WHERE id=?", (now if archived else None, now, connector_id))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="connectors.archive" if archived else "connectors.restore", target_type="connector", target_id=connector_id, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={})
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
                connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id IN (SELECT id FROM event_mappings WHERE source_identity_id=?)", (identity_id,))
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
                       i.display_name AS source_name,j.id AS job_id,
                       (SELECT a.reason_code FROM audit_entries a WHERE a.target_type='event' AND a.target_id=e.id ORDER BY a.sequence DESC LIMIT 1) AS outcome
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
                "outcome": row["outcome"],
                "payload": redact(json.loads(row["payload_json"])),
            }
            for row in rows
        ]

    def get_event(self, event_id: str) -> dict[str, object] | None:
        with connect(self.database_path) as connection:
            row = connection.execute(
                """
                SELECT e.id,e.event_type,e.occurred_at,e.received_at,e.payload_json,
                       i.display_name AS source_name,j.id AS job_id,
                       (SELECT a.reason_code FROM audit_entries a WHERE a.target_type='event' AND a.target_id=e.id ORDER BY a.sequence DESC LIMIT 1) AS outcome
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
            "outcome": row["outcome"],
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
                  (SELECT count(*) FROM jobs WHERE state='queued') AS queued_jobs,
                  (SELECT count(*) FROM jobs WHERE state='leased') AS running_jobs,
                  (SELECT count(*) FROM jobs WHERE state='dead_letter') AS dead_letter_jobs,
                  (SELECT count(*) FROM reports) AS reports,
                  (SELECT count(*) FROM events WHERE received_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-24 hours')) AS events_24h,
                  (SELECT count(*) FROM jobs WHERE state='completed' AND updated_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-24 hours')) AS completed_jobs_24h,
                  (SELECT count(*) FROM jobs WHERE state IN ('failed','dead_letter') AND updated_at >= strftime('%Y-%m-%dT%H:%M:%fZ','now','-24 hours')) AS failed_jobs_24h
                """
            ).fetchone()
        return {key: int(row[key]) for key in row.keys()}

    def list_jobs(self, limit: int = 100) -> list[dict[str, object]]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """
                SELECT j.id,j.event_id,j.task_name,j.state,j.created_at,j.updated_at,
                       count(DISTINCT r.id) AS report_count,count(DISTINCT a.id) AS attempt_count,
                       (SELECT a2.outcome FROM job_attempts a2 WHERE a2.job_id=j.id ORDER BY a2.attempt_number DESC LIMIT 1) AS last_attempt_outcome,
                       (SELECT a2.failure_reason FROM job_attempts a2 WHERE a2.job_id=j.id ORDER BY a2.attempt_number DESC LIMIT 1) AS last_failure_reason
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

    def requeue_dead_letter(self, job_id: str, correlation_id: str) -> tuple[str, str | None]:
        """Create a fresh job from a dead letter without rewriting its history."""
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            job = connection.execute(
                """SELECT j.state,j.event_id,j.task_name,j.policy_revision_id,j.task_revision_id,j.input_json,
                          d.id AS task_definition_id,d.enabled
                   FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                   JOIN task_definitions d ON d.id=r.task_definition_id
                   WHERE j.id=?""",
                (job_id,),
            ).fetchone()
            if job is None:
                return "not_found", None
            if job["state"] != "dead_letter":
                return "not_requeueable", None
            dependencies = connection.execute(
                """SELECT s.schema_fingerprint,c.enabled,c.status,t.schema_fingerprint AS current_fingerprint
                   FROM task_tool_selections s JOIN connectors c ON c.id=s.connector_id
                   LEFT JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                   WHERE s.task_revision_id=?""",
                (job["task_revision_id"],),
            ).fetchall()
            if not job["enabled"] or not dependencies or any(
                not item["enabled"]
                or item["status"] != "ready"
                or item["current_fingerprint"] != item["schema_fingerprint"]
                for item in dependencies
            ):
                return "task_unavailable", None
            if connection.execute(
                """SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                   WHERE r.task_definition_id=? AND j.state IN ('queued','leased') LIMIT 1""",
                (job["task_definition_id"],),
            ).fetchone():
                return "task_execution_active", None
            queued = connection.execute(
                "SELECT count(*) FROM jobs WHERE state IN ('queued','leased')"
            ).fetchone()[0]
            if queued >= self.queue_limit:
                return "queue_full", None
            new_job_id = str(uuid4())
            connection.execute(
                """INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at)
                   VALUES(?,?,?,'queued',?,?,?,?,?)""",
                (new_job_id, None, job["task_name"], job["policy_revision_id"], job["task_revision_id"], job["input_json"], now, now),
            )
            self._append_audit(
                connection,
                actor_identity_id=None,
                credential_id=None,
                action="jobs.requeue",
                target_type="job",
                target_id=job_id,
                decision="allowed",
                reason_code="ingress_admin",
                correlation_id=correlation_id,
                metadata={"new_job_id": new_job_id, "original_event_id": job["event_id"]},
            )
        return "queued", new_job_id

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
                """SELECT s.namespaced_name,t.input_schema_json
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

    def next_queued_capabilities(self, identity: AuthenticatedIdentity) -> list[dict[str, object]]:
        """Advertise only the tools of the exact next claimable job.

        Invocation still requires an identity-owned active lease.  Advertising
        before the claim accommodates MCP clients that keep a fixed tool
        registry for the lifetime of one reasoning turn.
        """
        self.authorize(identity, "jobs.claim")
        with connect(self.database_path) as connection:
            job = connection.execute(
                "SELECT task_revision_id FROM jobs WHERE state='queued' ORDER BY created_at,id LIMIT 1"
            ).fetchone()
            if job is None:
                return []
            rows = connection.execute(
                """
                SELECT s.namespaced_name,t.description,t.input_schema_json,d.display_name AS task_name
                FROM task_revisions r
                JOIN task_definitions d ON d.id=r.task_definition_id
                JOIN task_tool_selections s ON s.task_revision_id=r.id
                JOIN connectors c ON c.id=s.connector_id
                JOIN connector_tools t ON t.connector_id=s.connector_id AND t.name=s.tool_name
                WHERE r.id=? AND d.enabled=1 AND c.enabled=1 AND c.status='ready'
                  AND t.schema_fingerprint=s.schema_fingerprint
                ORDER BY s.namespaced_name
                """,
                (job["task_revision_id"],),
            ).fetchall()
        return [
            {
                "name": row["namespaced_name"],
                "description": f"Capacité de la prochaine tâche {row['task_name']}; réclamez d'abord son exécution. {row['description']}",
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

    def verify_audit_chain(self) -> dict[str, object]:
        with connect(self.database_path) as connection:
            rows = connection.execute(
                """SELECT sequence,id,occurred_at,actor_identity_id,credential_id,action,
                          target_type,target_id,decision,reason_code,correlation_id,
                          metadata_json,previous_hash,entry_hash
                   FROM audit_entries ORDER BY sequence"""
            ).fetchall()
        expected_previous = GENESIS_HASH
        for row in rows:
            material = canonical_json({
                "id": row["id"], "occurred_at": row["occurred_at"],
                "actor_identity_id": row["actor_identity_id"], "credential_id": row["credential_id"],
                "action": row["action"], "target_type": row["target_type"], "target_id": row["target_id"],
                "decision": row["decision"], "reason_code": row["reason_code"],
                "correlation_id": row["correlation_id"], "metadata_json": row["metadata_json"],
                "previous_hash": row["previous_hash"],
            })
            expected_hash = hmac.new(self.pepper, material.encode("utf-8"), hashlib.sha256).hexdigest()
            if row["previous_hash"] != expected_previous or not hmac.compare_digest(row["entry_hash"], expected_hash):
                return {"valid": False, "entries": len(rows), "failed_sequence": row["sequence"]}
            expected_previous = row["entry_hash"]
        return {"valid": True, "entries": len(rows), "failed_sequence": None}

    def retention_status(self) -> dict[str, object]:
        with connect(self.database_path) as connection:
            values = {row["key"]: row["value"] for row in connection.execute(
                "SELECT key,value FROM gateway_metadata WHERE key IN ('retention_days','retention_batch_size','retention_automatic','retention_last_run_at')"
            ).fetchall()}
        retention_days = int(values.get("retention_days", "90"))
        batch_size = int(values.get("retention_batch_size", "250"))
        automatic = values.get("retention_automatic", "0") == "1"
        preview = self._retention_preview(retention_days, batch_size)
        return {"retention_days": retention_days, "batch_size": batch_size, "automatic": automatic,
                "last_run_at": values.get("retention_last_run_at"), "preview": preview,
                "audit": self.verify_audit_chain()}

    def _retention_preview(self, retention_days: int, batch_size: int) -> dict[str, int]:
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        with connect(self.database_path) as connection:
            job_ids = [row["id"] for row in connection.execute(
                "SELECT id FROM jobs WHERE state IN ('completed','failed','cancelled','dead_letter') AND updated_at<? ORDER BY updated_at,id LIMIT ?",
                (cutoff, batch_size),
            ).fetchall()]
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                reports = connection.execute(f"SELECT count(*) FROM reports WHERE job_id IN ({placeholders})", job_ids).fetchone()[0]
                attempts = connection.execute(f"SELECT count(*) FROM job_attempts WHERE job_id IN ({placeholders})", job_ids).fetchone()[0]
                events = connection.execute(
                    f"""SELECT count(*) FROM events e WHERE e.received_at<?
                       AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.event_id=e.id AND j.id NOT IN ({placeholders}))
                       AND NOT EXISTS(SELECT 1 FROM pending_event_triggers p WHERE p.event_id=e.id)""",
                    (cutoff, *job_ids),
                ).fetchone()[0]
            else:
                reports = attempts = 0
                events = connection.execute(
                    """SELECT count(*) FROM events e WHERE e.received_at<?
                       AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.event_id=e.id)
                       AND NOT EXISTS(SELECT 1 FROM pending_event_triggers p WHERE p.event_id=e.id)""", (cutoff,)
                ).fetchone()[0]
        return {"jobs": len(job_ids), "reports": reports, "attempts": attempts, "orphan_events": min(events, batch_size)}

    def set_retention_policy(self, retention_days: int, batch_size: int, automatic: bool, correlation_id: str) -> None:
        if not 7 <= retention_days <= 3650 or not 10 <= batch_size <= 1000:
            raise ValueError("invalid_retention_policy")
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            for key, value in (("retention_days", str(retention_days)), ("retention_batch_size", str(batch_size)), ("retention_automatic", "1" if automatic else "0")):
                connection.execute("INSERT INTO gateway_metadata(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (key, value))
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="maintenance.retention_update", target_type="retention_policy", target_id=None, decision="allowed", reason_code="ingress_admin", correlation_id=correlation_id, metadata={"retention_days": retention_days, "batch_size": batch_size, "automatic": automatic})

    def run_retention(self, correlation_id: str, automatic: bool = False) -> dict[str, int]:
        with connect(self.database_path) as connection:
            values = {row["key"]: row["value"] for row in connection.execute(
                "SELECT key,value FROM gateway_metadata WHERE key IN ('retention_days','retention_batch_size','retention_automatic','retention_last_run_at')"
            ).fetchall()}
        retention_days = int(values.get("retention_days", "90"))
        batch_size = int(values.get("retention_batch_size", "250"))
        if automatic and values.get("retention_automatic", "0") != "1":
            return {"jobs": 0, "reports": 0, "attempts": 0, "orphan_events": 0}
        if automatic and values.get("retention_last_run_at"):
            last = datetime.fromisoformat(values["retention_last_run_at"].replace("Z", "+00:00"))
            if datetime.now(UTC) - last < timedelta(hours=24):
                return {"jobs": 0, "reports": 0, "attempts": 0, "orphan_events": 0}
        cutoff = (datetime.now(UTC) - timedelta(days=retention_days)).isoformat(timespec="milliseconds").replace("+00:00", "Z")
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            job_ids = [row["id"] for row in connection.execute(
                "SELECT id FROM jobs WHERE state IN ('completed','failed','cancelled','dead_letter') AND updated_at<? ORDER BY updated_at,id LIMIT ?", (cutoff, batch_size)
            ).fetchall()]
            reports = attempts = 0
            if job_ids:
                placeholders = ",".join("?" for _ in job_ids)
                report_ids = [row["id"] for row in connection.execute(f"SELECT id FROM reports WHERE job_id IN ({placeholders})", job_ids).fetchall()]
                if report_ids:
                    report_marks = ",".join("?" for _ in report_ids)
                    connection.execute(f"UPDATE reports SET supersedes_id=NULL WHERE supersedes_id IN ({report_marks})", report_ids)
                reports = connection.execute(f"DELETE FROM reports WHERE job_id IN ({placeholders})", job_ids).rowcount
                attempts = connection.execute(f"DELETE FROM job_attempts WHERE job_id IN ({placeholders})", job_ids).rowcount
                connection.execute(f"DELETE FROM jobs WHERE id IN ({placeholders})", job_ids)
            event_ids = [row["id"] for row in connection.execute(
                """SELECT e.id FROM events e WHERE e.received_at<?
                   AND NOT EXISTS(SELECT 1 FROM jobs j WHERE j.event_id=e.id)
                   AND NOT EXISTS(SELECT 1 FROM pending_event_triggers p WHERE p.event_id=e.id)
                   ORDER BY e.received_at,e.id LIMIT ?""", (cutoff, batch_size)
            ).fetchall()]
            if event_ids:
                event_marks = ",".join("?" for _ in event_ids)
                connection.execute(f"DELETE FROM events WHERE id IN ({event_marks})", event_ids)
            connection.execute("INSERT INTO gateway_metadata(key,value) VALUES('retention_last_run_at',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value", (now,))
            result = {"jobs": len(job_ids), "reports": reports, "attempts": attempts, "orphan_events": len(event_ids)}
            self._append_audit(connection, actor_identity_id=None, credential_id=None, action="maintenance.retention_run", target_type="retention_policy", target_id=None, decision="recorded", reason_code="automatic" if automatic else "ingress_admin", correlation_id=correlation_id, metadata=result)
        return result

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
        event_type = str(event.get("event_type", ""))
        now = utc_now()
        with connect(self.database_path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            existing = connection.execute(
                """SELECT e.id AS event_id,j.id AS job_id,
                          (SELECT a.reason_code FROM audit_entries a WHERE a.target_type='event' AND a.target_id=e.id ORDER BY a.sequence DESC LIMIT 1) AS outcome
                   FROM events e LEFT JOIN jobs j ON j.event_id=e.id
                   WHERE e.source_identity_id=? AND e.idempotency_key=?""",
                (identity.identity_id, idempotency_key),
            ).fetchone()
            if existing:
                return IntakeResult(existing["event_id"], existing["job_id"], True, existing["outcome"] or ("accepted" if existing["job_id"] else "suppressed"))
            task_revision = connection.execute(
                """SELECT r.id,d.id AS task_definition_id,d.name,m.id AS mapping_id,
                          m.cooldown_minutes,m.grace_minutes,m.recovery_event_type,m.input_mode,m.last_triggered_at,
                          CASE WHEN m.recovery_event_type=? THEN 1 ELSE 0 END AS is_recovery
                   FROM event_mappings m
                   JOIN task_definitions d ON d.id=m.task_definition_id
                   JOIN task_revisions r ON r.task_definition_id=d.id
                   WHERE m.source_identity_id=? AND (m.event_type=? OR m.recovery_event_type=?) AND m.enabled=1 AND d.enabled=1
                   ORDER BY r.revision DESC LIMIT 1""",
                (event_type, identity.identity_id, event_type, event_type),
            ).fetchone()
            if task_revision is None:
                raise ValueError("No active event mapping")
            task_name = task_revision["name"]
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
            if not task_revision["is_recovery"] and (not dependencies or any(
                not item["enabled"]
                or item["status"] != "ready"
                or item["current_fingerprint"] != item["schema_fingerprint"]
                for item in dependencies
            )):
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
            event_id = str(uuid4())
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
            task_input = canonical_json(redact(event if task_revision["input_mode"] == "full_event" else event[task_revision["input_mode"]]))
            if task_revision["is_recovery"]:
                cancelled = connection.execute("DELETE FROM pending_event_triggers WHERE mapping_id=?", (task_revision["mapping_id"],)).rowcount
                outcome = "grace_cancelled" if cancelled else "recovery_recorded"
                self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="events.create", target_type="event", target_id=event_id, decision="recorded", reason_code=outcome, correlation_id=correlation_id, metadata={"event_type": event["event_type"], "mapping_id": task_revision["mapping_id"]})
                return IntakeResult(event_id, None, False, outcome)
            cooldown_cutoff = (datetime.now(UTC) - timedelta(minutes=task_revision["cooldown_minutes"])).isoformat(timespec="milliseconds").replace("+00:00", "Z")
            outcome = None
            if task_revision["cooldown_minutes"] and task_revision["last_triggered_at"] and task_revision["last_triggered_at"] > cooldown_cutoff:
                outcome = "cooldown_active"
            elif connection.execute(
                """SELECT 1 FROM jobs j JOIN task_revisions r ON r.id=j.task_revision_id
                   WHERE r.task_definition_id=? AND j.state IN ('queued','leased') LIMIT 1""",
                (task_revision["task_definition_id"],),
            ).fetchone() is not None:
                outcome = "task_execution_active"
            if outcome:
                self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="events.create", target_type="event", target_id=event_id, decision="recorded", reason_code=outcome, correlation_id=correlation_id, metadata={"event_type": event["event_type"], "mapping_id": task_revision["mapping_id"]})
                return IntakeResult(event_id, None, False, outcome)
            if task_revision["grace_minutes"]:
                due_at = (datetime.now(UTC) + timedelta(minutes=task_revision["grace_minutes"])).isoformat(timespec="milliseconds").replace("+00:00", "Z")
                created = connection.execute(
                    "INSERT OR IGNORE INTO pending_event_triggers(mapping_id,event_id,task_revision_id,policy_revision_id,input_json,due_at,created_at) VALUES(?,?,?,?,?,?,?)",
                    (task_revision["mapping_id"], event_id, task_revision["id"], identity.policy_revision_id, task_input, due_at, now),
                ).rowcount
                outcome = "grace_started" if created else "grace_active"
                self._append_audit(connection, actor_identity_id=identity.identity_id, credential_id=identity.credential_id, action="events.create", target_type="event", target_id=event_id, decision="recorded", reason_code=outcome, correlation_id=correlation_id, metadata={"event_type": event["event_type"], "mapping_id": task_revision["mapping_id"], "due_at": due_at if created else None})
                return IntakeResult(event_id, None, False, outcome)
            queued = connection.execute("SELECT count(*) FROM jobs WHERE state IN ('queued','leased')").fetchone()[0]
            if queued >= self.queue_limit:
                raise QueueFullError("queue_full")
            job_id = str(uuid4())
            connection.execute(
                "INSERT INTO jobs(id,event_id,task_name,state,policy_revision_id,task_revision_id,input_json,created_at,updated_at) VALUES(?,?,?,?,?,?,?,?,?)",
                (job_id, event_id, task_name, "queued", identity.policy_revision_id, task_revision["id"], task_input, now, now),
            )
            connection.execute("UPDATE event_mappings SET last_triggered_at=?,updated_at=? WHERE id=?", (now, now, task_revision["mapping_id"]))
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
                metadata={"job_id": job_id, "event_type": event["event_type"], "mapping_id": task_revision["mapping_id"], "input_mode": task_revision["input_mode"]},
            )
        return IntakeResult(event_id, job_id, False, "queued")

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
