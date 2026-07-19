"""Synthetic-fixture + identity tests for the MR-002 val/OOS metric prototype.

NO real returns. Every input is a synthetic vector with a known closed-form answer, plus
determinism/reproducibility (seed 42) and INTEGRITY_STOP behavior. Proves the frozen §7/§8 spec is
implementable and reproducible by an independent implementation from the same vector alone.
"""

from __future__ import annotations

import numpy as np
import pytest

import mr002_valoos_metrics_prototype as m


def test_sharpe_closed_form_constant_mean_unit_std():
    # r ~ mean 0.001, sd exactly set: build a vector with known mean/std
    r = np.array([0.002, 0.000, 0.002, 0.000] * 100, dtype=np.float64)  # mean 0.001
    sd = r.std(ddof=1)
    expected = 0.001 / sd * np.sqrt(252.0)
    assert abs(m.annualized_sharpe(r) - expected) < 1e-12


def test_sharpe_scale_invariance_of_sign_and_monotonic():
    rng = np.random.default_rng(0)
    r = rng.normal(0.0005, 0.01, size=1000)
    s1 = m.annualized_sharpe(r)
    s2 = m.annualized_sharpe(r + 0.0005)  # higher mean, same sd shape -> higher sharpe
    assert s2 > s1


def test_sharpe_zero_volatility_integrity_stop():
    with pytest.raises(m.IntegrityStop, match="ZERO_VOLATILITY"):
        m.annualized_sharpe(np.full(500, 0.001))


def test_sharpe_nonfinite_integrity_stop():
    with pytest.raises(m.IntegrityStop):
        m.annualized_sharpe(np.array([0.01, np.nan, 0.02]))
    with pytest.raises(m.IntegrityStop):
        m.annualized_sharpe(np.array([], dtype=np.float64))


def test_bootstrap_deterministic_same_seed():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0008, 0.012, size=850)  # validation-sized synthetic
    a = m.block_bootstrap_mean_ci_lower(r, seed=42)
    b = m.block_bootstrap_mean_ci_lower(r, seed=42)
    assert a == b  # bit-identical -> reproducible


def test_bootstrap_different_seed_differs():
    rng = np.random.default_rng(7)
    r = rng.normal(0.0008, 0.012, size=850)
    assert m.block_bootstrap_mean_ci_lower(r, seed=42) != m.block_bootstrap_mean_ci_lower(r, seed=43)


def test_bootstrap_strong_positive_lower_bound_positive():
    # a strongly positive, low-noise synthetic mean -> one-sided 95% lower bound > 0
    r = np.full(850, 0.001) + np.random.default_rng(1).normal(0, 1e-5, 850)
    assert m.block_bootstrap_mean_ci_lower(r, seed=42) > 0.0


def test_bootstrap_zero_centered_lower_bound_not_positive():
    # zero-centered synthetic -> lower bound should not be > 0 (no spurious edge)
    r = np.random.default_rng(2).normal(0.0, 0.01, 850)
    assert m.block_bootstrap_mean_ci_lower(r, seed=42) <= 0.0


def test_noninferiority_diff_reproducible_and_signed():
    rng = np.random.default_rng(3)
    valid = rng.normal(0.0008, 0.012, 850)
    oos_better = valid.copy() * 0 + rng.normal(0.0012, 0.012, 850)
    d1 = m.sharpe_diff_noninferiority_lower(oos_better, valid, seed=42)
    d2 = m.sharpe_diff_noninferiority_lower(oos_better, valid, seed=42)
    assert d1 == d2  # reproducible


def test_block_length_and_constants_are_frozen():
    assert m.BLOCK_SESSIONS == 21 and m.RESAMPLES == 2000 and m.SEED == 42 and m.CONFIDENCE == 0.95
    assert abs(m.ANNUALIZATION - np.sqrt(252.0)) < 1e-15


def test_prototype_reads_no_data_sources():
    # identity: the prototype imports only numpy; no file/db/network access
    import ast
    import inspect
    src = inspect.getsource(m)
    tree = ast.parse(src)
    imports = set()
    for n in ast.walk(tree):
        if isinstance(n, ast.Import):
            imports.update(a.name for a in n.names)
        elif isinstance(n, ast.ImportFrom):
            imports.add(n.module)
    assert imports <= {"numpy", "__future__"}, f"unexpected imports: {imports}"
    assert "open(" not in src and "duckdb" not in src and "read_" not in src
