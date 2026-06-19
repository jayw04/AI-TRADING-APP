"""Gross-exposure overlay layer (P10 §2, ADR 0020).

A **separate, stateless, deterministic** risk-overlay layer. Its only job is to
compute a scalar *desired gross exposure* in ``[0, 1]`` from market state — it never
selects symbols, never changes weights, never emits orders, and never leverages
(gross is capped at 1.0). The caller (a strategy's daily overlay tick) applies the
scalar to the held book; a separate execute step diffs and routes orders through the
OrderRouter. See ADR 0020 for the full invariant table.
"""

from __future__ import annotations

import math
from collections.abc import Sequence

import pandas as pd

# Trading days per year — the annualization factor for a daily-vol estimate. Matches
# the backtest overlay (`backtest._vol_target_overlay`) so live and backtest agree.
_TRADING_DAYS = 252.0


def desired_gross(
    *,
    market_returns: Sequence[float],
    vol_target_annual: float,
    vol_ewma_span: int,
) -> float:
    """Target gross-exposure multiplier in ``[0, 1]`` for a vol-target overlay.

    ``min(1.0, vol_target_annual / realized_annual_vol)``, where
    ``realized_annual_vol = EWMA(span) std of the proxy's daily returns × √252``.
    The cap at 1.0 means the overlay never adds leverage; it only ever de-risks.

    Reuses the same EWMA-vol math as the backtest overlay
    (``backtest._vol_target_overlay`` / ``MomentumPortfolio._gross_scale``) so the
    live overlay and the backtest agree.

    **Fails OPEN — returns 1.0 (no scaling)** when: the target is non-positive; there
    are fewer than two finite returns to estimate σ; or σ is non-finite / ≤ 0. This
    matches the strategy's reviewed-and-praised fail-open-regime posture and ADR
    0020's fail-open boundary — a data gap must never force a liquidation.

    **Deterministic and stateless:** identical ``market_returns`` + params → identical
    output (ADR 0020). Knows nothing about positions, deltas, or orders — it returns a
    scalar, never weights.
    """
    if vol_target_annual <= 0:
        return 1.0
    rets = [float(r) for r in market_returns if r is not None and math.isfinite(float(r))]
    if len(rets) < 2:
        return 1.0  # too little history to estimate σ → fail open
    sigma_daily = float(pd.Series(rets, dtype=float).ewm(span=vol_ewma_span).std().iloc[-1])
    if not math.isfinite(sigma_daily) or sigma_daily <= 0:
        return 1.0
    realized_annual = sigma_daily * math.sqrt(_TRADING_DAYS)
    if realized_annual <= 0:
        return 1.0
    return min(1.0, vol_target_annual / realized_annual)
