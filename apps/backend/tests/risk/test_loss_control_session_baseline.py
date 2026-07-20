"""ADR 0043 §D3 — the session-baseline SHADOW capture.

Pins: authoritative ET session date, capture-before-activity, immutable reuse across restart, the
two fail-closed paths (activity-already-occurred incl. EXTERNAL broker orders; unverifiable), the
concurrent-capture race, and the off-session skip. Shadow-only — no risk decision is exercised.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, Mock

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.loss_control.session_baseline import (
    SHADOW_CAPTURED,
    SHADOW_INDETERMINATE,
    SHADOW_MISSING_AFTER_ACTIVITY,
    SHADOW_REUSED,
    SHADOW_SKIPPED_NON_TRADING,
    SessionBaselineShadow,
    _broker_order_instant,
    resolve_session_date,
)

D = Decimal
TRADING_NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)  # Monday 11:00 ET
SESSION_OPEN = datetime(2026, 7, 20, 13, 30, tzinfo=UTC)  # 09:30 ET (EDT) — this session's open
NON_TRADING_NOW = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)  # Saturday


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return 1


def _empty_adapter() -> Mock:
    a = Mock()
    a.list_orders = Mock(return_value=[])
    return a


def _order(order_id: int, created_at: datetime) -> Order:
    return Order(
        id=order_id, user_id=1, account_id=1, symbol_id=1, client_order_id=f"twb-{order_id}",
        side=OrderSide.BUY, qty=D("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
        created_at=created_at, updated_at=created_at,
    )


async def _baseline(session_factory, account_id: int) -> RiskSessionBaseline | None:
    async with session_factory() as s:
        return await s.scalar(
            select(RiskSessionBaseline).where(RiskSessionBaseline.account_id == account_id)
        )


# --------------------------------------------------------------- session date


def test_resolve_session_date_trading_day():
    assert resolve_session_date(TRADING_NOW) == "2026-07-20"


def test_resolve_session_date_non_trading_day():
    assert resolve_session_date(NON_TRADING_NOW) is None


# --------------------------------------------------------------- capture / reuse


async def test_capture_writes_baseline_when_no_activity(session_factory, acct):
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=_empty_adapter()).capture(
            account_id=acct, reconciled_equity=D("100000.0000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_CAPTURED
    assert result.market_session_date == "2026-07-20"
    assert result.baseline_equity == D("100000.0000")
    row = await _baseline(session_factory, acct)
    assert row is not None and row.baseline_equity == D("100000.0000")
    assert row.market_session_date == "2026-07-20" and row.baseline_source == "RECONCILED_OPEN"


async def test_existing_baseline_is_reused_immutably(session_factory, acct):
    async with session_factory() as s:
        s.add(RiskSessionBaseline(
            account_id=acct, market_session_date="2026-07-20", baseline_equity=D("99000"),
            baseline_source="RECONCILED_OPEN", captured_at=TRADING_NOW,
        ))
        await s.commit()
    async with session_factory() as s:  # a later poll offers a DIFFERENT equity
        result = await SessionBaselineShadow(s, adapter=_empty_adapter()).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_REUSED
    assert result.baseline_equity == D("99000")  # original preserved — never replaced
    async with session_factory() as s:
        rows = (
            await s.execute(select(RiskSessionBaseline).where(RiskSessionBaseline.account_id == acct))
        ).scalars().all()
    assert len(rows) == 1 and rows[0].baseline_equity == D("99000")


async def test_concurrent_capture_reuses_the_winner(session_factory, acct):
    # A concurrent winner already inserted; our existence check raced and saw nothing, so we reach
    # the INSERT — ON CONFLICT DO NOTHING makes it a no-op and we reuse the winner's immutable row.
    async with session_factory() as s:
        s.add(RiskSessionBaseline(
            account_id=acct, market_session_date="2026-07-20", baseline_equity=D("98000"),
            baseline_source="RECONCILED_OPEN", captured_at=TRADING_NOW,
        ))
        await s.commit()
    async with session_factory() as s:
        shadow = SessionBaselineShadow(s, adapter=_empty_adapter())
        shadow._existing_baseline = AsyncMock(return_value=None)  # simulate the lost race
        result = await shadow.capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_REUSED
    assert result.baseline_equity == D("98000")


# --------------------------------------------------------------- fail-closed: activity occurred


async def test_local_order_this_session_fails_closed(session_factory, acct):
    async with session_factory() as s:
        s.add(_order(1, created_at=SESSION_OPEN + timedelta(minutes=5)))
        await s.commit()
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=_empty_adapter()).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_MISSING_AFTER_ACTIVITY
    assert result.fail_closed and result.activity_detected
    assert await _baseline(session_factory, acct) is None  # NOT captured mid-session


async def test_local_fill_this_session_fails_closed(session_factory, acct):
    async with session_factory() as s:
        s.add(_order(1, created_at=SESSION_OPEN - timedelta(days=1)))  # order predates the session
        await s.flush()
        s.add(Fill(order_id=1, qty=D("1"), price=D("100"),
                   filled_at=SESSION_OPEN + timedelta(minutes=10)))  # but it fills THIS session
        await s.commit()
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=_empty_adapter()).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_MISSING_AFTER_ACTIVITY


async def test_external_broker_order_this_session_fails_closed(session_factory, acct):
    # The order exists ONLY at the broker (never in the local orders table) — must still count.
    adapter = Mock()
    adapter.list_orders = Mock(
        return_value=[{"id": "ext-1", "submitted_at": (SESSION_OPEN + timedelta(minutes=1)).isoformat()}]
    )
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_MISSING_AFTER_ACTIVITY
    assert await _baseline(session_factory, acct) is None


async def test_broker_order_before_session_is_not_activity(session_factory, acct):
    adapter = Mock()
    adapter.list_orders = Mock(
        return_value=[{"id": "old", "submitted_at": (SESSION_OPEN - timedelta(days=1)).isoformat()}]
    )
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_CAPTURED  # a pre-session broker order is not this-session activity


async def test_broker_order_without_timestamp_is_indeterminate(session_factory, acct):
    # An order whose activity time can't be established → we can't prove no activity → fail closed.
    adapter = Mock()
    adapter.list_orders = Mock(return_value=[{"id": "no-ts"}])
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_INDETERMINATE
    assert await _baseline(session_factory, acct) is None  # never mint a baseline on unverifiable evidence


async def test_broker_order_invalid_timestamp_is_indeterminate(session_factory, acct):
    adapter = Mock()
    adapter.list_orders = Mock(return_value=[{"id": "bad", "submitted_at": "not-a-timestamp"}])
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_INDETERMINATE
    assert await _baseline(session_factory, acct) is None


async def test_mixed_malformed_and_preopen_orders_is_indeterminate(session_factory, acct):
    # A malformed order cannot be dismissed just because the other orders are known pre-open.
    adapter = Mock()
    adapter.list_orders = Mock(return_value=[
        {"id": "preopen", "submitted_at": (SESSION_OPEN - timedelta(days=1)).isoformat()},
        {"id": "malformed"},  # no usable timestamp
    ])
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_INDETERMINATE
    assert await _baseline(session_factory, acct) is None


# --------------------------------------------------------------- fail-closed: unverifiable


async def test_no_adapter_is_indeterminate(session_factory, acct):
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=None).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_INDETERMINATE
    assert result.fail_closed
    assert await _baseline(session_factory, acct) is None  # never guess a baseline


async def test_broker_read_failure_is_indeterminate(session_factory, acct):
    adapter = Mock()
    adapter.list_orders = Mock(side_effect=RuntimeError("broker down"))
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=adapter).capture(
            account_id=acct, reconciled_equity=D("100000"), now=TRADING_NOW
        )
    assert result.outcome == SHADOW_INDETERMINATE


# --------------------------------------------------------------- off-session


async def test_non_trading_day_is_skipped(session_factory, acct):
    async with session_factory() as s:
        result = await SessionBaselineShadow(s, adapter=_empty_adapter()).capture(
            account_id=acct, reconciled_equity=D("100000"), now=NON_TRADING_NOW
        )
    assert result.outcome == SHADOW_SKIPPED_NON_TRADING
    assert result.market_session_date is None
    assert await _baseline(session_factory, acct) is None


# --------------------------------------------------------------- broker timestamp parsing


def test_broker_order_instant_parsing():
    dt = datetime(2026, 7, 20, 14, 0, tzinfo=UTC)
    assert _broker_order_instant({"submitted_at": dt}) == dt
    assert _broker_order_instant({"submitted_at": "2026-07-20T14:00:00Z"}) == dt
    # A naive value is out-of-contract → UNUSABLE (None), never assumed UTC.
    assert _broker_order_instant({"created_at": datetime(2026, 7, 20, 14, 0)}) is None
    assert _broker_order_instant({"submitted_at": "2026-07-20T14:00:00"}) is None  # naive string
    # An unusable (unparseable OR naive) field falls through to a usable tz-aware one.
    assert _broker_order_instant(
        {"submitted_at": "not-a-date", "created_at": "2026-07-20T14:00:00+00:00"}
    ) == dt
    assert _broker_order_instant({"submitted_at": "2026-07-20T09:00:00", "created_at": dt}) == dt
    assert _broker_order_instant({}) is None
    assert _broker_order_instant({"submitted_at": None, "created_at": None, "updated_at": None}) is None
