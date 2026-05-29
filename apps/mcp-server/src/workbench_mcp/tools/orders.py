"""Order tools: ``list_open_orders``, ``list_recent_orders``, ``list_recent_fills``.

All three derive from GET /api/v1/orders. Fills are flattened from each
order's embedded ``fills`` array (the orders endpoint eager-loads them).
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_ORDERS = 100
DEFAULT_ORDERS = 50
MAX_FILLS = 100
DEFAULT_FILLS = 50


async def list_open_orders(
    symbol: str | None = None,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Open (non-terminal) orders, optionally filtered by symbol.

    Output: ``{"orders": [...], "count": int}``.
    """
    if client is not None:
        payload = await client.get_orders(
            status="open", symbol=symbol, limit=MAX_ORDERS
        )
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_orders(
                status="open", symbol=symbol, limit=MAX_ORDERS
            )
    items = payload.get("items") or []
    capped = items[:MAX_ORDERS]
    return {"orders": capped, "count": len(capped)}


async def list_recent_orders(
    limit: int = DEFAULT_ORDERS,
    symbol: str | None = None,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Recent orders including terminal ones (filled / canceled / rejected).

    Output: ``{"orders": [...], "count": int}``.
    """
    bounded = max(1, min(limit, MAX_ORDERS))
    if client is not None:
        payload = await client.get_orders(symbol=symbol, limit=bounded)
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_orders(symbol=symbol, limit=bounded)
    items = payload.get("items") or []
    capped = items[:bounded]
    return {"orders": capped, "count": len(capped)}


async def list_recent_fills(
    limit: int = DEFAULT_FILLS,
    symbol: str | None = None,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Flatten the ``fills`` array on each recent order. P3 doesn't add a
    dedicated /fills endpoint — orders eager-load fills, so we derive
    here.

    Output: ``{"fills": [...], "count": int}`` where each fill carries
    ``order_id``, ``symbol``, ``side``, ``qty``, ``price``, ``filled_at``.
    """
    bounded = max(1, min(limit, MAX_FILLS))
    # Pull more orders than fills wanted so a single big order doesn't
    # starve the result. Cap at MAX_ORDERS to bound work.
    if client is not None:
        payload = await client.get_orders(
            status="history", symbol=symbol, limit=MAX_ORDERS
        )
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_orders(
                status="history", symbol=symbol, limit=MAX_ORDERS
            )
    orders = payload.get("items") or []
    fills: list[dict[str, Any]] = []
    for order in orders:
        order_id = order.get("id")
        order_symbol = order.get("symbol")
        side = order.get("side")
        for fill in order.get("fills") or []:
            fills.append(
                {
                    "order_id": order_id,
                    "symbol": order_symbol,
                    "side": side,
                    "qty": fill.get("qty"),
                    "price": fill.get("price"),
                    "filled_at": fill.get("filled_at"),
                }
            )
            if len(fills) >= bounded:
                break
        if len(fills) >= bounded:
            break
    return {"fills": fills, "count": len(fills)}
