"""ADR 0032 — the single-active-scheduler arm flag.

A DISARMED WorkbenchScheduler must NOT start its APScheduler (so it dispatches no recurring jobs /
orders); the default (armed) must start exactly as before. This is the safety mechanism that lets
the laptop stay installed but inert after cutover to AWS, without changing default behavior.
"""

from __future__ import annotations

from unittest.mock import MagicMock

from app.services.scheduler import WorkbenchScheduler


def _sched(*, enabled: bool = True) -> WorkbenchScheduler:
    return WorkbenchScheduler(MagicMock(), MagicMock(), MagicMock(), enabled=enabled)


def test_enabled_defaults_true_preserving_current_behavior() -> None:
    # No flag passed -> armed, exactly as the existing single-host construction.
    s = WorkbenchScheduler(MagicMock(), MagicMock(), MagicMock())
    assert s.enabled is True


async def test_armed_scheduler_starts() -> None:
    s = _sched(enabled=True)
    try:
        s.start()
        assert s.scheduler.running is True
    finally:
        await s.shutdown()


async def test_disarmed_scheduler_does_not_start() -> None:
    s = _sched(enabled=False)
    s.start()
    assert s.scheduler.running is False
    # No jobs registered on a disarmed host.
    assert s.scheduler.get_jobs() == []
    # shutdown() on a never-started scheduler is a safe no-op.
    await s.shutdown()
