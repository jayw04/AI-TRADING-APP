"""Branch-coverage backfill for StrategyEngine.

The base ``test_engine.py`` covers the happy paths (register / unregister /
fill routing / error containment / pine rejection). This file targets a
specific branch the base file doesn't exercise: the invalid-crontab
fallback to ``*/1 * * * *``. Per P2 Session 6 §6.2.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies import StrategyEngine

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1, ticker="AAPL", exchange="NASDAQ",
                asset_class="us_equity", name="Apple", active=True,
            )
        )
        await session.commit()


@pytest.fixture
async def engine(session_factory, seeded):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()

    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock()
    indicator_computer = MagicMock()
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=1))

    eng = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=bus,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )
    await asyncio.sleep(0)

    yield eng, scheduler

    await eng.shutdown()
    scheduler.shutdown(wait=False)


async def test_register_falls_back_when_crontab_is_invalid(
    engine, session_factory
):
    """A malformed schedule string must not block registration — engine
    falls back to '*/1 * * * *' and schedules the job."""
    eng, scheduler = engine
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1,
            name="bad-cron",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"],
            schedule="this is not a cron string",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    running = await eng.register(sid)

    assert running.job_id is not None
    job = scheduler.get_job(running.job_id)
    assert job is not None
    # The fallback schedule fires every minute.
    assert "minute='*/1'" in str(job.trigger)


async def test_register_rejects_unknown_strategy_id(engine):
    """Engine surfaces a StrategyLoadError (not an unhandled exception) when
    the row doesn't exist."""
    from app.strategies.loader import StrategyLoadError

    eng, _ = engine
    with pytest.raises(StrategyLoadError, match="not found"):
        await eng.register(99999)


async def test_register_rejects_when_no_paper_account(engine, session_factory):
    """No paper Account row for the strategy's user -> StrategyLoadError."""
    from app.strategies.loader import StrategyLoadError

    eng, _ = engine
    async with session_factory() as session:
        # User #2 has no Account row.
        session.add(User(id=2, email="jay2@test", display_name="Jay2"))
        await session.commit()

        row = StrategyRow(
            user_id=2,
            name="no-account",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={},
            symbols_json=["AAPL"],
            schedule="event",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    with pytest.raises(StrategyLoadError, match="no paper account"):
        await eng.register(sid)
