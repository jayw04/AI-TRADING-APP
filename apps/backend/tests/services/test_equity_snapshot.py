"""Equity-snapshot persistence tests (P12.5)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user import User
from app.services.day_change_basis import BROKER_LAST_EQUITY
from app.services.equity_snapshot import run_daily_equity_snapshot, snapshot_equity


async def _seed(session_factory, equity: str = "10000") -> None:
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"))
        session.add(AccountState(
            day_change_basis=BROKER_LAST_EQUITY,
            account_id=1, cash=Decimal("2000"), equity=Decimal(equity),
            last_equity=Decimal(equity), buying_power=Decimal("0"),
            portfolio_value=Decimal(equity), day_change_pct=Decimal("0.012"),
            updated_at=datetime.now(UTC),
        ))
        await session.commit()


async def test_snapshot_appends_one_per_account(session_factory) -> None:
    await _seed(session_factory, "10208")
    n = await snapshot_equity(session_factory)
    assert n == 1
    async with session_factory() as session:
        rows = (await session.execute(select(EquitySnapshot))).scalars().all()
        assert len(rows) == 1
        assert rows[0].account_id == 1
        assert rows[0].equity == Decimal("10208.0000")
        assert rows[0].day_change_pct == Decimal("0.012000")


async def test_snapshot_is_append_only_time_series(session_factory) -> None:
    await _seed(session_factory)
    await snapshot_equity(session_factory)
    await snapshot_equity(session_factory)  # second tick appends, never overwrites
    async with session_factory() as session:
        rows = (await session.execute(select(EquitySnapshot))).scalars().all()
        assert len(rows) == 2  # time series


async def test_snapshot_no_accounts_is_clean_noop(session_factory) -> None:
    assert await snapshot_equity(session_factory) == 0


async def test_daily_entrypoint_best_effort(session_factory) -> None:
    await _seed(session_factory)
    await run_daily_equity_snapshot(session_factory)  # should not raise

    def _bad():
        raise RuntimeError("db gone")

    await run_daily_equity_snapshot(_bad)  # swallows + logs, no raise
