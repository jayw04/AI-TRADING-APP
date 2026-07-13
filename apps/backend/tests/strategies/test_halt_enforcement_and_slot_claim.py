"""P0 (incident 2026-07-13): HALTED must stop DISPATCH, and a slot must run once.

Two defects, both proven live on 2026-07-13 on account 1 (momentum-portfolio):

1. HALT WAS NEVER ENFORCED AT DISPATCH. The circuit breaker tripped at 09:30:25 ET and set
   ``strategies.status = HALTED``. Nothing removed the strategy from the engine's ``_running``
   map, and ``_dispatch_bar_tick`` consulted ONLY ``_running`` — so at 10:00 ET the halted
   strategy dispatched anyway and fired 18 order proposals into the risk engine. Every one
   was rejected.

   ADR 0004 names this exact behaviour and says the HALTED status exists to prevent it:

       "A strategy that submits an order, gets a CIRCUIT_BREAKER rejection, and tries again
        on the next bar tick is not actually stopped — it's spinning at maximum rate. The
        HALTED status is the engine-level signal that the strategy should not be dispatched."

   It was written down and never implemented.

2. THE SLOT RAN SIX TIMES. 14:00:03 -> 14:00:52 UTC, re-proposing the same SNDK/LITE trims on
   every pass. The load-bearing semantic: **a run whose every order was risk-rejected is a
   COMPLETED run.** It happened; it was refused. Treating "no orders landed" as "nothing
   happened, try again" is what produced the repeat.

Both gates FAIL CLOSED. A status we cannot read, or a claim we cannot write, is not
permission to trade.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_slot_claim import (
    SLOT_COMPLETED,
    StrategySlotClaim,
)
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.strategies.engine import StrategyEngine

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


def _now() -> datetime:
    return datetime.now(UTC)


def _bars() -> pd.DataFrame:
    ts = pd.date_range("2026-07-13 09:30", periods=2, freq="1min", tz="America/New_York")
    return pd.DataFrame(
        {"t": ts, "o": [1.0, 1.0], "h": [1.0, 1.0], "l": [1.0, 1.0], "c": [1.0, 1.0], "v": [10, 10]}
    )


@pytest.fixture
async def eng(session_factory):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_bars())
    engine = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=EventBus(),
        bar_cache=bar_cache,
        indicator_computer=MagicMock(),
        order_router=MagicMock(submit=AsyncMock(return_value=MagicMock(id=1))),
        strategies_root=FIXTURES_ROOT,
    )
    await asyncio.sleep(0)
    yield engine
    await engine.shutdown()
    scheduler.shutdown(wait=False)


async def _seed(session_factory) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Alpaca Paper"))
        s.add(
            Symbol(
                id=1, ticker="AAPL", exchange="NASDAQ",
                asset_class="us_equity", name="Apple", active=True,
            )
        )
        row = StrategyRow(
            user_id=1, name="momentum-like", version="1.0.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"}, symbols_json=["AAPL"],
            schedule="event", created_at=_now(), updated_at=_now(),
        )
        s.add(row)
        await s.commit()
        return row.id


async def _set_status(session_factory, sid: int, status: StrategyStatus) -> None:
    async with session_factory() as s:
        row = await s.get(StrategyRow, sid)
        row.status = status
        await s.commit()


async def _claims(session_factory) -> list[StrategySlotClaim]:
    async with session_factory() as s:
        return list(
            (await s.execute(select(StrategySlotClaim).order_by(StrategySlotClaim.id)))
            .scalars()
            .all()
        )


# ------------------------------------------------------------------ P0-1: HALTED stops dispatch


async def test_halted_strategy_is_not_dispatched(eng, session_factory, monkeypatch):
    """THE INCIDENT. The breaker halts the strategy; the engine must not dispatch it.

    Note the setup mirrors reality exactly: the strategy is registered and LIVE in ``_running``,
    and only the PERSISTED status changes underneath it — which is precisely what a breaker
    trip does. An engine that trusts ``_running`` sails straight through this.
    """
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)

    await _set_status(session_factory, sid, StrategyStatus.HALTED)  # the breaker trips

    await eng._dispatch_bar_tick(strategy_id=sid)

    on_bar.assert_not_awaited()
    assert await _claims(session_factory) == [], "a halted strategy must not even claim a slot"


async def test_status_is_read_at_dispatch_time_not_at_schedule_time(eng, session_factory, monkeypatch):
    """The status can change BETWEEN the job being queued and the job starting — the breaker
    tripped at 09:30, half an hour after the scheduler had already armed the 10:00 slot. So the
    check must be a live read, not a cached value captured at registration."""
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)

    await eng._dispatch_bar_tick(strategy_id=sid)   # runnable -> dispatches
    assert on_bar.await_count == 1

    await _set_status(session_factory, sid, StrategyStatus.HALTED)
    await eng._dispatch_bar_tick(strategy_id=sid)   # halted mid-flight -> must not dispatch
    assert on_bar.await_count == 1, "dispatch used a stale status"


async def test_halt_gate_fails_closed_when_status_is_unreadable(eng, session_factory, monkeypatch):
    """A database we cannot query is NOT permission to trade."""
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)
    monkeypatch.setattr(
        eng, "_session_factory", MagicMock(side_effect=RuntimeError("database is locked"))
    )

    await eng._dispatch_bar_tick(strategy_id=sid)

    on_bar.assert_not_awaited()


@pytest.mark.parametrize("status", [StrategyStatus.HALTED, StrategyStatus.IDLE, StrategyStatus.ERROR])
async def test_no_dispatch_for_any_non_runnable_status(eng, session_factory, monkeypatch, status):
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)

    await _set_status(session_factory, sid, status)
    await eng._dispatch_bar_tick(strategy_id=sid)

    on_bar.assert_not_awaited()


async def test_overlay_tick_is_also_gated(eng, session_factory, monkeypatch):
    """momentum-portfolio has a DAILY overlay armed for 15:00 ET. Without this gate it would
    have fired a second wave of proposals hours after the breaker had halted it."""
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    tick = AsyncMock()
    monkeypatch.setattr(running.instance, "on_overlay_tick", tick, raising=False)

    await _set_status(session_factory, sid, StrategyStatus.HALTED)
    await eng._dispatch_overlay_tick(strategy_id=sid)

    tick.assert_not_awaited()


# ------------------------------------------------------------------ P0-2: one run per slot


async def test_slot_runs_once(eng, session_factory, monkeypatch):
    """Six dispatches of the SAME scheduled slot -> exactly one run."""
    sid = await _seed(session_factory)
    running = await eng.register(sid)
    on_bar = AsyncMock()
    monkeypatch.setattr(running.instance, "on_bar", on_bar)

    for _ in range(6):  # the exact repeat count from the incident
        await eng._dispatch_bar_tick(strategy_id=sid)

    assert on_bar.await_count == 1, "the slot ran more than once"
    claims = await _claims(session_factory)
    assert len(claims) == 1
    assert claims[0].outcome == SLOT_COMPLETED


async def test_an_all_rejected_run_still_claims_the_slot(eng, session_factory, monkeypatch):
    """THE LOAD-BEARING SEMANTIC. On 2026-07-13 every proposal was rejected by the daily-loss
    gate, so no orders landed — and the strategy took that as licence to try again.

    A run that reached signal generation and risk evaluation is COMPLETE. It happened; it was
    refused. 'No orders landed' is not 'nothing happened'.
    """
    sid = await _seed(session_factory)
    running = await eng.register(sid)

    # on_bar runs to completion but every order it proposes is rejected -> zero orders.
    monkeypatch.setattr(running.instance, "on_bar", AsyncMock())
    eng._order_router.submit = AsyncMock(
        return_value=MagicMock(id=None, rejection_reason="CIRCUIT_BREAKER")
    )

    await eng._dispatch_bar_tick(strategy_id=sid)
    await eng._dispatch_bar_tick(strategy_id=sid)  # the retry that must NOT happen

    claims = await _claims(session_factory)
    assert len(claims) == 1
    assert claims[0].outcome == SLOT_COMPLETED, (
        "an all-rejected run must be recorded as COMPLETED, not left open for a retry"
    )


async def test_uniqueness_is_enforced_in_the_database_not_in_memory(session_factory):
    """Process memory is not a safety boundary — it does not survive a restart, and a second
    scheduler would not see it. The UNIQUE constraint is the control."""
    from sqlalchemy.exc import IntegrityError

    sid = await _seed(session_factory)
    key = {
        "account_id": 1, "strategy_id": sid, "scheduled_slot": "2026-07-13T10:00",
        "strategy_version": "1.0.0", "retry_generation": 0,
    }
    async with session_factory() as s:
        s.add(StrategySlotClaim(**key, claimed_at=_now(), outcome=SLOT_COMPLETED))
        await s.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as s:
            s.add(StrategySlotClaim(**key, claimed_at=_now(), outcome=SLOT_COMPLETED))
            await s.commit()


async def test_an_explicit_retry_generation_can_rerun_a_slot(session_factory):
    """Retry must be a deliberate, RECORDED act — never a side effect of failure, and never by
    deleting the original claim."""
    sid = await _seed(session_factory)
    base = {
        "account_id": 1, "strategy_id": sid, "scheduled_slot": "2026-07-13T10:00",
        "strategy_version": "1.0.0",
    }
    async with session_factory() as s:
        s.add(StrategySlotClaim(**base, retry_generation=0, claimed_at=_now(), outcome=SLOT_COMPLETED))
        s.add(
            StrategySlotClaim(
                **base, retry_generation=1, claimed_at=_now(), outcome=SLOT_COMPLETED,
                retry_reason="operator: re-run after ADR 0042 corrective release",
            )
        )
        await s.commit()

    claims = await _claims(session_factory)
    assert len(claims) == 2
    assert claims[1].retry_reason is not None, "a retry must carry its justification"
