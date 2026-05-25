"""Integration tests for :class:`BacktestWorker`.

The happy-path test runs the real :class:`Backtester` against committed
AAPL fixture parquets; it skips if those fixtures aren't present (the
local Norton SSL environment couldn't generate them — see P2 S3
session log). The reconciliation + queued-cancel tests don't need
fixtures and always run.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
import pytest_asyncio
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import BacktestJobStatus, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_job import BacktestJob
from app.db.models.backtest_result import BacktestResult
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.indicators import IndicatorComputer
from app.services.backtest_worker import BacktestWorker

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"
FIXTURE_DAYS = ["2025-11-03", "2025-11-04", "2025-11-05"]


def _now() -> datetime:
    return datetime.now(UTC)


def _load_fixture_bars_or_skip() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for d in FIXTURE_DAYS:
        path = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not path.exists():
            pytest.skip(f"Fixture not present: {path}")
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


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
async def worker_setup(
    session_factory,
) -> AsyncIterator[
    tuple[BacktestWorker, AsyncIOScheduler, EventBus, async_sessionmaker]
]:
    await _seed(session_factory)
    scheduler = AsyncIOScheduler()
    scheduler.start()
    bus = EventBus()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=pd.DataFrame())
    indicator_computer = IndicatorComputer()
    w = BacktestWorker(
        scheduler=scheduler,
        session_factory=session_factory,
        bar_cache=bar_cache,
        indicator_computer=indicator_computer,
        bus=bus,
    )
    try:
        yield w, scheduler, bus, session_factory
    finally:
        scheduler.shutdown(wait=False)


async def test_worker_reconciles_orphaned_running_on_start(worker_setup) -> None:
    """Rows still in RUNNING when the worker boots must be marked FAILED."""
    w, _, _, factory = worker_setup
    async with factory() as session:
        session.add(
            BacktestJob(
                user_id=1,
                strategy_id=1,
                status=BacktestJobStatus.RUNNING,
                label="orphan",
                config_json={},
                percent_complete=42.0,
                submitted_at=_now(),
                started_at=_now(),
            )
        )
        await session.commit()

    await w.start()

    async with factory() as session:
        orphans = (
            await session.execute(
                select(BacktestJob).where(BacktestJob.label == "orphan")
            )
        ).scalars().all()
    assert len(orphans) == 1
    assert orphans[0].status == BacktestJobStatus.FAILED
    assert "abandoned" in (orphans[0].error_text or "")


async def test_worker_cancels_queued_job_synchronously(worker_setup) -> None:
    """A QUEUED job is cancelled inline (no worker tick required)."""
    w, _, _, factory = worker_setup
    async with factory() as session:
        job = BacktestJob(
            user_id=1,
            strategy_id=1,
            status=BacktestJobStatus.QUEUED,
            label="to-cancel",
            config_json={},
            percent_complete=0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        jid = job.id

    accepted = await w.request_cancel(jid)
    assert accepted is True

    async with factory() as session:
        row = await session.get(BacktestJob, jid)
    assert row.status == BacktestJobStatus.CANCELLED
    assert row.error_text is not None and "cancelled" in row.error_text.lower()


async def test_worker_request_cancel_returns_false_for_terminal_job(
    worker_setup,
) -> None:
    """COMPLETED / FAILED / CANCELLED jobs can't be re-cancelled."""
    w, _, _, factory = worker_setup
    async with factory() as session:
        job = BacktestJob(
            user_id=1,
            strategy_id=1,
            status=BacktestJobStatus.COMPLETED,
            label="done",
            config_json={},
            percent_complete=100,
            submitted_at=_now(),
            completed_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        jid = job.id

    accepted = await w.request_cancel(jid)
    assert accepted is False


async def test_worker_completes_a_queued_job(worker_setup) -> None:
    """End-to-end: queue a job, start the worker, wait for COMPLETED + the
    persisted BacktestResult. Requires committed AAPL fixtures."""
    bars = _load_fixture_bars_or_skip()
    w, _, bus, factory = worker_setup

    # Capture every bus event the worker emits.
    received: list[tuple[str, dict]] = []

    async def collector(topic: str, payload: dict) -> None:
        received.append((topic, payload))

    original_publish = bus.publish

    async def wrapped_publish(topic, payload):
        await collector(topic, payload)
        await original_publish(topic, payload)

    bus.publish = wrapped_publish  # type: ignore[assignment]

    # Re-bind bar_cache to return the real fixture bars.
    w._bar_cache.get_bars = AsyncMock(return_value=bars)

    async with factory() as session:
        job = BacktestJob(
            user_id=1,
            strategy_id=1,
            status=BacktestJobStatus.QUEUED,
            label="test",
            config_json={
                "start": "2025-11-03T00:00:00+00:00",
                "end": "2025-11-06T00:00:00+00:00",
                "initial_equity": "100000",
                "slippage_bps": 5.0,
                "commission_per_share": 0.0,
                "timeframe": "1Min",
                "params": {},
                "_symbols": ["AAPL"],
            },
            percent_complete=0.0,
            submitted_at=_now(),
        )
        session.add(job)
        await session.commit()
        await session.refresh(job)
        jid = job.id

    await w.start()

    # Poll until terminal (with a generous timeout).
    for _ in range(60):
        await asyncio.sleep(0.5)
        async with factory() as session:
            row = await session.get(BacktestJob, jid)
            if row.status in (
                BacktestJobStatus.COMPLETED,
                BacktestJobStatus.FAILED,
                BacktestJobStatus.CANCELLED,
            ):
                break

    async with factory() as session:
        final = await session.get(BacktestJob, jid)
    assert final.status == BacktestJobStatus.COMPLETED, (
        f"job ended {final.status.value}: {final.error_text}"
    )
    assert final.result_id is not None
    assert final.percent_complete == 100.0

    async with factory() as session:
        result = await session.get(BacktestResult, final.result_id)
    assert result is not None
    assert result.strategy_id == 1

    # We should have seen at least started + completed events on the bus.
    topics = [t for t, _ in received]
    assert "backtest.started" in topics
    assert "backtest.completed" in topics
