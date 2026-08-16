#!/usr/bin/env python3
"""Small read-only MCP server for Agent Gateway multi-connector acceptance tests."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run a harmless Streamable HTTP MCP test server.")
    parser.add_argument("--host", default="0.0.0.0", help="Listening address (default: 0.0.0.0)")
    parser.add_argument("--port", type=int, default=8765, help="Listening port (default: 8765)")
    parser.add_argument(
        "--server-marker",
        default="agent-gateway-fake-mcp",
        help="Marker returned by every tool so independent test servers can be distinguished.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.port <= 65535:
        raise SystemExit("port must be between 1 and 65535")
    if not 1 <= len(args.server_marker) <= 120:
        raise SystemExit("server marker must contain 1 to 120 characters")
    try:
        from mcp.server.fastmcp import FastMCP
    except ImportError as exc:
        raise SystemExit("Missing dependency. Run: python3 -m pip install 'mcp==1.28.1'") from exc

    server = FastMCP(
        f"Agent Gateway fake MCP ({args.server_marker})",
        instructions="Read-only acceptance server. Every result identifies this fake connector.",
        host=args.host,
        port=args.port,
        streamable_http_path="/mcp",
        stateless_http=True,
        json_response=True,
    )

    @server.tool(
        name="ha_get_addon",
        description=(
            "FAKE read-only add-on lookup used to test duplicate upstream tool names. "
            "It never contacts Home Assistant and always identifies the fake test server."
        ),
    )
    def fake_ha_get_addon(slug: str | None = None, source: str = "installed") -> dict[str, object]:
        return {
            "server_marker": args.server_marker,
            "tool_marker": "ha_get_addon",
            "requested_slug": slug,
            "requested_source": source,
            "read_only": True,
            "message": "Synthetic response from an Agent Gateway acceptance connector; no Home Assistant call occurred.",
            "observed_at": datetime.now(UTC).isoformat(),
        }

    @server.tool(
        name="echo_probe",
        description="Return a read-only synthetic payload that proves which MCP connector answered.",
    )
    def echo_probe(message: str = "Agent Gateway test") -> dict[str, object]:
        return {
            "server_marker": args.server_marker,
            "tool_marker": "echo_probe",
            "message": message,
            "read_only": True,
            "observed_at": datetime.now(UTC).isoformat(),
        }

    print(
        f"Fake MCP marker={args.server_marker} listening on http://{args.host}:{args.port}/mcp",
        flush=True,
    )
    server.run(transport="streamable-http")


if __name__ == "__main__":
    main()
