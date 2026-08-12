"""Runtime settings with conservative defaults."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Settings:
    data_dir: Path
    surface: str
    log_level: str

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
    return Settings(
        data_dir=Path(os.environ.get("AGENT_GATEWAY_DATA_DIR", "/data")),
        surface=surface,
        log_level=log_level,
    )
