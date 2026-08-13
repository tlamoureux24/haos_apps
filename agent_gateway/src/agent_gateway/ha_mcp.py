"""Private HA-MCP connector boundary; never exposed as a passthrough."""

from __future__ import annotations

import re

PRIVATE_URL = re.compile(r"^https?://[^\s/]+(?::[0-9]{1,5})?(?:/[^\s]*)?/private_[^/\s]+$")


def validate_private_url(url: str) -> str:
    value = url.strip()
    if value and not PRIVATE_URL.fullmatch(value):
        raise ValueError("invalid_ha_mcp_private_url")
    return value


async def probe_ha_mcp(url: str) -> dict[str, object]:
    if not url:
        return {"configured": False, "reachable": False, "tool_count": 0}
    try:
        import anyio
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        with anyio.fail_after(8):
            async with streamable_http_client(url) as (read, write, _):
                async with ClientSession(read, write) as session:
                    await session.initialize()
                    tools = await session.list_tools()
        return {"configured": True, "reachable": True, "tool_count": len(tools.tools)}
    except Exception:
        return {"configured": True, "reachable": False, "tool_count": 0}
