"""Pending-aware exposure gates (incident 2026-06-22).

Before this change the gross-exposure and per-position caps counted only SETTLED
positions and valued MARKET orders at 0, so a burst of baskets submitted before
any fill each passed against the same snapshot and stacked unintended leverage.

These tests pin the fix: the engine values market orders via a caller-supplied
``reference_price``, persists the estimated notional, and counts in-flight
(non-terminal) BUY orders in both gates. They fail on the pre-fix engine.
"""

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


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        session.add(
            Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                   name="Apple", active=True)
        )
        session.add(
            Symbol(id=2, ticker="MSFT", exchange="NASDAQ", asset_class="us_equity",
                   name="Microsoft", active=True)
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
                max_orders_per_minute=10000,  # high → never the cause of a reject here
                allow_short=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        session.add(
            AccountState(
                account_id=1, cash=Decimal("100000"), equity=Decimal("100000"),
                last_equity=Decimal("100000"), buying_power=Decimal("400000"),
                portfolio_value=Decimal("100000"), daytrade_count=0,
                day_change=Decimal(0), day_change_pct=Decimal(0), status="ACTIVE",
                pattern_day_trader=False, trading_blocked=False, account_blocked=False,
                raw_payload={}, updated_at=_now(),
            )
        )
        await session.commit()
    yield


def _req(**overrides) -> OrderRequest:
    base = dict(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("10"), type=OrderType.MARKET, tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(overrides)
    return OrderRequest(**base)


async def _add_order(
    session_factory, *, symbol_id: int = 1, qty: str = "10",
    est_notional: str | None = None, status: OrderStatus = OrderStatus.SUBMITTED,
    side: OrderSide = OrderSide.BUY, tag: str = "x",
) -> None:
    async with session_factory() as session:
        session.add(
            Order(
                user_id=1, account_id=1, symbol_id=symbol_id,
                client_order_id=f"seed-{tag}",
                side=side, qty=Decimal(qty), type=OrderType.MARKET,
                tif=TimeInForce.DAY, status=status,
                source_type=OrderSourceType.STRATEGY, source_id="4",
                estimated_notional=Decimal(est_notional) if est_notional is not None else None,
                created_at=_now() - timedelta(seconds=5), updated_at=_now(),
            )
        )
        await session.commit()


class _StubBarCache:
    """Minimal bar cache: returns a fixed close (or None = cold symbol)."""

    def __init__(self, price) -> None:
        self._price = price

    async def get_latest_bar(self, symbol: str):
        return {"c": self._price} if self._price is not None else None


# ---------- market-order valuation ----------


async def test_market_order_valued_via_reference_price(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), reference_price=Decimal("150")), trading_mode="paper"
    )
    assert out.passed
    assert out.estimated_notional == Decimal("1500")


async def test_market_order_without_reference_has_no_notional(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert out.passed
    assert out.estimated_notional is None


async def test_reference_price_ignored_when_limit_present(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), type=OrderType.LIMIT, limit_price=Decimal("200"),
             reference_price=Decimal("999")),
        trading_mode="paper",
    )
    assert out.passed
    assert out.estimated_notional == Decimal("2000")  # 10 * limit 200, not the ref


# ---------- market-order valuation from the bar cache (ADR 0040) ----------


async def test_market_buy_valued_from_bar_cache(session_factory, seeded) -> None:
    """A MARKET BUY with no limit/reference price is valued from the latest cached
    bar close, so the exposure gates can count it (ADR 0040)."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("1000")))
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert out.passed
    assert out.estimated_notional == Decimal("10000")  # 10 × 1000


async def test_market_buy_over_cap_via_bar_cache_rejected(session_factory, seeded) -> None:
    """Entry-side fix: a MARKET BUY that prices (via the bar cache) above the gross
    cap is now rejected GROSS_EXPOSURE. Pre-fix it estimated to 0 and slipped
    through, over-filling the account (incident 2026-07-07; ADR 0040)."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(Decimal("2000")))
    # 100 × 2000 = 200k > the 100k cap; qty 100 is within the 100-share qty cap.
    out = await eng.evaluate(_req(qty=Decimal("100")), trading_mode="paper")
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes


