"""Equity-snapshot persistence (P12.5 Production Validation).

Appends the current per-account equity (from `accounts_state`, which `AccountSyncService` keeps
fresh) into the `equity_snapshots` time series, so the live book's **equity curve** + realized
vol/drawdown/return can be reported. Read-only beyond its own append; no order path, no broker call.
Best-effort: never raises into the scheduler.
"""

from __future__ import annotations

from datetime import UTC, datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.db.models.account_state import AccountState
from app.db.models.equity_snapshot import EquitySnapshot

logger = structlog.get_logger(__name__)


async def snapshot_equity(session_factory: async_sessionmaker[AsyncSession]) -> int:
    """Append one ``EquitySnapshot`` per account from the current ``accounts_state``. Returns the
    number of accounts snapshotted. The time series is the history behind the point-in-time
    ``accounts_state`` — it never mutates account state."""
    async with session_factory() as session:
        states = (await session.execute(select(AccountState))).scalars().all()
        ts = datetime.now(UTC)
        for st in states:
            session.add(EquitySnapshot(
                account_id=st.account_id, ts=ts, equity=st.equity, cash=st.cash,
                portfolio_value=st.portfolio_value, day_change_pct=st.day_change_pct,
            ))
        await session.commit()
        return len(states)


async def run_daily_equity_snapshot(session_factory: async_sessionmaker[AsyncSession]) -> None:
    """Scheduler entrypoint (P12.5): persist one equity point per account near market close, so the
    live equity curve accrues. Best-effort; never raises into the scheduler."""
    try:
        n = await snapshot_equity(session_factory)
        logger.info("equity_snapshot_persisted", n_accounts=n)
    except Exception:
        logger.exception("equity_snapshot_failed")
