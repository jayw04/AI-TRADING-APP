"""Smoke tests for ``/api/v1/orders`` REST endpoints.

These exercise the FastAPI handler layer with a real DB but a mocked
``OrderRouter`` stashed on ``app.state.order_router``. The router itself is
covered by ``tests/orders/test_router.py``; here we only care about request
parsing (Pydantic strictness, status filters) and ownership behavior.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.order import Order
from app.db.models.risk_limits import RiskLimits
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test"))
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
        await session.commit()


@pytest_asyncio.fixture
async def client_with_mock_router() -> AsyncIterator[AsyncClient]:
    """A test client with seeded DB + a controllable mock router on app.state.

    The mock's ``submit`` persists a real Order row so the endpoint's
    re-fetch + relationship load works the same way it does in prod.
    """
    from app.config import get_settings
    from app.db import models  # noqa: F401 — register models on Base.metadata
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    await _seed(factory)

    app = create_app()

    submitted_counter = {"n": 0}

    async def _submit(req):
        submitted_counter["n"] += 1
        async with factory() as session:
            order = Order(
                user_id=req.user_id,
                account_id=req.account_id,
                symbol_id=1,  # AAPL — only seeded symbol
                broker_order_id=f"mock-{submitted_counter['n']}",
                client_order_id=req.client_order_id or f"twb-mock-{submitted_counter['n']}",
                side=req.side,
                qty=req.qty,
                type=req.type,
                limit_price=req.limit_price,
                stop_price=req.stop_price,
                tif=req.tif,
                extended_hours=req.extended_hours,
                status=OrderStatus.SUBMITTED,
                source_type=req.source_type,
                created_at=_now(),
                submitted_at=_now(),
                updated_at=_now(),
            )
            session.add(order)
            await session.commit()
            await session.refresh(order)
            return order

    mock_router = MagicMock()
    mock_router.submit = _submit
    app.state.order_router = mock_router

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_post_orders_happy_path(client_with_mock_router) -> None:
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "side": "buy", "qty": "1", "type": "market", "tif": "day"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["status"] == "submitted"
    assert data["symbol"] == "AAPL"
    assert data["broker_order_id"].startswith("mock-")


async def test_post_orders_rejects_extra_field(client_with_mock_router) -> None:
    """Pydantic's ``extra='forbid'`` is the schema-level tripwire that stops a
    typo from silently bypassing the risk engine via a misnamed override."""
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={
            "symbol": "AAPL",
            "side": "buy",
            "qty": "1",
            "type": "market",
            "fnord": "bypass-the-risk-engine",
        },
    )
    assert resp.status_code == 422


async def test_post_orders_rejects_negative_qty(client_with_mock_router) -> None:
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "AAPL", "side": "buy", "qty": "-1", "type": "market"},
    )
    assert resp.status_code == 422


async def test_post_orders_normalizes_symbol_to_upper(client_with_mock_router) -> None:
    resp = await client_with_mock_router.post(
        "/api/v1/orders",
        json={"symbol": "aapl", "side": "buy", "qty": "1", "type": "market"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["symbol"] == "AAPL"


async def test_get_orders_filters_by_status(client_with_mock_router) -> None:
    from app.db.session import get_sessionmaker

    factory = get_sessionmaker()
    async with factory() as session:
        # one open, one already-filled (terminal)
        session.add(
            Order(
                user_id=1, account_id=1, symbol_id=1,
                broker_order_id="open-1",
                client_order_id="twb-open-1",
                side=OrderSide.BUY, qty=Decimal("1"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED,
                source_type=OrderSourceType.MANUAL,
                created_at=_now(), updated_at=_now(),
            )
        )
        session.add(
            Order(
                user_id=1, account_id=1, symbol_id=1,
                broker_order_id="filled-1",
                client_order_id="twb-filled-1",
                side=OrderSide.BUY, qty=Decimal("1"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                status=OrderStatus.FILLED,
                source_type=OrderSourceType.MANUAL,
                created_at=_now(), updated_at=_now(), terminal_at=_now(),
            )
        )
        await session.commit()

    resp_open = await client_with_mock_router.get("/api/v1/orders?status=open")
    assert resp_open.status_code == 200
    assert resp_open.json()["count"] == 1

    resp_history = await client_with_mock_router.get("/api/v1/orders?status=history")
    assert resp_history.status_code == 200
    assert resp_history.json()["count"] == 1


async def test_get_order_by_id_404_when_not_owned(client_with_mock_router) -> None:
    """Stub auth returns user_id=1; an order owned by user_id=2 must 404,
    not 200, to prevent cross-account leakage."""
    from app.db.session import get_sessionmaker

    factory = get_sessionmaker()
    async with factory() as session:
        session.add(User(id=2, email="other@test"))
        session.add(
            Account(
                id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="Other"
            )
        )
        session.add(
            Order(
                id=42,
                user_id=2, account_id=2, symbol_id=1,
                broker_order_id="other-1",
                client_order_id="twb-other-1",
                side=OrderSide.BUY, qty=Decimal("1"),
                type=OrderType.MARKET, tif=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED,
                source_type=OrderSourceType.MANUAL,
                created_at=_now(), updated_at=_now(),
            )
        )
        await session.commit()

    resp = await client_with_mock_router.get("/api/v1/orders/42")
    assert resp.status_code == 404


async def test_post_orders_503_when_no_router_configured() -> None:
    """If the lifespan didn't wire app.state.order_router (e.g. broker
    startup disabled), the endpoint must 503 rather than crash."""
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    await _seed(get_sessionmaker())

    app = create_app()
    # Do NOT set app.state.order_router.
    transport = ASGITransport(app=app)
    try:
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            resp = await ac.post(
                "/api/v1/orders",
                json={"symbol": "AAPL", "side": "buy", "qty": "1", "type": "market"},
            )
        assert resp.status_code == 503
    finally:
        await engine.dispose()
        get_engine.cache_clear()
        get_sessionmaker.cache_clear()


# ---------- P4 §5: source_type / source_id filter ----------


async def _seed_order(
    *,
    user_id: int = 1,
    account_id: int = 1,
    symbol_id: int = 1,
    source_type: OrderSourceType,
    source_id: str | None,
    status: OrderStatus = OrderStatus.SUBMITTED,
    tag: str | None = None,
) -> int:
    """Persist one Order row through the test session factory. Returns the
    new row's id so a test can assert against it specifically."""
    from app.db.session import get_sessionmaker

    factory = get_sessionmaker()
    suffix = tag or f"{source_type.value}-{source_id or 'na'}"
    async with factory() as session:
        order = Order(
            user_id=user_id,
            account_id=account_id,
            symbol_id=symbol_id,
            broker_order_id=f"src-test-{suffix}-{_now().timestamp()}",
            client_order_id=f"twb-src-test-{suffix}-{_now().timestamp()}",
            side=OrderSide.BUY,
            qty=Decimal("10"),
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            status=status,
            source_type=source_type,
            source_id=source_id,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(order)
        await session.commit()
        await session.refresh(order)
        return order.id


async def test_filter_by_source_type_manual(client_with_mock_router) -> None:
    await _seed_order(source_type=OrderSourceType.MANUAL, source_id=None)
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="7")

    resp = await client_with_mock_router.get("/api/v1/orders?source_type=manual")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["source_type"] == "manual"


