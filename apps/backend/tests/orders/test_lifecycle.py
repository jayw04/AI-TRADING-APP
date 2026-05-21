"""TradeUpdateConsumer — translates alpaca.trade_update into local writes."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.lifecycle import TradeUpdateConsumer


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded_with_order(session_factory):
    """Seed a user/account/symbol + one SUBMITTED order with a broker_order_id."""
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
                ticker="F",
                exchange="NYSE",
                asset_class="us_equity",
                name="Ford",
                active=True,
            )
        )
        session.add(
            Order(
                id=1,
                user_id=1,
                account_id=1,
                symbol_id=1,
                broker_order_id="broker-99",
                client_order_id="twb-99",
                side=OrderSide.BUY,
                qty=Decimal("1"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED,
                source_type=OrderSourceType.MANUAL,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()
    yield


@pytest.fixture
def recomputer_mock() -> AsyncMock:
    m = AsyncMock()
    m.recompute = AsyncMock()
    return m


async def test_fill_creates_row_and_transitions_order(
    session_factory, seeded_with_order, recomputer_mock
) -> None:
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    await consumer._handle(
        {
            "event": "fill",
            "broker_order_id": "broker-99",
            "execution_id": "exec-1",
            "qty": "1",
            "price": "12.34",
            "symbol": "F",
        }
    )

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 1
        assert fills[0].order_id == 1
        assert fills[0].qty == Decimal("1")
        assert fills[0].price == Decimal("12.34")
        assert fills[0].broker_fill_id == "exec-1"

        order = (
            await session.execute(select(Order).where(Order.id == 1))
        ).scalars().first()
        assert order.status == OrderStatus.FILLED
        assert order.terminal_at is not None

    recomputer_mock.recompute.assert_awaited_once_with(1, 1)


async def test_partial_fill_keeps_order_partial(
    session_factory, seeded_with_order, recomputer_mock
) -> None:
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    # The seeded order has qty=1; a partial fill of 0.5 leaves 0.5 remaining.
    await consumer._handle(
        {
            "event": "partial_fill",
            "broker_order_id": "broker-99",
            "execution_id": "exec-1",
            "qty": "0.5",
            "price": "12.34",
        }
    )

    async with session_factory() as session:
        order = (
            await session.execute(select(Order).where(Order.id == 1))
        ).scalars().first()
        assert order.status == OrderStatus.PARTIALLY_FILLED
        assert order.terminal_at is None


async def test_fill_duplicate_execution_id_is_idempotent(
    session_factory, seeded_with_order, recomputer_mock
) -> None:
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    evt = {
        "event": "fill",
        "broker_order_id": "broker-99",
        "execution_id": "exec-dup",
        "qty": "1",
        "price": "12.34",
    }
    await consumer._handle(evt)
    await consumer._handle(evt)  # exact same event re-delivered

    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert len(fills) == 1


async def test_canceled_event_transitions_to_terminal(
    session_factory, seeded_with_order, recomputer_mock
) -> None:
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    await consumer._handle(
        {"event": "canceled", "broker_order_id": "broker-99"}
    )

    async with session_factory() as session:
        order = (
            await session.execute(select(Order).where(Order.id == 1))
        ).scalars().first()
        assert order.status == OrderStatus.CANCELED
        assert order.terminal_at is not None

        # And an audit row was written.
        audits = (
            await session.execute(
                select(AuditLog).where(AuditLog.action == "ORDER_CANCELED")
            )
        ).scalars().all()
        assert len(audits) == 1


async def test_unknown_broker_order_id_logs_but_does_not_raise(
    session_factory, recomputer_mock
) -> None:
    """A trade update for a broker_order_id we don't have should NOT crash."""
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    # No seeded order — nothing in our DB. Must not raise.
    await consumer._handle(
        {
            "event": "fill",
            "broker_order_id": "broker-unknown",
            "execution_id": "exec-x",
            "qty": "1",
            "price": "1",
        }
    )
    # No fills should have been written.
    async with session_factory() as session:
        fills = (await session.execute(select(Fill))).scalars().all()
        assert fills == []
    recomputer_mock.recompute.assert_not_awaited()


async def test_missing_broker_order_id_is_noop(
    session_factory, recomputer_mock
) -> None:
    bus = EventBus()
    consumer = TradeUpdateConsumer(session_factory, bus, recomputer_mock)
    await consumer._handle({"event": "fill", "qty": "1", "price": "1"})
    # No exception; nothing written.
