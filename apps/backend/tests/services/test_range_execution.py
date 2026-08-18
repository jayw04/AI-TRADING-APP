"""capture_window — materializes the daily SET range levels + high/low into range_execution_records.

The buy/sell columns hold the strategy's SET daily fade levels (from its ``range_levels`` INFO signal),
not fills. Uses a stub bar cache and dates relative to *now* (yesterday = a completed day; today =
incomplete) so the test is independent of the wall clock.
"""

from __future__ import annotations

from datetime import UTC, datetime, time, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.range_execution_record import RangeExecutionRecord
from app.db.models.signal import Signal, SignalType
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.range_execution import capture_window

_ET = ZoneInfo("America/New_York")


class _StubBarCache:
    """Returns a one-row 1Day frame for each (symbol, date) it knows; empty otherwise."""

    def __init__(self, hl: dict) -> None:
        self._hl = hl  # {(symbol, date): (low, high)}

    async def get_bars(self, symbol, timeframe, start, end):  # noqa: ANN001, ARG002
        rows = [
            {
                "t": pd.Timestamp(d.isoformat(), tz="UTC"),
                "o": lo,
                "h": hi,
                "l": lo,
                "c": hi,
                "v": 1.0,
            }
            for (sym, d), (lo, hi) in self._hl.items()
            if sym == symbol
        ]
        return pd.DataFrame(rows, columns=["t", "o", "h", "l", "c", "v"])


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory, day) -> None:
    async with factory() as s:
        s.add(User(id=2, email="range@test"))
        s.add(
            Symbol(
                id=1,
                ticker="MU",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Micron",
                active=True,
            )
        )
        s.add(
            Strategy(
                id=1,
                user_id=2,
                name="Range Trader Top-5",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="x.py",
                params_json={},
                symbols_json=["MU"],
                schedule="*/5 * * * *",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        # The strategy logs its SET fade levels for the day as a range_levels INFO signal (10:05 ET).
        received = datetime.combine(day, time(14, 5), tzinfo=UTC)
        s.add(
            Signal(
                user_id=2,
                strategy_id=1,
                symbol_id=1,
                type=SignalType.INFO,
                payload_json={
                    "kind": "range_levels",
                    "buy": 909.89,
                    "sell": 935.38,
                    "stop": 905.34,
                    "at_price": 918.42,
                },
                received_at=received,
            )
        )
        await s.commit()


async def test_capture_freezes_and_is_idempotent(session_factory) -> None:
    yesterday = datetime.now(_ET).date() - timedelta(days=1)
    await _seed(session_factory, yesterday)
    bc = _StubBarCache({("MU", yesterday): (Decimal("891.75"), Decimal("941.32"))})

    async with session_factory() as s:
        n = await capture_window(s, bc, yesterday, yesterday)
    assert n == 1

    async with session_factory() as s:
        r = (await s.execute(select(RangeExecutionRecord))).scalars().one()
        assert r.symbol == "MU"
        assert r.et_date == yesterday
        assert r.avg_buy_price == Decimal("909.89")  # the SET daily buy level (range_levels)
        assert r.avg_sell_price == Decimal("935.38")  # the SET daily sell level
        assert r.daily_low == Decimal("891.75")
        assert r.daily_high == Decimal("941.32")

    # Freeze: a second capture over the same window inserts nothing.
    async with session_factory() as s:
        n2 = await capture_window(s, bc, yesterday, yesterday)
    assert n2 == 0


async def test_capture_skips_incomplete_today(session_factory) -> None:
    today = datetime.now(_ET).date()
    await _seed(session_factory, today)
    bc = _StubBarCache({("MU", today): (Decimal("1"), Decimal("2"))})
    async with session_factory() as s:
        n = await capture_window(s, bc, today, today)
    assert n == 0  # today has not closed → not frozen


# ---- per-day book membership (the Top-5 rotates its slots) ----

_TICKERS = {1: "MU", 2: "TSLA", 3: "META", 4: "NFLX"}


async def _seed_book(factory, published: dict, *, roster: list[str]) -> None:
    """Seed the Range Trader plus its ``range_levels`` signals.

    ``published`` is {day: [tickers]} — the symbols that logged levels that day. ``roster`` is the
    strategy's CURRENT symbols_json, which must not leak into past days.
    """
    async with factory() as s:
        s.add(User(id=2, email="range@test"))
        for sid, tk in _TICKERS.items():
            s.add(
                Symbol(
                    id=sid,
                    ticker=tk,
                    exchange="NASDAQ",
                    asset_class="us_equity",
                    name=tk,
                    active=True,
                )
            )
        s.add(
            Strategy(
                id=1,
                user_id=2,
                name="Range Trader Top-5",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER,
                code_path="x.py",
                params_json={},
                symbols_json=roster,
                schedule="*/5 * * * *",
                created_at=_now(),
                updated_at=_now(),
            )
        )
        by_ticker = {tk: sid for sid, tk in _TICKERS.items()}
        for day, tickers in published.items():
            for tk in tickers:
                s.add(
                    Signal(
                        user_id=2,
                        strategy_id=1,
                        symbol_id=by_ticker[tk],
                        type=SignalType.INFO,
                        payload_json={
                            "kind": "range_levels",
                            "buy": 10.0,
                            "sell": 20.0,
                            "stop": 9.0,
                            "at_price": 15.0,
                        },
                        received_at=datetime.combine(day, time(14, 5), tzinfo=UTC),
                    )
                )
        await s.commit()


def _all_days_bars(days, tickers) -> _StubBarCache:
    return _StubBarCache({(tk, d): (Decimal("1"), Decimal("2")) for d in days for tk in tickers})


async def _captured(factory) -> set:
    async with factory() as s:
        rows = (await s.execute(select(RangeExecutionRecord))).scalars().all()
    return {(r.et_date, r.symbol, r.avg_buy_price is not None) for r in rows}


async def test_rotation_does_not_mint_blank_rows_for_days_a_name_was_not_held(
    session_factory,
) -> None:
    """The reported defect: rotating the 5th slot retroactively blanked every earlier day.

    Capturing a window that spans a rotation must not create rows for the incoming name on days
    before it joined, nor for the outgoing name on days after it left."""
    d1 = datetime.now(_ET).date() - timedelta(days=2)
    d2 = d1 + timedelta(days=1)
    await _seed_book(
        session_factory, {d1: ["MU", "TSLA"], d2: ["MU", "META"]}, roster=["MU", "META"]
    )
    bc = _all_days_bars([d1, d2], ["MU", "TSLA", "META"])

    async with session_factory() as s:
        await capture_window(s, bc, d1, d2)

    assert await _captured(session_factory) == {
        (d1, "MU", True),
        (d1, "TSLA", True),
        (d2, "MU", True),
        (d2, "META", True),
    }


async def test_outage_day_keeps_the_running_book_with_blank_levels(session_factory) -> None:
    """A day the stack was down publishes nothing — it stays visible as blank-level rows for the
    book that was actually running, not for today's roster."""
    d1 = datetime.now(_ET).date() - timedelta(days=2)
    d2 = d1 + timedelta(days=1)
    await _seed_book(session_factory, {d1: ["MU", "TSLA"]}, roster=["MU", "META"])
    bc = _all_days_bars([d1, d2], ["MU", "TSLA", "META"])

    async with session_factory() as s:
        await capture_window(s, bc, d1, d2)

    assert await _captured(session_factory) == {
        (d1, "MU", True),
        (d1, "TSLA", True),
        (d2, "MU", False),
        (d2, "TSLA", False),  # outage → carried forward, levels blank
    }


async def test_single_symbol_emit_failure_stays_visible_as_a_gap(session_factory) -> None:
    """One name failing to publish is a gap, not a rotation — it keeps its blank row."""
    d1 = datetime.now(_ET).date() - timedelta(days=2)
    d2 = d1 + timedelta(days=1)
    await _seed_book(session_factory, {d1: ["MU", "TSLA"], d2: ["MU"]}, roster=["MU", "TSLA"])
    bc = _all_days_bars([d1, d2], ["MU", "TSLA"])

    async with session_factory() as s:
        await capture_window(s, bc, d1, d2)

    assert await _captured(session_factory) == {
        (d1, "MU", True),
        (d1, "TSLA", True),
        (d2, "MU", True),
        (d2, "TSLA", False),  # TSLA did not emit → gap row
    }


async def test_window_opening_on_an_outage_day_uses_the_prior_membership(session_factory) -> None:
    """Membership carries in from *before* the window, so a narrow query around an outage does not
    attribute the day to today's roster."""
    d0 = datetime.now(_ET).date() - timedelta(days=3)
    d1 = d0 + timedelta(days=1)
    await _seed_book(session_factory, {d0: ["MU", "TSLA"]}, roster=["MU", "META"])
    bc = _all_days_bars([d0, d1], ["MU", "TSLA", "META"])

    async with session_factory() as s:
        await capture_window(s, bc, d1, d1)  # window starts on the outage day

    assert await _captured(session_factory) == {(d1, "MU", False), (d1, "TSLA", False)}


async def test_multi_rotation_window_rows_equal_daily_membership(session_factory) -> None:
    """#390 regression: a query spanning two rotations (TSLA -> META -> NFLX) must produce, for
    every day, exactly that day's membership — never the window-wide symbol union."""
    d1 = datetime.now(_ET).date() - timedelta(days=4)
    d2, d3 = d1 + timedelta(days=1), d1 + timedelta(days=2)
    published = {d1: ["MU", "TSLA"], d2: ["MU", "META"], d3: ["MU", "NFLX"]}
    await _seed_book(session_factory, published, roster=["MU", "NFLX"])
    bc = _all_days_bars([d1, d2, d3], ["MU", "TSLA", "META", "NFLX"])

    async with session_factory() as s:
        await capture_window(s, bc, d1, d3)

    async with session_factory() as s:
        rows = (await s.execute(select(RangeExecutionRecord))).scalars().all()
    rows_by_day: dict = {}
    for r in rows:
        rows_by_day.setdefault(r.et_date, set()).add(r.symbol)
        assert r.avg_buy_price is not None and r.avg_sell_price is not None
    assert rows_by_day == {d: set(tks) for d, tks in published.items()}


async def test_spanning_requery_cannot_mint_or_alter_frozen_rows(session_factory) -> None:
    """The production failure mode: each day is captured near its close; much later one query spans
    every rotation. That re-query must insert nothing — no phantom row for a rotated name on a day
    it was not held — and must leave every frozen row byte-identical."""
    d1 = datetime.now(_ET).date() - timedelta(days=4)
    d2, d3 = d1 + timedelta(days=1), d1 + timedelta(days=2)
    published = {d1: ["MU", "TSLA"], d2: ["MU", "META"], d3: ["MU", "NFLX"]}
    await _seed_book(session_factory, published, roster=["MU", "NFLX"])
    bc = _all_days_bars([d1, d2, d3], ["MU", "TSLA", "META", "NFLX"])

    for d in (d1, d2, d3):
        async with session_factory() as s:
            await capture_window(s, bc, d, d)

    async def _snapshot() -> set:
        async with session_factory() as s:
            rows = (await s.execute(select(RangeExecutionRecord))).scalars().all()
        return {(r.id, r.et_date, r.symbol, r.avg_buy_price, r.avg_sell_price) for r in rows}

    before = await _snapshot()
    async with session_factory() as s:
        n = await capture_window(s, bc, d1, d3)  # the rotation-spanning re-query
    assert n == 0
    assert await _snapshot() == before
