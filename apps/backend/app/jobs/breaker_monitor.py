"""Continuous circuit-breaker monitor (P10 §6, Review v2 Critical Issue #5).

The order-time `CircuitBreakerService.check()` only fires when an order is
submitted — so a portfolio whose drawdown deepens while no orders are flowing
(e.g. overnight) won't trip the daily-loss breaker until the next order attempt.
This periodic job closes that gap: every ~minute it calls `evaluate()` (the
non-raising sibling of `check()`) for each account that holds an open position,
tripping + HALTing exactly as the order path would.

Runs via the lifespan scheduler (interval). Best-effort: never raises into the
scheduler, and a failure on one account doesn't stop the others.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.position import Position
from app.market.session import MarketSession, default_market_session
from app.observability.metrics import automation_runs_total
from app.risk.circuit_breaker import CircuitBreakerService

logger = structlog.get_logger(__name__)


async def run_breaker_monitor(
    session_factory: async_sessionmaker[AsyncSession],
    bus: Any = None,
    market_session: MarketSession | None = None,
) -> None:
    """Trip the circuit breaker for any account whose net daily P&L has breached
    its limit, independent of order flow. `evaluate()` skips already-tripped and
    no-limit accounts, so this is safe to run on every account with open positions.

    RTH guard (ADR 0034 / 2026-07-02 incident): the daily-loss breaker is an
    intraday metric. Outside the REGULAR session, an account's unrealized P&L is
    computed from stale or thin pre-/post-market prints, so evaluating here trips
    the breaker on noise — a book that dips overnight and recovers by the open gets
    halted spuriously. So evaluation runs only during REGULAR hours; a genuine
    overnight gap is still caught at the first post-open run. Fail toward NOT
    tripping on any classification error."""
    ms = market_session or default_market_session()
    try:
        regular = ms.classify().is_regular
    except Exception:
        logger.warning("breaker_monitor_session_classify_failed", exc_info=True)
        regular = False
    if not regular:
        automation_runs_total.labels(actor="breaker_monitor", outcome="skipped").inc()
        return
    # P11 §2: record the run's OUTCOME — the scheduler listener only sees that this job
    # "executed" (it swallows internal errors below), so this captures the real result.
    outcome = "ok"
    try:
        async with session_factory() as session:
            account_ids = (
                await session.execute(
                    select(Position.account_id)
                    .where(Position.qty != Decimal(0))
                    .distinct()
                )
            ).scalars().all()
            if account_ids:
                cb = CircuitBreakerService(session=session, bus=bus)
                for account_id in account_ids:
                    try:
                        if await cb.evaluate(account_id):
                            logger.warning("breaker_monitor_tripped", account_id=account_id)
                    except Exception:
                        logger.exception(
                            "breaker_monitor_account_failed", account_id=account_id
                        )
    except Exception:
        outcome = "error"
        logger.exception("breaker_monitor_failed")
    automation_runs_total.labels(actor="breaker_monitor", outcome=outcome).inc()
