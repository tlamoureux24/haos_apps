"""Runtime settings with conservative defaults."""

from __future__ import annotations

import os
import ipaddress
from dataclasses import dataclass
from pathlib import Path

from agent_gateway.ha_mcp import validate_private_url


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    surface: str
    log_level: str
    ingress_proxy_ip: str
    intake_rate_limit_per_minute: int
    ha_mcp_url: str

    @property
    def database_path(self) -> Path:
        return self.data_dir / "agent_gateway.db"


def load_settings() -> Settings:
    surface = os.environ.get("AGENT_GATEWAY_SURFACE", "public")
    if surface not in {"admin", "public"}:
        raise RuntimeError("AGENT_GATEWAY_SURFACE must be admin or public")
    log_level = os.environ.get("AGENT_GATEWAY_LOG_LEVEL", "info").lower()
    if log_level not in {"debug", "info", "warning", "error"}:
        raise RuntimeError("Invalid AGENT_GATEWAY_LOG_LEVEL")
    ingress_proxy_ip = os.environ.get("AGENT_GATEWAY_INGRESS_PROXY_IP", "172.30.32.2")
    try:
        ipaddress.ip_address(ingress_proxy_ip)
    except ValueError as exc:
        raise RuntimeError("Invalid AGENT_GATEWAY_INGRESS_PROXY_IP") from exc
    try:
        intake_rate_limit = int(os.environ.get("AGENT_GATEWAY_INTAKE_RATE_LIMIT", "30"))
    except ValueError as exc:
        raise RuntimeError("Invalid AGENT_GATEWAY_INTAKE_RATE_LIMIT") from exc
    if not 1 <= intake_rate_limit <= 600:
        raise RuntimeError("AGENT_GATEWAY_INTAKE_RATE_LIMIT must be between 1 and 600")
    return Settings(
        data_dir=Path(os.environ.get("AGENT_GATEWAY_DATA_DIR", "/data")),
        surface=surface,
        log_level=log_level,
        ingress_proxy_ip=ingress_proxy_ip,
        intake_rate_limit_per_minute=intake_rate_limit,
        ha_mcp_url=validate_private_url(os.environ.get("AGENT_GATEWAY_HA_MCP_URL", "")),
    )
