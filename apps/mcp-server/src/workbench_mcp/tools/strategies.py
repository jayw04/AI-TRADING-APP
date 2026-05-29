"""Strategy tools: ``list_strategies``, ``get_strategy_detail``.

``get_strategy_detail`` fans out to three backend endpoints in parallel
(strategy + most-recent run + recent signals) and computes today's
signal count client-side rather than asking the backend for a separate
aggregate.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_STRATEGIES = 100
SIGNAL_LOOKBACK = 200


async def list_strategies(
    status: str | None = None,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """All strategies for the user, optionally filtered by status.

    Output: ``{"strategies": [...], "count": int}`` with each item
    carrying ``id``, ``name``, ``version``, ``type``, ``status``,
    ``symbols``, ``schedule``.
    """
    if client is not None:
        payload = await client.get_strategies(status=status)
    else:
        async with WorkbenchBackendClient() as c:
            payload = await c.get_strategies(status=status)
    items = payload.get("items") or []
    capped = items[:MAX_STRATEGIES]
    return {"strategies": capped, "count": len(capped)}


async def get_strategy_detail(
    strategy_id: int,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Strategy row + most-recent run + count of today's signals.

    Output:
        ``{"strategy": {...}, "last_run": {...} | None,
           "signals_today": int}``.
    """
    if client is not None:
        return await _detail(client, strategy_id)
    async with WorkbenchBackendClient() as c:
        return await _detail(c, strategy_id)


async def _detail(
    client: WorkbenchBackendClient, strategy_id: int
) -> dict[str, Any]:
    strategy = await client.get_strategy(strategy_id)
    runs_payload = await client.get_strategy_runs(strategy_id, limit=1)
    runs = runs_payload.get("items") or []
    last_run = runs[0] if runs else None

    signals_payload = await client.get_strategy_signals(
        strategy_id, limit=SIGNAL_LOOKBACK
    )
    signals = signals_payload.get("items") or []
    today = datetime.now(UTC).date().isoformat()
    signals_today = sum(
        1 for s in signals if str(s.get("received_at", "")).startswith(today)
    )
    return {
        "strategy": strategy,
        "last_run": last_run,
        "signals_today": signals_today,
    }
