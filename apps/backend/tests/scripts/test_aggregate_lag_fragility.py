"""Lag-fragility aggregator — pins the disposition tree and the no-silent-gap discipline."""

from __future__ import annotations

from scripts.aggregate_lag_fragility import _extract, _survives, aggregate, classify


def _r(lag, ci_low, ci_high=1.0, effect=0.5, n=300):
    return {"lag": lag, "effect_size": effect, "ci_low": ci_low, "ci_high": ci_high, "n": n}


def test_extract_normalises_alternate_field_names():
    e = _extract({"disclosure_lag_days": 30, "net_excess": 0.4, "ci95": [-0.1, 0.9],
                  "n_benchmarked": 250, "status": "rejected"})
    assert e["lag"] == 30 and e["effect_size"] == 0.4
    assert e["ci_low"] == -0.1 and e["ci_high"] == 0.9 and e["n"] == 250


def test_survives_requires_ci_low_above_zero():
    assert _survives(_r(30, 0.1))
    assert not _survives(_r(30, -0.1))
    assert not _survives(_r(30, 0.0))


def test_classify_robust_when_high_lags_survive():
    by = {lag: _r(lag, 0.1) for lag in (21, 27, 30, 45, 56, 60)}
    assert classify(by) == "lag_not_decision_critical"


def test_classify_pit_decision_critical_when_edge_dies_by_45_56():
    by = {21: _r(21, 0.2), 27: _r(27, 0.2), 30: _r(30, 0.1),
          45: _r(45, -0.1), 56: _r(56, -0.2), 60: _r(60, -0.2)}
    assert classify(by) == "pit_decision_critical"


def test_classify_leakage_when_only_tight_lags_survive():
    by = {21: _r(21, 0.2), 27: _r(27, 0.1), 30: _r(30, -0.1),
          45: _r(45, -0.2), 56: _r(56, -0.2), 60: _r(60, -0.3)}
    assert classify(by) == "leakage_concern"


def test_classify_economic_rejection_when_all_fail():
    by = {lag: _r(lag, -0.2) for lag in (21, 27, 30, 45, 56, 60)}
    assert classify(by) == "economic_rejection_reachable"


def test_aggregate_records_missing_lags_and_does_not_treat_them_as_passing():
    # only 3 of 6 grid lags supplied -> the other 3 must be reported missing, never silently passed
    out = aggregate([_r(21, 0.1), _r(30, 0.1), _r(60, 0.1)])
    assert out["lags_covered"] == [21, 30, 60]
    assert out["lags_missing"] == [27, 45, 56]
    assert len(out["by_lag"]) == 3
    assert out["by_lag"][0]["survives"] is True


def test_aggregate_economic_rejection_disposition_mentions_separate_finding():
    out = aggregate([_r(lag, -0.2) for lag in (21, 27, 30, 45, 56, 60)])
    assert out["classification"] == "economic_rejection_reachable"
    assert "SEPARATE" in out["disposition"]
