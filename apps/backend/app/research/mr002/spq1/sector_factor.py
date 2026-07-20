"""Step-1 orthogonalized sector factor u_sector (SIG-07, frozen §3 Step 1).

For each session s: fit r_sector,w = a + beta_sector*r_SPY,w + u on the registered window
w = s-60..s-1, then u_sector[s] = r_sector[s] - (a + beta_sector*r_SPY[s]). PIT-recursive: one
regression per session, never estimated once and applied retrospectively. SPY and the sector-ETF
series are frozen inputs; a missing/non-finite factor return refuses SIGNAL_INPUT_IDENTITY_MISMATCH.
"""
from __future__ import annotations

import numpy as np

from .constants import OLS_WINDOW
from .returns import require_factor_present
from .stock_regression import registered_ols

__all__ = ["sector_factor_at"]


def sector_factor_at(spy_ret: np.ndarray, sector_ret: np.ndarray, s: int) -> float:
    """u_sector[s] from the registered window s-60..s-1 (raises on insufficient history)."""
    spy_ret = np.asarray(spy_ret, dtype=np.float64)
    sector_ret = np.asarray(sector_ret, dtype=np.float64)
    lo = s - OLS_WINDOW
    if lo < 0:
        # sector-ETF factor lacking history is an input-identity problem, not a stock refusal.
        require_factor_present(np.array([np.nan]), "sector-ETF (insufficient history)")
    win_spy = spy_ret[lo:s]
    win_sec = sector_ret[lo:s]
    require_factor_present(win_spy, "SPY")
    require_factor_present(win_sec, "sector-ETF")
    require_factor_present(spy_ret[s : s + 1], "SPY (day s)")
    require_factor_present(sector_ret[s : s + 1], "sector-ETF (day s)")
    coef = registered_ols(win_sec, win_spy)  # [a, beta_sector]
    return float(sector_ret[s] - (coef[0] + coef[1] * spy_ret[s]))
