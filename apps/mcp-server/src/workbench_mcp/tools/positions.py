"""`list_positions` tool.

Returns up to 100 open positions. Mirrors GET /api/v1/positions.
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_POSITIONS = 100


async def list_positions(
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Returns the user's open positions, capped at 100.

    Output shape: ``{"positions": [...], "count": int}`` where each
    position carries ``symbol``, ``qty``, ``avg_entry_price``,
    ``market_value``, ``unrealized_pl``, ``unrealized_plpc``, ``side``.
    """
    if client is not None:
        payload = await client.get_positions()
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_positions()
    items = payload.get("items") or []
    capped = items[:MAX_POSITIONS]
    return {"positions": capped, "count": len(capped)}
