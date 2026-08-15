"""Pure definitions for the externally exposed HTTP surfaces."""

from __future__ import annotations


HEALTH_PATHS = ("/health/live", "/health/ready")


def exposed_paths(surface: str) -> tuple[str, ...]:
    if surface == "admin":
        return (
            "/",
            "/admin/assets/admin.css",
            "/admin/assets/admin.js",
            "/admin/assets/logo.png",
            "/admin/api/v1/status",
            "/admin/api/v1/connectors",
            "/admin/api/v1/connectors/check",
            "/admin/api/v1/connectors/delete",
            "/admin/api/v1/connectors/enabled",
            "/admin/api/v1/connectors/archived",
            "/admin/api/v1/connectors/tools",
            "/admin/api/v1/tasks",
            "/admin/api/v1/tasks/delete",
            "/admin/api/v1/tasks/enabled",
            "/admin/api/v1/tasks/archived",
            "/admin/api/v1/tasks/run",
            "/admin/api/v1/schedules",
            "/admin/api/v1/schedules/update",
            "/admin/api/v1/schedules/enabled",
            "/admin/api/v1/schedules/delete",
            "/admin/api/v1/event-mappings",
            "/admin/api/v1/event-mappings/update",
            "/admin/api/v1/event-mappings/enabled",
            "/admin/api/v1/event-mappings/incidents/retry",
            "/admin/api/v1/event-mappings/delete",
            "/admin/api/v1/identities",
            "/admin/api/v1/identities/revoke",
            "/admin/api/v1/events",
            "/admin/api/v1/jobs",
            "/admin/api/v1/jobs/cancel",
            "/admin/api/v1/jobs/requeue",
            "/admin/api/v1/reports",
            "/admin/api/v1/audit",
            "/admin/api/v1/audit/export",
            "/admin/api/v1/audit/verify",
            "/admin/api/v1/retention",
            "/admin/api/v1/retention/update",
            "/admin/api/v1/retention/run",
            *HEALTH_PATHS,
        )
    if surface == "public":
        return (
            "/api/v1/events",
            "/api/v1/jobs",
            "/api/v1/reports",
            "/api/v1/permissions/effective",
            *HEALTH_PATHS,
        )
    raise ValueError(f"Unknown surface: {surface}")
