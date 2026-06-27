"""Onboarding Gate + Lifecycle Fidelity scorecard (PORT-001 §2; ADR 0030 #4)."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.factor_lab.onboarding_gate import onboarding_gate


def _series(seed: int, n: int = 250) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(0.01 * rng.standard_normal(n))


def _passing_kwargs():
    base = _series(1)
    noise = 0.0005 * np.random.default_rng(99).standard_normal(len(base))
    w = np.array([0.3, 0.3, 0.2, 0.2])
    return dict(
        ref_sharpe=0.84, cand_sharpe=0.84,
        ref_maxdd=0.119, cand_maxdd=0.119,
        ref_daily_returns=base, cand_daily_returns=base + noise,  # ~0.999 corr
        ref_weights=w, cand_weights=w + 1e-4,
        ref_trades=120, cand_trades=122,
        deterministic=True,
    )


def test_all_criteria_pass():
    res = onboarding_gate(**_passing_kwargs())
    assert res.passed is True
    assert 0.0 <= res.fidelity <= 1.0 and res.fidelity > 0.9
    assert {c.name for c in res.criteria} == {
        "sharpe", "maxdd", "daily_return_corr", "weight_corr", "trade_count", "determinism",
    }
    sc = res.as_scorecard()
    assert sc["passed"] is True and sc["fidelity_pct"] > 90.0


def test_sharpe_drift_fails():
    kw = _passing_kwargs()
    kw["cand_sharpe"] = 0.84 + 0.10        # outside ±0.05
    res = onboarding_gate(**kw)
    assert res.passed is False
    assert not next(c for c in res.criteria if c.name == "sharpe").passed
    assert any("sharpe" in n for n in res.notes)


def test_low_return_correlation_fails():
    kw = _passing_kwargs()
    kw["cand_daily_returns"] = _series(999)    # uncorrelated → corr ≪ 0.98
    res = onboarding_gate(**kw)
    assert res.passed is False
    assert not next(c for c in res.criteria if c.name == "daily_return_corr").passed


def test_nondeterministic_fails():
    kw = _passing_kwargs()
    kw["deterministic"] = False
    res = onboarding_gate(**kw)
    assert res.passed is False
    assert not next(c for c in res.criteria if c.name == "determinism").passed


def test_trade_count_drift_fails():
    kw = _passing_kwargs()
    kw["cand_trades"] = 200                 # +67% vs 120 ref → outside ±10%
    res = onboarding_gate(**kw)
    assert res.passed is False
    assert not next(c for c in res.criteria if c.name == "trade_count").passed
