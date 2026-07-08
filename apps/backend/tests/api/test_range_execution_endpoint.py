"""GET /api/v1/range-execution — date-window filtering + response shape.

The app is driven via ASGITransport (no lifespan), so ``app.state.bar_cache`` is unset → the endpoint's
read-through capture is a no-op and it returns the seeded rows. Capture itself is covered in
tests/services/test_range_execution.py.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.range_execution_record import RangeExecutionRecord


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as s:
        s.add(RangeExecutionRecord(et_date=date(2026, 7, 7), symbol="MU",
                                   avg_buy_price=Decimal("910.81"), avg_sell_price=None,
                                   daily_low=Decimal("891.75"), daily_high=Decimal("941.32"),
                                   captured_at=_now()))
        s.add(RangeExecutionRecord(et_date=date(2026, 7, 7), symbol="INTC",
                                   avg_buy_price=Decimal("110.68"), avg_sell_price=None,
                                   daily_low=Decimal("108.30"), daily_high=Decimal("116.25"),
                                   captured_at=_now()))
        s.add(RangeExecutionRecord(et_date=date(2026, 7, 8), symbol="MU",
                                   avg_buy_price=None, avg_sell_price=None,
                                   daily_low=Decimal("902.58"), daily_high=Decimal("958.92"),
                                   captured_at=_now()))
        await s.commit()


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
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_window_filters_to_single_day(client) -> None:
    resp = await client.get("/api/v1/range-execution?from_date=2026-07-07&to_date=2026-07-07")
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["count"] == 2  # MU + INTC on 07-07; 07-08 excluded
    assert {i["symbol"] for i in data["items"]} == {"MU", "INTC"}
    mu = next(i for i in data["items"] if i["symbol"] == "MU")
    assert Decimal(mu["avg_buy_price"]) == Decimal("910.81")
    assert mu["avg_sell_price"] is None
    assert Decimal(mu["daily_low"]) == Decimal("891.75")
    assert Decimal(mu["daily_high"]) == Decimal("941.32")


async def test_full_window_returns_all_rows_ordered(client) -> None:
    resp = await client.get("/api/v1/range-execution?from_date=2026-07-01&to_date=2026-07-31")
    assert resp.status_code == 200, resp.text
    items = resp.json()["items"]
    assert len(items) == 3
    # ordered by et_date, then symbol
    assert [(i["et_date"], i["symbol"]) for i in items] == [
        ("2026-07-07", "INTC"), ("2026-07-07", "MU"), ("2026-07-08", "MU"),
    ]
