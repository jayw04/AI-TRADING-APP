"""P11 §1+§2 — operational-state resolver.

Drives `resolve_operational_state` through a stub engine (the resolver only calls
`running_strategies()` + `scheduler_has_job()`) and the in-process Prometheus registry.
Pins: enabled-from-flag, infra-from-job, verified passthrough, graceful degrade, and the
§2 MEASURED health (ok / stale / degraded / unknown / n_a) from the scheduler gauges.
"""

from __future__ import annotations

import time
from types import SimpleNamespace

import pytest

from app.observability import metrics as obs
from app.ops import state as ops_state
from app.ops.state import resolve_operational_state


def _running(params: dict, *, job_id="strategy:1:on_bar", overlay_job_id="strategy:1:overlay"):
    return SimpleNamespace(instance=SimpleNamespace(params=params),
                           job_id=job_id, overlay_job_id=overlay_job_id)


class _Engine:
    def __init__(self, running=(), jobs=()):
        self._running = list(running)
        self._jobs = set(jobs)

    def running_strategies(self):
        return self._running

    def scheduler_has_job(self, job_id):
        return job_id in self._jobs


def _state(states, key):
    return next(s for s in states if s.key == key)


@pytest.fixture
def past_grace(monkeypatch):
    """Move process-start back so health is evaluable (outside the startup grace)."""
    monkeypatch.setattr(ops_state, "_PROC_START", time.monotonic() - 3600.0)


# ---- §1 enabled / verified / category / graceful degrade ------------------------

def test_flag_feature_enabled_when_a_running_strategy_has_it_on() -> None:
    s = _state(resolve_operational_state(_Engine([_running({"use_daily_overlay": True})])), "daily_overlay")
    assert s.enabled is True and s.implemented is True and s.category == "portfolio"


def test_flag_feature_not_enabled_when_off() -> None:
    s = _state(resolve_operational_state(_Engine([_running({"use_daily_overlay": False})])), "daily_overlay")
    assert s.enabled is False and s.healthy == "n_a"


def test_numeric_flag_enabled_only_when_positive() -> None:
    off = _state(resolve_operational_state(_Engine([_running({"max_sector_pct": None})])), "sector_cap")
    on = _state(resolve_operational_state(_Engine([_running({"max_sector_pct": 0.40})])), "sector_cap")
    assert off.enabled is False and on.enabled is True


def test_infra_feature_enabled_iff_job_registered() -> None:
    on = _state(resolve_operational_state(_Engine(jobs=["breaker_monitor"])), "breaker_monitor")
    off = _state(resolve_operational_state(_Engine(jobs=[])), "breaker_monitor")
    assert on.enabled is True and off.enabled is False and off.healthy == "n_a"


def test_verified_passthrough_regime_overlays_no_go() -> None:
    states = resolve_operational_state(_Engine())
    assert _state(states, "breadth_overlay").verified == "no_go"
    assert _state(states, "vol_target").verified == "validated"


def test_engine_absent_degrades_gracefully() -> None:
    states = resolve_operational_state(None)
    assert states and all(not s.enabled for s in states) and all(s.implemented for s in states)


# ---- §2 measured health ---------------------------------------------------------

def test_health_unknown_within_startup_grace() -> None:
    """Enabled but inside the grace window → unknown (not degraded), regardless of metrics."""
    eng = _Engine([_running({"use_daily_overlay": True}, overlay_job_id="t_grace:overlay")])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.healthy == "unknown"


def test_health_unknown_when_no_metrics(past_grace) -> None:
    eng = _Engine([_running({"use_daily_overlay": True}, overlay_job_id="t_nometrics:overlay")])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.healthy == "unknown"


def test_health_ok_on_fresh_success(past_grace) -> None:
    obs.scheduler_job_last_success_timestamp.labels(job_id="t_ok:overlay").set(time.time())
    eng = _Engine([_running({"use_daily_overlay": True}, overlay_job_id="t_ok:overlay")])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.healthy == "ok" and s.last_success_age_s is not None and s.last_success_age_s < 60


def test_health_stale_on_old_success(past_grace) -> None:
    obs.scheduler_job_last_success_timestamp.labels(job_id="t_stale:overlay").set(time.time() - 3 * 86_400)
    eng = _Engine([_running({"use_daily_overlay": True}, overlay_job_id="t_stale:overlay")])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.healthy == "stale"  # > 2-day overlay window


def test_health_degraded_when_last_run_errored(past_grace) -> None:
    obs.scheduler_job_last_success_timestamp.labels(job_id="t_deg:overlay").set(time.time() - 100)
    obs.scheduler_job_last_error_timestamp.labels(job_id="t_deg:overlay").set(time.time())  # error newer
    eng = _Engine([_running({"use_daily_overlay": True}, overlay_job_id="t_deg:overlay")])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.healthy == "degraded"