async def test_bar_cache_cold_symbol_contributes_zero(session_factory, seeded) -> None:
    """Fail-open preserved: when the bar cache has no bar for the symbol, a MARKET
    order still estimates to None (contributes 0) rather than erroring (ADR 0040)."""
    eng = RiskEngine(session_factory, bar_cache=_StubBarCache(None))
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert out.passed
    assert out.estimated_notional is None


# ---------- gross-exposure: in-flight orders count ----------


async def test_inflight_buy_orders_count_toward_gross(session_factory, seeded) -> None:
    """95k of in-flight BUY notional (MSFT) + a 10k AAPL market buy = 105k > 100k."""
    await _add_order(session_factory, symbol_id=2, qty="100", est_notional="95000", tag="msft")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), reference_price=Decimal("1000")), trading_mode="paper"
    )
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes


async def test_filled_orders_do_not_count_toward_gross(session_factory, seeded) -> None:
    """Same notional but the orders are FILLED (terminal) → not counted → passes."""
    await _add_order(session_factory, symbol_id=2, qty="100", est_notional="95000",
                     status=OrderStatus.FILLED, tag="msft")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), reference_price=Decimal("1000")), trading_mode="paper"
    )
    assert out.passed


async def test_null_estimated_notional_contributes_zero(session_factory, seeded) -> None:
    """In-flight orders the engine couldn't price (NULL) add 0 → gross still passes."""
    await _add_order(session_factory, symbol_id=2, qty="100", est_notional=None, tag="msft")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), reference_price=Decimal("1000")), trading_mode="paper"
    )
    assert out.passed


async def test_settled_plus_inflight_combine_for_gross(session_factory, seeded) -> None:
    """50k settled position + 50k in-flight + 10k incoming = 110k > 100k."""
    async with session_factory() as session:
        session.add(
            Position(user_id=1, account_id=1, symbol_id=2, qty=Decimal("50"),
                     avg_entry_price=Decimal("1000"), market_value=Decimal("50000"),
                     updated_at=_now())
        )
        await session.commit()
    await _add_order(session_factory, symbol_id=2, qty="50", est_notional="50000", tag="msft")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(qty=Decimal("10"), reference_price=Decimal("1000")), trading_mode="paper"
    )
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes


async def test_incoming_sell_not_added_to_gross(session_factory, seeded) -> None:
    """A SELL does not grow gross exposure: with 95k in-flight buys, a sell of a
    held position still passes the gross gate (it is not credited, but not charged
    either)."""
    async with session_factory() as session:
        session.add(
            Position(user_id=1, account_id=1, symbol_id=1, qty=Decimal("100"),
                     avg_entry_price=Decimal("100"), market_value=Decimal("10000"),
                     updated_at=_now())
        )
        await session.commit()
    await _add_order(session_factory, symbol_id=2, qty="100", est_notional="80000", tag="msft")
    # allow_short False but we hold 100 AAPL, so selling 10 is not a short.
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.SELL, qty=Decimal("10")), trading_mode="paper"
    )
    assert out.passed


# ---------- per-position qty cap: in-flight orders count ----------


async def test_inflight_buy_qty_counts_toward_position_cap(session_factory, seeded) -> None:
    """95 in-flight AAPL shares + a 10-share buy = 105 > the 100 qty cap."""
    await _add_order(session_factory, symbol_id=1, qty="95", est_notional=None, tag="aapl")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_QTY in out.reason_codes


async def test_inflight_qty_for_other_symbol_does_not_block(session_factory, seeded) -> None:
    """In-flight MSFT shares must not count against the AAPL per-position cap."""
    await _add_order(session_factory, symbol_id=2, qty="95", est_notional=None, tag="msft")
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("10")), trading_mode="paper")
    assert out.passed


