"""Equal-Risk-Contribution (ERC) optimizer — Portfolio Construction Engine primitive (§2).

The allocation policy PORT-001 blends its two sleeves with (ADR 0030 #1: ERC is the only
policy built now; the PCE is allocation-policy-agnostic). ERC / risk-budgeting finds weights
where each asset's **risk contribution** is equal (or matches a target budget), so neither
sleeve dominates portfolio risk — the spec's "blended so neither dominates risk".

Risk contribution of asset i:  RC_i = w_i · (Σw)_i ,  with Σ_i RC_i = w'Σw (total variance).
ERC ⇔ RC_i equal across i. The general form targets a **risk budget** b_i (b summing to 1);
ERC is b_i = 1/n.

Solved by the standard risk-budgeting **sqrt-damped multiplicative iteration** (long-only,
fully-invested): nudge each weight toward its target by the ratio of target budget to current
risk contribution, ``w_i ← w_i·√(b_i / RC_i)``, then renormalize, to convergence. (The
undamped fixed point ``w_i ← b_i/(Σw)_i`` overshoots / oscillates for unequal budgets; the
sqrt damping makes it a contraction.) Pure / deterministic — no SciPy dependency.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt

_FLOOR = 1e-18


def erc_weights(
    cov: npt.ArrayLike,
    budgets: npt.ArrayLike | None = None,
    *,
    max_iter: int = 10_000,
    tol: float = 1e-12,
) -> np.ndarray:
    """Long-only, fully-invested (sum = 1) risk-budgeting weights for covariance ``cov``.
    ``budgets`` are target risk fractions (default equal = ERC). Deterministic."""
    sigma = np.asarray(cov, dtype=float)
    n = sigma.shape[0]
    if sigma.shape != (n, n):
        raise ValueError("cov must be square")
    b: npt.NDArray[np.float64]
    if budgets is None:
        b = np.full(n, 1.0 / n)
    else:
        b = np.asarray(budgets, dtype=float)
        if b.shape != (n,) or np.any(b <= 0):
            raise ValueError("budgets must be positive and length n")
        b = b / b.sum()

    vol = np.sqrt(np.clip(np.diag(sigma), _FLOOR, None))
    w: npt.NDArray[np.float64] = 1.0 / vol
    w = w / w.sum()  # inverse-vol warm start

    for _ in range(max_iter):
        rc = w * (sigma @ w)             # unnormalized risk contributions
        total = rc.sum()
        if total <= _FLOOR:
            break
        rc_norm = rc / total
        w_new = w * np.sqrt(b / np.clip(rc_norm, _FLOOR, None))  # sqrt-damped nudge to budget
        w_new = w_new / w_new.sum()
        if np.max(np.abs(w_new - w)) < tol:
            return w_new
        w = w_new
    return w


def risk_contributions(cov: npt.ArrayLike, weights: npt.ArrayLike) -> np.ndarray:
    """Normalized risk contributions per asset (sum to 1): RC_i / Σ_j RC_j."""
    sigma = np.asarray(cov, dtype=float)
    w = np.asarray(weights, dtype=float)
    rc = w * (sigma @ w)
    total = rc.sum()
    if total <= _FLOOR:
        return np.zeros_like(rc)
    return rc / total
