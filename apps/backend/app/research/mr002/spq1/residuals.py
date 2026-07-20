"""Step-2 stock residual + market beta (SIG-08/09, frozen §3 Step 2; OWNER-A chain).

Coefficients estimated on the registered window t-60..t-1 only; the day-t residual uses those
t-1 coefficients with the day-t factor returns:

    eps_i,t = r_i,t - (alpha_hat_{t-1} + beta_m_hat_{t-1} r_SPY,t + beta_s_hat_{t-1} u_sector,t)

The emitted beta is beta_m_hat_{t-1} (the market-beta coefficient) — no separate beta model.
A non-finite residual fails closed INTEGRITY_STOP:RESIDUAL_NONFINITE.
"""
from __future__ import annotations

import numpy as np

from .constants import OLS_WINDOW
from .refusals import refuse
from .stock_regression import registered_ols

__all__ = ["stock_residual_and_beta"]


def stock_residual_and_beta(
    stock_ret: np.ndarray, spy_ret: np.ndarray, u_sector: np.ndarray, t: int
) -> tuple[float, float]:
    """Return (eps_t, beta_m_hat_{t-1}) for decision session t.

    Inputs are calendar-aligned float64 arrays already validated present over t-60..t.
    """
    stock_ret = np.asarray(stock_ret, dtype=np.float64)
    spy_ret = np.asarray(spy_ret, dtype=np.float64)
    u_sector = np.asarray(u_sector, dtype=np.float64)
    lo = t - OLS_WINDOW
    y = stock_ret[lo:t]
    X = np.column_stack([spy_ret[lo:t], u_sector[lo:t]])
    coef = registered_ols(y, X)  # [alpha, beta_m, beta_s]
    beta_m = float(coef[1])
    eps_t = float(
        stock_ret[t] - (coef[0] + coef[1] * spy_ret[t] + coef[2] * u_sector[t])
    )
    if not np.isfinite(eps_t):
        raise refuse("INTEGRITY_STOP:RESIDUAL_NONFINITE", f"non-finite residual at t={t}")
    return eps_t, beta_m
