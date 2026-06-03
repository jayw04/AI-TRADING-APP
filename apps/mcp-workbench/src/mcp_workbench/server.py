"""workbench-mcp FastMCP server — 12 read-only tools over the backend HTTP API.

Transport: SSE on host:port (default 127.0.0.1:8766), matching P3's chart MCP
(which runs ``server.run(transport="sse")`` on 8765). Each tool is a thin
adapter — one HTTP call, no business logic. The ONE non-GET call
(``workbench_morning_brief_generate`` → POST .../morning-brief/generate) is
idempotent per (user, date) and is the sole entry in the
``check_workbench_mcp_readonly`` allowlist.

Tool functions are module-level (so they're unit-testable with a mocked HTTP
layer); ``build_server`` registers them on the FastMCP instance.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import structlog
from mcp.server.fastmcp import FastMCP

from mcp_workbench.client import WorkbenchClient
from mcp_workbench.config import get_settings

log = structlog.get_logger("mcp_workbench")


async def _get(path: str, params: dict[str, Any] | None = None) -> Any:
    async with WorkbenchClient() as c:
        return await c.get(path, params=params)


async def _post(path: str, json: dict[str, Any] | None = None) -> Any:
    async with WorkbenchClient() as c:
        return await c.post(path, json=json)


# -------------------- tools (read-only) --------------------


async def workbench_status() -> dict[str, Any]:
    """Overall workbench health (database, scheduler, broker registry, circuit
    breakers). Call this first to confirm the workbench is healthy."""
    return await _get("/healthz")


async def workbench_morning_brief_today() -> dict[str, Any] | None:
    """Today's morning brief if generated: per-symbol bias labels, key levels,
    indicator snapshots, and the agent note (if any). Null if none today."""
    return await _get("/api/v1/morning-brief/today")


async def workbench_morning_brief_generate() -> dict[str, Any]:
    """Generate a fresh morning brief now (reads the trading profile, computes
    indicators, applies bias thresholds). Idempotent per (user, today)."""
    return await _post("/api/v1/morning-brief/generate")


async def workbench_trading_profile_get() -> dict[str, Any]:
    """The user's trading profile: watchlist tiers, bias criteria, bias
    thresholds, session preferences, risk preferences."""
    return await _get("/api/v1/users/me/trading-profile")


async def workbench_list_accounts() -> dict[str, Any]:
    """All the user's brokerage accounts (paper and live)."""
    return await _get("/api/v1/accounts")


async def workbench_list_strategies() -> dict[str, Any]:
    """All strategies with status (idle, paper, live, pending_live, halted,
    error)."""
    return await _get("/api/v1/strategies")


async def workbench_list_positions(account_id: int) -> dict[str, Any]:
    """Open positions on one account (symbol, qty, avg price, market value,
    unrealized P&L)."""
    return await _get(f"/api/v1/accounts/{account_id}/positions")


async def workbench_list_orders(limit: int = 20) -> dict[str, Any]:
    """Recent orders across accounts (paper + live). Default 20, max 100."""
    return await _get("/api/v1/orders", params={"limit": min(limit, 100)})


async def workbench_account_risk_state(account_id: int) -> dict[str, Any]:
    """Risk state for one account: circuit breaker (tripped/clear + PnL), PDT
    status, daily-loss headroom."""
    return await _get(f"/api/v1/accounts/{account_id}/risk-state")


async def workbench_strategy_activation_status(strategy_id: int) -> dict[str, Any]:
    """Activation status for a strategy: current state, the five prerequisites,
    and the 24h cooldown remaining if PENDING_LIVE."""
    return await _get(f"/api/v1/strategies/{strategy_id}/activation")


async def workbench_recent_briefs(limit: int = 7) -> dict[str, Any]:
    """The last N morning briefs for trend comparison. Default 7, max 30."""
    return await _get("/api/v1/morning-brief/recent", params={"limit": min(limit, 30)})


async def workbench_audit_recent(limit: int = 50) -> dict[str, Any]:
    """Recent audit-log entries for the user (newest first). Action names are
    UPPER (e.g. MORNING_BRIEF_GENERATED, CIRCUIT_BREAKER_TRIPPED). Default 50,
    max 200. For brief cost: filter MORNING_BRIEF_GENERATED, read
    payload_json -> llm.cost_cents (a stringified Decimal)."""
    return await _get("/api/v1/audit", params={"limit": min(limit, 200)})


