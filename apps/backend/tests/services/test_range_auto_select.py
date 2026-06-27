"""Daily Range-Trader universe auto-selection (design §"Top 3–5 candidates").

Covers discovery (opt-in marker), the orchestration (stop → set symbols → start → audit),
its idempotent / not-running / no-candidate branches, and the scheduled entry (weekend skip,
fan-out). Uses an in-memory DB + a fake engine that mirrors register/unregister status flips.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest_asyncio
from sqlalchemy import func, select

from app.audit.logger import AuditAction
from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.services.range_auto_select import (
    AUTOSELECT_SOURCE,
    find_autoselect_range_strategies,
    refresh_range_universe,
    run_daily_range_universe,
    select_range_universe,
)

RANGE_CODE = "templates/range_trader.py"
# Times for the schedule gates (June = EDT, UTC-4):
SATURDAY = datetime(2026, 6, 27, 13, 0, tzinfo=UTC)        # weekend
WEEKDAY = datetime(2026, 6, 26, 13, 0, tzinfo=UTC)         # Fri 09:00 ET — pre-open (valid)
WEEKDAY_AFTER_OPEN = datetime(2026, 6, 26, 14, 0, tzinfo=UTC)  # Fri 10:00 ET — RTH, frozen


def _range_bound_bars() -> pd.DataFrame:
    end = pd.Timestamp(2026, 6, 25, 13, tz="UTC")
    dates = [end - pd.Timedelta(days=24 - i) for i in range(25)]
    return pd.DataFrame(
        {"t": dates, "o": [100.0] * 25, "h": [103.0] * 25, "l": [98.0] * 25,
         "c": [100.0] * 25, "v": [1_000_000] * 25}
    )


class _FakeBarCache:
    async def get_bars(self, symbol: str, tf: str, start: Any, end: Any) -> pd.DataFrame:
        return _range_bound_bars()


class _FakeEngine:
    """Mirrors the real engine's status flips so was_running / restart logic is exercised."""

    def __init__(self, session_factory: Any) -> None:
        self._sf = session_factory
        self.unregister_calls: list[tuple[int, str]] = []
        self.register_calls: list[int] = []

    async def unregister(self, strategy_id: int, *, reason: str = "user_stop") -> None:
        self.unregister_calls.append((strategy_id, reason))
        async with self._sf() as s:
            row = await s.get(StrategyRow, strategy_id)
            if row is not None:
                row.status = StrategyStatus.IDLE
                await s.commit()

    async def register(self, strategy_id: int) -> object:
        self.register_calls.append(strategy_id)
        async with self._sf() as s:
            row = await s.get(StrategyRow, strategy_id)
            if row is not None:
                row.status = StrategyStatus.PAPER
                await s.commit()
        return object()


@pytest_asyncio.fixture
async def db() -> AsyncIterator[Any]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield get_sessionmaker()
    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def _seed_strategy(
    session_factory: Any, *, symbols: list[str], status: StrategyStatus,
    params: dict[str, Any], parent_id: int | None = None,
) -> int:
    now = datetime.now(UTC)
    async with session_factory() as s:
        row = StrategyRow(
            user_id=1, name="Range", version="0.1.0", type=StrategyType.PYTHON,
            status=status, code_path=RANGE_CODE, params_json=params, symbols_json=symbols,
            schedule="*/5 * * * *", parent_strategy_id=parent_id,
            created_at=now, updated_at=now,
        )
        s.add(row)
        await s.flush()
        sid = row.id
        await s.commit()
    return sid


async def _paper_account(session_factory: Any, user_id: int = 1) -> int:
    async with session_factory() as s:
        acct = (
            await s.execute(
                select(Account).where(
                    Account.user_id == user_id, Account.broker == "alpaca",
                    Account.mode == AccountMode.paper,
                )
            )
        ).scalars().first()
        if acct is None:
            acct = Account(user_id=user_id, broker="alpaca", mode=AccountMode.paper)
            s.add(acct)
            await s.flush()
        aid = acct.id
        await s.commit()
    return aid


async def _symbol_id(session_factory: Any, ticker: str) -> int:
    async with session_factory() as s:
        sym = (await s.execute(select(Symbol).where(Symbol.ticker == ticker))).scalars().first()
        if sym is None:
            sym = Symbol(ticker=ticker)
            s.add(sym)
            await s.flush()
        sid = sym.id
        await s.commit()
    return sid


