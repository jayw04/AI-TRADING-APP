"""Smoke tests for the trading-domain models.

Checks that the schema is well-formed: rows can be inserted with the expected
types, FK constraints behave, the circular Order<->RiskCheck FK works, and the
Position unique constraint fires.
"""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import selectinload

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskDecision,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    """Seed minimal user/account/symbol so the trading rows have FKs to satisfy."""
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
                name="Apple Inc.",
                active=True,
            )
        )
        await session.commit()
    yield


async def test_insert_order_with_minimum_fields(session_factory, seeded) -> None:
    async with session_factory() as session:
        order = Order(
            user_id=1,
            account_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            qty=Decimal("10"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=OrderStatus.PENDING_RISK,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(order)
        await session.commit()
        assert order.id is not None
        assert order.status == OrderStatus.PENDING_RISK
        assert order.extended_hours is False


async def test_circular_order_risk_check_link(session_factory, seeded) -> None:
    async with session_factory() as session:
        order = Order(
            user_id=1,
            account_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            qty=Decimal("1"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=OrderStatus.PENDING_RISK,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(order)
        await session.flush()

        rc = RiskCheck(
            order_id=order.id,
            decision=RiskDecision.PASS,
            reason_codes=["OK"],
            evaluated_at=_now(),
        )
        session.add(rc)
        await session.flush()

        order.risk_check_id = rc.id
        await session.commit()

    async with session_factory() as session:
        loaded = (
            await session.execute(
                select(Order).options(selectinload(Order.risk_check))
            )
        ).scalars().first()
        assert loaded is not None
        assert loaded.risk_check_id is not None
        assert loaded.risk_check.decision == RiskDecision.PASS


async def test_fill_cascade_on_order_delete(session_factory, seeded) -> None:
    async with session_factory() as session:
        order = Order(
            user_id=1,
            account_id=1,
            symbol_id=1,
            side=OrderSide.BUY,
            qty=Decimal("1"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=OrderStatus.FILLED,
            source_type=OrderSourceType.MANUAL,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(order)
        await session.flush()
        session.add(
            Fill(
                order_id=order.id,
                qty=Decimal("1"),
                price=Decimal("190.00"),
                commission=Decimal("0"),
                filled_at=_now(),
            )
        )
        await session.commit()
        order_id = order.id

    async with session_factory() as session:
        order = (
            await session.execute(select(Order).where(Order.id == order_id))
        ).scalars().first()
        await session.delete(order)
        await session.commit()

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 0  # cascade-deleted


async def test_position_unique_account_symbol(session_factory, seeded) -> None:
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=1,
                qty=Decimal("10"),
                avg_entry_price=Decimal("190.00"),
                side="long",
                market_value=Decimal("1950.00"),
                cost_basis=Decimal("1900.00"),
                unrealized_pl=Decimal("50.00"),
                unrealized_plpc=Decimal("0.026"),
                updated_at=_now(),
            )
        )
        await session.commit()

    with pytest.raises(IntegrityError):
        async with session_factory() as session:
            session.add(
                Position(
                    user_id=1,
                    account_id=1,
                    symbol_id=1,  # same (account_id, symbol_id) → UNIQUE violation
                    qty=Decimal("5"),
                    avg_entry_price=Decimal("190.00"),
                    side="long",
                    market_value=Decimal("0"),
                    cost_basis=Decimal("0"),
                    unrealized_pl=Decimal("0"),
                    unrealized_plpc=Decimal("0"),
                    updated_at=_now(),
                )
            )
            await session.commit()


async def test_default_risk_limits_seed_shape(session_factory) -> None:
    """In tests we insert the default global row inline to assert the shape is valid."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.flush()
        session.add(
            RiskLimits(
                user_id=1,
                scope_type=RiskScopeType.GLOBAL,
                scope_id=None,
                max_position_qty=Decimal("1000"),
                max_position_notional=Decimal("25000"),
                max_gross_exposure=Decimal("100000"),
                max_daily_loss=Decimal("2000"),
                max_orders_per_minute=10,
                allow_short=False,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()
        row = (await session.execute(select(RiskLimits))).scalars().first()
        assert row is not None
        assert row.scope_type == RiskScopeType.GLOBAL
        assert row.max_daily_loss == Decimal("2000")
        assert row.allow_short is False
