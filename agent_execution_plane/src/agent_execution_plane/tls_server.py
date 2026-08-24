"""Start an external-TLS Uvicorn listener without exposing its private key."""
from __future__ import annotations

import os
import ssl

import uvicorn

from agent_execution_plane.settings import load_settings
from agent_execution_plane.tls import prepare_certificate


def _drop_privileges() -> None:
    os.setgroups([])
    os.setgid(1000)
    os.setuid(1000)
    if os.geteuid() != 1000 or os.getegid() != 1000:
        raise RuntimeError("failed_to_drop_runtime_privileges")


def main() -> None:
    settings = load_settings()
    certificate = prepare_certificate(
        settings.data_dir, "external", settings.certfile, settings.keyfile
    )
    context = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    context.minimum_version = ssl.TLSVersion.TLSv1_2
    context.load_cert_chain(certificate.certfile, certificate.keyfile)
    _drop_privileges()
    config = uvicorn.Config(
        "agent_execution_plane.main:app", host="0.0.0.0", port=8098,
        log_level=settings.log_level, access_log=False,
        log_config="/app/src/agent_execution_plane/uvicorn_logging.json",
    )
    config.load()
    config.ssl = context
    uvicorn.Server(config).run()


if __name__ == "__main__":
    main()
