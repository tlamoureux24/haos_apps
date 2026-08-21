"""Runtime settings with conservative HAOS defaults."""

from __future__ import annotations

import ipaddress
import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    log_level: str
    ingress_proxy_ip: str
    admin_host: str = "0.0.0.0"
    admin_port: int = 8099
    public_host: str = "0.0.0.0"
    public_port: int = 8098

    @property
    def database_path(self) -> Path:
        return self.data_dir / "mcp_capability_bridge.db"


def load_settings() -> Settings:
    log_level = os.environ.get("MCP_CAPABILITY_BRIDGE_LOG_LEVEL", "info").lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise RuntimeError("Invalid MCP_CAPABILITY_BRIDGE_LOG_LEVEL")
    ingress_proxy_ip = os.environ.get("MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP", "172.30.32.2")
    try:
        ipaddress.ip_address(ingress_proxy_ip)
    except ValueError as exc:
        raise RuntimeError("Invalid MCP_CAPABILITY_BRIDGE_INGRESS_PROXY_IP") from exc
    return Settings(
        data_dir=Path(os.environ.get("MCP_CAPABILITY_BRIDGE_DATA_DIR", "/data")),
        log_level=log_level,
        ingress_proxy_ip=ingress_proxy_ip,
    )
