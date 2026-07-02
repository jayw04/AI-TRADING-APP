"""Tests for /api/v1/journal — the trade journal + per-trade notes.

Exercises the handler layer against a real (in-memory) DB. The auth stub resolves
to user 1, so user-2 rows exercise the ownership boundary.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


def _order(**kw) -> Order:
    base = dict(
        account_id=1,
        symbol_id=1,
        type=OrderType.MARKET,
        tif=TimeInForce.DAY,
        source_type=OrderSourceType.MANUAL,
        created_at=_now(),
        submitted_at=_now(),
        updated_at=_now(),
    )
    base.update(kw)
    return Order(**base)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test"))
        session.add(User(id=2, email="other@test"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"))
        session.add(Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="P2"))
        session.add(
            Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity", name="Apple", active=True)
        )
        # user 1: a FILLED buy (10 @ 150) — appears in the journal
        session.add(_order(id=100, user_id=1, side=OrderSide.BUY, qty=Decimal("10"), status=OrderStatus.FILLED))
        session.add(Fill(order_id=100, qty=Decimal("10"), price=Decimal("150.00"), filled_at=_now()))
        # user 1: a SUBMITTED order — must NOT appear (not a completed trade)
        session.add(_order(id=101, user_id=1, side=OrderSide.BUY, qty=Decimal("5"), status=OrderStatus.SUBMITTED))
        # user 2: a FILLED order — ownership boundary
        session.add(_order(id=200, user_id=2, account_id=2, side=OrderSide.SELL, qty=Decimal("3"), status=OrderStatus.FILLED))
        session.add(Fill(order_id=200, qty=Decimal("3"), price=Decimal("140.00"), filled_at=_now()))
        await session.commit()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
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
    await _seed(get_sessionmaker())

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_journal_lists_only_filled_owned_trades(client) -> None:
    resp = await client.get("/api/v1/journal")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    # Only user 1's FILLED order — not the SUBMITTED one, not user 2's.
    assert data["count"] == 1
    entry = data["items"][0]
    assert entry["order_id"] == 100
    assert entry["symbol"] == "AAPL"
    assert entry["side"] == "buy"
    assert entry["source_label"] == "Manual"
    assert Decimal(entry["avg_fill_price"]) == Decimal("150.00")
    assert Decimal(entry["value"]) == Decimal("1500.00")
    assert entry["note"] == ""


async def test_upsert_note_then_reflected_in_list(client) -> None:
    put = await client.put("/api/v1/journal/100/note", json={"note": "bought the dip"})
    assert put.status_code == 200, put.text
    assert put.json() == {"order_id": 100, "note": "bought the dip"}

    # Update (upsert) the same note.
    put2 = await client.put("/api/v1/journal/100/note", json={"note": "revised rationale"})
    assert put2.status_code == 200

    resp = await client.get("/api/v1/journal")
    entry = next(e for e in resp.json()["items"] if e["order_id"] == 100)
    assert entry["note"] == "revised rationale"


async def test_note_on_foreign_order_is_404(client) -> None:
    # Order 200 belongs to user 2; the auth stub is user 1.
    resp = await client.put("/api/v1/journal/200/note", json={"note": "nope"})
    assert resp.status_code == 404
