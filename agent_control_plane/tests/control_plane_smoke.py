"""Container-only transaction smoke test run after clean schema initialization."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_control_plane.control_plane import AuthenticationError, AuthorizationError, ControlPlane, LeaseError


database = Path("/data/agent_control_plane.db")
control_plane = ControlPlane(database, Path("/data/private"))
with sqlite3.connect(database) as connection:
    connection.execute(
        "INSERT INTO task_definitions(id,name,display_name,enabled,created_at) VALUES(?,?,?,?,?)",
        ("ci-inspection", "inspect_service", "Inspect service", 1, "2026-08-13T00:00:00.000Z"),
    )
    connection.execute(
        "INSERT INTO task_revisions(id,task_definition_id,revision,objective,input_schema_json,report_schema_json,max_attempts,created_at) VALUES(?,?,?,?,?,?,?,?)",
        (
            "ci-inspection-v1",
            "ci-inspection",
            1,
            "Inspect the supplied service and return a structured report.",
            '{"type":"object"}',
            '{"type":"object","required":["schema_version","summary","findings"],"additionalProperties":false,"properties":{"schema_version":{"type":"integer"},"summary":{"type":"string","minLength":1,"maxLength":2000},"findings":{"type":"array","maxItems":100}}}',
            3,
            "2026-08-13T00:00:00.000Z",
        ),
    )
    connection.execute(
        "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
        ("ci-connector", "CI connector", "streamable_http", "test-only", "http://ci.invalid", "2026-08-13T00:00:00.000Z", "2026-08-13T00:00:00.000Z"),
    )
    connection.execute(
        "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
        ("ci-connector", "inspect", "Inspect", '{"type":"object"}', "a" * 64, "2026-08-13T00:00:00.000Z"),
    )
    connection.execute(
        "INSERT INTO task_tool_selections(task_revision_id,connector_id,tool_name,schema_fingerprint,namespaced_name,constraints_json) VALUES(?,?,?,?,?,?)",
        ("ci-inspection-v1", "ci-connector", "inspect", "a" * 64, "connector/ci-connector/inspect", "{}"),
    )
created = control_plane.create_identity(
    "CI Home Assistant events",
    "event_source",
    ["events.create"],
    "ci-create-identity",
)
identity = control_plane.authenticate(created.credential.token)
mapping_id = control_plane.create_event_mapping(
    "CI service alerts", identity.identity_id, "service.alert", "ci-inspection", 0, 0, None, "full_event", "simple", "ci-create-mapping"
)
event = {
    "schema_version": 1,
    "event_type": "service.alert",
    "occurred_at": "2026-08-12T15:00:00Z",
    "subject": {"service_id": "ci-service"},
    "attributes": {"status": "unavailable"},
}
with ThreadPoolExecutor(max_workers=8) as executor:
    results = list(
        executor.map(
            lambda index: control_plane.ingest_event(
                identity, "ci-stable-key", event, f"ci-concurrent-{index}"
            ),
            range(16),
        )
    )
first = results[0]
assert len({result.event_id for result in results}) == 1
assert len({result.job_id for result in results}) == 1
assert sum(not result.duplicate for result in results) == 1
suppressed = control_plane.ingest_event(identity, "ci-active-key", event, "ci-active-event")
assert suppressed.job_id is None
assert suppressed.outcome == "task_execution_active"

worker_created = control_plane.create_identity(
    "CI reasoning worker",
    "client",
    ["jobs.claim", "jobs.heartbeat", "jobs.complete", "jobs.fail"],
    "ci-create-worker",
)
worker = control_plane.authenticate(worker_created.credential.token)
queued_capabilities = control_plane.next_queued_capabilities(worker)
assert len(queued_capabilities) == 1
assert queued_capabilities[0]["name"] == "connector/ci-connector/inspect"
try:
    control_plane.resolve_active_capability(worker, "connector/ci-connector/inspect", {}, "ci-before-claim")
except AuthorizationError as exc:
    assert str(exc) == "capability_not_available"
else:
    raise AssertionError("An advertised capability was invokable before its lease")
with ThreadPoolExecutor(max_workers=8) as executor:
    claims = list(executor.map(lambda index: control_plane.claim_job(worker, f"ci-claim-{index}"), range(8)))
leases = [claim for claim in claims if claim is not None]
assert len(leases) == 1
lease = leases[0]
assert lease.job["id"] == first.job_id
assert lease.job["allowed_capabilities"] == [
    {"name": "connector/ci-connector/inspect", "input_schema": {"type": "object"}}
]
assert "connector_id" not in str(lease.job["allowed_capabilities"])
assert "tool_name" not in str(lease.job["allowed_capabilities"])
capabilities = control_plane.active_capabilities(worker)
assert len(capabilities) == 1
assert capabilities[0]["name"] == "connector/ci-connector/inspect"
assert capabilities[0]["input_schema"] == {"type": "object"}
assert control_plane.claim_job(worker, "ci-empty-claim") is None
other_created = control_plane.create_identity(
    "CI other worker", "client", ["jobs.heartbeat"], "ci-create-other"
)
other = control_plane.authenticate(other_created.credential.token)
try:
    control_plane.heartbeat_job(other, first.job_id, lease.lease_token, "ci-stolen")
except LeaseError as exc:
    assert str(exc) == "lease_not_owned"
else:
    raise AssertionError("Another identity extended a stolen lease")
control_plane.heartbeat_job(worker, first.job_id, lease.lease_token, "ci-heartbeat")
report_id = control_plane.complete_job(
    worker,
    first.job_id,
    lease.lease_token,
    "ci-completion",
    {"schema_version": 1, "summary": "CI complete", "findings": []},
    "ci-complete",
)
assert control_plane.active_capabilities(worker) == []
assert control_plane.complete_job(
    worker,
    first.job_id,
    lease.lease_token,
    "ci-completion",
    {"schema_version": 1, "summary": "CI complete", "findings": []},
    "ci-complete-replay",
) == report_id
with sqlite3.connect(database) as connection:
    connection.execute("UPDATE event_mappings SET cooldown_minutes=15 WHERE id=?", (mapping_id,))
cooldown = control_plane.ingest_event(identity, "ci-cooldown-key", event, "ci-cooldown-event")
assert cooldown.job_id is None
assert cooldown.outcome == "cooldown_active"
with sqlite3.connect(database) as connection:
    connection.execute("UPDATE event_mappings SET cooldown_minutes=0,input_mode='attributes' WHERE id=?", (mapping_id,))
failed = control_plane.ingest_event(identity, "ci-failure-key", event, "ci-failure-event")
assert control_plane.get_job(failed.job_id)["input"] == {"status": "unavailable"}
failed_lease = control_plane.claim_job(worker, "ci-failure-claim")
assert failed_lease is not None and failed_lease.job["id"] == failed.job_id
with sqlite3.connect(database) as connection:
    connection.execute(
        "UPDATE job_attempts SET lease_expires_at='2000-01-01T00:00:00.000Z' WHERE job_id=? AND finished_at IS NULL",
        (failed.job_id,),
    )
failed_lease = control_plane.claim_job(worker, "ci-expired-reclaim")
assert failed_lease is not None and failed_lease.job["id"] == failed.job_id
for attempt_number in range(2, 4):
    state = control_plane.fail_job(
        worker,
        failed.job_id,
        failed_lease.lease_token,
        "bounded transient CI failure",
        True,
        f"ci-fail-{attempt_number}",
    )
    if attempt_number < 3:
        assert state == "queued"
        failed_lease = control_plane.claim_job(worker, f"ci-retry-{attempt_number}")
        assert failed_lease is not None and failed_lease.job["id"] == failed.job_id
    else:
        assert state == "dead_letter"

requeue_state, requeued_job_id = control_plane.requeue_dead_letter(
    failed.job_id, "ci-dead-letter-requeue"
)
assert requeue_state == "queued" and requeued_job_id
blocked_state, blocked_job_id = control_plane.requeue_dead_letter(
    failed.job_id, "ci-dead-letter-requeue-active"
)
assert blocked_state == "task_execution_active" and blocked_job_id is None
assert control_plane.cancel_job(requeued_job_id, "ci-requeued-cancel") == "cancelled"

with sqlite3.connect(database) as connection:
    connection.execute("UPDATE event_mappings SET grace_minutes=1,recovery_event_type='service.recovered' WHERE id=?", (mapping_id,))
grace_started = control_plane.ingest_event(identity, "ci-grace-start", event, "ci-grace-start")
assert grace_started.job_id is None and grace_started.outcome == "grace_started"
recovery_event = {**event, "event_type": "service.recovered"}
grace_cancelled = control_plane.ingest_event(identity, "ci-grace-recovery", recovery_event, "ci-grace-recovery")
assert grace_cancelled.job_id is None and grace_cancelled.outcome == "grace_cancelled"
grace_restarted = control_plane.ingest_event(identity, "ci-grace-restart", event, "ci-grace-restart")
assert grace_restarted.job_id is None and grace_restarted.outcome == "grace_started"
with sqlite3.connect(database) as connection:
    connection.execute("UPDATE event_incidents SET due_at='2000-01-01T00:00:00.000Z',next_attempt_at='2000-01-01T00:00:00.000Z' WHERE mapping_id=?", (mapping_id,))
assert control_plane.run_due_event_triggers() == 1
grace_job = next(job for job in control_plane.list_jobs() if job["event_id"] == grace_restarted.event_id)
assert grace_job["state"] == "queued"
assert control_plane.cancel_job(grace_job["id"], "ci-grace-cancel") == "cancelled"

try:
    control_plane.authenticate(created.credential.token[:-1] + "x")
except AuthenticationError:
    pass
else:
    raise AssertionError("A modified credential was accepted")

with sqlite3.connect(database) as connection:
    assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 7
    assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 4
    assert {row[0] for row in connection.execute("SELECT state FROM jobs")} == {"completed", "dead_letter", "cancelled"}
    assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM job_attempts").fetchone()[0] == 4
    assert connection.execute("SELECT count(*) FROM job_attempts WHERE job_id=?", (requeued_job_id,)).fetchone()[0] == 0
    assert connection.execute("SELECT event_id FROM jobs WHERE id=?", (requeued_job_id,)).fetchone()[0] is None
