"""Missingness analyzer — pins the selection-bias statistics and the governance thresholds."""

from __future__ import annotations

from scripts.analyze_govcontract_missingness import (
    _chi2_cramers_v,
    _ks,
    _rank_auc,
    _smd,
    analyze,
)


def _row(outcome, amount, size, **kw):
    base = dict(reconcile_outcome=outcome, amount_ge_250k=amount >= 250_000, award_amount=amount,
                size=size, year=2024, recency_bucket="1-2y", name_quality="high",
                agency_normalized="DEFENSE", event_density=1, candidate_count=1)
    base.update(kw)
    return base


def test_smd_separates_clearly_different_groups():
    assert _smd([100.0] * 10, [100.0] * 10) == 0.0          # identical -> 0
    assert abs(_smd([10.0, 11, 9, 10, 10], [0.0, 1, -1, 0, 0])) > 2.0  # far apart -> large


def test_rank_auc_is_1_for_perfect_separation_and_half_for_none():
    assert _rank_auc([1.0, 2, 3, 4], [0, 0, 1, 1]) == 1.0    # high score => reconciled
    assert _rank_auc([4.0, 3, 2, 1], [0, 0, 1, 1]) == 0.0    # reversed
    assert _rank_auc([1.0, 1, 1, 1], [0, 1, 0, 1]) == 0.5    # no information


def test_chi2_cramers_v_zero_when_independent_large_when_dependent():
    indep = {"a": (10, 10), "b": (10, 10)}                    # same 50/50 split
    _, _, cv0 = _chi2_cramers_v(indep)
    assert cv0 == 0.0
    dep = {"a": (20, 0), "b": (0, 20)}                        # perfectly separated
    _, _, cv1 = _chi2_cramers_v(dep)
    assert cv1 > 0.9


def test_ks_detects_distribution_shift():
    assert _ks([1.0, 2, 3], [1.0, 2, 3]) == 0.0
    assert _ks([0.0] * 10, [100.0] * 10) == 1.0


def test_analyze_flags_material_imbalance_when_reconciliation_tracks_award_size():
    rows = ([_row("RECONCILED", 5_000_000, ">10M") for _ in range(40)] +
            [_row("VALID_NON_RECONCILIATION", 50_000, "<100K") for _ in range(40)])
    out = analyze(rows)
    assert out["overall_reconciliation_rate"] == 0.5
    assert out["material_award_reconciliation_rate_ge_250k"] == 1.0   # large awards all reconcile
    assert out["strategy_eligible_reconciliation_rate"] is None       # reserved, never fabricated
    assert out["continuous_standardized_difference"]["award_amount"]["material_imbalance"]
    assert out["categorical_association"]["size"]["material_imbalance"]
    assert out["material_imbalance_flags"]
    assert out["verdict"].startswith("MATERIAL_IMBALANCE")


def test_analyze_reports_no_imbalance_when_reconciliation_is_independent():
    rows = []
    for i in range(80):
        rows.append(_row("RECONCILED" if i % 2 == 0 else "VALID_NON_RECONCILIATION",
                         1_000_000, "1-10M"))
    out = analyze(rows)
    assert out["overall_reconciliation_rate"] == 0.5
    assert not out["material_imbalance_flags"]
    assert out["verdict"].startswith("NO_MATERIAL_IMBALANCE")


def test_operational_rows_are_excluded_from_adjudicated():
    rows = ([_row("RECONCILED", 300_000, "100K-1M") for _ in range(10)] +
            [_row("HTTP_429", 300_000, "100K-1M") for _ in range(5)])
    out = analyze(rows)
    assert out["n_total"] == 15 and out["n_adjudicated"] == 10
    assert out["n_operational_excluded"] == 5
