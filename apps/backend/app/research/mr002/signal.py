"""MR-002 signal construction — FROZEN v1.0 §3 (do not modify: any change requires a
registered version increment).

Implements exactly:

  Step 1 — ORTHOGONALIZED SECTOR FACTOR, generated recursively and point-in-time.
    For every session s, sector-regression coefficients estimated on s-60..s-1 are
    applied to session s:   r_Sector,s = a + b_Sector * r_SPY,s + u_Sector,s
    The stored PIT sequence of u_Sector is what the stock model consumes. It is
    PROHIBITED to estimate one sector regression and apply it retrospectively.

  Step 2 — STOCK MODEL, rolling 60 sessions, betas from t-60..t-1 only:
    r_i,t = alpha_i + beta_m,i * r_SPY,t + beta_s,i * u_Sector,t + eps_i,t
    OLS WITH intercept; NO regularization; singular or zero-variance => the
    observation is unavailable and the stock is ineligible that day.

  Step 3 — SIGNAL:
    R5_i,t = sum_{k=0..4} eps_i,t-k
    z_i,t  = (R5_i,t - mu_i,t-1) / sigma_i,t-1
    mu/sigma from rolling windows ENDING AT t-1 (the day-t signal never enters its
    own normalization); EXACTLY 60 complete five-day observations required;
    ddof=1; arithmetic total returns (closeadj); any missing observation => the
    stock is ineligible that day; NO winsorization.
"""

from __future__ import annotations

import numpy as np

LOOKBACK = 60          # sessions for both regressions and the z normalization
RESID_WINDOW = 5       # cumulative residual horizon
MIN_Z_OBS = 60         # complete five-day observations required
DDOF = 1


def _ols(y: np.ndarray, X: np.ndarray) -> np.ndarray | None:
    """OLS with intercept. Returns coefficients [a, b1, ...] or None if singular."""
    A = np.column_stack([np.ones(len(y)), X])
    if np.linalg.matrix_rank(A) < A.shape[1]:
        return None
    try:
        beta, *_ = np.linalg.lstsq(A, y, rcond=None)
    except np.linalg.LinAlgError:
        return None
    return beta


def sector_residuals(sector_ret: np.ndarray, spy_ret: np.ndarray) -> np.ndarray:
    """PIT-recursive orthogonalized sector factor u_Sector (frozen §3 step 1).

    Returns an array the same length as the inputs; entries before enough history
    are NaN. u[s] is computed from coefficients fitted on s-LOOKBACK..s-1 ONLY.
    """
    n = len(sector_ret)
    u = np.full(n, np.nan)
    for s in range(LOOKBACK, n):
        y = sector_ret[s - LOOKBACK:s]
        x = spy_ret[s - LOOKBACK:s]
        if np.isnan(y).any() or np.isnan(x).any():
            continue
        if np.nanstd(x, ddof=DDOF) == 0:
            continue
        beta = _ols(y, x.reshape(-1, 1))
        if beta is None:
            continue
        u[s] = sector_ret[s] - (beta[0] + beta[1] * spy_ret[s])
    return u


def stock_residuals(stock_ret: np.ndarray, spy_ret: np.ndarray,
                    u_sector: np.ndarray) -> np.ndarray:
    """Day-t residual eps from betas fitted on t-LOOKBACK..t-1 (frozen §3 step 2)."""
    n = len(stock_ret)
    eps = np.full(n, np.nan)
    for t in range(LOOKBACK, n):
        y = stock_ret[t - LOOKBACK:t]
        X = np.column_stack([spy_ret[t - LOOKBACK:t], u_sector[t - LOOKBACK:t]])
        if np.isnan(y).any() or np.isnan(X).any():
            continue
        if np.isnan(stock_ret[t]) or np.isnan(spy_ret[t]) or np.isnan(u_sector[t]):
            continue
        if np.nanstd(X[:, 0], ddof=DDOF) == 0 or np.nanstd(X[:, 1], ddof=DDOF) == 0:
            continue
        beta = _ols(y, X)
        if beta is None:
            continue
        eps[t] = stock_ret[t] - (beta[0] + beta[1] * spy_ret[t] + beta[2] * u_sector[t])
    return eps


def residual_zscores(eps: np.ndarray) -> np.ndarray:
    """Mean-adjusted 5-day residual z-score with t-1 normalization (frozen §3 step 3).

    R5_t = sum(eps[t-4..t]); z_t = (R5_t - mu_{t-1}) / sigma_{t-1}, where mu/sigma
    are the mean/std (ddof=1) of the R5 series over the 60 complete overlapping
    five-day observations ENDING AT t-1. The day-t value never enters its own
    normalization. Fewer than 60 complete observations => NaN (ineligible).
    """
    n = len(eps)
    r5 = np.full(n, np.nan)
    for t in range(RESID_WINDOW - 1, n):
        w = eps[t - RESID_WINDOW + 1:t + 1]
        if not np.isnan(w).any():
            r5[t] = w.sum()
    z = np.full(n, np.nan)
    for t in range(n):
        hist = r5[max(0, t - MIN_Z_OBS):t]          # ENDS at t-1 (exclusive of t)
        if len(hist) < MIN_Z_OBS or np.isnan(hist).any() or np.isnan(r5[t]):
            continue
        sigma = np.std(hist, ddof=DDOF)
        if sigma == 0 or not np.isfinite(sigma):
            continue
        z[t] = (r5[t] - np.mean(hist)) / sigma
    return z


def arithmetic_returns(closeadj: np.ndarray) -> np.ndarray:
    """Arithmetic total returns from the dividend-adjusted signal series (frozen §4)."""
    r = np.full(len(closeadj), np.nan)
    r[1:] = closeadj[1:] / closeadj[:-1] - 1.0
    return r
