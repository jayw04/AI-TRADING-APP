"""Tests for /api/v1/range-levels — the range buy/sell/stop monitoring feed."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import SignalType, StrategyStatus
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test"))
        session.add(User(id=2, email="other@test"))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"))
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity", name="Apple", active=True))
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ", asset_class="us_equity", name="Microsoft", active=True))
        session.add(
            Strategy(
                id=1, user_id=1, name="Range Trader", status=StrategyStatus.PAPER,
                symbols_json=["AAPL", "MSFT"], created_at=_now(), updated_at=_now(),
            )
        )
        # AAPL has published levels + a held position; MSFT has no levels yet (forming).
        session.add(
            Signal(
                user_id=1, strategy_id=1, symbol_id=1, type=SignalType.INFO,
                payload_json={"kind": "range_levels", "buy": 100.0, "sell": 110.0, "stop": 98.0},
                received_at=_now(),
            )
        )
        session.add(Position(user_id=1, account_id=1, symbol_id=1, qty=Decimal("5"), updated_at=_now()))
        # another user's strategy (ownership boundary)
        session.add(
            Strategy(
                id=2, user_id=2, name="Other", status=StrategyStatus.PAPER,
                symbols_json=["AAPL"], created_at=_now(), updated_at=_now(),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac
    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_range_levels_shows_published_levels_and_position(client) -> None:
    resp = await client.get("/api/v1/range-levels")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["strategy_id"] == 1
    rows = {r["symbol"]: r for r in data["rows"]}
    assert set(rows) == {"AAPL", "MSFT"}
    # AAPL: levels from the signal + held position → holding
    aapl = rows["AAPL"]
    assert aapl["buy"] == 100.0 and aapl["sell"] == 110.0 and aapl["stop"] == 98.0
    assert aapl["position_qty"] == 5.0
    assert aapl["status"] == "holding"
    # MSFT: no published levels yet → forming, flat
    msft = rows["MSFT"]
    assert msft["buy"] is None
    assert msft["position_qty"] == 0.0
    assert msft["status"] == "forming"


async def test_range_levels_foreign_strategy_is_404(client) -> None:
    resp = await client.get("/api/v1/range-levels?strategy_id=2")
    assert resp.status_code == 404
