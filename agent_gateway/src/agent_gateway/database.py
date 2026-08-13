"""SQLite schema initialization for clean development installations."""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path


SCHEMA_GENERATION = "8"
SCHEMA_SQL = """
PRAGMA foreign_keys=ON;
CREATE TABLE gateway_metadata(key TEXT PRIMARY KEY, value TEXT NOT NULL);
INSERT INTO gateway_metadata VALUES('application','agent_gateway');
INSERT INTO gateway_metadata VALUES('schema_generation','8');
CREATE TABLE identities(
  id TEXT PRIMARY KEY,display_name TEXT NOT NULL,identity_type TEXT NOT NULL,
  status TEXT NOT NULL,created_at TEXT NOT NULL,
  CHECK(identity_type IN ('client','event_source','scheduler')),
  CHECK(status IN ('active','revoked')));
CREATE TABLE credentials(
  id TEXT PRIMARY KEY,identity_id TEXT NOT NULL,verifier TEXT NOT NULL,
  created_at TEXT NOT NULL,expires_at TEXT,last_used_at TEXT,revoked_at TEXT,
  FOREIGN KEY(identity_id) REFERENCES identities(id) ON DELETE CASCADE);
CREATE INDEX ix_credentials_identity ON credentials(identity_id);
CREATE TABLE policy_documents(
  id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,created_at TEXT NOT NULL);
CREATE TABLE policy_revisions(
  id TEXT PRIMARY KEY,policy_id TEXT NOT NULL,schema_version INTEGER NOT NULL,
  document_json TEXT NOT NULL,created_at TEXT NOT NULL,
  FOREIGN KEY(policy_id) REFERENCES policy_documents(id) ON DELETE CASCADE,
  UNIQUE(policy_id,id));
CREATE TABLE policy_bindings(
  identity_id TEXT PRIMARY KEY,policy_revision_id TEXT NOT NULL,bound_at TEXT NOT NULL,
  FOREIGN KEY(identity_id) REFERENCES identities(id) ON DELETE CASCADE,
  FOREIGN KEY(policy_revision_id) REFERENCES policy_revisions(id));
CREATE TABLE task_definitions(
  id TEXT PRIMARY KEY,name TEXT NOT NULL UNIQUE,display_name TEXT NOT NULL,
  enabled INTEGER NOT NULL,created_at TEXT NOT NULL,
  CHECK(enabled IN (0,1)));
CREATE TABLE task_revisions(
  id TEXT PRIMARY KEY,task_definition_id TEXT NOT NULL,revision INTEGER NOT NULL,
  objective TEXT NOT NULL,input_schema_json TEXT NOT NULL,report_schema_json TEXT NOT NULL,
  max_attempts INTEGER NOT NULL,created_at TEXT NOT NULL,
  FOREIGN KEY(task_definition_id) REFERENCES task_definitions(id),
  UNIQUE(task_definition_id,revision),CHECK(max_attempts BETWEEN 1 AND 10));
CREATE TABLE connectors(
  id TEXT PRIMARY KEY,display_name TEXT NOT NULL UNIQUE,transport TEXT NOT NULL,
  protected_config TEXT NOT NULL,display_endpoint TEXT NOT NULL,status TEXT NOT NULL,
  enabled INTEGER NOT NULL,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
  last_checked_at TEXT,last_error_code TEXT,inventory_revision INTEGER NOT NULL DEFAULT 0,
  CHECK(transport IN ('streamable_http')),
  CHECK(status IN ('ready','unreachable','disabled','inventory_changed','invalid')),
  CHECK(enabled IN (0,1)));
CREATE TABLE connector_tools(
  connector_id TEXT NOT NULL,name TEXT NOT NULL,description TEXT NOT NULL,
  input_schema_json TEXT NOT NULL,schema_fingerprint TEXT NOT NULL,discovered_at TEXT NOT NULL,
  PRIMARY KEY(connector_id,name),
  FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE CASCADE);
CREATE INDEX ix_connector_tools_connector ON connector_tools(connector_id);
CREATE TABLE task_tool_selections(
  task_revision_id TEXT NOT NULL,connector_id TEXT NOT NULL,tool_name TEXT NOT NULL,
  schema_fingerprint TEXT NOT NULL,namespaced_name TEXT NOT NULL,
  constraints_json TEXT NOT NULL,
  PRIMARY KEY(task_revision_id,connector_id,tool_name),
  UNIQUE(task_revision_id,namespaced_name),
  FOREIGN KEY(task_revision_id) REFERENCES task_revisions(id) ON DELETE CASCADE,
  FOREIGN KEY(connector_id) REFERENCES connectors(id) ON DELETE RESTRICT);
CREATE INDEX ix_task_tool_connector ON task_tool_selections(connector_id,tool_name);
CREATE TABLE schedules(
  id TEXT PRIMARY KEY,display_name TEXT NOT NULL,task_definition_id TEXT NOT NULL,
  interval_minutes INTEGER NOT NULL,enabled INTEGER NOT NULL,next_run_at TEXT NOT NULL,
  last_run_at TEXT,last_outcome TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
  FOREIGN KEY(task_definition_id) REFERENCES task_definitions(id) ON DELETE RESTRICT,
  CHECK(interval_minutes BETWEEN 1 AND 10080),CHECK(enabled IN (0,1)),
  CHECK(last_outcome IS NULL OR last_outcome IN ('queued','skipped_active','task_unavailable','queue_full')));
CREATE INDEX ix_schedules_due ON schedules(enabled,next_run_at);
CREATE TABLE event_mappings(
  id TEXT PRIMARY KEY,display_name TEXT NOT NULL,source_identity_id TEXT NOT NULL,
  event_type TEXT NOT NULL,task_definition_id TEXT NOT NULL,enabled INTEGER NOT NULL,
  created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
  FOREIGN KEY(source_identity_id) REFERENCES identities(id) ON DELETE RESTRICT,
  FOREIGN KEY(task_definition_id) REFERENCES task_definitions(id) ON DELETE RESTRICT,
  UNIQUE(source_identity_id,event_type),CHECK(enabled IN (0,1)));
CREATE INDEX ix_event_mappings_lookup ON event_mappings(source_identity_id,event_type,enabled);
CREATE TABLE events(
  id TEXT PRIMARY KEY,source_identity_id TEXT NOT NULL,idempotency_key TEXT NOT NULL,
  schema_version INTEGER NOT NULL,event_type TEXT NOT NULL,occurred_at TEXT NOT NULL,
  received_at TEXT NOT NULL,payload_json TEXT NOT NULL,
  FOREIGN KEY(source_identity_id) REFERENCES identities(id),
  UNIQUE(source_identity_id,idempotency_key));
CREATE INDEX ix_events_received ON events(received_at);
CREATE TABLE jobs(
  id TEXT PRIMARY KEY,event_id TEXT,task_name TEXT NOT NULL,state TEXT NOT NULL,
  policy_revision_id TEXT NOT NULL,task_revision_id TEXT NOT NULL,input_json TEXT NOT NULL,created_at TEXT NOT NULL,
  updated_at TEXT NOT NULL,FOREIGN KEY(event_id) REFERENCES events(id),
  FOREIGN KEY(policy_revision_id) REFERENCES policy_revisions(id),
  FOREIGN KEY(task_revision_id) REFERENCES task_revisions(id),
  CHECK(state IN ('queued','leased','completed','failed','cancelled','dead_letter')));
CREATE INDEX ix_jobs_state_created ON jobs(state,created_at);
CREATE TABLE job_attempts(
  id TEXT PRIMARY KEY,job_id TEXT NOT NULL,attempt_number INTEGER NOT NULL,
  identity_id TEXT NOT NULL,lease_verifier TEXT NOT NULL,leased_at TEXT NOT NULL,
  lease_expires_at TEXT NOT NULL,max_expires_at TEXT NOT NULL,finished_at TEXT,
  outcome TEXT,failure_reason TEXT,completion_key TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(id),FOREIGN KEY(identity_id) REFERENCES identities(id),
  UNIQUE(job_id,attempt_number),UNIQUE(job_id,completion_key),
  CHECK(outcome IS NULL OR outcome IN ('completed','failed')));
CREATE INDEX ix_job_attempts_job ON job_attempts(job_id,attempt_number);
CREATE TABLE reports(
  id TEXT PRIMARY KEY,job_id TEXT NOT NULL,schema_version INTEGER NOT NULL,
  report_json TEXT NOT NULL,created_at TEXT NOT NULL,supersedes_id TEXT,
  FOREIGN KEY(job_id) REFERENCES jobs(id),
  FOREIGN KEY(supersedes_id) REFERENCES reports(id));
CREATE INDEX ix_reports_job ON reports(job_id);
CREATE TABLE audit_entries(
  sequence INTEGER PRIMARY KEY AUTOINCREMENT,id TEXT NOT NULL UNIQUE,
  occurred_at TEXT NOT NULL,actor_identity_id TEXT,credential_id TEXT,
  action TEXT NOT NULL,target_type TEXT,target_id TEXT,decision TEXT NOT NULL,
  reason_code TEXT NOT NULL,correlation_id TEXT NOT NULL,metadata_json TEXT NOT NULL,
  previous_hash TEXT NOT NULL,entry_hash TEXT NOT NULL,
  FOREIGN KEY(actor_identity_id) REFERENCES identities(id),
  CHECK(decision IN ('allowed','denied','recorded')));
CREATE TABLE intake_rate_windows(
  identity_id TEXT PRIMARY KEY,window_started_at TEXT NOT NULL,request_count INTEGER NOT NULL,
  FOREIGN KEY(identity_id) REFERENCES identities(id),CHECK(request_count >= 0));
"""


