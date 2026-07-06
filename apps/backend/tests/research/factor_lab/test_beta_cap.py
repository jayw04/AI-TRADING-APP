"""Look-through equity-beta-cap governor (PORT-001 lever #2) — de-risk-only, mask, bisection."""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.research.factor_lab.beta_cap import (
    NON_EQUITY_ETFS,
    cap_equity_beta,
    default_equity_names,
)


def _panel(
    n: int = 200, *, n_equity: int = 3, beta: float = 0.9, seed: int = 3
) -> tuple[pd.DataFrame, dict[str, float]]:
    """Build a return panel where ``n_equity`` equity-correlated stocks share a market factor (high
    common risk) plus two low-vol, negatively-correlated hedges (TLT, GLD). Returns (panel, weights)."""
    rng = np.random.default_rng(seed)
    mkt = rng.standard_normal(n) * 0.02
    cols = {f"S{i}": beta * mkt + rng.standard_normal(n) * 0.005 for i in range(n_equity)}
    cols["TLT"] = -0.3 * mkt + rng.standard_normal(n) * 0.004
    cols["GLD"] = rng.standard_normal(n) * 0.004
    idx = pd.date_range("2025-01-01", periods=n, freq="B")
    panel = pd.DataFrame(cols, index=idx)
    w = {f"S{i}": 0.30 for i in range(n_equity)}
    w["TLT"] = 0.05
    w["GLD"] = 0.05
    return panel, w


def test_classification_excludes_only_non_equity_etfs():
    eq = default_equity_names(["AAPL", "SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"])
    assert eq == {"AAPL", "SPY", "EFA", "EEM"}            # stocks + equity ETFs are equity-beta
    assert {"TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"} == NON_EQUITY_ETFS


def test_over_budget_derisks_equity_only_and_frees_cash():
    panel, w = _panel()
    eq = default_equity_names(list(w))
    new, rep = cap_equity_beta(w, panel, equity_names=eq, cap=0.80)
    assert rep["applied"] is True
    assert rep["equity_beta_rc_before"] > 0.80
    assert rep["equity_beta_rc_after"] <= 0.80 + 1e-6
    # only the equity names are scaled DOWN; the hedges are untouched.
    for s in ("S0", "S1", "S2"):
        assert new[s] < w[s]
    assert new["TLT"] == w["TLT"] and new["GLD"] == w["GLD"]
    # de-risk only → gross falls, cash freed.
    assert sum(new.values()) < sum(w.values())
    assert rep["cash_freed"] > 0


def test_within_budget_is_noop():
    # A book that is already diversified (equal risk-ish) should not be touched.
    panel, _ = _panel(n_equity=1)          # 1 stock + 2 hedges → equity share modest
    w = {"S0": 0.20, "TLT": 0.40, "GLD": 0.40}
    new, rep = cap_equity_beta(w, panel, equity_names=default_equity_names(list(w)),
                               cap=0.99)   # generous cap → guaranteed within budget
    assert rep["applied"] is False
    assert new == w


def test_fewer_than_three_priced_skips():
    panel, _ = _panel()
    w = {"S0": 0.5, "ZZZZ": 0.5}           # only S0 is priced in the panel
    new, rep = cap_equity_beta(w, panel, equity_names={"S0", "ZZZZ"}, cap=0.10)
    assert rep["applied"] is False and rep["n_priced"] < 3
    assert new == w


def test_unpriced_names_untouched():
    panel, w = _panel()
    w = dict(w)
    w["NOBARS"] = 0.10                      # a name with no return history
    new, rep = cap_equity_beta(w, panel, equity_names=default_equity_names(list(w)), cap=0.80)
    assert new["NOBARS"] == 0.10           # governor never touches an unpriced name
    assert rep["applied"] is True          # the priced equity names still got trimmed


def test_deterministic():
    panel, w = _panel()
    eq = default_equity_names(list(w))
    a, _ = cap_equity_beta(w, panel, equity_names=eq, cap=0.80)
    b, _ = cap_equity_beta(w, panel, equity_names=eq, cap=0.80)
    assert a == b
