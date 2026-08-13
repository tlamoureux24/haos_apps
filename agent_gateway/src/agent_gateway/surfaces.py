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
            "/admin/api/v1/connectors/ha-mcp/tools",
            "/admin/api/v1/identities",
            "/admin/api/v1/identities/revoke",
            "/admin/api/v1/events",
            "/admin/api/v1/jobs",
            "/admin/api/v1/jobs/cancel",
            "/admin/api/v1/reports",
            "/admin/api/v1/audit",
            "/admin/api/v1/audit/export",
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
