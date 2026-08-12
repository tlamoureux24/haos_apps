"""Pure definitions for the externally exposed HTTP surfaces."""

from __future__ import annotations


HEALTH_PATHS = ("/health/live", "/health/ready")


def exposed_paths(surface: str) -> tuple[str, ...]:
    if surface == "admin":
        return ("/", *HEALTH_PATHS)
    if surface == "public":
        return HEALTH_PATHS
    raise ValueError(f"Unknown surface: {surface}")
