"""P8 §5a — range-candidate ranking (which symbols to range-trade today)."""

from __future__ import annotations

from app.services.range_insight import (
    DEFAULT_CANDIDATE_UNIVERSE,
    CandidateEvidence,
    HardFilters,
    RangeInsight,
    rank_candidates,
    top_range_symbols,
)


def _ri(symbol: str, *, status="ok", atr20_pct=None, classification=None,
        atr20=None, intraday_range=None, last_close=100.0,
        efficiency_ratio=None, adv=1e9, cs_spread_pct=None) -> RangeInsight:
    """A RangeInsight with only the ranking-relevant fields set; rest are inert.
    ``adv`` defaults to $1B so candidates clear the liquidity hard filter unless overridden."""
    return RangeInsight(
        symbol=symbol, status=status, bars_used=60, low_confidence=False, as_of=None,
        anchor=None, anchor_source=None, last_close=last_close, atr20=atr20,
        atr20_pct=atr20_pct, adv=adv, cs_spread_pct=cs_spread_pct,
        typical_move_up=None, typical_move_down=None,
        support=None, resistance=None, high_band=None, low_band=None,
        intraday_range=intraday_range, classification=classification,
        efficiency_ratio=efficiency_ratio,
    )


def test_ranks_range_bound_high_atr_first():
    out = rank_candidates([
        _ri("MSFT", atr20_pct=0.038, classification="mixed"),
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),   # best: range_bound + highest %
        _ri("NVDA", atr20_pct=0.040, classification="range_bound"),
        _ri("TSLA", atr20_pct=0.046, classification="trending"),     # high % but trending -> penalized
    ])
    assert [c.symbol for c in out] == ["AMD", "NVDA", "MSFT", "TSLA"]
    assert [c.rank for c in out] == [1, 2, 3, 4]
    assert out[0].suitable is True               # AMD range_bound
    assert out[3].suitable is False              # TSLA trending


def test_trending_penalized_below_range_bound_even_with_bigger_range():
    # AMD trending (0.10) vs NVDA range_bound (0.04): weight makes NVDA win
    out = rank_candidates([
        _ri("AMD", atr20_pct=0.10, classification="trending"),    # 0.10 * 0.1 = 0.010
        _ri("NVDA", atr20_pct=0.04, classification="range_bound"),  # 0.04 * 1.0 = 0.040
    ])
    assert [c.symbol for c in out] == ["NVDA", "AMD"]


def test_insufficient_or_missing_data_sorts_last_and_unsuitable():
    out = rank_candidates([
        _ri("BADX", status="insufficient_data", atr20_pct=None, classification=None),
        _ri("KO", atr20_pct=0.02, classification="range_bound"),
        _ri("NODATA", atr20_pct=None, classification="range_bound"),  # no atr% -> score 0
    ])
    assert out[0].symbol == "KO" and out[0].rank == 1
    # the two score-0 names sort after KO (deterministic by symbol)
    assert {c.symbol for c in out[1:]} == {"BADX", "NODATA"}
    assert all(c.suitable is False for c in out if c.symbol != "KO")


def test_score_normalization_beats_raw_dollar_intuition():
    # NVDA tiny $ intraday range but decent ATR% should outrank a high-$ trending name
    out = rank_candidates([
        _ri("PRICEY", atr20_pct=0.035, classification="trending", intraday_range=25.0),
        _ri("NVDA", atr20_pct=0.040, classification="range_bound", intraday_range=4.0),
    ])
    assert out[0].symbol == "NVDA"  # normalized + range_bound wins over big-dollar trender


def test_default_universe_is_sane():
    assert "AMD" in DEFAULT_CANDIDATE_UNIVERSE and "NVDA" in DEFAULT_CANDIDATE_UNIVERSE
    assert len(set(DEFAULT_CANDIDATE_UNIVERSE)) == len(DEFAULT_CANDIDATE_UNIVERSE)  # no dups


def test_rank_is_stable_and_one_based():
    out = rank_candidates([_ri(s, atr20_pct=0.05, classification="range_bound")
                           for s in ("ZZZ", "AAA", "MMM")])
    # equal scores/atr% -> tie-break by symbol ascending
    assert [c.symbol for c in out] == ["AAA", "MMM", "ZZZ"]
    assert [c.rank for c in out] == [1, 2, 3]


