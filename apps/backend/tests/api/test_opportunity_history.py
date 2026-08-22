"""GET /api/v1/opportunities/history — durable occurrences, read-time price."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, date, datetime

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.opportunity_occurrence import OpportunityOccurrence
from app.db.models.user import User
from app.research.disc001.spec import PRICE_SOURCE_GAP, PRICE_SOURCE_SEP, SCREEN_ID, SCREEN_VERSION


def _nvda_series() -> dict[str, tuple[tuple[date, float], ...]]:
    return {
        "NVDA": (
            (date(2026, 8, 14), 100.0),
            (date(2026, 8, 17), 104.0),
            (date(2026, 8, 18), 106.0),
            (date(2026, 8, 19), 120.5),
            (date(2026, 8, 20), 130.0),
            (date(2026, 8, 21), 128.0),
        )
    }


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
        session.add(
            OpportunityOccurrence(
                symbol="XYZ",
                candidate_date="2026-08-19",
                family="GAP",
                horizon="hours–1d",
                status_at_proposal="Backtest Pending",
                proposal_price=12.0,
                proposal_price_source=PRICE_SOURCE_GAP,
                adjustment_basis=PRICE_SOURCE_GAP,
                screen_id=SCREEN_ID,
                screen_version=SCREEN_VERSION,
                snapshot_sha256="c" * 64,
                snapshot_generated_at="2026-08-20T20:20:00+00:00",
                reason_json='{"chips":[{"key":"gap","value":"+8.1%"}],"why":"gap"}',
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
        "app.api.v1.opportunities.history_price_series",
        lambda symbols, start, end=None: _nvda_series(),
    )
    monkeypatch.setattr(
        "app.api.v1.opportunities.explain_history_why_left",
        lambda items, sessions_by_symbol: {},
    )
    resp = await client.get("/api/v1/opportunities/history")
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "summary"
    by_family = {item["family"]: item for item in body["items"] if item["symbol"] == "NVDA"}
    item = by_family["OVERSOLD"]
    assert item["candidate_date"] == "2026-08-19"
    assert item["proposal_price"] == 120.5
    assert item["first_seen"] == "2026-08-14"
    assert item["last_seen"] == "2026-08-19"
    assert item["occurrence_count"] == 2
    assert item["current_price"] == 128.0
    assert item["change_pct"] == pytest.approx(128.0 / 120.5 - 1.0)
    assert item["screen_version"] == "v0.3.0"
    by_cp = {c["checkpoint"]: c for c in item["checkpoints"]}
    assert by_cp["D1"]["price"] == 130.0
    assert by_cp["D1"]["return_pct"] == pytest.approx(130.0 / 120.5 - 1.0)
    assert by_cp["D5"]["price"] is None
    assert item["horizon"] == "1–10d"


async def test_timeline_keeps_every_row(client_and_factory, monkeypatch) -> None:
    client, _ = client_and_factory
    monkeypatch.setattr(
        "app.api.v1.opportunities.history_price_series",
        lambda symbols, start, end=None: {},
    )
    monkeypatch.setattr(
        "app.api.v1.opportunities.explain_history_why_left",
        lambda items, sessions_by_symbol: {},
    )
    resp = await client.get("/api/v1/opportunities/history", params={"symbol": "NVDA"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["view"] == "timeline"
    assert [row["candidate_date"] for row in body["items"]] == ["2026-08-14", "2026-08-19"]
    assert body["items"][0]["proposal_price"] == 100.0
    assert body["items"][1]["proposal_price"] == 120.5
    assert body["items"][0]["current_price"] is None


async def test_gap_current_price_is_shown_without_mixed_basis_return(
    client_and_factory, monkeypatch
) -> None:
    client, _ = client_and_factory

    def series(symbols, start, end=None):
        out = _nvda_series()
        out["XYZ"] = (
            (date(2026, 8, 19), 11.5),
            (date(2026, 8, 20), 13.0),
        )
        return out

    monkeypatch.setattr("app.api.v1.opportunities.history_price_series", series)
    monkeypatch.setattr(
        "app.api.v1.opportunities.explain_history_why_left",
        lambda items, sessions_by_symbol: {},
    )
    resp = await client.get("/api/v1/opportunities/history")
    assert resp.status_code == 200
    gap = next(item for item in resp.json()["items"] if item["family"] == "GAP")
    assert gap["horizon"] == "hours–1d"
    assert gap["current_price"] == 13.0
    assert gap["change_pct"] is None
    by_cp = {c["checkpoint"]: c for c in gap["checkpoints"]}
    assert by_cp["D1"]["price"] == 13.0
    assert by_cp["D1"]["return_pct"] is None
    assert by_cp["D1"]["adjustment_basis"] == PRICE_SOURCE_SEP
    assert by_cp["PROPOSAL"]["adjustment_basis"] == PRICE_SOURCE_GAP


async def test_why_left_is_read_time_frozen_rule_not_a_signal(
    client_and_factory, monkeypatch
) -> None:
    from app.research.disc001.why_left import NOT_A_SIGNAL, STATE_NO_LONGER_MEETS, WhyLeft

    def why(items, sessions_by_symbol):
        out = {}
        for symbol, family, candidate_date in items:
            out[(symbol, family, candidate_date)] = WhyLeft(
                family=family,
                state=STATE_NO_LONGER_MEETS,
                as_of="2026-08-21",
                summary="No longer OVERSOLD: RSI14 = 34.2.",
                details=("RSI14 = 34.2",),
                not_a_signal=NOT_A_SIGNAL,
            )
        return out

    monkeypatch.setattr(
        "app.api.v1.opportunities.history_price_series",
        lambda symbols, start, end=None: _nvda_series(),
    )
    monkeypatch.setattr("app.api.v1.opportunities.explain_history_why_left", why)
    client, _ = client_and_factory
    resp = await client.get("/api/v1/opportunities/history")
    assert resp.status_code == 200
    item = next(
        row
        for row in resp.json()["items"]
        if row["symbol"] == "NVDA" and row["family"] == "OVERSOLD"
    )
    assert item["why_left"]["summary"] == "No longer OVERSOLD: RSI14 = 34.2."
    assert item["why_left"]["not_a_signal"] == NOT_A_SIGNAL
    assert item["why_left"]["state"] == STATE_NO_LONGER_MEETS
    assert item["screen_version"] == "v0.3.0"

