"""Create the minimal ready ACP graph required by the TLS event smoke test."""

from __future__ import annotations

import sqlite3
import sys

from agent_control_plane.control_plane import ControlPlane
from agent_control_plane.settings import load_settings


source_identity_id = sys.argv[1]
settings = load_settings()
control_plane = ControlPlane(settings.database_path, settings.data_dir / "private")
connector_id = "10000000-0000-0000-0000-000000000099"
stamp = "2026-08-23T00:00:00Z"
with sqlite3.connect(settings.database_path) as database:
    database.execute(
        "INSERT INTO connectors(id,display_name,transport,protected_config,display_endpoint,status,enabled,created_at,updated_at,inventory_revision) VALUES(?,?,?,?,?,'ready',1,?,?,1)",
        (connector_id, "TLS fixture", "streamable_http", "fixture", "https://fixture.invalid", stamp, stamp),
    )
    database.execute(
        "INSERT INTO connector_tools(connector_id,name,description,input_schema_json,schema_fingerprint,discovered_at) VALUES(?,?,?,?,?,?)",
        (connector_id, "inspect", "Inspect", '{"type":"object"}', "a" * 64, stamp),
    )
task_id = control_plane.create_task(
    "TLS event task", "tls-event-task", "Validate authenticated HTTPS Event Intake.", 1,
    [{"connector_id": connector_id, "tool_name": "inspect"}], "tls-event-task",
)
control_plane.create_event_mapping(
    "TLS event mapping", source_identity_id, "service.alert", task_id, 0, 0, None,
    "full_event", "simple", "tls-event-mapping",
)