# --- Range Score = ATR% × oscillation (Range Efficiency = 1 − Kaufman ER) ---

def test_range_score_uses_efficiency_oscillation():
    # WIDE: high ATR% but a strong TRENDER (ER 0.8 → osc 0.2) → 0.066×0.2 = 0.0132
    # CHOP: lower ATR% but oscillating (ER 0.1 → osc 0.9) → 0.040×0.9 = 0.036 → wins
    out = rank_candidates([
        _ri("WIDE", atr20_pct=0.066, classification="trending", efficiency_ratio=0.8),
        _ri("CHOP", atr20_pct=0.040, classification="range_bound", efficiency_ratio=0.1),
    ])
    assert [c.symbol for c in out] == ["CHOP", "WIDE"]  # oscillation beats raw ATR%
    chop = next(c for c in out if c.symbol == "CHOP")
    assert chop.oscillation == 0.9
    assert round(chop.score, 4) == 0.036


def test_efficiency_overrides_classification_bucket_when_present():
    # same coarse 'mixed' bucket, very different ER → different oscillation/score/order
    out = rank_candidates([
        _ri("DRIFT", atr20_pct=0.05, classification="mixed", efficiency_ratio=0.7),  # osc 0.3
        _ri("BOUNCE", atr20_pct=0.05, classification="mixed", efficiency_ratio=0.1),  # osc 0.9
    ])
    assert [c.symbol for c in out] == ["BOUNCE", "DRIFT"]


def test_oscillation_falls_back_to_classification_without_er():
    # no efficiency_ratio → oscillation uses the coarse class weight (back-compatible)
    out = rank_candidates([_ri("X", atr20_pct=0.05, classification="range_bound")])
    assert out[0].efficiency_ratio is None
    assert out[0].oscillation == 1.0  # range_bound class weight


# --- Evidence-first ranking: realized backtest win rate leads (design §8.4) ----------

def test_evidence_win_rate_drives_order_aapl_above_nvda():
    # The motivating case: NVDA structurally looks fine but its 5-min fade backtested at a
    # 25% win rate / Sharpe -1.12, while AAPL was 62% / +0.46. Win rate must order them.
    out = rank_candidates(
        [
            _ri("NVDA", atr20_pct=0.040, classification="range_bound", efficiency_ratio=0.1),
            _ri("AAPL", atr20_pct=0.030, classification="range_bound", efficiency_ratio=0.2),
        ],
        evidence={
            "NVDA": CandidateEvidence(win_rate=0.25, sharpe=-1.12, n_trades=20),
            "AAPL": CandidateEvidence(win_rate=0.62, sharpe=0.46, n_trades=24),
        },
    )
    assert [c.symbol for c in out] == ["AAPL", "NVDA"]
    aapl = out[0]
    assert aapl.backtested is True
    assert aapl.win_rate == 0.62 and aapl.sharpe == 0.46 and aapl.n_trades == 24


def test_evidence_outranks_structural_prior():
    # AMD has the best structural Range Score but no backtest; AAPL is backtested. Evidence
    # beats structure → AAPL first, AMD (structural-only) second.
    out = rank_candidates(
        [
            _ri("AMD", atr20_pct=0.066, classification="range_bound", efficiency_ratio=0.1),
            _ri("AAPL", atr20_pct=0.030, classification="range_bound", efficiency_ratio=0.2),
        ],
        evidence={"AAPL": CandidateEvidence(win_rate=0.58, sharpe=0.3, n_trades=15)},
    )
    assert [c.symbol for c in out] == ["AAPL", "AMD"]
    assert out[0].backtested is True
    assert out[1].backtested is False and out[1].win_rate is None


def test_evidence_sharpe_breaks_win_rate_ties():
    out = rank_candidates(
        [
            _ri("LOWSH", atr20_pct=0.05, classification="range_bound", efficiency_ratio=0.1),
            _ri("HISH", atr20_pct=0.05, classification="range_bound", efficiency_ratio=0.1),
        ],
        evidence={
            "LOWSH": CandidateEvidence(win_rate=0.55, sharpe=0.2, n_trades=30),
            "HISH": CandidateEvidence(win_rate=0.55, sharpe=0.9, n_trades=30),
        },
    )
    assert [c.symbol for c in out] == ["HISH", "LOWSH"]  # equal win rate → higher Sharpe wins


