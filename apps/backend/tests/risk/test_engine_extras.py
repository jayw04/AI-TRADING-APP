"""Branch-coverage backfill for ``app/risk/engine.py``.

The base ``test_engine.py`` covers each of the eight checks at the
happy-path / single-rejection level. This file targets branches the base
file misses, identified from a coverage.xml snapshot at the close of
P2 S6:

- STOP-without-stop-price reject (the ``_TYPES_NEEDING_STOP`` arm of the
  shape check; the base file only exercises the ``_TYPES_NEEDING_LIMIT``
  arm via type=LIMIT).
- Denied-symbols list hit.
- Allowed-symbols list miss (allowlist mode rejects a non-listed
  symbol).
- SHORT_NOT_ALLOWED when a partial long position exists (pos.qty > 0
  but < req.qty — the base file only exercises pos=None which makes
  current_qty=0).
- Gross exposure cap rejection.
- Rate limit rejection (10 orders in the last minute trips the cap).

Together these push ``risk/engine.py`` branch-rate above the 0.85
floor that ``check_risk_coverage.py`` enforces.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest
from app.services.day_change_basis import BROKER_LAST_EQUITY


def _now() -> datetime:
    return datetime.now(UTC)


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1,
        account_id=1,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


@pytest.fixture
async def seeded(session_factory):
    """Default seed identical to tests/risk/test_engine.py — kept local so
    individual tests can adjust the RiskLimits row without ripping a shared
    fixture."""
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
        session.add(
            RiskLimits(
                user_id=1,
                scope_type=RiskScopeType.GLOBAL,
                scope_id=None,
                max_position_qty=Decimal("100"),
                max_position_notional=Decimal("25000"),
                max_gross_exposure=Decimal("100000"),
                max_daily_loss=Decimal("2000"),
                max_orders_per_minute=10,
                allow_short=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            AccountState(
                day_change_basis=BROKER_LAST_EQUITY,
                account_id=1,
                cash=Decimal("100000"),
                equity=Decimal("100000"),
                last_equity=Decimal("100000"),
                buying_power=Decimal("200000"),
                portfolio_value=Decimal("100000"),
                daytrade_count=0,
                day_change=Decimal(0),
                day_change_pct=Decimal(0),
                status="ACTIVE",
                pattern_day_trader=False,
                trading_blocked=False,
                account_blocked=False,
                raw_payload={},
                updated_at=_now(),
            )
        )
        await session.commit()


# ---------- shape check: STOP without stop_price ----------


async def test_rejects_stop_without_stop_price(session_factory, seeded) -> None:
    """The ``_TYPES_NEEDING_STOP`` shape-check branch: a STOP order with
    no ``stop_price`` should reject INVALID_INPUT, not fall through to
    later checks."""
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(type=OrderType.STOP, stop_price=None), trading_mode="paper"
    )
    assert not out.passed
    assert ReasonCode.INVALID_INPUT in out.reason_codes


async def test_rejects_stop_limit_without_stop_price(session_factory, seeded) -> None:
    """STOP_LIMIT needs both. Limit price present but stop missing should
    still fail the stop-price arm specifically (the limit arm passes
    first)."""
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(
            type=OrderType.STOP_LIMIT,
            limit_price=Decimal("190"),
            stop_price=None,
        ),
        trading_mode="paper",
    )
    assert not out.passed
    assert ReasonCode.INVALID_INPUT in out.reason_codes


# ---------- symbol allow/deny lists ----------


async def test_rejects_denied_symbol(session_factory, seeded) -> None:
    """A ticker on ``denied_symbols`` rejects even when the symbol exists
    and is active."""
    async with session_factory() as session:
        limits = (
            await session.execute(
                __import__("sqlalchemy").select(RiskLimits).limit(1)
            )
        ).scalars().first()
        limits.denied_symbols = ["AAPL"]
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.SYMBOL_DENIED in out.reason_codes


async def test_rejects_symbol_not_in_allowlist(session_factory, seeded) -> None:
    """Allowlist mode: AAPL is registered + active, but the user's
    allowlist is ``["MSFT"]`` — must reject SYMBOL_DENIED."""
    async with session_factory() as session:
        limits = (
            await session.execute(
                __import__("sqlalchemy").select(RiskLimits).limit(1)
            )
        ).scalars().first()
        limits.allowed_symbols = ["MSFT"]
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.SYMBOL_DENIED in out.reason_codes


# ---------- SHORT_NOT_ALLOWED: partial-cover edge ----------


async def test_rejects_short_when_partial_long_cover(session_factory, seeded) -> None:
    """SELL 10 with a 3-share long position: covers only the first 3
    shares, the remaining 7 would open a short → SHORT_NOT_ALLOWED.
    Distinct from the base ``test_rejects_short_when_not_allowed`` which
    exercises the pos=None path (current_qty=0 < req.qty=10)."""
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=1,
                qty=Decimal("3"),
                avg_entry_price=Decimal("190"),
                market_value=Decimal("570"),
                updated_at=_now(),
            )
        )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(side=OrderSide.SELL), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_passes_sell_when_fully_covered(session_factory, seeded) -> None:
    """SELL 5 with a 20-share long position: short-restriction branch is
    skipped entirely (the ``if current_qty < req.qty`` predicate is
    False). Covers the negation of the SHORT_NOT_ALLOWED branch."""
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=1,
                qty=Decimal("20"),
                avg_entry_price=Decimal("190"),
                market_value=Decimal("3800"),
                updated_at=_now(),
            )
        )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.SELL, qty=Decimal("5")), trading_mode="paper"
    )
    assert out.passed


# ---------- gross exposure ----------


async def test_rejects_when_gross_exposure_would_breach(
    session_factory, seeded
) -> None:
    """Seed an existing MSFT position whose ``market_value`` consumes most
    of the 100k gross-exposure cap, then submit a small AAPL limit order
    that stays under the 25k per-position notional cap but tips gross
    over. The per-position cap (check 7) fires first if our new order is
    too big, so we keep the new order intentionally cheap and lean on the
    existing position to push us over."""
    async with session_factory() as session:
        session.add(
            Symbol(
                id=2, ticker="MSFT", exchange="NASDAQ",
                asset_class="us_equity", name="Microsoft", active=True,
            )
        )
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=2,
                qty=Decimal("100"),
                avg_entry_price=Decimal("950"),
                market_value=Decimal("95000"),  # 95k of 100k cap already used
                updated_at=_now(),
            )
        )
        await session.commit()

    eng = RiskEngine(session_factory)
    # 10 shares @ $1000 = $10k notional (under 25k per-position cap)
    # Projected gross: 95k + 10k = $105k > 100k cap.
    out = await eng.evaluate(
        _req(qty=Decimal("10"), type=OrderType.LIMIT, limit_price=Decimal("1000")),
        trading_mode="paper",
    )
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes


# ---------- rate limit ----------


async def test_rejects_when_rate_limit_reached(session_factory, seeded) -> None:
    """Seed 10 orders in the last 60s for this user; the 11th evaluation
    must reject RATE_LIMIT."""
    async with session_factory() as session:
        for i in range(10):
            session.add(
                Order(
                    user_id=1,
                    account_id=1,
                    symbol_id=1,
                    client_order_id=f"rate-test-{i}",
                    side=OrderSide.BUY,
                    qty=Decimal("1"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.FILLED,
                    source_type=OrderSourceType.MANUAL,
                    created_at=_now() - timedelta(seconds=10),
                    updated_at=_now(),
                )
            )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.RATE_LIMIT in out.reason_codes


async def test_rate_limit_ignores_old_orders(session_factory, seeded) -> None:
    """Orders older than the 60s window must not count toward the limit
    — covers the ``Order.created_at >= since`` predicate's False branch."""
    async with session_factory() as session:
        for i in range(20):
            session.add(
                Order(
                    user_id=1,
                    account_id=1,
                    symbol_id=1,
                    client_order_id=f"old-{i}",
                    side=OrderSide.BUY,
                    qty=Decimal("1"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.FILLED,
                    source_type=OrderSourceType.MANUAL,
                    created_at=_now() - timedelta(minutes=5),  # well outside 60s window
                    updated_at=_now(),
                )
            )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert out.passed


# ---------- inactive symbol → SYMBOL_DENIED ----------


async def test_inactive_symbol_is_denied(session_factory, seeded) -> None:
    """Symbols filtered by ``Symbol.active.is_(True)`` — an existing row
    with active=False should not resolve, yielding SYMBOL_DENIED."""
    async with session_factory() as session:
        session.add(
            Symbol(
                id=2, ticker="DEAD", exchange="NASDAQ",
                asset_class="us_equity", name="Defunct", active=False,
            )
        )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(symbol_ticker="DEAD"), trading_mode="paper")
    assert ReasonCode.SYMBOL_DENIED in out.reason_codes
