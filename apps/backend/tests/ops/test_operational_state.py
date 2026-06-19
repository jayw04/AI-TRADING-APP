"""P11 §1 — operational-state resolver.

Drives `resolve_operational_state` through a lightweight stub engine (the resolver only
calls `running_strategies()` + `scheduler_has_job()`), pinning: enabled-from-flag,
not-enabled-when-off, infra-from-job, basic health, verified passthrough, and graceful
degrade when the engine is absent.
"""

from __future__ import annotations

from types import SimpleNamespace

from app.ops.state import resolve_operational_state


def _running(params: dict, *, job_id: str | None = "job", overlay_job_id: str | None = None):
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


def test_flag_feature_enabled_when_a_running_strategy_has_it_on() -> None:
    eng = _Engine(running=[_running({"use_daily_overlay": True})])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.enabled is True and s.healthy == "ok" and s.implemented is True


def test_flag_feature_not_enabled_when_off() -> None:
    eng = _Engine(running=[_running({"use_daily_overlay": False})])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.enabled is False and s.healthy == "n_a"


def test_numeric_flag_enabled_only_when_positive() -> None:
    """max_sector_pct / overlay_gross_smooth_span are 'on' when set (>0), off when None/0."""
    off = _state(resolve_operational_state(_Engine([_running({"max_sector_pct": None})])), "sector_cap")
    on = _state(resolve_operational_state(_Engine([_running({"max_sector_pct": 0.40})])), "sector_cap")
    assert off.enabled is False and on.enabled is True


def test_infra_feature_enabled_iff_job_registered() -> None:
    on = _state(resolve_operational_state(_Engine(jobs=["breaker_monitor"])), "breaker_monitor")
    off = _state(resolve_operational_state(_Engine(jobs=[])), "breaker_monitor")
    assert on.enabled is True and on.healthy == "ok"
    assert off.enabled is False and off.healthy == "n_a"


def test_degraded_when_enabling_strategy_has_no_job() -> None:
    eng = _Engine(running=[_running({"use_daily_overlay": True}, job_id=None)])
    s = _state(resolve_operational_state(eng), "daily_overlay")
    assert s.enabled is True and s.healthy == "degraded"


def test_verified_passthrough_regime_overlays_no_go() -> None:
    states = resolve_operational_state(_Engine())
    assert _state(states, "breadth_overlay").verified == "no_go"
    assert _state(states, "vix_overlay").verified == "no_go"
    assert _state(states, "vol_target").verified == "validated"


def test_engine_absent_degrades_gracefully() -> None:
    """No engine (tests / alpaca-disabled) → everything not-enabled, never raises."""
    states = resolve_operational_state(None)
    assert states and all(not s.enabled for s in states)
    assert all(s.implemented for s in states)  # implemented is static-true
