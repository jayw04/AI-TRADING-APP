"""FastMCP server entrypoint.

Registers the workbench tools and runs over SSE on MCP_HOST:MCP_PORT.

P0 ships with one tool: get_system_status. More land in P1+.
"""

from __future__ import annotations

import structlog
from mcp.server.fastmcp import FastMCP

from workbench_mcp.config import get_settings
from workbench_mcp.tools.system import get_system_status as _get_system_status

log = structlog.get_logger("workbench_mcp")


def build_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP("Trading Workbench", host=settings.host, port=settings.port)

    @server.tool(
        name="get_system_status",
        description=(
            "Returns current Trading Workbench system status "
            "(DB, broker, WS, halt state)."
        ),
    )
    async def get_system_status() -> dict:
        return await _get_system_status()

    return server


def main() -> None:
    settings = get_settings()
    log.info(
        "mcp.start",
        host=settings.host,
        port=settings.port,
        backend_url=settings.backend_url,
    )
    server = build_server()
    server.run(transport="sse")


if __name__ == "__main__":
    main()
