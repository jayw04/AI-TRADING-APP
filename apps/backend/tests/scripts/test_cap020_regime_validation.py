"""CAP-020 regime-overlay validation — pure-helper tests (offline, no store)."""

from __future__ import annotations

import importlib.util
import sys
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "cap020_regime_validation.py"
_spec = importlib.util.spec_from_file_location("cap020_regime_validation", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)


# ---- regime gate ------------------------------------------------------------

def test_regime_riskon_no_lookahead_and_warmup_fails_open():
    idx = pd.bdate_range("2020-01-01", periods=300)
    px = pd.Series(np.concatenate([np.linspace(100, 220, 240), np.linspace(220, 120, 60)]), index=idx)
    r = _mod.regime_riskon(px, sma_days=200)
    assert r.dtype == bool and len(r) == len(px)
    assert bool(r.iloc[0]) is True          # warm-up (pre-SMA) fails open to risk-ON
    assert bool(r.iloc[230]) is True         # deep in the uptrend
    assert bool(r.iloc[-1]) is False         # deep in the downtrend

def test_regime_riskon_is_shifted_one_day():
    # a proxy that crosses below its SMA on a known day; the flag must react the NEXT day
    idx = pd.bdate_range("2020-01-01", periods=260)
    px = pd.Series(np.concatenate([np.linspace(100, 200, 205), np.linspace(200, 100, 55)]), index=idx)
    raw = (px > px.rolling(200).mean())
    shifted = _mod.regime_riskon(px, 200)
    assert list(shifted.iloc[1:].astype(bool)) == list(raw.iloc[:-1].astype(bool))


# ---- gross + overlay + cost -------------------------------------------------

def test_gross_series_maps_regime_to_exposure():
    idx = pd.bdate_range("2021-01-01", periods=5)
    riskon = pd.Series([True, True, False, False, True], index=idx)
    g = _mod.gross_series(riskon, 0.5)
    assert list(g) == [1.0, 1.0, 0.5, 0.5, 1.0]

def test_overlay_scales_returns_and_charges_flip_cost():
    idx = pd.bdate_range("2021-01-01", periods=4)
    eqw = pd.Series([0.01, 0.01, 0.01, 0.01], index=idx)
    riskon = pd.Series([True, True, False, False], index=idx)   # one flip (day 3): gross 1.0 -> 0.5
    ov = _mod.overlay_returns(eqw, riskon, risk_off_gross=0.5, cost_bps=100)  # 100bps = 0.01
    # day1,2 risk-on: gross 1.0, no turnover -> 0.01
    assert round(ov.iloc[0], 6) == 0.01 and round(ov.iloc[1], 6) == 0.01
    # day3 flip to 0.5: 0.5*0.01 - |0.5-1.0|*0.01 = 0.005 - 0.005 = 0.0
    assert round(ov.iloc[2], 6) == 0.0
    # day4 no flip: 0.5*0.01 - 0 = 0.005
    assert round(ov.iloc[3], 6) == 0.005

def test_overlay_with_zero_cost_is_pure_gross_scaling():
    idx = pd.bdate_range("2021-01-01", periods=3)
    eqw = pd.Series([0.02, -0.02, 0.02], index=idx)
    riskon = pd.Series([False, False, False], index=idx)   # always risk-off; flip only on day1 (1->0.5)
    ov = _mod.overlay_returns(eqw, riskon, 0.5, cost_bps=0)
    assert round(ov.iloc[1], 6) == -0.01 and round(ov.iloc[2], 6) == 0.01


# ---- metrics ----------------------------------------------------------------

def test_mdd_calmar_cagr_known_values():
    # +100% then -50% → back to start: maxdd = -50%, total return 0 → cagr ~0
    rets = [1.0, -0.5]
    assert round(_mod._mdd(rets), 4) == -0.5
    assert abs(_mod._cagr(rets)) < 1e-9
    assert _mod._calmar(rets) == 0.0 or abs(_mod._calmar(rets)) < 1e-9

