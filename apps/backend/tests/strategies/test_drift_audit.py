"""§8 drift-audit comparison core — fixture tests proving the comparison is trustworthy."""

from __future__ import annotations

from app.strategies.drift_audit import (
    GROSS_DAILY_ABS_TOL,
    WEIGHT_ABS_TOL,
    SeamRecord,
    build_report,
    compare_day,
)


def _rec(date, *, elig=("A", "B", "C"), target=("A", "B"), weights=None, gross=0.60,
         trade=True, scores=None, is_seed=False, trigger="t") -> SeamRecord:
    return SeamRecord(
        date=date, scores=scores or {"A": 1.0, "B": 0.9, "C": 0.5},
        eligible=elig, ranking=elig, target_names=target,
        weights=weights or {t: 0.5 for t in target}, regime_gross=gross,
        trade_initiated=trade, trigger=trigger, is_seed=is_seed)


# ---- per-day comparison ----

def test_identical_day_has_no_mismatch():
    d = compare_day(_rec("2005-01-03"), _rec("2005-01-03"))
    assert not d.any_mismatch and not d.economically_material


def test_different_selected_names_is_semantic_material_mismatch():
    live = _rec("2005-01-04", target=("A", "B"))
    rep = _rec("2005-01-04", target=("A", "C"))
    d = compare_day(live, rep)
    assert "target_names" in d.semantic_mismatches and d.economically_material


def test_ranking_order_difference_is_semantic():
    d = compare_day(_rec("2005-01-05", elig=("A", "B", "C")),
                    _rec("2005-01-05", elig=("B", "A", "C")))
    assert "ranking" in d.semantic_mismatches


def test_trade_decision_divergence_is_flagged_with_triggers():
    live = _rec("2005-01-06", trade=False, trigger="reviewed_no_trigger")
    rep = _rec("2005-01-06", trade=True, trigger="changed")
    d = compare_day(live, rep)
    assert "trade_initiated" in d.semantic_mismatches and d.economically_material
    assert d.detail["trade_initiated"]["live_trigger"] == "reviewed_no_trigger"


def test_weight_within_band_ok_but_over_band_flagged():
    ok = compare_day(_rec("2005-01-07", weights={"A": 0.5, "B": 0.5}),
                     _rec("2005-01-07", weights={"A": 0.5 + WEIGHT_ABS_TOL / 2, "B": 0.5}))
    assert "weights" not in ok.numeric_violations
    bad = compare_day(_rec("2005-01-07", weights={"A": 0.5, "B": 0.5}),
                      _rec("2005-01-07", weights={"A": 0.5 + WEIGHT_ABS_TOL * 3, "B": 0.5}))
    assert "weights" in bad.numeric_violations and bad.economically_material


def test_regime_gross_band():
    ok = compare_day(_rec("2005-01-08", gross=0.60),
                     _rec("2005-01-08", gross=0.60 + GROSS_DAILY_ABS_TOL / 2))
    assert "regime_gross" not in ok.numeric_violations
    bad = compare_day(_rec("2005-01-08", gross=0.60),
                      _rec("2005-01-08", gross=0.60 + GROSS_DAILY_ABS_TOL * 2))
    assert "regime_gross" in bad.numeric_violations


def test_scores_are_diagnostic_not_a_gate():
    live = _rec("2005-01-09", scores={"A": 1.0, "B": 0.9, "C": 0.5})
    rep = _rec("2005-01-09", scores={"A": 1.5, "B": 0.9, "C": 0.5})  # big score diff, same seams
    d = compare_day(live, rep)
    assert d.score_max_abs_diff == 0.5 and not d.any_mismatch  # scores don't gate


# ---- run-level report ----

def test_report_all_match_is_pass_structural():
    days = ["2005-01-03", "2005-01-04", "2005-01-05"]
    live = [_rec(d, is_seed=(d == days[0])) for d in days]
    rep = [_rec(d) for d in days]
    r = build_report(live, rep)
    assert r.conformance_verdict == "PASS_STRUCTURAL"
    assert r.first_mismatch_date is None and r.total_mismatch_sessions == 0
    assert r.structural["first_trade_date_identical"] and r.structural["initial_target_names_identical"]
    assert r.structural["cold_start_seed_count_is_one"]


def test_report_captures_first_mismatch_and_categories():
    days = ["2005-01-03", "2005-01-04", "2005-01-05", "2005-01-06"]
    live = [_rec(d, is_seed=(d == days[0])) for d in days]
    rep = [_rec(d) for d in days]
    # divergence on day 3: replica trades (changed), live doesn't
    live[2] = _rec(days[2], trade=False, trigger="reviewed_no_trigger")
    rep[2] = _rec(days[2], trade=True, target=("A", "C"), trigger="changed")
    r = build_report(live, rep)
    assert r.conformance_verdict == "MISMATCHES_TO_ADJUDICATE"
    assert r.first_mismatch_date == days[2]
    assert r.category_counts["trade_initiated"] == 1 and r.category_counts["target_names"] == 1
    assert r.material_mismatch_sessions == 1
    assert r.first_mismatch_detail["date"] == days[2]


def test_report_first_trade_date_divergence_fails_structural():
    days = ["2005-01-03", "2005-01-04"]
    # live's first trade is day 2, replica's is day 1 -> structural first-trade-date differs
    live = [_rec(days[0], trade=False), _rec(days[1], trade=True, is_seed=False)]
    rep = [_rec(days[0], trade=True), _rec(days[1], trade=True)]
    r = build_report(live, rep)
    assert r.structural["first_trade_date_identical"] is False
    assert r.conformance_verdict == "MISMATCHES_TO_ADJUDICATE"
