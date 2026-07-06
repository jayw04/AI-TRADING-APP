"""P11 ops — strategy-dispatch liveness health (the silent-inertness detector)."""

from __future__ import annotations

import pytest

from app.ops.dispatch_health import (
    MIN_STALE_AFTER_S,
    STARTUP_GRACE_S,
    DispatchSnapshot,
    dispatch_cadence_minutes,
    evaluate_dispatch_health,
    evaluate_one,
    parse_timeframe_minutes,
    stale_dispatch,
)

NOW = 1_000_000.0
UP = STARTUP_GRACE_S + 10  # past the startup grace


def _snap(**kw) -> DispatchSnapshot:
    base = dict(strategy_id=1, name="range-trader", schedule="*/5 * * * *",
                timeframe="5Min", last_dispatch_at=NOW - 60)
    base.update(kw)
    return DispatchSnapshot(**base)


def _ev(snap, *, regular=True, up=UP):
    return evaluate_one(snap, now=NOW, is_regular_session=regular, engine_uptime_s=up)


# --- timeframe parsing ---------------------------------------------------------

@pytest.mark.parametrize("tf,exp", [
    ("5Min", 5), ("1Min", 1), ("15Min", 15), ("1Hour", 60), ("1Day", 1440),
    ("", None), ("weekly", None), ("5x", None),
])
def test_parse_timeframe_minutes(tf, exp):
    assert parse_timeframe_minutes(tf) == exp


# --- cadence classification ----------------------------------------------------

@pytest.mark.parametrize("schedule,timeframe,exp", [
    ("*/5 * * * *", "5Min", 5.0),       # the Range Trader
    ("*/1 * * * *", "1Min", 1.0),
    ("* * * * *", "5Min", 1.0),         # every minute
    ("0 * * * *", "5Min", 60.0),        # hourly (fixed minute, wildcard hour)
    ("event", "5Min", 5.0),             # event-driven => from timeframe
    ("0 14 * * mon", "1Day", None),     # weekly rebalance => NOT bar-driven
    ("0 14 * * *", "1Day", None),       # daily fixed time => NOT bar-driven
    ("garbage", "5Min", None),
    ("*/x * * * *", "5Min", None),
])
def test_dispatch_cadence_minutes(schedule, timeframe, exp):
    assert dispatch_cadence_minutes(schedule, timeframe) == exp


# --- the state machine ---------------------------------------------------------

def test_recent_dispatch_is_ok():
    assert _ev(_snap(last_dispatch_at=NOW - 60)).health == "ok"


def test_stale_when_no_dispatch_beyond_threshold():
    # cadence 5m -> stale_after = max(3*5*60, 900) = 900s; 30m old => stale
    r = _ev(_snap(last_dispatch_at=NOW - 30 * 60))
    assert r.health == "stale"
    assert "no on_bar dispatch" in r.reason


def test_never_dispatched_during_rth_is_stale():
    r = _ev(_snap(last_dispatch_at=None))
    assert r.health == "stale"
    assert "never dispatched" in r.reason


def test_not_regular_session_is_na():
    # even with no dispatch ever, a closed market must not alarm
    assert _ev(_snap(last_dispatch_at=None), regular=False).health == "n_a"


def test_weekly_strategy_not_liveness_checked():
    snap = _snap(strategy_id=2, name="momentum-portfolio",
                 schedule="0 14 * * mon", timeframe="1Day", last_dispatch_at=None)
    r = _ev(snap)
    assert r.health == "n_a"
    assert r.cadence_minutes is None


def test_startup_grace_reports_unknown():
    # fresh engine: even with no dispatch, hold off (unknown, not stale)
    r = _ev(_snap(last_dispatch_at=None), up=STARTUP_GRACE_S - 1)
    assert r.health == "unknown"


def test_min_stale_floor_protects_short_cadence():
    # 1-min cadence: stale_after floored at MIN_STALE_AFTER_S (15m), so 10m old is still ok
    snap = _snap(schedule="*/1 * * * *", timeframe="1Min", last_dispatch_at=NOW - 10 * 60)
    assert MIN_STALE_AFTER_S == 900
    assert _ev(snap).health == "ok"


def test_evaluate_and_stale_filter():
    snaps = [
        _snap(strategy_id=1, last_dispatch_at=NOW - 60),               # ok
        _snap(strategy_id=3, name="range-aapl", last_dispatch_at=None),  # stale
        _snap(strategy_id=2, name="momentum", schedule="0 14 * * mon",
              timeframe="1Day", last_dispatch_at=None),                 # n_a
    ]
    results = evaluate_dispatch_health(
        snaps, now=NOW, is_regular_session=True, engine_uptime_s=UP
    )
    assert {r.strategy_id: r.health for r in results} == {1: "ok", 3: "stale", 2: "n_a"}
    assert [r.strategy_id for r in stale_dispatch(results)] == [3]