def test_mdd_monotonic_decline():
    assert round(_mod._mdd([-0.1, -0.1, -0.1]), 4) == round((0.9**3 - 1), 4)


# ---- paired bootstrap -------------------------------------------------------

def test_paired_diff_ci_is_deterministic_and_orders_ci():
    rng = np.random.default_rng(0)
    a = list(rng.normal(0.001, 0.01, 400))
    b = list(rng.normal(0.0, 0.01, 400))
    d1, lo1, hi1 = _mod.paired_diff_ci(a, b, _mod._mdd, seed=17)
    d2, lo2, hi2 = _mod.paired_diff_ci(a, b, _mod._mdd, seed=17)
    assert (d1, lo1, hi1) == (d2, lo2, hi2)   # deterministic for a fixed seed
    assert lo1 <= hi1

def test_paired_diff_ci_short_series_returns_nan_ci():
    d, lo, hi = _mod.paired_diff_ci([0.01, -0.01], [0.0, 0.0], _mod._mdd)
    assert lo != lo and hi != hi   # NaN


# ---- decision matrix --------------------------------------------------------

def _cell(**over):
    base = _mod.CellResult(
        sma=200, gross=0.5, cost_bps=10, d_calmar=0.20, calmar_ci=[0.05, 0.35],
        d_maxdd_pp=8.0, maxdd_ci_pp=[3.0, 12.0], d_sharpe=0.02, d_cagr_pp=-1.0,
        n_flips=6, turnover=3.0, passes_primary=True, passes_supporting=True,
        passes_guardrails=True, passes=True)
    return replace(base, **over)

def test_classify_validated_when_all_pass_and_robust():
    assert _mod.classify(_cell(), robustness_frac=0.78) == "Validated"

def test_classify_conditionally_promising_when_robustness_short():
    assert _mod.classify(_cell(), robustness_frac=0.5) == "Conditionally Promising"

def test_classify_conditionally_promising_when_guardrail_fails():
    c = _cell(passes=False, passes_guardrails=False, d_sharpe=-0.2)
    assert _mod.classify(c, robustness_frac=0.9) == "Conditionally Promising"

def test_classify_rejected_when_no_benefit():
    c = _cell(passes=False, passes_primary=False, passes_supporting=False,
              d_calmar=-0.05, d_maxdd_pp=-1.0)
    assert _mod.classify(c, robustness_frac=0.9) == "Rejected (Evidenced)"

def test_classify_rejected_when_calmar_negative_and_guardrail_fails():
    # the real CAP-020 result: negative Calmar + a positive ΔMaxDD point but Sharpe guardrail breached
    # → Rejected (the primary rule governs), NOT Conditionally Promising off the positive ΔMaxDD.
    c = _cell(passes=False, passes_primary=False, passes_guardrails=False,
              d_calmar=-0.30, d_maxdd_pp=2.6, d_sharpe=-0.23)
    assert _mod.classify(c, robustness_frac=0.0) == "Rejected (Evidenced)"

def test_robustness_fraction_counts_passing_cells():
    cells = [_cell(passes=True), _cell(passes=True), _cell(passes=False)]
    assert abs(_mod.robustness_fraction(cells) - 2 / 3) < 1e-9


# ---- data-sufficiency gate --------------------------------------------------

def test_data_sufficiency_flags_short_bullonly_window():
    # 1.6y, 1 flip, only a bull environment → all three insufficiency reasons fire
    reasons = _mod.data_sufficiency(1.6, 1, ["bull_2023_24"])
    assert len(reasons) == 3

def test_data_sufficiency_passes_full_window_with_bears():
    reasons = _mod.data_sufficiency(7.4, 8, ["covid_2020", "bear_2022", "bull_2023_24"])
    assert reasons == []

def test_data_sufficiency_requires_a_bear_environment():
    reasons = _mod.data_sufficiency(6.0, 6, ["bull_2023_24"])  # long enough, enough flips, but no bear
    assert len(reasons) == 1 and "bear" in reasons[0]
