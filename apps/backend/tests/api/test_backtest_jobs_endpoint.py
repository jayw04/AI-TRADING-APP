"""Tests for the async backtest job REST surface (P4 §2).

Covers the new behavior of ``POST /api/v1/strategies/{id}/backtest`` (now
returns 202 with a job_id), plus the three new endpoints:

- ``GET  /api/v1/strategies/{id}/backtest-jobs`` (list, filter by status)
- ``GET  /api/v1/backtest-jobs/{id}``            (get state)
- ``POST /api/v1/backtest-jobs/{id}/cancel``     (request cancellation)

The worker itself is mocked here; ``test_backtest_worker.py`` exercises
the real worker against fixture bars.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import BacktestJobStatus, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_job import BacktestJob
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
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
                name="Apple",
                active=True,
            )
        )
        session.add(
            StrategyRow(
                id=1,
                user_id=1,
                name="rsi",
                version="0.1.0",
                type=StrategyType.PYTHON,
                status=StrategyStatus.IDLE,
                code_path="examples/rsi_meanreversion.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="*/1 * * * *",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> (
    AsyncIterator[tuple[AsyncClient, async_sessionmaker]]
):
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
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    app.state.indicator_computer = MagicMock()
    # Cancellation tests need a worker mock — the cancel endpoint reads
    # this off app.state.
    app.state.backtest_worker = MagicMock()
    app.state.backtest_worker.request_cancel = AsyncMock(return_value=True)

    # Replace bus.publish with a mock so we can assert on topics.
    bus = get_event_bus()
    bus.publish = AsyncMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


@pytest_asyncio.fixture
async def client(client_and_factory) -> AsyncClient:
    return client_and_factory[0]


@pytest_asyncio.fixture
async def factory(client_and_factory) -> async_sessionmaker:
    return client_and_factory[1]


# ---------- submit ----------


async def test_submit_returns_202_with_job_id(client, factory) -> None:
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-10T00:00:00+00:00",
            "label": "test",
            "slippage_bps": 5,
        },
    )
    assert resp.status_code == 202, resp.text
    body = resp.json()
    assert body["status"] == "queued"
    assert body["job_id"] > 0

    async with factory() as session:
        job = await session.get(BacktestJob, body["job_id"])
    assert job is not None
    assert job.label == "test"
    assert job.percent_complete == 0
    assert job.status == BacktestJobStatus.QUEUED


async def test_long_range_no_longer_rejected(client) -> None:
    """The 1-year cap that bounded the sync endpoint is gone."""
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2020-01-01T00:00:00+00:00",
            "end": "2025-01-01T00:00:00+00:00",
            "label": "long",
        },
    )
    assert resp.status_code == 202


async def test_inverted_range_still_rejected(client) -> None:
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-10T00:00:00+00:00",
            "end": "2025-11-03T00:00:00+00:00",
            "label": "backwards",
        },
    )
    assert resp.status_code == 400


async def test_extra_field_rejected(client) -> None:
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-06T00:00:00+00:00",
            "fnord": "extra",
        },
    )
    assert resp.status_code == 422


async def test_single_flight_per_strategy(client) -> None:
    """Second submit while the first is QUEUED returns 409."""
    r1 = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-10T00:00:00+00:00",
            "label": "first",
        },
    )
    assert r1.status_code == 202

    r2 = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-10T00:00:00+00:00",
            "label": "second",
        },
    )
    assert r2.status_code == 409


async def test_submit_publishes_queued_event(client) -> None:
    from app.events import get_event_bus

    bus = get_event_bus()
    await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-04T00:00:00+00:00",
        },
    )
    topics = [c.args[0] for c in bus.publish.call_args_list]
    assert "backtest.queued" in topics


# ---------- GET /backtest-jobs/{id} ----------


async def test_get_job_returns_state(client) -> None:
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-04T00:00:00+00:00",
            "label": "tiny",
        },
    )
    job_id = resp.json()["job_id"]

    r = await client.get(f"/api/v1/backtest-jobs/{job_id}")
    assert r.status_code == 200
    body = r.json()
    assert body["id"] == job_id
    assert body["status"] == "queued"
    assert body["label"] == "tiny"


async def test_get_job_returns_404_for_other_user(client, factory) -> None:
    async with factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.commit()
        job = BacktestJob(
            user_id=2,
            strategy_id=1,
            status=BacktestJobStatus.QUEUED,
            config_json={},
            label="x",
            percent_complete=0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        other_jid = job.id

    r = await client.get(f"/api/v1/backtest-jobs/{other_jid}")
    assert r.status_code == 404


# ---------- cancel ----------


async def test_cancel_calls_worker_and_succeeds(client) -> None:
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-04T00:00:00+00:00",
        },
    )
    job_id = resp.json()["job_id"]
    r = await client.post(f"/api/v1/backtest-jobs/{job_id}/cancel")
    assert r.status_code == 200
    client._transport.app.state.backtest_worker.request_cancel.assert_awaited_with(
        job_id
    )


async def test_cancel_returns_409_when_worker_refuses(client) -> None:
    """If the job is already terminal, the worker returns False."""
    resp = await client.post(
        "/api/v1/strategies/1/backtest",
        json={
            "start": "2025-11-03T00:00:00+00:00",
            "end": "2025-11-04T00:00:00+00:00",
        },
    )
    job_id = resp.json()["job_id"]
    client._transport.app.state.backtest_worker.request_cancel = AsyncMock(
        return_value=False
    )
    r = await client.post(f"/api/v1/backtest-jobs/{job_id}/cancel")
    assert r.status_code == 409


# ---------- list jobs ----------


async def test_list_jobs_filters_by_status(client, factory) -> None:
    """Three jobs in different statuses; status filter returns only matches."""
    for status in [
        BacktestJobStatus.QUEUED,
        BacktestJobStatus.COMPLETED,
        BacktestJobStatus.FAILED,
    ]:
        async with factory() as session:
            session.add(
                BacktestJob(
                    user_id=1,
                    strategy_id=1,
                    status=status,
                    config_json={},
                    label=status.value,
                    percent_complete=0,
                    submitted_at=_now(),
                )
            )
            await session.commit()

    r = await client.get("/api/v1/strategies/1/backtest-jobs?status=failed")
    assert r.status_code == 200
    body = r.json()
    assert body["count"] >= 1
    assert all(item["status"] == "failed" for item in body["items"])
