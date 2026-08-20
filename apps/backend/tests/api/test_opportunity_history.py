"""GET /api/v1/opportunities/history — durable occurrences, read-time price."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.opportunity_occurrence import OpportunityOccurrence
from app.db.models.user import User
from app.research.disc001.spec import PRICE_SOURCE_SEP, SCREEN_ID, SCREEN_VERSION
from app.services.opportunity_history import PriceQuote


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            OpportunityOccurrence(
                symbol="NVDA",
                candidate_date="2026-08-14",
                family="OVERSOLD",
                horizon="1–10d",
                status_at_proposal="Watch",
                proposal_price=100.0,
                proposal_price_source=PRICE_SOURCE_SEP,
                adjustment_basis=PRICE_SOURCE_SEP,
                screen_id=SCREEN_ID,
                screen_version=SCREEN_VERSION,
                snapshot_sha256="a" * 64,
                snapshot_generated_at="2026-08-14T20:20:00+00:00",
                reason_json='{"chips":[{"key":"rsi14","value":"24"}],"why":"first"}',
                features_json=None,
                created_at=datetime(2026, 8, 14, tzinfo=UTC),
            )
        )
        session.add(
            OpportunityOccurrence(
                symbol="NVDA",
                candidate_date="2026-08-19",
                family="OVERSOLD",
                horizon="1–10d",
                status_at_proposal="Watch",
                proposal_price=120.5,
                proposal_price_source=PRICE_SOURCE_SEP,
                adjustment_basis=PRICE_SOURCE_SEP,
                screen_id=SCREEN_ID,
                screen_version=SCREEN_VERSION,
                snapshot_sha256="b" * 64,
                snapshot_generated_at="2026-08-20T20:20:00+00:00",
                reason_json='{"chips":[{"key":"rsi14","value":"22"}],"why":"later"}',
                features_json=None,
                created_at=datetime(2026, 8, 20, tzinfo=UTC),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> AsyncIterator[tuple[AsyncClient, async_sessionmaker]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.events.bus import get_event_bus
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    await _seed(factory)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


async def test_summary_uses_last_occurrence(client_and_factory, monkeypatch) -> None:
    client, _ = client_and_factory
    monkeypatch.setattr(
        "app.api.v1.opportunities.latest_closes",
        lambda symbols: {
            "NVDA": PriceQuote(price=130.0, as_of="2026-08-20", source=PRICE_SOURCE_SEP)
        },
    )
    resp = await client.get("/api/v1/opportunities/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "summary"
    assert body["count"] == 1
    item = body["items"][0]
    assert item["symbol"] == "NVDA"
    assert item["candidate_date"] == "2026-08-19"
    assert item["proposal_price"] == 120.5
    assert item["first_seen"] == "2026-08-14"
    assert item["last_seen"] == "2026-08-19"
    assert item["occurrence_count"] == 2
    assert item["current_price"] == 130.0
    assert item["change_pct"] == pytest.approx(130.0 / 120.5 - 1.0)
    assert item["screen_version"] == "v0.3.0"


async def test_timeline_keeps_every_row(client_and_factory, monkeypatch) -> None:
    client, _ = client_and_factory
    monkeypatch.setattr("app.api.v1.opportunities.latest_closes", lambda symbols: {})
    resp = await client.get("/api/v1/opportunities/history", params={"symbol": "NVDA"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "timeline"
    assert [row["candidate_date"] for row in body["items"]] == ["2026-08-14", "2026-08-19"]
    assert body["items"][0]["proposal_price"] == 100.0
    assert body["items"][1]["proposal_price"] == 120.5
    assert body["items"][0]["current_price"] is None
