"""`list_recent_signals` tool.

Returns up to 200 recent signals. Mirrors GET /api/v1/signals.
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_SIGNALS = 200
DEFAULT_SIGNALS = 100


async def list_recent_signals(
    limit: int = DEFAULT_SIGNALS,
    strategy_id: int | None = None,
    symbol: str | None = None,
    type_: str | None = None,
    since: str | None = None,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Recent signals across the user's strategies, with optional filters.

    Output: ``{"signals": [...], "count": int}`` with each item carrying
    ``id``, ``strategy_id``, ``symbol``, ``type``, ``payload``,
    ``received_at``.
    """
    bounded = max(1, min(limit, MAX_SIGNALS))
    if client is not None:
        payload = await client.get_signals(
            limit=bounded,
            strategy_id=strategy_id,
            symbol=symbol,
            type_=type_,
            since=since,
        )
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_signals(
                limit=bounded,
                strategy_id=strategy_id,
                symbol=symbol,
                type_=type_,
                since=since,
            )
    items = payload.get("items") or []
    capped = items[:bounded]
    return {"signals": capped, "count": len(capped)}