async def test_three_basket_stack_is_blocked(session_factory, seeded) -> None:
    """Incident reproduction: a first basket of ~100k in-flight BUY notional makes
    the next basket's first order breach the gross cap — the stack stops at ~1x."""
    # First basket: five 20k market buys, all in-flight (SUBMITTED).
    for i, sym in enumerate([2, 2, 2, 2, 2]):
        await _add_order(session_factory, symbol_id=sym, qty="20",
                         est_notional="20000", tag=f"b1-{i}")
    eng = RiskEngine(session_factory)
    # Second basket's first order: 100k already in flight + 20k → 120k > 100k.
    out = await eng.evaluate(
        _req(qty=Decimal("20"), reference_price=Decimal("1000")), trading_mode="paper"
    )
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes


# ---------- gross-exposure: reducing-sell exemption (ADR 0038) ----------


async def _seed_over_cap_positions(session_factory) -> None:
    """90k MSFT + 20k AAPL = 110k settled gross, over the 100k cap. AAPL is the
    symbol the reducing-sell tests exit (held qty 100 @ avg 200)."""
    async with session_factory() as session:
        session.add(
            Position(user_id=1, account_id=1, symbol_id=2, qty=Decimal("100"),
                     avg_entry_price=Decimal("900"), market_value=Decimal("90000"),
                     updated_at=_now())
        )
        session.add(
            Position(user_id=1, account_id=1, symbol_id=1, qty=Decimal("100"),
                     avg_entry_price=Decimal("200"), market_value=Decimal("20000"),
                     updated_at=_now())
        )
        await session.commit()


async def test_reducing_sell_exempt_when_over_cap(session_factory, seeded) -> None:
    """Settled gross is already OVER the cap (110k > 100k). A position-reducing
    SELL (sell 50 of a held 100 AAPL) can only LOWER gross, so it is exempt from
    the gross gate and passes. Pre-fix this rejected GROSS_EXPOSURE and trapped
    the exit (incident 2026-07-07)."""
    await _seed_over_cap_positions(session_factory)
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.SELL, qty=Decimal("50")), trading_mode="paper"
    )
    assert out.passed
    assert ReasonCode.GROSS_EXPOSURE not in out.reason_codes


async def test_full_close_sell_exempt_when_over_cap(session_factory, seeded) -> None:
    """Selling the ENTIRE held position (100 of 100 AAPL) when gross is over the
    cap passes — a full exit is the maximal de-risk (ADR 0038)."""
    await _seed_over_cap_positions(session_factory)
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.SELL, qty=Decimal("100")), trading_mode="paper"
    )
    assert out.passed


async def test_short_opening_sell_not_exempt_over_cap(session_factory, seeded) -> None:
    """The exemption is scoped to REDUCING sells: a SELL exceeding the held long
    (sell 50 of only 30 held) is not a reduce. With allow_short=false it is
    rejected by the §6 short restriction — the exemption never lets a short
    through (ADR 0038)."""
    async with session_factory() as session:
        session.add(
            Position(user_id=1, account_id=1, symbol_id=1, qty=Decimal("30"),
                     avg_entry_price=Decimal("100"), market_value=Decimal("3000"),
                     updated_at=_now())
        )
        await session.commit()
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.SELL, qty=Decimal("50")), trading_mode="paper"
    )
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_buy_still_blocked_when_over_cap(session_factory, seeded) -> None:
    """Regression: the reducing-sell exemption does not touch BUYs — a BUY while
    gross is over the cap is still rejected GROSS_EXPOSURE (ADR 0038). The BUY is
    in a fresh symbol (AAPL, 0 held) so the per-position qty cap is not the cause."""
    async with session_factory() as session:
        session.add(
            Position(user_id=1, account_id=1, symbol_id=2, qty=Decimal("100"),
                     avg_entry_price=Decimal("1100"), market_value=Decimal("110000"),
                     updated_at=_now())
        )
        await session.commit()
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(side=OrderSide.BUY, qty=Decimal("1"), reference_price=Decimal("100")),
        trading_mode="paper",
    )
    assert ReasonCode.GROSS_EXPOSURE in out.reason_codes