def test_evidence_none_is_pure_structural_and_backtested_false():
    # No evidence → identical to the structural ranking, and every candidate is backtested=False.
    out = rank_candidates([
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),
        _ri("NVDA", atr20_pct=0.040, classification="range_bound"),
    ])
    assert [c.symbol for c in out] == ["AMD", "NVDA"]
    assert all(c.backtested is False and c.win_rate is None for c in out)


def test_evidence_with_null_win_rate_is_treated_as_no_evidence():
    # A backtest row that produced no win_rate (e.g. zero trades) must not jump the queue.
    out = rank_candidates(
        [
            _ri("AMD", atr20_pct=0.066, classification="range_bound"),
            _ri("ZERO", atr20_pct=0.020, classification="range_bound"),
        ],
        evidence={"ZERO": CandidateEvidence(win_rate=None, sharpe=None, n_trades=0)},
    )
    assert [c.symbol for c in out] == ["AMD", "ZERO"]  # falls back to structural score
    assert all(c.backtested is False for c in out)


# --- Top-N selection: the day's picks the Candidate Engine hands to the Range Trader -----

def test_top_range_symbols_picks_n_in_rank_order():
    ranked = rank_candidates([
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),
        _ri("NVDA", atr20_pct=0.050, classification="range_bound"),
        _ri("KO", atr20_pct=0.020, classification="range_bound"),
        _ri("MSFT", atr20_pct=0.038, classification="range_bound"),
    ])
    assert top_range_symbols(ranked, n=2) == ["AMD", "NVDA"]  # top-2 by rank
    assert top_range_symbols(ranked, n=10) == ["AMD", "NVDA", "MSFT", "KO"]  # n>len → all eligible


def test_top_range_symbols_min_score_floor():
    # Range Score = atr20_pct × oscillation (range_bound class weight 1.0 here).
    ranked = rank_candidates([
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),   # score 0.066
        _ri("KO", atr20_pct=0.020, classification="range_bound"),    # score 0.020
    ])
    # A floor between the two keeps only AMD; a floor above both selects nothing (skip day).
    assert top_range_symbols(ranked, n=5, min_score=0.03) == ["AMD"]
    assert top_range_symbols(ranked, n=5, min_score=0.10) == []


# --- Hard filters → qualified universe (two-step screen, ADR 0028 review #4) ---

def test_hard_filters_tag_qualified_with_reason():
    fil = HardFilters(min_price=10.0, min_adv=50_000_000.0, min_atr_pct=0.03)
    out = rank_candidates([
        _ri("OK",    atr20_pct=0.05, classification="range_bound", last_close=100, adv=1e8),
        _ri("THIN",  atr20_pct=0.01, classification="range_bound", last_close=100, adv=1e8),
        _ri("ILLIQ", atr20_pct=0.05, classification="range_bound", last_close=100, adv=1e6),
        _ri("CHEAP", atr20_pct=0.05, classification="range_bound", last_close=5,   adv=1e8),
    ], hard_filters=fil)
    by = {c.symbol: c for c in out}
    assert by["OK"].qualified is True and by["OK"].qualify_reason is None
    assert by["THIN"].qualified is False and by["THIN"].qualify_reason == "atr_below_min"
    assert by["ILLIQ"].qualify_reason == "adv_below_min"
    assert by["CHEAP"].qualify_reason == "price_below_min"


def test_top_range_symbols_require_qualified_gates_universe():
    out = rank_candidates([
        _ri("OK",   atr20_pct=0.05, classification="range_bound", adv=1e8),
        _ri("THIN", atr20_pct=0.01, classification="range_bound", adv=1e8),  # fails ATR% filter
    ], hard_filters=HardFilters())
    # Qualified universe only (range-boundness is a score factor, not a gate → require_suitable False).
    assert top_range_symbols(out, n=5, require_suitable=False, require_qualified=True) == ["OK"]
    # Without require_qualified the hard filter doesn't gate (back-compatible).
    assert set(top_range_symbols(out, n=5, require_suitable=False)) == {"OK", "THIN"}


def test_no_hard_filters_all_ok_are_qualified():
    out = rank_candidates([_ri("X", atr20_pct=0.05, classification="range_bound")])  # filters None
    assert out[0].qualified is True and out[0].qualify_reason is None


