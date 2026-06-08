"""P8 §2 — scanner endpoints: CRUD + run (persist + audit) + 400/503/404."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from typing import Any

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker


def _bars(close: float, rows: int = 5) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "t": pd.date_range("2026-01-01", periods=rows, tz="UTC"),
            "o": [close] * rows,
            "h": [close + 1] * rows,
            "l": [close - 1] * rows,
            "c": [close] * rows,
            "v": [1_000_000] * rows,
        }
    )


class _FakeBarCache:
    def __init__(self, bars_by_symbol: dict[str, pd.DataFrame]) -> None:
        self._b = bars_by_symbol

    async def get_bars(
        self, symbol: str, timeframe: str, start: Any, end: Any
    ) -> pd.DataFrame:
        return self._b.get(symbol, pd.DataFrame())


@pytest_asyncio.fixture
async def scanner_app() -> AsyncIterator[tuple[AsyncClient, Any, async_sessionmaker]]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.models.user import User
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    async with factory() as s:
        s.add(User(id=1, email="dev@workbench.local", display_name="Dev"))
        s.add(User(id=2, email="other@x", display_name="Other"))
        await s.commit()

    app = create_app()
    app.state.bar_cache = _FakeBarCache(
        {"AAPL": _bars(100.0), "MSFT": _bars(10.0)}  # TSLA absent → no_bars skip
    )
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, app, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


def _create_body() -> dict:
    return {
        "name": "above 50",
        "criteria": "close > 50",
        "universe": {"kind": "symbols", "symbols": ["AAPL", "MSFT", "TSLA"]},
    }


async def test_crud_lifecycle(scanner_app) -> None:
    client, _, _ = scanner_app
    r = await client.post("/api/v1/scanner/definitions", json=_create_body())
    assert r.status_code == 201
    did = r.json()["id"]
    assert r.json()["universe_symbols"] == ["AAPL", "MSFT", "TSLA"]

    assert (await client.get(f"/api/v1/scanner/definitions/{did}")).status_code == 200
    lst = await client.get("/api/v1/scanner/definitions")
    assert [d["id"] for d in lst.json()] == [did]

    assert (await client.delete(f"/api/v1/scanner/definitions/{did}")).status_code == 204
    assert (await client.get(f"/api/v1/scanner/definitions/{did}")).status_code == 404


async def test_invalid_criterion_400(scanner_app) -> None:
    client, _, _ = scanner_app
    body = _create_body()
    body["criteria"] = "rsi(14) < 30"  # Call → rejected
    r = await client.post("/api/v1/scanner/definitions", json=body)
    assert r.status_code == 400
    assert "invalid criterion" in r.json()["detail"]


async def test_run_persists_and_audits(scanner_app) -> None:
    from app.db.models.audit_log import AuditLog

    client, _, factory = scanner_app
    did = (await client.post("/api/v1/scanner/definitions", json=_create_body())).json()["id"]

    r = await client.post(f"/api/v1/scanner/definitions/{did}/run")
    assert r.status_code == 200
    run = r.json()
    assert run["status"] == "ok"
    assert run["universe_size"] == 3
    assert run["matched_count"] == 1
    assert run["evaluated_count"] == 2  # TSLA skipped
    assert [m["symbol"] for m in run["matched"]] == ["AAPL"]
    assert {s["symbol"]: s["reason"] for s in run["skipped"]} == {"TSLA": "no_bars"}

    # the run is queryable + a SCANNER_RUN audit row was written
    runs = await client.get(f"/api/v1/scanner/definitions/{did}/runs")
    assert [x["id"] for x in runs.json()] == [run["id"]]
    async with factory() as s:
        rows = (
            await s.execute(
                select(AuditLog).where(AuditLog.action == "SCANNER_RUN")
            )
        ).scalars().all()
    assert len(rows) == 1


async def test_run_without_bar_cache_503(scanner_app) -> None:
    client, app, _ = scanner_app
    did = (await client.post("/api/v1/scanner/definitions", json=_create_body())).json()["id"]
    app.state.bar_cache = None
    r = await client.post(f"/api/v1/scanner/definitions/{did}/run")
    assert r.status_code == 503


async def test_update_definition_preserves_id(scanner_app) -> None:
    client, _, _ = scanner_app
    did = (await client.post("/api/v1/scanner/definitions", json=_create_body())).json()["id"]
    body = _create_body()
    body["name"] = "renamed"
    body["criteria"] = "close > 200"
    r = await client.put(f"/api/v1/scanner/definitions/{did}", json=body)
    assert r.status_code == 200
    assert r.json()["id"] == did  # same row → run history preserved
    assert r.json()["name"] == "renamed"
    assert r.json()["criteria"] == "close > 200"


async def test_update_invalid_criterion_400(scanner_app) -> None:
    client, _, _ = scanner_app
    did = (await client.post("/api/v1/scanner/definitions", json=_create_body())).json()["id"]
    body = _create_body()
    body["criteria"] = "close[0] > 1"  # Subscript → rejected
    r = await client.put(f"/api/v1/scanner/definitions/{did}", json=body)
    assert r.status_code == 400


async def test_create_with_scheduled_flag(scanner_app) -> None:
    client, _, _ = scanner_app
    body = _create_body()
    body["scheduled"] = True
    r = await client.post("/api/v1/scanner/definitions", json=body)
    assert r.status_code == 201
    assert r.json()["scheduled"] is True
    # default is False
    r2 = await client.post("/api/v1/scanner/definitions", json=_create_body())
    assert r2.json()["scheduled"] is False


async def test_vocabulary(scanner_app) -> None:
    client, _, _ = scanner_app
    r = await client.get("/api/v1/scanner/vocabulary")
    assert r.status_code == 200
    body = r.json()
    assert "RSI14" in body["indicators"]
    assert "macd" in body["indicators"]
    assert "close" in body["fields"]
    assert "price" in body["fields"]


async def test_other_users_definition_404(scanner_app) -> None:
    client, _, factory = scanner_app
    from app.db.models.scanner_definition import ScannerDefinition

    async with factory() as s:
        now = datetime.now(UTC)
        d = ScannerDefinition(
            user_id=2,  # not the authenticated user (1)
            name="theirs",
            criteria="close > 1",
            universe_kind="symbols",
            universe_symbols_json=["AAPL"],
            timeframe="1Day",
            created_at=now,
            updated_at=now,
        )
        s.add(d)
        await s.commit()
        other_id = d.id

    assert (await client.get(f"/api/v1/scanner/definitions/{other_id}")).status_code == 404
