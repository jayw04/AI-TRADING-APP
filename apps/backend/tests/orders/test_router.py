"""OrderRouter — happy path, risk reject, broker reject, back-link verification."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.brokers.alpaca.errors import PermanentAlpacaError
from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.risk_check import RiskCheck
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.orders.router import OrderRouter
from app.risk import OrderRequest, RiskEngine


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
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
        await session.commit()
    yield


def _req(**ov) -> OrderRequest:
    base = dict(
        user_id=1,
        account_id=1,
        symbol_ticker="F",
        side=OrderSide.BUY,
        qty=Decimal("1"),
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
    )
    base.update(ov)
    return OrderRequest(**base)


@pytest.fixture
def adapter_mock_ok() -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.submit_order.return_value = {"id": "broker-1", "status": "accepted"}
    return a


@pytest.fixture
def adapter_mock_perm_fail() -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.submit_order.side_effect = PermanentAlpacaError("insufficient funds")
    return a


async def test_happy_path(session_factory, seeded, adapter_mock_ok) -> None:
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    order = await router.submit(_req())
    assert order.status == OrderStatus.SUBMITTED
    assert order.broker_order_id == "broker-1"

    async with session_factory() as session:
        # Audit chain for this order: ORDER_RISK_PASSED + ORDER_SUBMITTED.
        audits = (
            await session.execute(
                select(AuditLog).where(AuditLog.target_type == "order")
            )
        ).scalars().all()
        actions = {a.action for a in audits}
        assert "ORDER_RISK_PASSED" in actions
        assert "ORDER_SUBMITTED" in actions


async def test_risk_reject_never_calls_broker(
    session_factory, seeded, adapter_mock_ok
) -> None:
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    # qty 9999 exceeds position cap of 100
    order = await router.submit(_req(qty=Decimal("9999")))
    assert order.status == OrderStatus.REJECTED
    assert "POSITION_CAP_QTY" in (order.rejection_reason or "")
    adapter_mock_ok.submit_order.assert_not_called()


async def test_broker_permanent_error_marks_rejected(
    session_factory, seeded, adapter_mock_perm_fail
) -> None:
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_perm_fail, eng, session_factory, bus)

    order = await router.submit(_req())
    assert order.status == OrderStatus.REJECTED
    assert "insufficient funds" in (order.rejection_reason or "")


# ---- non-fractionable rounding (avoids the Alpaca "not fractionable" reject that trips
# the §6 strategy cooldown and cascades through a rebalance batch) ----


@pytest.fixture
def adapter_non_fractionable() -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.is_fractionable.return_value = False
    a.submit_order.return_value = {"id": "broker-nf", "status": "accepted"}
    return a


async def test_non_fractionable_qty_floored_to_whole_shares(
    session_factory, seeded, adapter_non_fractionable
) -> None:
    router = OrderRouter(
        adapter_non_fractionable, RiskEngine(session_factory), session_factory, EventBus()
    )
    order = await router.submit(_req(qty=Decimal("5.7")))
    assert order.status == OrderStatus.SUBMITTED
    # The broker saw WHOLE shares — never the fractional 5.7 (which Alpaca rejects).
    assert adapter_non_fractionable.submit_order.call_args.kwargs["qty"] == Decimal("5")


async def test_fractionable_qty_is_left_untouched(
    session_factory, seeded, adapter_mock_ok
) -> None:
    adapter_mock_ok.is_fractionable.return_value = True
    router = OrderRouter(
        adapter_mock_ok, RiskEngine(session_factory), session_factory, EventBus()
    )
    order = await router.submit(_req(qty=Decimal("5.7")))
    assert order.status == OrderStatus.SUBMITTED
    assert adapter_mock_ok.submit_order.call_args.kwargs["qty"] == Decimal("5.7")


async def test_non_fractionable_sub_share_rejected_without_broker_call(
    session_factory, seeded, adapter_non_fractionable
) -> None:
    router = OrderRouter(
        adapter_non_fractionable, RiskEngine(session_factory), session_factory, EventBus()
    )
    order = await router.submit(_req(qty=Decimal("0.5")))
    assert order.status == OrderStatus.REJECTED
    assert "NON_FRACTIONABLE_SUB_SHARE" in (order.rejection_reason or "")
    adapter_non_fractionable.submit_order.assert_not_called()


async def test_risk_check_back_links_order(
    session_factory, seeded, adapter_mock_ok
) -> None:
    bus = EventBus()
    eng = RiskEngine(session_factory)
    router = OrderRouter(adapter_mock_ok, eng, session_factory, bus)

    order = await router.submit(_req())
    async with session_factory() as session:
        rc = (
            await session.execute(
                select(RiskCheck).where(RiskCheck.id == order.risk_check_id)
            )
        ).scalars().first()
        assert rc is not None
        assert rc.order_id == order.id
