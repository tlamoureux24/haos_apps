"""One process and event loop owning both isolated listener servers."""

from __future__ import annotations

import asyncio
import logging
import os
import signal
from contextlib import contextmanager
from pathlib import Path

import uvicorn

from mcp_capability_bridge.main import RuntimeState, create_apps
from mcp_capability_bridge.settings import load_settings

logger = logging.getLogger("mcp_capability_bridge")


class ManagedServer(uvicorn.Server):
    """Uvicorn server whose signals are coordinated by the shared runtime."""

    @contextmanager
    def capture_signals(self):
        yield


async def serve() -> None:
    if os.geteuid() != 1000:
        raise RuntimeError("MCP Capability Bridge must run with UID 1000")
    settings = load_settings()
    admin_app, public_app = create_apps(RuntimeState(settings))
    log_config = str(Path(__file__).with_name("uvicorn_logging.json"))
    servers = (
        ManagedServer(uvicorn.Config(admin_app, host=settings.admin_host,
                                     port=settings.admin_port, log_level=settings.log_level,
                                     access_log=False, log_config=log_config)),
        ManagedServer(uvicorn.Config(public_app, host=settings.public_host,
                                     port=settings.public_port, log_level=settings.log_level,
                                     access_log=False, log_config=log_config)),
    )
    loop = asyncio.get_running_loop()

    def request_shutdown() -> None:
        for server in servers:
            server.should_exit = True

    for signum in (signal.SIGTERM, signal.SIGINT):
        loop.add_signal_handler(signum, request_shutdown)
    logger.info("Starting one runtime with Ingress 8099 and public health 8098")
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
        logger.info("MCP Capability Bridge stopped")


if __name__ == "__main__":
    asyncio.run(serve())
