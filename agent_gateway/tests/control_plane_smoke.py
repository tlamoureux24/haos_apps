"""Container-only transaction smoke test run after clean schema initialization."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_gateway.control_plane import AuthenticationError, ControlPlane, LeaseError


database = Path("/data/agent_gateway.db")
control_plane = ControlPlane(database, Path("/data/private"))
with sqlite3.connect(database) as connection:
    connection.execute(
        "INSERT INTO task_definitions(id,name,created_at) VALUES(?,?,?)",
        ("ci-inspection", "inspect_service", "2026-08-13T00:00:00.000Z"),
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
created = control_plane.create_identity(
    "CI Home Assistant events",
    "event_source",
    ["events.create"],
    "ci-create-identity",
)
identity = control_plane.authenticate(created.credential.token)
event = {
    "schema_version": 1,
    "event_type": "service.alert",
    "occurred_at": "2026-08-12T15:00:00Z",
    "subject": {"service_id": "ci-service"},
    "attributes": {"status": "unavailable"},
    "requested_task": "inspect_service",
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

worker_created = control_plane.create_identity(
    "CI reasoning worker",
    "client",
    ["jobs.claim", "jobs.heartbeat", "jobs.complete", "jobs.fail"],
    "ci-create-worker",
)
worker = control_plane.authenticate(worker_created.credential.token)
with ThreadPoolExecutor(max_workers=8) as executor:
    claims = list(executor.map(lambda index: control_plane.claim_job(worker, f"ci-claim-{index}"), range(8)))
leases = [claim for claim in claims if claim is not None]
assert len(leases) == 1
lease = leases[0]
assert lease.job["id"] == first.job_id
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
assert control_plane.complete_job(
    worker,
    first.job_id,
    lease.lease_token,
    "ci-completion",
    {"schema_version": 1, "summary": "CI complete", "findings": []},
    "ci-complete-replay",
) == report_id
failed = control_plane.ingest_event(identity, "ci-failure-key", event, "ci-failure-event")
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

try:
    control_plane.authenticate(created.credential.token[:-1] + "x")
except AuthenticationError:
    pass
else:
    raise AssertionError("A modified credential was accepted")

with sqlite3.connect(database) as connection:
    assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
    assert {row[0] for row in connection.execute("SELECT state FROM jobs")} == {"completed", "dead_letter"}
    assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM job_attempts").fetchone()[0] == 4
