"""PdtAnalyzer tests (P5 §5).

Adapted to live schema: Order uses symbol_id (not a symbol string), so the
fixture seeds Symbol rows; Fill has no signed_direction.

Clock discipline
----------------
These tests state a fixed evaluation instant (`_AS_OF`) and fixed NYSE session
dates. They must never derive fixtures from `datetime.now()`.

The earlier form seeded each day trade as ``now - N hours`` with the closing
fill two hours later. Because the analyzer buckets fills by Eastern date, a run
started while it was late evening in Eastern time placed the opening and
closing fills in *different* buckets: the position walk never returned to zero
within a bucket, every day trade went undetected, and the suite failed with
``assert 0 == 3``. The failure was a deterministic function of the hour the
suite happened to start, not a flake — it reproduced for any run starting in
the 03:00–05:00 UTC band and passed at every other hour.

Fills are therefore placed at mid-session Eastern times, which keeps the
opening and closing fills in one bucket regardless of when the suite runs and
regardless of any future correction to the analyzer's Eastern-offset handling.
"""
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.pdt_analyzer import PdtAnalyzer

_TICKERS = {"AAPL": 1, "MSFT": 2, "GOOG": 3}

# Evaluation instant every test anchors to: Wednesday 2026-07-15, 13:00 Eastern.
_AS_OF = datetime(2026, 7, 15, 18, 0, tzinfo=UTC)

# Three NYSE sessions inside the 5-business-day window that _AS_OF opens.
# The window walks back five weekdays from Wednesday 2026-07-15, so it reaches
# Wednesday 2026-07-08; all three sessions sit comfortably inside it.
_SESSION_A = date(2026, 7, 14)  # Tuesday
_SESSION_B = date(2026, 7, 13)  # Monday
_SESSION_C = date(2026, 7, 10)  # Friday

# The analyzer buckets fills by Eastern date using a fixed UTC-5 offset.
_ET_UTC_OFFSET_HOURS = 5

# Mid-session Eastern hours. Chosen far from the Eastern midnight boundary so
# an open/close pair shares a bucket under either a -5 or a -4 offset.
_OPEN_ET_HOUR = 10
_CLOSE_ET_HOUR = 12


def _session_instant(session_date: date, eastern_hour: int) -> datetime:
    """UTC instant for `eastern_hour` on `session_date`, per the analyzer's offset."""
    return datetime.combine(
        session_date, time(hour=eastern_hour + _ET_UTC_OFFSET_HOURS), tzinfo=UTC
    )


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper", created_at=_AS_OF))
        for ticker, sid in _TICKERS.items():
            session.add(Symbol(id=sid, ticker=ticker, exchange="NASDAQ",
                               asset_class="us_equity", name=ticker, active=True))
        await session.commit()
    return session_factory


@pytest.fixture
def broker_registry_factory():
    def _make(equity: Decimal):
        reg = MagicMock()
        adapter = MagicMock()
        adapter.get_account = MagicMock(return_value={
            "cash": "10000", "equity": str(equity), "buying_power": str(equity),
        })
        reg.get.return_value = adapter
        return reg
    return _make


async def _add_day_trade(session, symbol: str, session_date: date) -> None:
    """Seed a buy + sell of the same symbol within one session (a day trade)."""
    sid = _TICKERS[symbol]
    opened = _session_instant(session_date, _OPEN_ET_HOUR)
    closed = _session_instant(session_date, _CLOSE_ET_HOUR)
    buy = Order(
        account_id=1, user_id=1, symbol_id=sid, side=OrderSide.BUY,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
        created_at=opened, updated_at=opened,
    )
    sell = Order(
        account_id=1, user_id=1, symbol_id=sid, side=OrderSide.SELL,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
        created_at=closed, updated_at=closed,
    )
    session.add_all([buy, sell])
    await session.flush()
    session.add_all([
        Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"), filled_at=opened),
        Fill(order_id=sell.id, qty=Decimal("10"), price=Decimal("101"), filled_at=closed),
    ])


async def _seed_three_day_trades(seeded) -> None:
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", _SESSION_A)
        await _add_day_trade(session, "MSFT", _SESSION_B)
        await _add_day_trade(session, "GOOG", _SESSION_C)
        await session.commit()


