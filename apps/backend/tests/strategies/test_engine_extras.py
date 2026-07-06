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


# ---- crontab day-of-week normalization (the off-by-one fix) -------------------

@pytest.mark.parametrize(
    "crontab,expected",
    [
        ("0 14 * * 1", "0 14 * * mon"),       # the bug: cron 1=Mon, APScheduler 1=Tue
        ("0 14 * * 0", "0 14 * * sun"),       # cron 0=Sun
        ("0 14 * * 7", "0 14 * * sun"),       # cron 7=Sun (APScheduler rejects bare 7)
        ("0 14 * * 1-5", "0 14 * * mon-fri"), # range endpoints
        ("0 14 * * 1,3,5", "0 14 * * mon,wed,fri"),  # comma list
        ("0 14 * * mon", "0 14 * * mon"),     # already a name → unchanged
        ("0 14 * * *", "0 14 * * *"),         # wildcard → unchanged
        ("0 14 * * */2", "0 14 * * */2"),     # step → passed through untouched
        ("30 9 15 * *", "30 9 15 * *"),       # day-of-MONTH 15 must NOT be touched
        ("event", "event"),                   # non-5-field → unchanged
    ],
)
def test_normalize_crontab_dow(crontab, expected):
    from app.strategies.engine import _normalize_crontab_dow

    assert _normalize_crontab_dow(crontab) == expected


def test_normalized_weekly_cron_fires_on_monday():
    """★ The load-bearing assertion: '0 14 * * 1' must schedule a MONDAY fire, not
    Tuesday (the pre-fix behavior that made momentum-portfolio miss its rebalance)."""
    from apscheduler.triggers.cron import CronTrigger

    from app.strategies.engine import _normalize_crontab_dow

    base = datetime(2026, 6, 15, 11, 0, tzinfo=UTC)  # a Monday, pre-14:00
    trigger = CronTrigger.from_crontab(
        _normalize_crontab_dow("0 14 * * 1"), timezone=UTC
    )
    nxt = trigger.get_next_fire_time(None, base)
    assert nxt.weekday() == 0  # Monday
    assert (nxt.hour, nxt.minute) == (14, 0)


def test_strategy_schedule_is_eastern_time_pinned_across_dst():
    """★ The drift fix: strategy crons are evaluated in Eastern time, so a market-clock
    schedule fires at the same ET wall-time year-round — NOT a fixed UTC hour that slides
    vs the 09:30 open across daylight saving. '0 10 * * mon' = 10:00 ET in both seasons:
    14:00 UTC in summer (EDT) and 15:00 UTC in winter (EST)."""
    from zoneinfo import ZoneInfo

    from apscheduler.triggers.cron import CronTrigger

    from app.strategies.engine import _STRATEGY_SCHEDULE_TZ

    assert str(_STRATEGY_SCHEDULE_TZ) == "America/New_York"
    et = ZoneInfo("America/New_York")
    trigger = CronTrigger.from_crontab("0 10 * * mon", timezone=_STRATEGY_SCHEDULE_TZ)

    summer = trigger.get_next_fire_time(None, datetime(2026, 7, 6, 6, 0, tzinfo=UTC))
    assert (summer.astimezone(et).hour, summer.astimezone(et).minute) == (10, 0)
    assert summer.astimezone(UTC).hour == 14  # 10:00 EDT == 14:00 UTC

    winter = trigger.get_next_fire_time(None, datetime(2026, 1, 5, 6, 0, tzinfo=UTC))
    assert (winter.astimezone(et).hour, winter.astimezone(et).minute) == (10, 0)
    assert winter.astimezone(UTC).hour == 15  # 10:00 EST == 15:00 UTC
