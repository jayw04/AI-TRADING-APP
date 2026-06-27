"""ERC optimizer (PORT-001 §2) — risk-budgeting fixed point."""

from __future__ import annotations

import numpy as np

from app.research.factor_lab.erc import erc_weights, risk_contributions


def test_equal_vol_uncorrelated_is_equal_weight():
    w = erc_weights([[1.0, 0.0], [0.0, 1.0]])
    assert np.allclose(w, [0.5, 0.5], atol=1e-6)


def test_inverse_to_vol_when_uncorrelated():
    # Equal risk with σ = 1 and 2 (var 1, 4), zero corr → w ∝ 1/σ → [2/3, 1/3].
    w = erc_weights([[1.0, 0.0], [0.0, 4.0]])
    assert np.allclose(w, [2 / 3, 1 / 3], atol=1e-4)
    rc = risk_contributions([[1.0, 0.0], [0.0, 4.0]], w)
    assert np.allclose(rc, [0.5, 0.5], atol=1e-4)   # equal risk contributions


def test_risk_contributions_equal_at_erc_three_assets():
    rng = np.random.default_rng(7)
    a = rng.standard_normal((400, 3)) @ np.array([[1.0, 0.2, 0.0], [0.0, 1.0, 0.3], [0.0, 0.0, 1.0]])
    cov = np.cov(a, rowvar=False)
    w = erc_weights(cov)
    rc = risk_contributions(cov, w)
    assert np.allclose(rc, 1 / 3, atol=1e-3)        # all three contribute equal risk
    assert abs(w.sum() - 1.0) < 1e-9 and np.all(w > 0)


def test_risk_budgets_respected():
    # A 70/30 risk budget → risk contributions ≈ 70/30 (not weights).
    cov = [[1.0, 0.0], [0.0, 4.0]]
    w = erc_weights(cov, budgets=[0.7, 0.3])
    rc = risk_contributions(cov, w)
    assert np.allclose(rc, [0.7, 0.3], atol=1e-3)


def test_deterministic():
    cov = [[1.0, 0.3], [0.3, 2.0]]
    assert np.array_equal(erc_weights(cov), erc_weights(cov))