async def test_no_day_trades_not_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 0
    assert status.is_at_risk is False


async def test_two_day_trades_below_threshold(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", _SESSION_A)
        await _add_day_trade(session, "MSFT", _SESSION_B)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 2
    assert status.is_at_risk is False


async def test_three_day_trades_low_equity_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    await _seed_three_day_trades(seeded)
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is True


async def test_three_day_trades_high_equity_not_at_risk(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("50000"))
    await _seed_three_day_trades(seeded)
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is False


async def test_buy_only_not_a_day_trade(seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    opened = _session_instant(_SESSION_A, _OPEN_ET_HOUR)
    async with seeded() as session:
        buy = Order(
            account_id=1, user_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=opened, updated_at=opened,
        )
        session.add(buy)
        await session.flush()
        session.add(Fill(order_id=buy.id, qty=Decimal("10"),
                         price=Decimal("100"), filled_at=opened))
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 0


async def test_equity_none_when_no_registry(seeded):
    await _seed_three_day_trades(seeded)
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=None, as_of=_AS_OF
        ).compute(1)
    # equity unknown → at risk (conservative) once over the day-trade threshold.
    assert status.account_equity is None
    assert status.is_at_risk is True


@pytest.mark.parametrize("utc_hour", range(24))
async def test_day_trade_detection_is_independent_of_run_time(
    seeded, broker_registry_factory, utc_hour
):
    """Regression: detection must not depend on the hour the suite starts.

    The historical defect surfaced only for evaluation instants in the
    03:00–05:00 UTC band, so the whole day is swept rather than that band
    alone — a fixture that silently drifted out of the window would otherwise
    still look correct here.
    """
    reg = broker_registry_factory(Decimal("10000"))
    as_of = _AS_OF.replace(hour=utc_hour)
    await _seed_three_day_trades(seeded)
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=as_of
        ).compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is True


async def test_fills_before_the_window_are_excluded(seeded, broker_registry_factory):
    """The rolling window still excludes older sessions, anchored to `as_of`."""
    reg = broker_registry_factory(Decimal("10000"))
    stale_session = date(2026, 7, 1)  # well behind the 5-business-day cutoff
    async with seeded() as session:
        await _add_day_trade(session, "AAPL", _SESSION_A)
        await _add_day_trade(session, "MSFT", stale_session)
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(
            session=session, broker_registry=reg, as_of=_AS_OF
        ).compute(1)
    assert status.day_trade_count == 1


async def test_defaults_to_wall_clock_when_as_of_omitted(seeded, broker_registry_factory):
    """Production path: omitting `as_of` anchors the window to the wall clock.

    The one test that reads the live clock, because it is the only way to
    exercise the default branch. It stays boundary-safe by resolving the clock
    to an Eastern *date* first and then placing both fills at mid-session on
    that date, rather than offsetting each fill from the current instant: the
    pair shares a bucket at every hour of the day, and the previous session is
    always inside the 5-business-day window.
    """
    reg = broker_registry_factory(Decimal("10000"))
    eastern_now = datetime.now(UTC) - timedelta(hours=_ET_UTC_OFFSET_HOURS)
    previous_session = (eastern_now - timedelta(days=1)).date()
    opened = _session_instant(previous_session, _OPEN_ET_HOUR)
    closed = _session_instant(previous_session, _CLOSE_ET_HOUR)
    async with seeded() as session:
        buy = Order(
            account_id=1, user_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=opened, updated_at=opened,
        )
        sell = Order(
            account_id=1, user_id=1, symbol_id=1, side=OrderSide.SELL,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=closed, updated_at=closed,
        )
        session.add_all([buy, sell])
        await session.flush()
        session.add_all([
            Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"),
                 filled_at=opened),
            Fill(order_id=sell.id, qty=Decimal("10"), price=Decimal("101"),
                 filled_at=closed),
        ])
        await session.commit()
    async with seeded() as session:
        status = await PdtAnalyzer(session=session, broker_registry=reg).compute(1)
    assert status.day_trade_count == 1
