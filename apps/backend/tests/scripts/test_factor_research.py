"""Factor research engine — pure-metric + run_study smoke tests (offline)."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import numpy as np
import pandas as pd

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "factor_research.py"
_spec = importlib.util.spec_from_file_location("factor_research", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)
spearman_ic = _mod.spearman_ic
quintile_ls = _mod.quintile_ls
run_study = _mod.run_study


def test_spearman_ic_perfect_positive_and_negative():
    f = pd.Series([1, 2, 3, 4, 5, 6])
    assert spearman_ic(f, f) == 1.0
    assert spearman_ic(f, f[::-1].reset_index(drop=True)) == -1.0


def test_spearman_ic_insufficient_or_constant_returns_none():
    assert spearman_ic(pd.Series([1, 2, 3]), pd.Series([1, 2, 3])) is None  # < 5
    assert spearman_ic(pd.Series([1, 1, 1, 1, 1, 1]), pd.Series([1, 2, 3, 4, 5, 6])) is None


def test_quintile_ls_sign():
    f = pd.Series(range(20), dtype=float)
    fwd_aligned = pd.Series(range(20), dtype=float)        # high factor → high return
    fwd_inverted = pd.Series(range(20, 0, -1), dtype=float)
    assert quintile_ls(f, fwd_aligned) > 0
    assert quintile_ls(f, fwd_inverted) < 0


def test_quintile_ls_insufficient_returns_none():
    assert quintile_ls(pd.Series([1.0, 2, 3]), pd.Series([1.0, 2, 3])) is None


def _synthetic_close(n_tickers=24, n_days=700, seed=3) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    idx = pd.bdate_range("2020-01-01", periods=n_days)
    # per-ticker drift + noise → some names trend, giving momentum signal
    drift = rng.normal(0, 0.0008, n_tickers)
    rets = rng.normal(0, 0.015, (n_days, n_tickers)) + drift
    px = 100 * np.exp(np.cumsum(rets, axis=0))
    return pd.DataFrame(px, index=idx, columns=[f"T{i:02d}" for i in range(n_tickers)])


def test_run_study_shape_and_no_crash():
    close = _synthetic_close()
    results, ls_panel = run_study(close, split=pd.Timestamp("2021-06-01"))
    factors = {"mom_12_1", "mom_6_1", "mom_12", "lowvol_6m", "reversal_1m"}
    # one IS + one OOS row per factor
    assert {r.factor for r in results} == factors
    assert {(r.factor, r.window) for r in results} == {(f, w) for f in factors for w in ("IS", "OOS")}
    assert set(ls_panel.columns) == factors
    # IC summaries are computed for the in-sample window
    is_mom = next(r for r in results if r.factor == "mom_12_1" and r.window == "IS")
    assert is_mom.n_periods > 0
    assert is_mom.mean_ic is None or -1.0 <= is_mom.mean_ic <= 1.0


def test_run_study_decay_horizons_present():
    results, _ = run_study(_synthetic_close(), split=pd.Timestamp("2021-06-01"))
    r = results[0]
    assert set(r.decay_ic) == {"1m", "3m", "6m", "12m"}