# -------------------- P6 §1b proposal-context tools (read-only) --------------------


async def workbench_strategy_history(strategy_id: int, limit: int = 30) -> dict[str, Any]:
    """A strategy snapshot (name, version, status, params, symbols) plus a
    lightweight recent-orders summary — the context the agent reads before
    proposing a parameter change. Default 30, max 90."""
    return await _get(
        f"/api/v1/strategies/{strategy_id}/history",
        params={"limit": min(limit, 90)},
    )


async def workbench_recent_proposals_for_strategy(
    strategy_id: int, limit: int = 5
) -> dict[str, Any]:
    """The last N proposals for a strategy (newest first). The agent reads this
    to avoid repeating prior suggestions. Default 5, max 30."""
    return await _get(
        "/api/v1/proposals",
        params={"strategy_id": strategy_id, "limit": min(limit, 30)},
    )


async def workbench_strategy_recent_orders(
    strategy_id: int, limit: int = 20
) -> dict[str, Any]:
    """Recent orders submitted by one strategy (execution context for proposal
    generation). Filters orders by source_type=strategy + source_id. Default 20,
    max 100."""
    return await _get(
        "/api/v1/orders",
        params={
            "source_type": "strategy",
            "source_id": str(strategy_id),
            "limit": min(limit, 100),
        },
    )


async def workbench_get_proposal(proposal_id: int) -> dict[str, Any]:
    """One proposal in full: payload, evidence bundle, evaluation results (if
    any), lifecycle state. For follow-up questions about a specific proposal."""
    return await _get(f"/api/v1/proposals/{proposal_id}")


async def workbench_proposal_eval_summary(
    strategy_id: int, window: int = 30
) -> dict[str, Any]:
    """Aggregate proposal backtest-eval data for a strategy over the last N days
    (P6 §2b): counts by eval state (complete/pending/skipped/failed), counts by
    verdict (above_baseline/below_baseline), and the latest complete eval's delta
    metrics. Use for 'how is the agent doing for this strategy / are my proposals
    working?'. Default 30, max 365."""
    return await _get(
        f"/api/v1/strategies/{strategy_id}/proposal-eval-summary",
        params={"window": min(window, 365)},
    )


async def workbench_drift_findings(
    strategy_id: int, lookback_days: int = 30
) -> dict[str, Any]:
    """Drift status for a strategy (P6b §1b): whether its recent live behavior
    diverged from its backtest baseline (win_rate / avg_return_per_trade beyond
    the user's thresholds) within the lookback window. Returns
    {status: 'drift_detected' | 'no_recent_drift', ..., payload: {...}}. Use when
    proposing a change to a strategy (drift is evidence) or answering 'is strategy
    X behaving as backtested?'. Default lookback 30 days (longitudinal)."""
    return await _get(
        f"/api/v1/strategies/{strategy_id}/drift-status",
        params={"lookback_days": lookback_days},
    )


_TOOLS: list[Callable[..., Any]] = [
    workbench_status,
    workbench_morning_brief_today,
    workbench_morning_brief_generate,
    workbench_trading_profile_get,
    workbench_list_accounts,
    workbench_list_strategies,
    workbench_list_positions,
    workbench_list_orders,
    workbench_account_risk_state,
    workbench_strategy_activation_status,
    workbench_recent_briefs,
    workbench_audit_recent,
    # P6 §1b proposal-context tools.
    workbench_strategy_history,
    workbench_recent_proposals_for_strategy,
    workbench_strategy_recent_orders,
    workbench_get_proposal,
    # P6 §2b proposal-eval summary.
    workbench_proposal_eval_summary,
    # P6b §1b drift status.
    workbench_drift_findings,
]


def build_server() -> FastMCP:
    settings = get_settings()
    server = FastMCP("Trading Workbench State", host=settings.host, port=settings.port)
    for fn in _TOOLS:
        server.tool(name=fn.__name__, description=(fn.__doc__ or "").strip())(fn)
    return server


def main() -> None:
    settings = get_settings()
    if not settings.mcp_key:
        raise RuntimeError(
            "WORKBENCH_MCP_KEY env var required. Generate it via Settings → "
            "Credentials in the UI, then export it to this process's environment."
        )
    log.info(
        "mcp_workbench.start",
        host=settings.host,
        port=settings.port,
        backend_url=settings.backend_url,
    )
    build_server().run(transport="sse")


if __name__ == "__main__":
    main()
