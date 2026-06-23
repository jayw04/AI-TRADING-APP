"""SCAN-001 Candidate Engine tests (the pure selection core).

Covers the feature functions (gap %, RVOL, ATR %, intraday range), the eligibility gates,
the opportunity-signal attribution that drives the explainable ``reason``, the bounded
[0,1] confidence, and the ranked top-N selection — including the robustness tightening and
the boundary/malformed-input behaviour the Candidate Report depends on.
"""

from __future__ import annotations

import math

from app.factor_data import candidate_engine as ce

# ---- pure feature functions ------------------------------------------------


def test_gap_pct_basic_and_symmetric() -> None:
    assert ce.gap_pct(110.0, 100.0) == 10.0
    # gap is absolute — a down-gap of the same magnitude reads the same
    assert ce.gap_pct(90.0, 100.0) == 10.0


def test_gap_pct_zero_prev_close_is_safe() -> None:
    assert ce.gap_pct(50.0, 0.0) == 0.0


def test_rvol_proxy() -> None:
    assert ce.rvol(3_000_000, 1_000_000) == 3.0
    assert ce.rvol(100, 0) == 0.0  # no trailing average → safe zero, not a crash


def test_atr_pct_needs_enough_bars() -> None:
    # fewer than n+1 bars → 0.0 (not enough history to be a real signal)
    assert ce.atr_pct([10, 11], [9, 10], [9.5, 10.5], n=14) == 0.0


def test_atr_pct_constant_range() -> None:
    # 16 bars, each a clean $2 high-low range around a flat $100 close → ATR≈2 → 2%
    highs = [101.0] * 16
    lows = [99.0] * 16
    closes = [100.0] * 16
    assert ce.atr_pct(highs, lows, closes, n=14) == 2.0


def test_intraday_range_pct_is_the_outcome_metric() -> None:
    assert ce.intraday_range_pct(105.0, 95.0, 100.0) == 10.0
    assert ce.intraday_range_pct(105.0, 95.0, 0.0) == 0.0  # malformed open → safe


# ---- eligibility gates -----------------------------------------------------


def _feat(**kw: object) -> dict[str, object]:
    base = {
        "symbol": "TEST",
        "gap_pct": 5.0,
        "rvol": 3.0,
        "atr_pct": 4.0,
        "price": 50.0,
        "dollar_vol": 100_000_000.0,
    }
    base.update(kw)
    return base


def test_eligible_clean_name_passes() -> None:
    assert ce.is_eligible(_feat()) is True


def test_eligible_rejects_penny_and_illiquid() -> None:
    assert ce.is_eligible(_feat(price=5.0)) is False           # under $10 floor
    assert ce.is_eligible(_feat(dollar_vol=1_000_000.0)) is False  # under $20M floor


def test_eligible_excludes_earnings_today() -> None:
    # the safety exclusion fires even when every opportunity signal is screaming
    assert ce.is_eligible(_feat(earnings_today=True)) is False


def test_eligible_missing_fields_fail_closed() -> None:
    assert ce.is_eligible({"symbol": "X"}) is False


# ---- opportunity signals + reason ------------------------------------------


def test_signals_all_three_fire() -> None:
    assert ce.opportunity_signals(_feat()) == ["Gap", "RVOL", "ATR"]


def test_signals_single_driver() -> None:
    # gap below threshold, rvol below, only ATR clears
    feat = _feat(gap_pct=1.0, rvol=1.5, atr_pct=4.0)
    assert ce.opportunity_signals(feat) == ["ATR"]


def test_signals_threshold_is_strict_greater_than() -> None:
    # exactly at the threshold does NOT clear (conservative: must exceed)
    feat = _feat(gap_pct=3.0, rvol=2.0, atr_pct=2.0)
    assert ce.opportunity_signals(feat) == []


# ---- confidence ------------------------------------------------------------


def test_confidence_bounds() -> None:
    assert ce.confidence(_feat(), ["Gap", "RVOL", "ATR"]) <= 1.0
    assert ce.confidence(_feat(), []) == 0.0


def test_confidence_at_threshold_is_zero() -> None:
    # just over the line on one signal → confidence ≈ 0 for that signal
    feat = _feat(gap_pct=3.0001, rvol=0, atr_pct=0)
    assert ce.confidence(feat, ["Gap"]) == 0.0


def test_confidence_saturates_at_two_x() -> None:
    # ≥2× the threshold on every cleared signal → confidence 1.0
    feat = _feat(gap_pct=6.0, rvol=4.0, atr_pct=4.0)
    assert ce.confidence(feat, ["Gap", "RVOL", "ATR"]) == 1.0


# ---- selection + ranking ---------------------------------------------------


def test_select_filters_and_ranks() -> None:
    panel = [
        _feat(symbol="AAA", gap_pct=6.0, rvol=4.0, atr_pct=4.0),   # 3 signals, strong
        _feat(symbol="BBB", gap_pct=1.0, rvol=1.0, atr_pct=4.0),   # 1 signal (ATR)
        _feat(symbol="CCC", price=4.0),                            # ineligible (penny)
        _feat(symbol="DDD", gap_pct=1.0, rvol=1.0, atr_pct=1.0),   # no signal → dropped
    ]
    out = ce.select_candidates(panel, top_n=10)
    syms = [c.symbol for c in out]
    assert syms == ["AAA", "BBB"]           # CCC/DDD excluded
    assert out[0].rank == 1 and out[1].rank == 2
    assert out[0].score > out[1].score      # 3-signal name ranks above 1-signal name
    assert out[0].reason == "Gap + RVOL + ATR"
    assert out[1].reason == "ATR"


def test_select_top_n_truncates() -> None:
    panel = [_feat(symbol=f"S{i}") for i in range(20)]
    out = ce.select_candidates(panel, top_n=5)
    assert len(out) == 5
    assert [c.rank for c in out] == [1, 2, 3, 4, 5]


def test_require_all_signals_tightening() -> None:
    panel = [
        _feat(symbol="AAA", gap_pct=6.0, rvol=4.0, atr_pct=4.0),  # 3 signals
        _feat(symbol="BBB", gap_pct=1.0, rvol=1.0, atr_pct=4.0),  # 1 signal only
    ]
    out = ce.select_candidates(panel, top_n=10, require_all_signals=True)
    assert [c.symbol for c in out] == ["AAA"]  # BBB dropped under the strict variant


def test_select_empty_panel() -> None:
    assert ce.select_candidates([], top_n=10) == []


def test_candidate_to_dict_is_json_safe() -> None:
    out = ce.select_candidates([_feat(symbol="AAA")], top_n=1)
    d = out[0].to_dict()
    assert d["symbol"] == "AAA" and d["rank"] == 1
    assert set(d) == {
        "symbol", "rank", "gap_pct", "rvol", "atr_pct",
        "price", "dollar_vol", "reason", "confidence", "score",
    }
    assert all(not isinstance(v, float) or math.isfinite(v) for v in d.values())
