"""Market-data tools: ``get_quote``, ``get_bars``, ``get_indicators``.

All three mirror the backend market-data endpoints; ``get_bars`` is
capped at 200 bars at the tool level (the backend allows up to 10,000
but the agent's context window is precious).
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_BARS = 200
DEFAULT_BARS = 50


async def get_quote(
    symbol: str,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Last quote for ``symbol``.

    Output: ``{symbol, bid, ask, last, ts}`` (plus optional ``bid_size``
    / ``ask_size``).
    """
    if client is not None:
        return await client.get_quote(symbol)
    async with WorkbenchBackendClient() as c:
        return await c.get_quote(symbol)


async def get_bars(
    symbol: str,
    timeframe: str = "1Min",
    limit: int = DEFAULT_BARS,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Historical OHLCV bars for ``symbol``. Capped at 200 bars at the
    tool boundary regardless of the requested ``limit``.

    Output: ``{"symbol", "timeframe", "bars": [{t,o,h,l,c,v}, ...],
    "count": int}``.
    """
    bounded = max(1, min(limit, MAX_BARS))
    if client is not None:
        payload = await client.get_bars(
            symbol, timeframe=timeframe, limit=bounded
        )
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_bars(
                symbol, timeframe=timeframe, limit=bounded
            )
    bars = payload.get("bars") or []
    capped = bars[:bounded]
    return {
        "symbol": payload.get("symbol", symbol.upper()),
        "timeframe": payload.get("timeframe", timeframe),
        "bars": capped,
        "count": len(capped),
    }


async def get_indicators(
    symbol: str,
    names: str | None = None,
    timeframe: str = "1Min",
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Latest indicator values + a short sparkline per indicator.

    Output mirrors GET /api/v1/indicators/{symbol}.
    """
    if client is not None:
        return await client.get_indicators(
            symbol, names=names, timeframe=timeframe
        )
    async with WorkbenchBackendClient() as c:
        return await c.get_indicators(
            symbol, names=names, timeframe=timeframe
        )
