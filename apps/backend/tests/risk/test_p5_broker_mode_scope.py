"""P5 §1 — RiskLimits.broker_mode scoping in the engine's limits resolver.

The engine only matches limits whose broker_mode equals the evaluated mode:
a live trade never falls back to paper-scoped limits, and vice versa. Existing
rows backfill to PAPER via the column default.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.reason_codes import ReasonCode
from app.risk.types import OrderRequest


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_account_and_symbol(session, *, mode=AccountMode.paper) -> None:
    session.add(User(id=1, email="t@t.test", display_name="T"))
    await session.flush()
    session.add(Account(id=1, user_id=1, broker="alpaca", mode=mode, label="a"))
    session.add(
        Symbol(id=1, ticker="AAPL", name="Apple", asset_class="us_equity", active=True)
    )
    await session.commit()


def _limits(**overrides) -> RiskLimits:
    kwargs = dict(
        user_id=1,
        scope_type=RiskScopeType.GLOBAL,
        max_position_qty=Decimal("1000"),
        max_position_notional=Decimal("1000000"),
        max_gross_exposure=Decimal("5000000"),
        max_daily_loss=Decimal("100000"),
        max_orders_per_minute=1000,
        allow_short=False,
        created_at=_now(),
        updated_at=_now(),
    )
    kwargs.update(overrides)
    return RiskLimits(**kwargs)


def _req() -> OrderRequest:
    return OrderRequest(
        user_id=1,
        account_id=1,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("10"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )


@pytest.mark.asyncio
async def test_limits_backfill_to_paper_by_default(session_factory):
    """A RiskLimits row created without broker_mode is PAPER-scoped."""
    async with session_factory() as session:
        await _seed_account_and_symbol(session)
        session.add(_limits())
        await session.commit()
        row = (await session.get(RiskLimits, 1))
    assert row.broker_mode == AccountMode.paper


@pytest.mark.asyncio
async def test_paper_evaluation_matches_paper_limits(session_factory):
    async with session_factory() as session:
        await _seed_account_and_symbol(session)
        session.add(_limits(broker_mode=AccountMode.paper))
        await session.commit()
    engine = RiskEngine(session_factory)
    outcome = await engine.evaluate(
        _req(), trading_mode="paper", broker_mode=AccountMode.paper
    )
    assert outcome.passed is True


@pytest.mark.asyncio
async def test_live_evaluation_does_not_match_paper_limits(session_factory):
    """Only paper-scoped limits exist → a live evaluation finds none."""
    async with session_factory() as session:
        await _seed_account_and_symbol(session, mode=AccountMode.live)
        session.add(_limits(broker_mode=AccountMode.paper))
        await session.commit()
    engine = RiskEngine(session_factory)
    outcome = await engine.evaluate(
        _req(), trading_mode="live", broker_mode=AccountMode.live
    )
    assert outcome.passed is False
    assert ReasonCode.NO_LIMITS_CONFIGURED in outcome.reason_codes


@pytest.mark.asyncio
async def test_live_evaluation_matches_live_limits(session_factory):
    async with session_factory() as session:
        await _seed_account_and_symbol(session, mode=AccountMode.live)
        # Both a paper-scoped and a live-scoped GLOBAL row exist; the resolver
        # must pick the live one for a live evaluation.
        session.add(_limits(broker_mode=AccountMode.paper))
        session.add(_limits(broker_mode=AccountMode.live))
        await session.commit()
    engine = RiskEngine(session_factory)
    outcome = await engine.evaluate(
        _req(), trading_mode="live", broker_mode=AccountMode.live
    )
    assert outcome.passed is True
