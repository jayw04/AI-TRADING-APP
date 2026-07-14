"""ADR 0042 § A — the causally-complete snapshot.

The rule is not "recent enough". It is:

    the snapshot must be AT OR BEYOND every broker event we have already observed locally.

A read that is merely *recent* but sits **behind a fill we have already persisted** is not a
stale account — it is a **different account**, and classifying against it can approve a
reduction that has, in reality, already happened.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pytest

from app.db.enums import OrderSide, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order, OrderSourceType
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.account_snapshot import fetch_snapshot
from app.risk.risk_effect import RiskEffectReason

D = Decimal
T0 = datetime(2026, 7, 13, 14, 0, tzinfo=UTC)


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(
            Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                   name="Apple", active=True)
        )
        await s.commit()
    return 1


def _adapter(positions=None, orders=None):
    ad = MagicMock()
    ad.get_account.return_value = {"cash": "1000", "equity": "50000", "id": "acct-x"}
    ad.get_positions.return_value = positions or []
    ad.list_orders.return_value = orders or []
    return ad


async def _fetch(session_factory, ad, account_id=1):
    async with session_factory() as s:
        return await fetch_snapshot(session=s, account_id=account_id, adapter=ad)


# ---------------------------------------------------------------- positions


async def test_a_short_position_is_signed_negative(session_factory, acct):
    """The whole classifier turns on the SIGN. Alpaca reports a short with side='short' and a
    positive qty on some SDK paths — if that reaches the classifier unsigned, a buy-to-cover
    would look like a buy-to-open and a sell-to-open would look like a reduction."""
    ad = _adapter([{"symbol": "AAPL", "qty": "100", "side": "short", "current_price": "50"}])
    snap = await _fetch(session_factory, ad)
    assert snap.positions["AAPL"].qty == D("-100")
    assert snap.gross_exposure() == D("5000")  # gross uses ABS


async def test_price_falls_back_to_market_value_over_qty(session_factory, acct):
    ad = _adapter([{"symbol": "AAPL", "qty": "100", "side": "long", "market_value": "7500"}])
    snap = await _fetch(session_factory, ad)
    assert snap.positions["AAPL"].price == D("75")


async def test_unparseable_numbers_do_not_crash_the_read(session_factory, acct):
    ad = _adapter([{"symbol": "AAPL", "qty": "not-a-number", "side": "long", "current_price": ""}])
    snap = await _fetch(session_factory, ad)
    assert snap.positions["AAPL"].qty == D(0)


# ---------------------------------------------------------------- open orders


async def test_an_open_sell_against_a_long_is_marked_reducing(session_factory, acct):
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "o1", "symbol": "AAPL", "side": "sell", "qty": "100", "filled_qty": "0",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    o = snap.open_orders[0]
    assert o.reduces_position is True
    assert o.remaining_qty == D("100")


async def test_an_open_sell_with_NO_position_is_not_reducing(session_factory, acct):
    """It would OPEN a short. A sell is not a reduction just because it is a sell."""
    ad = _adapter(
        [],
        [{"id": "o1", "symbol": "AAPL", "side": "sell", "qty": "100", "filled_qty": "0",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    assert snap.open_orders[0].reduces_position is False


async def test_a_buy_against_a_short_is_reducing(session_factory, acct):
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "100", "side": "short", "current_price": "50"}],
        [{"id": "o1", "symbol": "AAPL", "side": "buy", "qty": "40", "filled_qty": "0",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    assert snap.open_orders[0].reduces_position is True


async def test_remaining_qty_nets_out_the_filled_portion(session_factory, acct):
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "o1", "symbol": "AAPL", "side": "sell", "qty": "100", "filled_qty": "30",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    assert snap.open_orders[0].remaining_qty == D("70")


async def test_a_partial_fill_we_have_not_ingested_is_UNRESOLVED(session_factory, acct):
    """The broker says 30 filled; we have no fill row. The true position is ambiguous, and
    ambiguity is INDETERMINATE — never 'probably fine'."""
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "unseen", "symbol": "AAPL", "side": "sell", "qty": "100", "filled_qty": "30",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    assert snap.open_orders[0].has_unresolved_partial_fill is True

    ok, why = snap.is_causally_complete()
    assert ok is False
    assert why is RiskEffectReason.UNRESOLVED_PARTIAL_FILL


async def test_a_partial_fill_we_HAVE_ingested_is_resolved(session_factory, acct):
    async with session_factory() as s:
        o = Order(
            user_id=1, account_id=1, symbol_id=1, broker_order_id="known",
            side=OrderSide.SELL, qty=D("100"), type=OrderType.MARKET,
            tif=TimeInForce.DAY, status=OrderStatus.PARTIALLY_FILLED,
            source_type=OrderSourceType.STRATEGY, created_at=T0, updated_at=T0,
        )
        s.add(o)
        await s.flush()
        s.add(Fill(order_id=o.id, broker_fill_id="f1", qty=D("30"), price=D("100"), filled_at=T0))
        await s.commit()

    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "known", "symbol": "AAPL", "side": "sell", "qty": "100", "filled_qty": "30",
          "submitted_at": "2026-07-13T14:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    assert snap.open_orders[0].has_unresolved_partial_fill is False


# ---------------------------------------------------------------- causality (§ A)


async def test_the_snapshot_is_stale_when_it_is_behind_a_fill_we_already_saw(
    session_factory, acct
):
    """THE § A CHECK. Not an age threshold — a causality check.

    We have already persisted a fill stamped LATER than anything in this broker read. The read
    is behind us. That is not 'a bit old': the account we are looking at is not the account we
    have.
    """
    later = T0 + timedelta(minutes=5)
    async with session_factory() as s:
        o = Order(
            user_id=1, account_id=1, symbol_id=1, broker_order_id="b1",
            side=OrderSide.SELL, qty=D("10"), type=OrderType.MARKET,
            tif=TimeInForce.DAY, status=OrderStatus.FILLED,
            source_type=OrderSourceType.STRATEGY, created_at=T0, updated_at=T0,
        )
        s.add(o)
        await s.flush()
        s.add(Fill(order_id=o.id, broker_fill_id="f1", qty=D("10"), price=D("100"), filled_at=later))
        await s.commit()

    # the broker read only knows about an OLDER event
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "o-old", "symbol": "AAPL", "side": "sell", "qty": "1", "filled_qty": "0",
          "updated_at": str(T0)}],
    )
    snap = await _fetch(session_factory, ad)

    assert snap.observed_cursor is not None
    assert snap.broker_cursor < snap.observed_cursor

    ok, why = snap.is_causally_complete()
    assert ok is False
    assert why is RiskEffectReason.SNAPSHOT_STALE


async def test_a_broker_read_failure_yields_an_incomplete_snapshot(session_factory, acct):
    """A broker we cannot read is not permission to trade."""
    ad = _adapter()
    ad.get_positions.side_effect = RuntimeError("broker unreachable")

    snap = await _fetch(session_factory, ad)

    assert snap.complete is False
    ok, why = snap.is_causally_complete()
    assert ok is False
    assert why is RiskEffectReason.SNAPSHOT_INCOMPLETE


async def test_a_clean_snapshot_is_causally_complete(session_factory, acct):
    ad = _adapter(
        [{"symbol": "AAPL", "qty": "500", "side": "long", "current_price": "100"}],
        [{"id": "o1", "symbol": "AAPL", "side": "sell", "qty": "10", "filled_qty": "0",
          "updated_at": "2026-07-13T20:00:00Z"}],
    )
    snap = await _fetch(session_factory, ad)
    ok, why = snap.is_causally_complete()
    assert ok is True and why is None
