"""Durable per-strategy state — the Workstream B prerequisite.

The point of this mechanism is that it survives what an in-memory attribute does not: a reload. So
the tests exercise it against a real (in-memory SQLite) session, and the load-bearing one proves
that a value written by one context instance is read back by a FRESH instance — the reload the
in-memory `_last_rebalance_week` counter could never survive.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from app.db.base import Base
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.strategies.context import StrategyContext


def _strategy(**over):
    now = datetime.now(UTC)
    return Strategy(**{
        "user_id": 1, "name": "momentum-daily", "status": "IDLE",
        "params_json": {}, "symbols_json": [], "created_at": now, "updated_at": now, **over,
    })


@pytest_asyncio.fixture
async def sessionmaker_with_strategy():
    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    sf = async_sessionmaker(engine, expire_on_commit=False)
    async with sf() as s, s.begin():
        s.add(User(id=1, email="wsb@local.dev"))
        s.add(_strategy(id=1))
    yield sf
    await engine.dispose()


def _ctx(sf, strategy_id=1):
    return StrategyContext(
        strategy_id=strategy_id, user_id=1, account_id=1, symbols=["AAA"],
        session_factory=sf, bar_cache=None, indicator_computer=None,
        submit_order_fn=None,
    )


async def test_unset_key_returns_the_default(sessionmaker_with_strategy):
    ctx = _ctx(sessionmaker_with_strategy)
    assert await ctx.get_state("missing") is None
    assert await ctx.get_state("missing", 42) == 42


async def test_set_then_get_roundtrips_json(sessionmaker_with_strategy):
    ctx = _ctx(sessionmaker_with_strategy)
    await ctx.set_state("phase", "CHURN")
    await ctx.set_state("cycles", 3)
    await ctx.set_state("lifecycle", {"signal_date": "2026-07-14", "attempts": 2})
    assert await ctx.get_state("phase") == "CHURN"
    assert await ctx.get_state("cycles") == 3
    assert await ctx.get_state("lifecycle") == {"signal_date": "2026-07-14", "attempts": 2}


async def test_state_SURVIVES_a_fresh_context_instance(sessionmaker_with_strategy):
    """The whole reason this exists. Write with one instance, read with another — the reload an
    in-memory attribute cannot survive."""
    writer = _ctx(sessionmaker_with_strategy)
    await writer.set_state("last_completed_review", "2026-07-14")

    reloaded = _ctx(sessionmaker_with_strategy)          # a brand-new instance, as after a reload
    assert await reloaded.get_state("last_completed_review") == "2026-07-14"


async def test_set_overwrites_in_place_not_a_second_row(sessionmaker_with_strategy):
    ctx = _ctx(sessionmaker_with_strategy)
    await ctx.set_state("k", 1)
    await ctx.set_state("k", 2)
    assert await ctx.get_state("k") == 2
    # a second write must not create a duplicate row — the unique constraint would reject it and the
    # value must simply be the latest
    from sqlalchemy import func, select

    from app.db.models.strategy_state import StrategyState
    async with sessionmaker_with_strategy() as s:
        n = (await s.execute(
            select(func.count()).select_from(StrategyState).where(StrategyState.key == "k")
        )).scalar_one()
    assert n == 1


async def test_clear_state_removes_the_key(sessionmaker_with_strategy):
    ctx = _ctx(sessionmaker_with_strategy)
    await ctx.set_state("k", "v")
    await ctx.clear_state("k")
    assert await ctx.get_state("k", "gone") == "gone"


async def test_state_is_isolated_per_strategy(sessionmaker_with_strategy):
    """One strategy's state must never be visible to another — the FK and the (strategy_id, key)
    key enforce it."""
    async with sessionmaker_with_strategy() as s, s.begin():
        s.add(_strategy(id=2, name="other"))
    a = _ctx(sessionmaker_with_strategy, strategy_id=1)
    b = _ctx(sessionmaker_with_strategy, strategy_id=2)
    await a.set_state("shared_key", "A-value")
    await b.set_state("shared_key", "B-value")
    assert await a.get_state("shared_key") == "A-value"
    assert await b.get_state("shared_key") == "B-value"


async def test_none_is_a_storable_value_distinct_from_unset(sessionmaker_with_strategy):
    ctx = _ctx(sessionmaker_with_strategy)
    await ctx.set_state("explicit_none", None)
    # the row exists with value None; get_state returns None either way, but the row must be present
    from sqlalchemy import func, select

    from app.db.models.strategy_state import StrategyState
    async with sessionmaker_with_strategy() as s:
        n = (await s.execute(
            select(func.count()).select_from(StrategyState).where(
                StrategyState.key == "explicit_none")
        )).scalar_one()
    assert n == 1
    assert await ctx.get_state("explicit_none", "default") is None


@pytest.mark.parametrize("bad", ["not-json-safe-object"])
async def test_arbitrary_json_scalars_and_containers(sessionmaker_with_strategy, bad):
    ctx = _ctx(sessionmaker_with_strategy)
    await ctx.set_state("list", [1, 2, 3])
    await ctx.set_state("float", 1.5)
    await ctx.set_state("bool", True)
    assert await ctx.get_state("list") == [1, 2, 3]
    assert await ctx.get_state("float") == 1.5
    assert await ctx.get_state("bool") is True
    _ = bad