async def test_filter_by_source_type_and_id(client_with_mock_router) -> None:
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="7")
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="8")
    await _seed_order(source_type=OrderSourceType.MANUAL, source_id=None)

    resp = await client_with_mock_router.get(
        "/api/v1/orders?source_type=strategy&source_id=7"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["source_id"] == "7"
    assert body["items"][0]["source_type"] == "strategy"


async def test_source_id_without_source_type_returns_400(
    client_with_mock_router,
) -> None:
    resp = await client_with_mock_router.get("/api/v1/orders?source_id=42")
    assert resp.status_code == 400
    assert "requires source_type" in resp.json()["detail"]


async def test_source_filter_returns_empty_when_no_match(
    client_with_mock_router,
) -> None:
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="7")
    resp = await client_with_mock_router.get(
        "/api/v1/orders?source_type=strategy&source_id=999"
    )
    assert resp.status_code == 200
    assert resp.json()["count"] == 0


async def test_source_type_only_returns_all_orders_of_that_type(
    client_with_mock_router,
) -> None:
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="7")
    await _seed_order(source_type=OrderSourceType.STRATEGY, source_id="8")
    await _seed_order(source_type=OrderSourceType.MANUAL, source_id=None)

    resp = await client_with_mock_router.get("/api/v1/orders?source_type=strategy")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 2
    assert all(item["source_type"] == "strategy" for item in body["items"])


async def test_source_filter_combines_with_status_open(
    client_with_mock_router,
) -> None:
    """Strategy filter + status=open (the existing string param) compose
    correctly — only non-terminal orders of that source remain."""
    open_id = await _seed_order(
        source_type=OrderSourceType.STRATEGY,
        source_id="7",
        status=OrderStatus.SUBMITTED,
        tag="open",
    )
    await _seed_order(
        source_type=OrderSourceType.STRATEGY,
        source_id="7",
        status=OrderStatus.FILLED,
        tag="filled",
    )

    resp = await client_with_mock_router.get(
        "/api/v1/orders?source_type=strategy&source_id=7&status=open"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["id"] == open_id


async def test_source_filter_combines_with_symbol(client_with_mock_router) -> None:
    """Strategy orders on AAPL vs MSFT; filter by symbol drops MSFT."""
    from app.db.session import get_sessionmaker

    factory = get_sessionmaker()
    async with factory() as session:
        session.add(
            Symbol(
                id=2,
                ticker="MSFT",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Microsoft",
                active=True,
            )
        )
        await session.commit()
    await _seed_order(
        symbol_id=1, source_type=OrderSourceType.STRATEGY, source_id="7", tag="aapl"
    )
    await _seed_order(
        symbol_id=2, source_type=OrderSourceType.STRATEGY, source_id="7", tag="msft"
    )

    resp = await client_with_mock_router.get(
        "/api/v1/orders?source_type=strategy&source_id=7&symbol=AAPL"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "AAPL"


async def test_invalid_source_type_returns_422(client_with_mock_router) -> None:
    """FastAPI's enum-coercion of OrderSourceType rejects unknown values
    with 422 (Unprocessable Entity), not 400."""
    resp = await client_with_mock_router.get("/api/v1/orders?source_type=garbage")
    assert resp.status_code == 422


# Reference list — Order.unrealized_pl read used only at top to keep
# the IDE happy that the import wasn't dropped.
_ = select(Order)
