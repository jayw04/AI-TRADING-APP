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


# ---- v0.2 outcome metrics --------------------------------------------------


def test_expansion_ratio_detautologizes() -> None:
    # realized range 6% on a 3%-ATR name → expanded 2× its own vol
    assert ce.expansion_ratio(6.0, 3.0) == 2.0
    # realized exactly its ATR → ratio 1.0 (no opportunity beyond vol)
    assert ce.expansion_ratio(3.0, 3.0) == 1.0
    assert ce.expansion_ratio(5.0, 0.0) == 0.0  # no ATR → safe


def test_trend_efficiency_chop_vs_trend() -> None:
    # close == open → pure round trip → 0
    assert ce.trend_efficiency(100.0, 105.0, 95.0, 100.0) == 0.0
    # close at the high, open at the low → clean one-way → full range directional
    assert ce.trend_efficiency(100.0, 110.0, 100.0, 110.0) == 1.0
    assert ce.trend_efficiency(100.0, 100.0, 100.0, 100.0) == 0.0  # flat → safe


def test_capturable_move_takes_best_excursion() -> None:
    # up 8 from open vs down 5 → best excursion is the 8% up move
    assert ce.capturable_move(100.0, 108.0, 95.0) == 8.0
    # down excursion larger
    assert ce.capturable_move(100.0, 102.0, 90.0) == 10.0


def test_net_move_is_open_to_close() -> None:
    assert ce.net_move(100.0, 103.0) == 3.0
    assert ce.net_move(100.0, 97.0) == 3.0  # absolute
    assert ce.net_move(0.0, 50.0) == 0.0


# ---- v0.2 signal selector (H3 attribution) ---------------------------------


def test_active_signals_atr_only() -> None:
    feat = _feat(gap_pct=6.0, rvol=4.0, atr_pct=4.0)  # clears all three
    assert ce.opportunity_signals(feat, active_signals=("ATR",)) == ["ATR"]


def test_active_signals_excludes_inactive_driver() -> None:
    feat = _feat(gap_pct=6.0, rvol=1.0, atr_pct=4.0)  # Gap + ATR fire, RVOL doesn't
    assert ce.opportunity_signals(feat, active_signals=("Gap", "ATR")) == ["Gap", "ATR"]
    assert ce.opportunity_signals(feat, active_signals=("RVOL", "ATR")) == ["ATR"]


def test_select_with_atr_only_screen_drops_gap_only_names() -> None:
    panel = [
        _feat(symbol="GAPONLY", gap_pct=6.0, rvol=1.0, atr_pct=1.0),  # only Gap fires
        _feat(symbol="ATRNAME", gap_pct=1.0, rvol=1.0, atr_pct=4.0),  # only ATR fires
    ]
    out = ce.select_candidates(panel, top_n=10, active_signals=("ATR",))
    assert [c.symbol for c in out] == ["ATRNAME"]  # GAPONLY dropped (Gap inactive)


def test_require_all_signals_respects_active_subset() -> None:
    panel = [_feat(symbol="X", gap_pct=6.0, rvol=1.0, atr_pct=4.0)]  # Gap+ATR, not RVOL
    out = ce.select_candidates(
        panel, top_n=10, active_signals=("Gap", "ATR"), require_all_signals=True
    )
    assert [c.symbol for c in out] == ["X"]  # both active signals fired
    out2 = ce.select_candidates(
        panel, top_n=10, active_signals=("Gap", "RVOL"), require_all_signals=True
    )
    assert out2 == []  # RVOL didn't fire → fails all-active


# ---- v0.3 regime classifiers ------------------------------------------------


def test_sma_and_trailing_return() -> None:
    assert ce.sma([1, 2, 3, 4], 2) == 3.5
    assert ce.sma([1, 2], 5) is None
    assert abs(ce.trailing_return([100, 110], 1) - 0.10) < 1e-9
    assert ce.trailing_return([100], 1) is None


def test_realized_vol_zero_for_flat_returns() -> None:
    assert ce.realized_vol([0.0] * 21, n=21) == 0.0
    assert ce.realized_vol([0.01] * 5, n=21) is None  # insufficient history