# --- Spread hard filter (Corwin-Schultz estimate; default-OFF) — range follow-up TASK 1 ---

def test_spread_filter_off_by_default_ignores_spread():
    # Default HardFilters has max_spread_pct=None → a wide estimated spread does NOT disqualify.
    out = rank_candidates(
        [_ri("WIDE", atr20_pct=0.05, classification="range_bound", cs_spread_pct=0.01)],
        hard_filters=HardFilters(),
    )
    assert out[0].qualified is True and out[0].qualify_reason is None
    assert out[0].cs_spread_pct == 0.01  # surfaced on the candidate


def test_spread_filter_gates_when_enabled():
    fil = HardFilters(max_spread_pct=0.001)  # 0.10% cap
    out = rank_candidates([
        _ri("TIGHT", atr20_pct=0.05, classification="range_bound", cs_spread_pct=0.0005),
        _ri("WIDE",  atr20_pct=0.05, classification="range_bound", cs_spread_pct=0.0030),
        _ri("NONE",  atr20_pct=0.05, classification="range_bound", cs_spread_pct=None),
    ], hard_filters=fil)
    by = {c.symbol: c for c in out}
    assert by["TIGHT"].qualified is True and by["TIGHT"].qualify_reason is None
    assert by["WIDE"].qualified is False and by["WIDE"].qualify_reason == "spread_above_max"
    # No estimate available → cannot prove tightness → excluded under an active spread gate.
    assert by["NONE"].qualified is False and by["NONE"].qualify_reason == "spread_above_max"


def test_corwin_schultz_spread_estimator():
    import pandas as pd

    from app.services.range_insight import _corwin_schultz_spread
    # A constant high/low ratio with no overnight drift → small, non-negative estimate.
    highs = pd.Series([101.0, 101.0, 101.0, 101.0])
    lows = pd.Series([100.0, 100.0, 100.0, 100.0])
    s = _corwin_schultz_spread(highs, lows)
    assert s is not None and 0.0 <= s < 0.05  # a fraction of price, floored at 0
    # Degenerate inputs are handled (no crash, None when not computable).
    assert _corwin_schultz_spread(pd.Series([100.0]), pd.Series([100.0])) is None


def test_top_range_symbols_excludes_unsuitable_and_insufficient():
    ranked = rank_candidates([
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),     # suitable
        _ri("TSLA", atr20_pct=0.060, classification="trending"),       # not range_bound → unsuitable
        _ri("BADX", status="insufficient_data"),                       # not ok
    ])
    # Even asking for 5, only the genuinely suitable name is returned — no padding.
    assert top_range_symbols(ranked, n=5) == ["AMD"]


def test_top_range_symbols_require_suitable_false_allows_ok_trending():
    ranked = rank_candidates([
        _ri("AMD", atr20_pct=0.066, classification="range_bound"),
        _ri("TSLA", atr20_pct=0.060, classification="trending"),
        _ri("BADX", status="insufficient_data"),
    ])
    # Relaxed: any ``ok`` name qualifies (still excludes insufficient_data); rank order kept.
    assert top_range_symbols(ranked, n=5, require_suitable=False) == ["AMD", "TSLA"]


def test_top_range_symbols_evidence_first_picks_winners():
    # The picks honor evidence-first ranking: AAPL (62%) leads NVDA (25%) despite NVDA's
    # higher structural ATR%.
    ranked = rank_candidates(
        [
            _ri("NVDA", atr20_pct=0.060, classification="range_bound"),
            _ri("AAPL", atr20_pct=0.030, classification="range_bound"),
        ],
        evidence={
            "NVDA": CandidateEvidence(win_rate=0.25, sharpe=-1.12, n_trades=20),
            "AAPL": CandidateEvidence(win_rate=0.62, sharpe=0.46, n_trades=24),
        },
    )
    assert top_range_symbols(ranked, n=1) == ["AAPL"]


def test_top_range_symbols_n_zero_or_negative_selects_none():
    ranked = rank_candidates([_ri("AMD", atr20_pct=0.066, classification="range_bound")])
    assert top_range_symbols(ranked, n=0) == []
    assert top_range_symbols(ranked, n=-3) == []
