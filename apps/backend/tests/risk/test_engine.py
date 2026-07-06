"""Risk Engine — covers each of the eight checks + halt persistence."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.halt import is_halted, set_halted
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest


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
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
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
    yield


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


async def test_passes_clean_buy(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert out.passed
    assert out.reason_codes == [ReasonCode.OK]
    assert out.risk_check_id is not None


async def test_rejects_negative_qty(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("-1")), trading_mode="paper")
    assert not out.passed
    assert ReasonCode.INVALID_INPUT in out.reason_codes


async def test_rejects_limit_without_price(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(
        _req(type=OrderType.LIMIT, limit_price=None), trading_mode="paper"
    )
    assert ReasonCode.INVALID_INPUT in out.reason_codes


async def test_rejects_mode_mismatch(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="live")
    assert ReasonCode.MODE_MISMATCH in out.reason_codes


async def test_rejects_unknown_symbol(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(symbol_ticker="ZZZZZ"), trading_mode="paper")
    assert ReasonCode.SYMBOL_DENIED in out.reason_codes


async def test_rejects_short_when_not_allowed(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(side=OrderSide.SELL), trading_mode="paper")
    assert ReasonCode.SHORT_NOT_ALLOWED in out.reason_codes


async def test_rejects_oversized_qty(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(qty=Decimal("9999")), trading_mode="paper")
    assert ReasonCode.POSITION_CAP_QTY in out.reason_codes


async def test_rejects_oversized_notional(session_factory, seeded) -> None:
    eng = RiskEngine(session_factory)
    # qty=50 * limit_price=600 = 30k > 25k cap, but qty stays under 100 cap
    out = await eng.evaluate(
        _req(qty=Decimal("50"), type=OrderType.LIMIT, limit_price=Decimal("600")),
        trading_mode="paper",
    )
    assert ReasonCode.POSITION_CAP_NOTIONAL in out.reason_codes


async def test_rejects_when_already_halted(session_factory, seeded) -> None:
    async with session_factory() as session:
        await set_halted(session, True, reason="test")
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.HALT_REACHED in out.reason_codes


async def test_daily_loss_cap_trips_account_breaker(session_factory, seeded) -> None:
    """ADR 0034: a daily-loss breach trips THIS account's circuit breaker (the
    order is rejected with CIRCUIT_BREAKER) and does NOT set the global halt."""
    async with session_factory() as session:
        state = (await session.execute(select(AccountState))).scalars().first()
        state.day_change = Decimal("-2500")  # below -max_daily_loss (2000)
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.CIRCUIT_BREAKER in out.reason_codes

    async with session_factory() as session:
        # Per-account breaker tripped; the GLOBAL halt is NOT set (ADR 0034).
        assert await is_halted(session) is False
        acct = await session.get(Account, 1)
        assert acct.circuit_breaker_tripped_at is not None


async def test_daily_loss_halt_is_account_scoped(session_factory, seeded) -> None:
    """ADR 0034 blast-radius: account 1 breaching its cap trips only account 1;
    account 2 (healthy) still trades — no system-wide halt."""
    async with session_factory() as session:
        session.add(User(id=2, email="k@test", display_name="K"))
        session.add(
            Account(
                id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="Paper2"
            )
        )
        session.add(
            RiskLimits(
                user_id=2,
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
                account_id=2,
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
        state1 = (
            await session.execute(
                select(AccountState).where(AccountState.account_id == 1)
            )
        ).scalars().first()
        state1.day_change = Decimal("-2500")  # account 1 breaches
        await session.commit()

    eng = RiskEngine(session_factory)
    out1 = await eng.evaluate(_req(account_id=1), trading_mode="paper")
    assert ReasonCode.CIRCUIT_BREAKER in out1.reason_codes
    # Account 2 is untouched — the halt did not go system-wide.
    out2 = await eng.evaluate(_req(user_id=2, account_id=2), trading_mode="paper")
    assert out2.passed
    async with session_factory() as session:
        assert await is_halted(session) is False
        assert (await session.get(Account, 2)).circuit_breaker_tripped_at is None


async def test_no_limits_configured(session_factory) -> None:
    """User without a risk_limits row: rejected with NO_LIMITS_CONFIGURED."""
    async with session_factory() as session:
        session.add(User(id=1, email="j@t"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
            )
        )
        await session.commit()

    eng = RiskEngine(session_factory)
    out = await eng.evaluate(_req(), trading_mode="paper")
    assert ReasonCode.NO_LIMITS_CONFIGURED in out.reason_codes
