"""Runtime settings with conservative HAOS defaults."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    surface: str
    log_level: str
    ingress_proxy_ip: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "agent_execution_plane.db"


def load_settings() -> Settings:
    surface = os.environ.get("AGENT_EXECUTION_PLANE_SURFACE", "api")
    if surface not in {"admin", "api"}:
        raise RuntimeError("AGENT_EXECUTION_PLANE_SURFACE must be admin or api")
    log_level = os.environ.get("AGENT_EXECUTION_PLANE_LOG_LEVEL", "info").lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise RuntimeError("Invalid AGENT_EXECUTION_PLANE_LOG_LEVEL")
    ingress_proxy_ip = os.environ.get("AGENT_EXECUTION_PLANE_INGRESS_PROXY_IP", "172.30.32.2")
    try:
        ipaddress.ip_address(ingress_proxy_ip)
    except ValueError as exc:
        raise RuntimeError("Invalid AGENT_EXECUTION_PLANE_INGRESS_PROXY_IP") from exc
    return Settings(Path(os.environ.get("AGENT_EXECUTION_PLANE_DATA_DIR", "/data")), surface, log_level, ingress_proxy_ip)
