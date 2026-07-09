"""Scheduler heartbeat — the dispatch-liveness stamp (MissedDispatch metric input).

The CloudWatch ``MissedDispatch`` metric reads ``scheduler_heartbeat.last_dispatch_at``;
before the engine_getter wiring nothing ever wrote it, so the alarm fired every market
morning by construction. These tests pin the stamp semantics: real engine dispatch time
is persisted, and a restart (engine value None) never clobbers the last known stamp.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.db.models.scheduler_heartbeat import SchedulerHeartbeat
from app.jobs.scheduler_heartbeat import _latest_dispatch_at, run_scheduler_heartbeat


class _Running:
    def __init__(self, last_dispatch_at: float | None) -> None:
        self.last_dispatch_at = last_dispatch_at


class _FakeEngine:
    def __init__(self, epochs: list[float | None]) -> None:
        self._epochs = epochs

    def running_strategies(self) -> list[_Running]:
        return [_Running(e) for e in self._epochs]


def test_latest_dispatch_at_takes_max_and_converts() -> None:
    got = _latest_dispatch_at(_FakeEngine([100.0, None, 250.0]))
    assert got == datetime.fromtimestamp(250.0, tz=UTC)


def test_latest_dispatch_at_none_when_nothing_dispatched() -> None:
    assert _latest_dispatch_at(_FakeEngine([None, None])) is None
    assert _latest_dispatch_at(_FakeEngine([])) is None


def test_latest_dispatch_at_swallows_broken_engine() -> None:
    class _Broken:
        def running_strategies(self):  # noqa: ANN202
            raise RuntimeError("boom")

    assert _latest_dispatch_at(_Broken()) is None


async def _get_row(session_factory) -> SchedulerHeartbeat:
    async with session_factory() as session:
        return (await session.execute(select(SchedulerHeartbeat))).scalars().one()


@pytest.mark.anyio
async def test_heartbeat_stamps_engine_dispatch_time(session_factory) -> None:
    epoch = datetime(2026, 7, 9, 13, 50, tzinfo=UTC).timestamp()
    await run_scheduler_heartbeat(
        session_factory, "test-host", engine_getter=lambda: _FakeEngine([epoch])
    )
    row = await _get_row(session_factory)
    assert row.armed is True
    assert row.last_dispatch_at is not None
    assert row.last_dispatch_at.replace(tzinfo=UTC) == datetime.fromtimestamp(epoch, tz=UTC)


@pytest.mark.anyio
async def test_restart_none_does_not_clobber_stamp(session_factory) -> None:
    epoch = datetime(2026, 7, 9, 13, 50, tzinfo=UTC).timestamp()
    await run_scheduler_heartbeat(
        session_factory, "test-host", engine_getter=lambda: _FakeEngine([epoch])
    )
    # Simulate the post-restart beat: engine is up but nothing has dispatched yet.
    await run_scheduler_heartbeat(
        session_factory, "test-host", engine_getter=lambda: _FakeEngine([None])
    )
    row = await _get_row(session_factory)
    assert row.last_dispatch_at is not None  # the stamp survived


@pytest.mark.anyio
async def test_heartbeat_without_engine_getter_still_beats(session_factory) -> None:
    await run_scheduler_heartbeat(session_factory, "test-host")
    row = await _get_row(session_factory)
    assert row.armed is True
    assert row.last_dispatch_at is None
