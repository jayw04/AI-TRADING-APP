"""Integration: a strategy whose order is rejected by the Risk Engine
(via the OrderRouter) keeps running rather than entering ERROR.

This exercises the real :class:`StrategyEngine` + a strategy whose
context's ``submit_order`` returns a rejected order. Uses the
:class:`EchoStrategy` fixture from Session 2 — we don't need the
reference RSI strategy here; we just want to verify the framework's
rejection-tolerance.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.risk import OrderRequest
from app.strategies import StrategyEngine

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"


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
                id=1, ticker="AAPL", exchange="NASDAQ",
                asset_class="us_equity", name="Apple", active=True,
            )
        )
        session.add(
            RiskLimits(
                user_id=1, scope_type=RiskScopeType.GLOBAL, scope_id=None,
                max_position_qty=Decimal("100"),
                max_position_notional=Decimal("25000"),
                max_gross_exposure=Decimal("100000"),
                max_daily_loss=Decimal("2000"),
                max_orders_per_minute=10,
                allow_short=False,
                created_at=_now(), updated_at=_now(),
            )
        )
        await session.commit()


async def test_rejected_order_does_not_crash_strategy(session_factory, seeded):
    """Engine register, strategy submits an oversized order, router rejects
    it; the strategy must NOT enter ERROR status."""
    scheduler = AsyncIOScheduler()
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    indicator_computer = MagicMock()
    order_router = MagicMock()
    rejected_order = MagicMock()
    rejected_order.id = 99
    rejected_order.status = OrderStatus.REJECTED
    rejected_order.rejection_reason = "POSITION_CAP_NOTIONAL"
    order_router.submit = AsyncMock(return_value=rejected_order)

    eng = StrategyEngine(
        scheduler=scheduler,
        session_factory=session_factory,
        bus=bus,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )

    # Register the Session 2 EchoStrategy fixture. It doesn't submit orders
    # itself; we'll drive its ctx.submit_order manually below.
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1,
            name="echo-test",
            version="0.0.1",
            type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE,
            code_path="echo_strategy.py",
            params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"],
            schedule="event",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    running = await eng.register(sid)

    req = OrderRequest(
        user_id=0, account_id=0,
        symbol_ticker="AAPL",
        side=OrderSide.BUY,
        qty=Decimal("100000"),  # blows past any reasonable cap
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.STRATEGY,
    )
    await running.instance.ctx.submit_order(req)

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
        assert row.status == StrategyStatus.PAPER, (
            f"Strategy entered {row.status.value} after a rejection; "
            "should keep running."
        )
    assert sid in eng._running

    await eng.shutdown()
    scheduler.shutdown(wait=False)