async def _seed_position(session_factory: Any, *, ticker: str, qty: int, user_id: int = 1) -> None:
    aid = await _paper_account(session_factory, user_id)
    syid = await _symbol_id(session_factory, ticker)
    async with session_factory() as s:
        s.add(Position(
            user_id=user_id, account_id=aid, symbol_id=syid, qty=qty, side="long",
            updated_at=datetime.now(UTC),
        ))
        await s.commit()


async def _seed_order(
    session_factory: Any, *, strategy_id: int, ticker: str, status: OrderStatus, user_id: int = 1
) -> None:
    aid = await _paper_account(session_factory, user_id)
    syid = await _symbol_id(session_factory, ticker)
    async with session_factory() as s:
        now = datetime.now(UTC)
        s.add(Order(
            user_id=user_id, account_id=aid, symbol_id=syid, side=OrderSide.BUY, qty=1,
            type=OrderType.MARKET, tif=TimeInForce.DAY, status=status,
            source_type=OrderSourceType.STRATEGY, source_id=str(strategy_id),
            created_at=now, updated_at=now,
        ))
        await s.commit()


# ---- discovery ----

async def test_find_autoselect_only_marked_non_variants(db) -> None:
    marked = await _seed_strategy(db, symbols=["X"], status=StrategyStatus.PAPER,
                                  params={"auto_select_top_n": 3})
    await _seed_strategy(db, symbols=["Y"], status=StrategyStatus.PAPER, params={})  # no marker
    await _seed_strategy(db, symbols=["Z"], status=StrategyStatus.PAPER,
                         params={"auto_select_top_n": 5}, parent_id=marked)  # variant
    async with db() as s:
        targets = await find_autoselect_range_strategies(s)
    assert targets == [(marked, 3, None)]


async def test_find_autoselect_carries_universe_override(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["X"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB"]},
    )
    async with db() as s:
        targets = await find_autoselect_range_strategies(s)
    assert targets == [(sid, 2, ["AAA", "BBB"])]


# ---- selection ----

async def test_select_range_universe_returns_top_n(db) -> None:
    async with db() as s:
        picks = await select_range_universe(
            s, bar_cache=_FakeBarCache(), n=2, universe=["CCC", "AAA", "BBB"], now=WEEKDAY
        )
    # Identical bars → structural tie broken by symbol asc → top-2 = AAA, BBB.
    assert picks == ["AAA", "BBB"]


# ---- orchestration ----

async def test_refresh_applies_and_restarts_running_strategy(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "applied"
    assert out["selected"] == ["AAA", "BBB"] and out["previous"] == ["ZZZ"]
    assert out["restarted"] is True
    # stop-then-start happened exactly once each.
    assert engine.unregister_calls == [(sid, "daily_range_autoselect")]
    assert engine.register_calls == [sid]
    # row now carries the new universe and is running again.
    async with db() as s:
        row = await s.get(StrategyRow, sid)
        assert row.symbols_json == ["AAA", "BBB"]
        assert row.status == StrategyStatus.PAPER
        audits = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == AuditAction.STRATEGY_UPDATED.value)
            )
        ).scalars().all()
    assert len(audits) == 1
    payload = json.loads(audits[0].payload_json)
    assert payload["source"] == AUTOSELECT_SOURCE
    assert payload["changed"]["symbols"] == ["AAA", "BBB"]
    assert payload["previous"] == ["ZZZ"]
    assert audits[0].actor_type == "system"


async def test_refresh_unchanged_is_a_noop(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["AAA", "BBB"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2},
    )
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "unchanged"
    assert engine.unregister_calls == [] and engine.register_calls == []


async def test_refresh_idle_strategy_updates_without_restart(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.IDLE,
        params={"auto_select_top_n": 2},
    )
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "applied" and out["restarted"] is False
    assert engine.unregister_calls == [] and engine.register_calls == []
    async with db() as s:
        row = await s.get(StrategyRow, sid)
        assert row.symbols_json == ["AAA", "BBB"]
        assert row.status == StrategyStatus.IDLE  # left idle — activation stays a user action


async def test_refresh_skips_live_strategy(db) -> None:
    # ADR 0028: LIVE books are out of scope — the job must skip them, not cycle them through
    # IDLE (which would downgrade LIVE→PAPER). No engine calls, universe untouched.
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.LIVE,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "skipped_live"
    assert engine.unregister_calls == [] and engine.register_calls == []
    async with db() as s:
        row = await s.get(StrategyRow, sid)
        assert row.symbols_json == ["ZZZ"]
        assert row.status == StrategyStatus.LIVE  # untouched


