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

# Default regime-signal ramp thresholds (P10 §5, ADR 0022). Conservative starting
# points; the ADR-0022 §7 promotion backtest tunes them before the regime overlay is
# enabled on a book. Breadth ramps UP (healthy tape → factor 1.0); VIX percentile ramps
# DOWN (stress → factor 0.0).
_BREADTH_FLOOR = 0.30   # breadth ≤ this → regime factor 0 (narrow market, fully de-risk)
_BREADTH_FULL = 0.60    # breadth ≥ this → regime factor 1 (broad participation, no cut)
_VIX_CALM_PCT = 0.50    # VIX percentile ≤ this → factor 1 (calm)
_VIX_STRESS_PCT = 0.90  # VIX percentile ≥ this → factor 0 (stress)


def _ramp_up(x: float, lo: float, hi: float) -> float:
    """0 at/below ``lo``, 1 at/above ``hi``, linear between (hi > lo)."""
    if hi <= lo:
        return 1.0 if x >= hi else 0.0
    return min(1.0, max(0.0, (x - lo) / (hi - lo)))


def _ramp_down(x: float, lo: float, hi: float) -> float:
    """1 at/below ``lo``, 0 at/above ``hi``, linear between (hi > lo)."""
    return 1.0 - _ramp_up(x, lo, hi)


def desired_gross(
    *,
    market_returns: Sequence[float],
    vol_target_annual: float,
    vol_ewma_span: int,
    gross_smooth_span: int | None = None,
    breadth: float | None = None,
    vix_percentile: float | None = None,
    breadth_floor: float = _BREADTH_FLOOR,
    breadth_full: float = _BREADTH_FULL,
    vix_calm_pct: float = _VIX_CALM_PCT,
    vix_stress_pct: float = _VIX_STRESS_PCT,
) -> float:
    """Target gross-exposure multiplier in ``[0, 1]`` for a vol-target overlay.

    ``min(1.0, vol_target_annual / realized_annual_vol)``, where
    ``realized_annual_vol = EWMA(span) std of the proxy's daily returns × √252``.
    The cap at 1.0 means the overlay never adds leverage; it only ever de-risks.

    Reuses the same EWMA-vol math as the backtest overlay
    (``backtest._vol_target_overlay`` / ``MomentumPortfolio._gross_scale``) so the
    live overlay and the backtest agree.

    **Exposure smoothing (P10 §4, optional).** When ``gross_smooth_span`` is set
    (> 1), the *per-day gross-target series* is EWMA-smoothed before the latest value
    is returned, so a single noisy vol spike doesn't whipsaw the book's gross. The
    smoothing is **stateless** — it is recomputed from ``market_returns`` each call, so
    it preserves ADR 0020's stateless / restart-safe property (no stored prior gross).
    ``None`` (the default) returns the raw latest gross, byte-identical to §2.

    **Regime signals (P10 §5, ADR 0022, optional).** ``breadth`` (fraction of the
    universe above its MA, ramps UP: healthy tape → no cut) and ``vix_percentile``
    (trailing VIX percentile, ramps DOWN: stress → cut) fold in as a multiplicative
    factor in ``[0, 1]`` — the WORST signal governs (``min``), and the factor only ever
    scales gross *down*. Each is optional: a ``None`` signal (overlay off, or fail-open
    from the source) simply doesn't contribute, so the default leaves the vol-target
    gross unchanged. (The ramp thresholds are backtest-tuned per ADR 0022 §7.)

    **Fails OPEN — returns 1.0 (no scaling)** when: the target is non-positive; there
    are fewer than two finite returns to estimate σ; or σ is non-finite / ≤ 0 (those
    days contribute 1.0 to the series). This matches the strategy's
    reviewed-and-praised fail-open-regime posture and ADR 0020's fail-open boundary —
    a data gap must never force a liquidation.

    **Deterministic and stateless:** identical ``market_returns`` + params → identical
    output (ADR 0020). Knows nothing about positions, deltas, or orders — it returns a
    scalar, never weights.
    """
    if vol_target_annual <= 0:
        return 1.0
    rets = [float(r) for r in market_returns if r is not None and math.isfinite(float(r))]
    if len(rets) < 2:
        return 1.0  # too little history to estimate σ → fail open

    sigma = pd.Series(rets, dtype=float).ewm(span=vol_ewma_span).std()
    realized_annual = (sigma * math.sqrt(_TRADING_DAYS)).where(lambda s: s > 0)  # ≤0/NaN → NaN
    # Per-day gross target, capped at 1.0; invalid-vol days fail open to 1.0. Dividing by
    # the NaN-masked vol avoids inf (no div-by-zero) before the fillna.
    gross = (vol_target_annual / realized_annual).clip(upper=1.0).fillna(1.0)
    if gross_smooth_span and gross_smooth_span > 1:
        gross = gross.ewm(span=int(gross_smooth_span)).mean()  # §4 temporal damping

    val = float(gross.iloc[-1])
    if not math.isfinite(val):
        return 1.0

    # P10 §5 (ADR 0022): fold in regime signals as a multiplicative factor in [0, 1].
    # Each is OPTIONAL — a None signal (off, or fail-open from the source) doesn't
    # contribute. The WORST signal governs (min), so any one stress signal de-risks;
    # the factor only ever scales gross DOWN (never adds, never leverages).
    regime = 1.0
    if breadth is not None and math.isfinite(breadth):
        regime = min(regime, _ramp_up(breadth, breadth_floor, breadth_full))
    if vix_percentile is not None and math.isfinite(vix_percentile):
        regime = min(regime, _ramp_down(vix_percentile, vix_calm_pct, vix_stress_pct))

    return min(1.0, max(0.0, val * regime))
