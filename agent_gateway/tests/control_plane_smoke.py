"""Container-only transaction smoke test run after clean schema initialization."""

from __future__ import annotations

import sqlite3
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

from agent_gateway.control_plane import AuthenticationError, ControlPlane, LeaseError


database = Path("/data/agent_gateway.db")
control_plane = ControlPlane(database, Path("/data/private"))
created = control_plane.create_identity(
    "CI Home Assistant events",
    "event_source",
    ["events.create"],
    "ci-create-identity",
)
identity = control_plane.authenticate(created.credential.token)
event = {
    "schema_version": 1,
    "event_type": "gatus.endpoint_unavailable",
    "occurred_at": "2026-08-12T15:00:00Z",
    "source": "home_assistant",
    "subject": {"entity_id": "binary_sensor.ci_connectivity"},
    "attributes": {"state": "off"},
    "requested_task": "gatus_readonly_diagnostic",
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
    {"schema_version": 1, "summary": "CI complete", "observations": []},
    "ci-complete",
)
assert control_plane.complete_job(
    worker,
    first.job_id,
    lease.lease_token,
    "ci-completion",
    {"schema_version": 1, "summary": "CI complete", "observations": []},
    "ci-complete-replay",
) == report_id
failed = control_plane.ingest_event(identity, "ci-failure-key", event, "ci-failure-event")
failed_lease = control_plane.claim_job(worker, "ci-failure-claim")
assert failed_lease is not None and failed_lease.job["id"] == failed.job_id
control_plane.fail_job(worker, failed.job_id, failed_lease.lease_token, "bounded CI failure", "ci-fail")

try:
    control_plane.authenticate(created.credential.token[:-1] + "x")
except AuthenticationError:
    pass
else:
    raise AssertionError("A modified credential was accepted")

with sqlite3.connect(database) as connection:
    assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 2
    assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 2
    assert {row[0] for row in connection.execute("SELECT state FROM jobs")} == {"completed", "failed"}
    assert connection.execute("SELECT count(*) FROM reports").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM job_attempts").fetchone()[0] == 2