async def test_refresh_skips_when_open_position(db) -> None:
    # ADR 0028 / review #6: don't stop→start a running sleeve that holds a position.
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    await _seed_position(db, ticker="ZZZ", qty=10)  # open position in the held symbol
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "skipped_open_position"
    assert engine.unregister_calls == [] and engine.register_calls == []
    async with db() as s:
        assert (await s.get(StrategyRow, sid)).symbols_json == ["ZZZ"]  # untouched


async def test_refresh_ignores_position_in_unheld_symbol(db) -> None:
    # A position in a symbol the sleeve does NOT trade must not block the rotation.
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    await _seed_position(db, ticker="QQQ", qty=10)  # unrelated holding
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "applied"
    assert engine.register_calls == [sid]


async def test_refresh_skips_when_pending_order(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    await _seed_order(db, strategy_id=sid, ticker="ZZZ", status=OrderStatus.SUBMITTED)  # working
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "skipped_pending_order"
    assert engine.unregister_calls == [] and engine.register_calls == []


async def test_refresh_ignores_terminal_order(db) -> None:
    # A filled (terminal) order from this strategy must not block.
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    await _seed_order(db, strategy_id=sid, ticker="ZZZ", status=OrderStatus.FILLED)
    engine = _FakeEngine(db)
    out = await refresh_range_universe(
        db, engine, _FakeBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB", "CCC"], now=WEEKDAY,
    )
    assert out["status"] == "applied"


async def test_run_daily_skips_after_market_open(db) -> None:
    # Once RTH has begun the day's universe is frozen — no intraday rotation (review #2).
    await _seed_strategy(db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
                         params={"auto_select_top_n": 2})
    out = await run_daily_range_universe(
        db, _FakeEngine(db), _FakeBarCache(), now=WEEKDAY_AFTER_OPEN
    )
    assert out == []


async def test_refresh_no_candidates_leaves_strategy_untouched(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2},
    )
    engine = _FakeEngine(db)

    class _EmptyBarCache:
        async def get_bars(self, *a: Any, **k: Any) -> pd.DataFrame:
            return pd.DataFrame()  # insufficient_data → nothing suitable

    out = await refresh_range_universe(
        db, engine, _EmptyBarCache(), strategy_id=sid, n=2,
        universe=["AAA", "BBB"], now=WEEKDAY,
    )
    assert out["status"] == "no_candidates"
    assert engine.unregister_calls == [] and engine.register_calls == []
    async with db() as s:
        row = await s.get(StrategyRow, sid)
        assert row.symbols_json == ["ZZZ"]  # unchanged


# ---- scheduled entry ----

async def test_run_daily_skips_weekend(db) -> None:
    await _seed_strategy(db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
                         params={"auto_select_top_n": 2})
    out = await run_daily_range_universe(db, _FakeEngine(db), _FakeBarCache(), now=SATURDAY)
    assert out == []


async def test_run_daily_no_targets_returns_empty(db) -> None:
    await _seed_strategy(db, symbols=["Y"], status=StrategyStatus.PAPER, params={})  # no marker
    out = await run_daily_range_universe(db, _FakeEngine(db), _FakeBarCache(), now=WEEKDAY)
    assert out == []


async def test_run_daily_applies_each_target(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 2, "auto_select_universe": ["AAA", "BBB", "CCC"]},
    )
    out = await run_daily_range_universe(db, _FakeEngine(db), _FakeBarCache(), now=WEEKDAY)
    assert len(out) == 1
    assert out[0]["strategy_id"] == sid and out[0]["status"] == "applied"
    assert out[0]["selected"] == ["AAA", "BBB"]


async def test_run_daily_unwired_is_safe(db) -> None:
    out = await run_daily_range_universe(db, None, None, now=WEEKDAY)
    assert out == []


async def test_audit_chain_single_row_per_apply(db) -> None:
    sid = await _seed_strategy(
        db, symbols=["ZZZ"], status=StrategyStatus.PAPER,
        params={"auto_select_top_n": 1, "auto_select_universe": ["AAA", "BBB"]},
    )
    await refresh_range_universe(db, _FakeEngine(db), _FakeBarCache(),
                                 strategy_id=sid, n=1, universe=["AAA", "BBB"], now=WEEKDAY)
    async with db() as s:
        n = (await s.execute(select(func.count()).select_from(AuditLog))).scalar_one()
    assert n == 1