def test_market_regime_bull_bear_sideways() -> None:
    # Bull: rising series ends above its SMA200 with a positive 60d return
    bull = [100 + i * 0.5 for i in range(260)]
    assert ce.market_regime(bull) == "bull"
    # Bear: falling series ends below its SMA200 with a negative 60d return
    bear = [200 - i * 0.5 for i in range(260)]
    assert ce.market_regime(bear) == "bear"
    # Sideways: flat ends at its SMA200 with ~0 60d return → not bull/bear
    flat = [100.0] * 260
    assert ce.market_regime(flat) == "sideways"


def test_market_regime_insufficient_history() -> None:
    assert ce.market_regime([100.0] * 50) is None


def test_vol_regime_split() -> None:
    hist = [0.10, 0.20, 0.30]  # median 0.20
    assert ce.vol_regime(0.25, hist) == "high"
    assert ce.vol_regime(0.15, hist) == "low"
    assert ce.vol_regime(None, hist) is None
    assert ce.vol_regime(0.25, []) is None


# ---- v0.4 Confidence Model -------------------------------------------------


def test_discovery_confidence_negative_regime_is_zero() -> None:
    # a no-go regime (point ≤ 0) contributes no confidence regardless of the other stats
    assert ce.discovery_confidence(point=-0.1, ci_low=-0.3, p_value=0.5, ref=0.2) == 0.0
    assert ce.discovery_confidence(point=0.0, ci_low=-0.1, p_value=0.1, ref=0.2) == 0.0


def test_discovery_confidence_separated_blends_sep_and_magnitude() -> None:
    # positive + CI-separated: 0.5·(1−p) + 0.5·(point/ref). p=0, point==ref → 0.5 + 0.5 = 1.0
    assert ce.discovery_confidence(point=0.2, ci_low=0.1, p_value=0.0, ref=0.2) == 1.0
    # half the reference magnitude, still perfectly separated → 0.5 + 0.25 = 0.75
    assert ce.discovery_confidence(point=0.1, ci_low=0.05, p_value=0.0, ref=0.2) == 0.75


def test_discovery_confidence_not_separated_is_discounted() -> None:
    # positive point but CI spans 0 → weak branch 0.4·(1−p); p=0.2 → 0.4·0.8 = 0.32
    assert ce.discovery_confidence(point=0.05, ci_low=-0.01, p_value=0.2, ref=0.2) == 0.32


def test_discovery_confidence_bounded_and_ref_zero_safe() -> None:
    # magnitude clamps at 1.0 even when point > ref; and ref==0 → magnitude 0 (no crash)
    assert ce.discovery_confidence(point=0.5, ci_low=0.4, p_value=0.0, ref=0.2) == 1.0
    assert ce.discovery_confidence(point=0.1, ci_low=0.05, p_value=0.0, ref=0.0) == 0.5


def test_composite_confidence_is_the_frozen_product() -> None:
    assert ce.composite_confidence(0.8, 0.9) == 0.72
    # neutral discovery confidence (warm-up) leaves opportunity confidence untouched
    assert ce.composite_confidence(0.6, ce.NEUTRAL_CONFIDENCE) == 0.6
    # a zero on either lever zeroes the composite
    assert ce.composite_confidence(0.0, 0.9) == 0.0
    assert ce.composite_confidence(0.9, 0.0) == 0.0


def test_composite_confidence_clamps_malformed_inputs() -> None:
    # out-of-range inputs are clamped, never propagated out of [0, 1]
    assert ce.composite_confidence(1.5, 0.5) == 0.5
    assert ce.composite_confidence(-0.2, 0.5) == 0.0
    assert ce.composite_confidence(0.5, 2.0) == 0.5


def test_candidate_to_dict_is_json_safe() -> None:
    out = ce.select_candidates([_feat(symbol="AAA")], top_n=1)
    d = out[0].to_dict()
    assert d["symbol"] == "AAA" and d["rank"] == 1
    assert set(d) == {
        "symbol", "rank", "gap_pct", "rvol", "atr_pct",
        "price", "dollar_vol", "reason", "confidence", "score",
    }
    assert all(not isinstance(v, float) or math.isfinite(v) for v in d.values())
