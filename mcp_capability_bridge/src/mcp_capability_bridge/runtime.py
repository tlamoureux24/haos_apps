"""One process and event loop owning both isolated listener servers."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import signal
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from mcp_capability_bridge.main import build_runtime_state, create_apps
from mcp_capability_bridge.settings import load_settings
from mcp_capability_bridge.tls import prepare_certificate

logger = logging.getLogger("mcp_capability_bridge")


def load_log_configuration(level: str) -> dict[str, object]:
    path = Path(__file__).with_name("uvicorn_logging.json")
    configuration = json.loads(path.read_text(encoding="utf-8"))
    configuration["loggers"]["mcp_capability_bridge"] = {
        "handlers": ["default"], "level": level.upper(), "propagate": False,
    }
    return configuration


class ManagedServer(uvicorn.Server):
    """Uvicorn server whose signals are coordinated by the shared runtime."""

    @contextmanager
    def capture_signals(self):
        yield


async def serve() -> None:
    if os.geteuid() != 1000:
        raise RuntimeError("MCP Capability Bridge must run with UID 1000")
    settings = load_settings()
    state=build_runtime_state(settings)
    admin_app, public_app = create_apps(state)
    log_config = load_log_configuration(settings.log_level)
    servers = [
        ManagedServer(uvicorn.Config(admin_app, host=settings.admin_host,
                                     port=settings.admin_port, log_level=settings.log_level,
                                     access_log=False, log_config=log_config)),
    ]
    public_enabled=True;public_options={}
    if settings.public_transport=="http":
        logger.warning("MCP endpoint uses unencrypted HTTP; namespace credentials, tool arguments, and tool results are not encrypted by this application")
    else:
        try:
            if stage_error := os.environ.get("MCP_CAPABILITY_BRIDGE_EXTERNAL_TLS_STAGE_ERROR"):
                raise RuntimeError(stage_error)
            certificate=prepare_certificate(settings.data_dir,settings.certificate_source,settings.certfile,settings.keyfile)
            public_options={"ssl_certfile":str(certificate.certfile),"ssl_keyfile":str(certificate.keyfile)}
            logger.info("Public TLS certificate source: %s",certificate.source)
            logger.info("Public TLS certificate SHA-256: %s",certificate.fingerprint_sha256)
            logger.info("Public TLS certificate expires at: %s",certificate.not_after)
        except Exception as exc:
            public_enabled=False;logger.error("Public TLS certificate is invalid; MCP HTTPS listener was not started and Ingress administration remains available error=%s",str(exc))
    if public_enabled:
        servers.append(ManagedServer(uvicorn.Config(public_app,host=settings.public_host,port=settings.public_port,log_level=settings.log_level,access_log=False,log_config=log_config,**public_options)))
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        for server in servers:
            server.should_exit = True

    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, request_shutdown)
    logger.info("Starting one runtime with Ingress 8099 and authenticated MCP 8098")
    tasks = [asyncio.create_task(server.serve()) for server in servers]
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        request_shutdown()
        await asyncio.gather(*tasks)
        for task in done:
            task.result()
    finally:
        request_shutdown()
        await asyncio.gather(*tasks, return_exceptions=True)
        if not public_enabled:
            await state.counters.shutdown();await state.web_sessions.close_all();await state.browser.close()
        logger.info("MCP Capability Bridge stopped")


if __name__ == "__main__":
    asyncio.run(serve())
