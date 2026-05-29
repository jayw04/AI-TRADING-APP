"""`list_recent_backtests` tool.

If ``strategy_id`` is provided, pulls that strategy's backtests directly.
Otherwise lists the first 10 strategies and fans out — the doc flags this
as suboptimal; a cross-strategy ``/api/v1/backtests`` endpoint is P4 polish.

The returned ``metrics_summary`` is the four headline numbers
(``trade_count``, ``total_return``, ``sharpe_ratio``, ``max_drawdown``);
the full metrics object stays in the backend for `get_backtest_detail`-
style future tools.
"""

from __future__ import annotations

from typing import Any

from workbench_mcp.client import WorkbenchBackendClient

MAX_BACKTESTS = 50
DEFAULT_BACKTESTS = 20
CROSS_STRATEGY_FANOUT = 10


def _summarize(backtest: dict[str, Any]) -> dict[str, Any]:
    metrics = backtest.get("metrics") or {}
    summary = {
        "trade_count": metrics.get("trade_count"),
        "total_return": metrics.get("total_return"),
        "sharpe_ratio": metrics.get("sharpe_ratio"),
        "max_drawdown": metrics.get("max_drawdown"),
    }
    return {
        "id": backtest.get("id"),
        "strategy_id": backtest.get("strategy_id"),
        "label": backtest.get("label"),
        "range_start": backtest.get("range_start"),
        "range_end": backtest.get("range_end"),
        "metrics_summary": summary,
        "created_at": backtest.get("created_at"),
    }


async def list_recent_backtests(
    strategy_id: int | None = None,
    limit: int = DEFAULT_BACKTESTS,
    client: WorkbenchBackendClient | None = None,
) -> dict[str, Any]:
    """Most recent backtests, summarized.

    With ``strategy_id``: limits to that strategy. Without: fans out
    across the first ``CROSS_STRATEGY_FANOUT`` strategies.
    Output: ``{"backtests": [...], "count": int}``.
    """
    bounded = max(1, min(limit, MAX_BACKTESTS))
    if client is not None:
        return await _run(client, strategy_id, bounded)
    async with WorkbenchBackendClient() as c:
        return await _run(c, strategy_id, bounded)


async def _run(
    client: WorkbenchBackendClient,
    strategy_id: int | None,
    bounded: int,
) -> dict[str, Any]:
    collected: list[dict[str, Any]] = []
    if strategy_id is not None:
        payload = await client.get_strategy_backtests(strategy_id, limit=bounded)
        collected = [_summarize(b) for b in payload.get("items") or []]
    else:
        strategies_payload = await client.get_strategies()
        strategies = (strategies_payload.get("items") or [])[
            :CROSS_STRATEGY_FANOUT
        ]
        for s in strategies:
            sid = s.get("id")
            if sid is None:
                continue
            sub = await client.get_strategy_backtests(int(sid), limit=bounded)
            collected.extend(_summarize(b) for b in sub.get("items") or [])
            if len(collected) >= bounded:
                break
        collected = collected[:bounded]
    return {"backtests": collected, "count": len(collected)}
