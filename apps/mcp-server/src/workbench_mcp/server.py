"""FastMCP server entrypoint.

Registers the workbench tools and runs over SSE on MCP_HOST:MCP_PORT.

P0 shipped one tool (``get_system_status``). P3 §2 expands the catalog
to twelve read-only tools (account, positions, orders, fills, strategies,
signals, backtests, quotes, bars, indicators) — all delegate to the
backend over HTTP. Mutating tools are deliberately absent; the
``check_mcp_readonly.sh`` tripwire enforces that at CI time.
"""

from __future__ import annotations

from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP

from workbench_mcp.config import get_settings
from workbench_mcp.tools.account import get_account_state as _get_account_state
from workbench_mcp.tools.backtests import (
    list_recent_backtests as _list_recent_backtests,
)
from workbench_mcp.tools.market_data import get_bars as _get_bars
from workbench_mcp.tools.market_data import get_indicators as _get_indicators
from workbench_mcp.tools.market_data import get_quote as _get_quote
from workbench_mcp.tools.orders import list_open_orders as _list_open_orders
from workbench_mcp.tools.orders import list_recent_fills as _list_recent_fills
from workbench_mcp.tools.orders import list_recent_orders as _list_recent_orders
from workbench_mcp.tools.positions import list_positions as _list_positions
from workbench_mcp.tools.signals import (
    list_recent_signals as _list_recent_signals,
)
from workbench_mcp.tools.strategies import (
    get_strategy_detail as _get_strategy_detail,
)
from workbench_mcp.tools.strategies import list_strategies as _list_strategies
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
    async def get_system_status() -> dict[str, Any]:
        return await _get_system_status()

    @server.tool(
        name="get_account_state",
        description=(
            "Returns the user's current Alpaca account state "
            "(cash, equity, buying power, day P&L)."
        ),
    )
    async def get_account_state() -> dict[str, Any]:
        return await _get_account_state()

    @server.tool(
        name="list_positions",
        description="Returns the user's open positions (capped at 100).",
    )
    async def list_positions() -> dict[str, Any]:
        return await _list_positions()

    @server.tool(
        name="list_open_orders",
        description=(
            "Returns open (non-terminal) orders, optionally filtered "
            "by symbol. Capped at 100."
        ),
    )
    async def list_open_orders(symbol: str | None = None) -> dict[str, Any]:
        return await _list_open_orders(symbol=symbol)

    @server.tool(
        name="list_recent_orders",
        description=(
            "Returns recent orders including terminal ones "
            "(filled / canceled / rejected). Default 50, max 100."
        ),
    )
    async def list_recent_orders(
        limit: int = 50,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        return await _list_recent_orders(limit=limit, symbol=symbol)

    @server.tool(
        name="list_recent_fills",
        description=(
            "Returns recent fills flattened from terminal orders. "
            "Default 50, max 100."
        ),
    )
    async def list_recent_fills(
        limit: int = 50,
        symbol: str | None = None,
    ) -> dict[str, Any]:
        return await _list_recent_fills(limit=limit, symbol=symbol)

    @server.tool(
        name="list_strategies",
        description=(
            "Returns all strategies for the user, optionally filtered by status."
        ),
    )
    async def list_strategies(status: str | None = None) -> dict[str, Any]:
        return await _list_strategies(status=status)

    @server.tool(
        name="get_strategy_detail",
        description=(
            "Returns a strategy + its most-recent run + count of today's signals."
        ),
    )
    async def get_strategy_detail(strategy_id: int) -> dict[str, Any]:
        return await _get_strategy_detail(strategy_id=strategy_id)

    @server.tool(
        name="list_recent_signals",
        description=(
            "Returns recent signals across the user's strategies "
            "(filters: strategy_id, symbol, type, since)."
        ),
    )
    async def list_recent_signals(
        limit: int = 100,
        strategy_id: int | None = None,
        symbol: str | None = None,
        type: str | None = None,
        since: str | None = None,
    ) -> dict[str, Any]:
        return await _list_recent_signals(
            limit=limit,
            strategy_id=strategy_id,
            symbol=symbol,
            type_=type,
            since=since,
        )

    @server.tool(
        name="list_recent_backtests",
        description=(
            "Returns recent backtests (summarized). With strategy_id, scoped "
            "to that strategy; without, fans out across the first 10 strategies."
        ),
    )
    async def list_recent_backtests(
        strategy_id: int | None = None,
        limit: int = 20,
    ) -> dict[str, Any]:
        return await _list_recent_backtests(
            strategy_id=strategy_id, limit=limit
        )

    @server.tool(
        name="get_quote",
        description="Returns the last quote for one symbol (bid/ask/last/ts).",
    )
    async def get_quote(symbol: str) -> dict[str, Any]:
        return await _get_quote(symbol=symbol)

    @server.tool(
        name="get_bars",
        description=(
            "Returns historical OHLCV bars for one symbol. "
            "Always capped at 200 bars."
        ),
    )
    async def get_bars(
        symbol: str,
        timeframe: str = "1Min",
        limit: int = 50,
    ) -> dict[str, Any]:
        return await _get_bars(
            symbol=symbol, timeframe=timeframe, limit=limit
        )

    @server.tool(
        name="get_indicators",
        description=(
            "Returns latest indicator values and a short sparkline "
            "per indicator for one symbol."
        ),
    )
    async def get_indicators(
        symbol: str,
        names: str | None = None,
        timeframe: str = "1Min",
    ) -> dict[str, Any]:
        return await _get_indicators(
            symbol=symbol, names=names, timeframe=timeframe
        )

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
