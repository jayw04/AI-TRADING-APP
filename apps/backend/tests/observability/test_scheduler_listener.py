"""P11 §2 — the WorkbenchScheduler APScheduler listener records job KPIs.

Synthesizes APScheduler executed/error/missed events and asserts the right
`scheduler_job_events_total` increments + the last-success / last-error gauges. No real
scheduler needed — `_on_job_event` is a pure metrics sink.
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import MagicMock

from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_EXECUTED, EVENT_JOB_MISSED
from prometheus_client import REGISTRY

from app.services.scheduler import WorkbenchScheduler


def _sched() -> WorkbenchScheduler:
    return WorkbenchScheduler(MagicMock(), MagicMock(), MagicMock())


def _events(job_id, code):
    return REGISTRY.get_sample_value(
        "workbench_scheduler_job_events_total", {"job_id": job_id, "event": code}
    ) or 0.0


def test_executed_increments_and_sets_last_success() -> None:
    s = _sched()
    before = _events("job_exec", "executed")
    s._on_job_event(SimpleNamespace(job_id="job_exec", code=EVENT_JOB_EXECUTED))
    assert _events("job_exec", "executed") == before + 1
    assert REGISTRY.get_sample_value(
        "workbench_scheduler_job_last_success_timestamp", {"job_id": "job_exec"}
    ) is not None


def test_error_increments_and_sets_last_error() -> None:
    s = _sched()
    before = _events("job_err", "error")
    s._on_job_event(SimpleNamespace(job_id="job_err", code=EVENT_JOB_ERROR))
    assert _events("job_err", "error") == before + 1
    assert REGISTRY.get_sample_value(
        "workbench_scheduler_job_last_error_timestamp", {"job_id": "job_err"}
    ) is not None


def test_missed_increments_missed() -> None:
    s = _sched()
    before = _events("job_miss", "missed")
    s._on_job_event(SimpleNamespace(job_id="job_miss", code=EVENT_JOB_MISSED))
    assert _events("job_miss", "missed") == before + 1


def test_unknown_event_is_ignored() -> None:
    s = _sched()
    # A code outside the mask must not raise (defensive).
    s._on_job_event(SimpleNamespace(job_id="job_x", code=-999))
