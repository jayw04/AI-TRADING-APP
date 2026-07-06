"""Look-through equity-beta-cap governor — PORT-001 lever #2 (spec §11 #2 / §6.2).

A **de-risk-only** governor: given a target book and a daily-return panel over its names, compute
the book's *look-through equity-beta risk contribution* — the share of total portfolio risk carried
by the equity-beta names (single stocks + the equity ETFs SPY/EFA/EEM) — and, if it exceeds a budget
(default 0.80), scale those equity-beta positions **down** (raising cash) until within budget. The
non-equity legs (bonds / gold / commodities / USD / managed futures) are left untouched.

This directly acts on the capability's headline disclosure (§6.2): the equity sleeve is a small share
of *capital* but the majority of *risk*. Faithful port of the sibling ``portfolio_riskmodel.cap_equity_beta``
(``_cov`` sample covariance + off-diagonal Ledoit-Wolf-lite shrink + risk-contribution mask + monotone
bisection). Pure / deterministic; never raises; never *increases* a weight (de-risk only).

The risk-contribution primitive is reused from ``erc.risk_contributions`` (the tested PCE primitive).
"""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

from app.research.factor_lab.erc import risk_contributions

# The cross-asset ETFs that are NOT equity-beta — the governor never scales these. Everything else in
# the book (single stocks + the equity ETFs SPY/EFA/EEM) is treated as equity-beta. Mirrors the
# sibling's ETF_CLASS / EQUITY_CLASSES split (managed futures = KMLM is NOT equity).
NON_EQUITY_ETFS: frozenset[str] = frozenset({"TLT", "IEF", "GLD", "DBC", "UUP", "KMLM"})

_BISECTION_ITERS = 50


def default_equity_names(names: list[str]) -> set[str]:
    """Classify book names into the equity-beta set (all names except the non-equity ETFs)."""
    return {n.upper() for n in names if n.upper() not in NON_EQUITY_ETFS}


def _shrink_cov(returns: np.ndarray, shrink: float) -> np.ndarray:
    """Sample covariance (ddof=1) with Ledoit-Wolf-lite off-diagonal shrinkage toward a diagonal
    target: ``C_s = (1-λ)·C + λ·diag(diag(C))`` (diagonal unchanged, off-diagonals ×(1-λ))."""
    cov = np.cov(returns, rowvar=False, ddof=1)
    cov = np.atleast_2d(cov)
    return (1.0 - shrink) * cov + shrink * np.diag(np.diag(cov))


def cap_equity_beta(
    weights: dict[str, float],
    returns: pd.DataFrame,
    *,
    equity_names: set[str],
    cap: float = 0.80,
    lookback: int = 120,
    shrink: float = 0.15,
) -> tuple[dict[str, float], dict[str, Any]]:
    """Return ``(new_weights, report)``. When the book's look-through equity-beta risk contribution
    exceeds ``cap``, scale the equity-beta weights DOWN (bisection) until within budget; otherwise the
    weights are returned unchanged. De-risk only.

    Parameters
    ----------
    weights : the target book, ``{symbol: weight}`` (weights are fractions of equity; any gross).
    returns : daily-return panel (index = date, columns = symbol) for the priced names. Names absent
        from ``returns`` are left untouched (they cannot be assessed).
    equity_names : the symbols treated as equity-beta (the mask). Case-insensitive.
    cap : max equity-beta risk-contribution share (default 0.80).
    lookback : trailing rows of ``returns`` used for the covariance (default 120).
    shrink : off-diagonal covariance shrinkage λ (default 0.15).
    """
    report: dict[str, Any] = {"applied": False, "cap": cap}
    new_weights = dict(weights)

    # Priced names present in BOTH the book and the return panel, order-stable.
    cols = {c.upper(): c for c in returns.columns}
    priced = [s for s in weights if s.upper() in cols]
    report["n_priced"] = len(priced)
    if len(priced) < 3:
        report["note"] = "fewer than 3 priced names; governor skipped"
        return new_weights, report

    panel = returns[[cols[s.upper()] for s in priced]].dropna(how="any")
    if panel.shape[0] > lookback:
        panel = panel.iloc[-lookback:]
    if panel.shape[0] < 3:
        report["note"] = "fewer than 3 common-date rows; governor skipped"
        return new_weights, report

    cov = _shrink_cov(panel.to_numpy(dtype=float), shrink)
    v = np.array([float(weights[s]) for s in priced])
    eq = frozenset(n.upper() for n in equity_names)
    mask = np.array([s.upper() in eq for s in priced])

    def equity_rc(vec: np.ndarray) -> float:
        rc = risk_contributions(cov, vec)
        return float(rc[mask].sum())

    rc0 = equity_rc(v)
    gross0 = float(np.abs(v).sum())
    report.update({
        "equity_beta_rc_before": round(rc0, 4),
        "gross_before": round(gross0, 4),
        "n_equity": int(mask.sum()),
    })

    if rc0 <= cap:
        report["note"] = "within budget; no change"
        return new_weights, report

    # Monotone bisection: scaling the equity-beta weights by f in [0,1] drives their risk share from
    # the breached level (f=1) toward 0 (f=0). Take the lo side so the result is guaranteed <= cap.
    lo, hi = 0.0, 1.0
    for _ in range(_BISECTION_ITERS):
        f = (lo + hi) / 2.0
        if equity_rc(np.where(mask, v * f, v)) > cap:
            hi = f
        else:
            lo = f
    f = lo
    vv = np.where(mask, v * f, v)
    for i, s in enumerate(priced):
        new_weights[s] = round(float(vv[i]), 6)

    report.update({
        "applied": True,
        "scale_equity_beta": round(f, 4),
        "equity_beta_rc_after": round(equity_rc(vv), 4),
        "gross_after": round(float(np.abs(vv).sum()), 4),
        "cash_freed": round(gross0 - float(np.abs(vv).sum()), 4),
    })
    return new_weights, report
