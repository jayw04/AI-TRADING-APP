"""Operational KPI scorecard (P13.5) — pure assembly."""

from __future__ import annotations

from dataclasses import replace

from app.ops.kpis import KpiInputs, build_scorecard, scorecard_summary


def _clean() -> KpiInputs:
    return KpiInputs(
        reconciliation_runs=40, reconciliation_passes=40, reconciliation_discrepancies=0,
        replay_checked=200, replay_matched=200,
        orders_risk_passed=8, orders_rejected_by_risk=2, orders_rejected_by_broker=0,
        breaker_trips=1, breaker_resets=1, breaker_recovery_minutes=20.0,
        orders_submitted=10, fills_ingested=10,
        expected_snapshot_days=30, actual_snapshot_days=30,
    )


def _by_key(rows):
    return {r["key"]: r for r in rows}


def test_clean_inputs_all_ok():
    rows = build_scorecard(_clean())
    assert all(r["status"] in ("ok",) for r in rows)
    assert scorecard_summary(rows) == {"ok": len(rows), "watch": 0, "n_a": 0}


def test_rates_computed():
    r = _by_key(build_scorecard(_clean()))
    assert r["reconciliation_success"]["value"] == 100.0
    assert r["replay_consistency"]["value"] == 100.0
    assert r["fill_success"]["value"] == 100.0
    assert r["operational_continuity"]["value"] == 100.0
    assert r["risk_gate_efficacy"]["value"] == 20.0  # 2 rejected / 10 checked


def test_unrecovered_breaker_and_discrepancy_watch():
    rows = _by_key(build_scorecard(
        replace(_clean(), breaker_trips=2, breaker_resets=1, reconciliation_discrepancies=3)))
    assert rows["breaker_recovery"]["status"] == "watch"
    assert rows["reconciliation_drift"]["status"] == "watch"
    assert rows["reconciliation_drift"]["value"] == 3


def test_replay_consistency_below_target_watches():
    rows = _by_key(build_scorecard(replace(_clean(), replay_matched=195)))  # 97.5% < 99.9
    assert rows["replay_consistency"]["status"] == "watch"


def test_zero_denominator_is_na_not_crash():
    fresh = KpiInputs(
        reconciliation_runs=0, reconciliation_passes=0, reconciliation_discrepancies=0,
        replay_checked=0, replay_matched=0,
        orders_risk_passed=0, orders_rejected_by_risk=0, orders_rejected_by_broker=0,
        breaker_trips=0, breaker_resets=0, breaker_recovery_minutes=None,
        orders_submitted=0, fills_ingested=0,
        expected_snapshot_days=0, actual_snapshot_days=0,
    )
    rows = _by_key(build_scorecard(fresh))
    assert rows["reconciliation_success"]["value"] is None
    assert rows["reconciliation_success"]["status"] == "n_a"
    assert rows["replay_consistency"]["status"] == "n_a"


def test_risk_gate_efficacy_is_informational_ok():
    # even a high reject rate is 'ok' — the gate firing is the success signal, not a failure
    rows = _by_key(build_scorecard(replace(_clean(), orders_rejected_by_risk=50)))
    assert rows["risk_gate_efficacy"]["status"] == "ok"