def connect(path: Path) -> sqlite3.Connection:
    connection = sqlite3.connect(path, timeout=5)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=5000")
    return connection


def initialize_database(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with connect(path) as connection:
        tables = connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        if not tables:
            connection.executescript(SCHEMA_SQL)
            return
        try:
            generation = connection.execute(
                "SELECT value FROM gateway_metadata WHERE key='schema_generation'"
            ).fetchone()
        except sqlite3.Error as exc:
            raise RuntimeError("incompatible_database_remove_app_data") from exc
        if generation and generation[0] == "6":
            connection.executescript(
                """
                CREATE TABLE schedules(
                  id TEXT PRIMARY KEY,display_name TEXT NOT NULL,task_definition_id TEXT NOT NULL,
                  interval_minutes INTEGER NOT NULL,enabled INTEGER NOT NULL,next_run_at TEXT NOT NULL,
                  last_run_at TEXT,last_outcome TEXT,created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                  FOREIGN KEY(task_definition_id) REFERENCES task_definitions(id) ON DELETE RESTRICT,
                  CHECK(interval_minutes BETWEEN 1 AND 10080),CHECK(enabled IN (0,1)),
                  CHECK(last_outcome IS NULL OR last_outcome IN ('queued','skipped_active','task_unavailable','queue_full')));
                CREATE INDEX ix_schedules_due ON schedules(enabled,next_run_at);
                UPDATE gateway_metadata SET value='7' WHERE key='schema_generation';
                """
            )
            generation = ("7",)
        if generation and generation[0] == "7":
            connection.executescript(
                """
                CREATE TABLE event_mappings(
                  id TEXT PRIMARY KEY,display_name TEXT NOT NULL,source_identity_id TEXT NOT NULL,
                  event_type TEXT NOT NULL,task_definition_id TEXT NOT NULL,enabled INTEGER NOT NULL,
                  created_at TEXT NOT NULL,updated_at TEXT NOT NULL,
                  FOREIGN KEY(source_identity_id) REFERENCES identities(id) ON DELETE RESTRICT,
                  FOREIGN KEY(task_definition_id) REFERENCES task_definitions(id) ON DELETE RESTRICT,
                  UNIQUE(source_identity_id,event_type),CHECK(enabled IN (0,1)));
                CREATE INDEX ix_event_mappings_lookup ON event_mappings(source_identity_id,event_type,enabled);
                UPDATE gateway_metadata SET value='8' WHERE key='schema_generation';
                """
            )
            return
        if generation is None or generation[0] != SCHEMA_GENERATION:
            raise RuntimeError("incompatible_database_remove_app_data")


def database_ready(path: Path) -> bool:
    if not path.is_file():
        return False
    try:
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True, timeout=1)
        try:
            integrity = connection.execute("PRAGMA quick_check").fetchone()
            application = connection.execute(
                "SELECT value FROM gateway_metadata WHERE key='application'"
            ).fetchone()
            generation = connection.execute(
                "SELECT value FROM gateway_metadata WHERE key='schema_generation'"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return False
    return bool(
        integrity
        and integrity[0] == "ok"
        and application
        and application[0] == "agent_gateway"
        and generation
        and generation[0] == SCHEMA_GENERATION
    )


if __name__ == "__main__":
    if sys.argv[1:] != ["initialize"]:
        raise SystemExit("usage: python -m agent_gateway.database initialize")
    from agent_gateway.settings import load_settings

    initialize_database(load_settings().database_path)
