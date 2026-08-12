"""Container-only transaction smoke test run after Alembic migrations."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from agent_gateway.control_plane import AuthenticationError, ControlPlane


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
first = control_plane.ingest_event(identity, "ci-stable-key", event, "ci-event")
replay = control_plane.ingest_event(identity, "ci-stable-key", event, "ci-replay")
assert replay.duplicate and first.event_id == replay.event_id and first.job_id == replay.job_id

try:
    control_plane.authenticate(created.credential.token[:-1] + "x")
except AuthenticationError:
    pass
else:
    raise AssertionError("A modified credential was accepted")

with sqlite3.connect(database) as connection:
    assert connection.execute("SELECT count(*) FROM events").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM jobs").fetchone()[0] == 1
    assert connection.execute("SELECT count(*) FROM audit_entries").fetchone()[0] == 2
