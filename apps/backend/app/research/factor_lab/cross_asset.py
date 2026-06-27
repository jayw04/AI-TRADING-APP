"""Cross-asset time-series-momentum (TSMOM) sleeve — PORT-001 Sleeve B (§1; spec §3.2).

A long/flat trend sleeve over 8 asset-class ETFs, risk-parity weighted and portfolio
vol-targeted. Faithful port of the sibling `cross_asset_momentum.py` (research parity):

  1. **Trend:** 12-1 momentum (lookback 252d, skip 21d) per asset → **long if positive,
     else flat** (no shorting). The 252-day total return ending 21 days before as-of.
  2. **Sizing:** risk-parity (1/vol over 60d) across the in-trend assets.
  3. **Vol-target (de-risk only):** scale the whole sleeve so its annualized vol ≈ 10%,
     never levering up (gross ≤ 1). Goes to cash as fewer assets trend — the defensive
     mechanism.

Consumes **total-return** bars (the `total_return` adapter, §1) — distributions matter for
the bond/commodity legs. Pure/deterministic over a price panel; the Portfolio Construction
Engine (§2) blends this with the equity sleeve at ERC.
"""

from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd

# The validated 8 (spec §5.4 — expansion was researched and REJECTED; keep the 8).
CROSS_ASSET_UNIVERSE: tuple[str, ...] = (
    "SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "UUP",
)

_TRADING_DAYS = 252
_EPS_VOL = 1e-9  # an asset with ~zero 60d vol can't be risk-weighted (1/vol → ∞); drop it.


@dataclass(frozen=True)
class CrossAssetSleeve:
    """The sleeve's output for one as-of date."""

    weights: dict[str, float]              # per-asset sleeve weights (sum = gross; ≤ 1)
    gross: float                           # total invested fraction (1 − cash)
    cash: float                            # 1 − gross
    in_trend: list[str]                    # assets with positive 12-1 momentum
    momentum: dict[str, float]             # 12-1 momentum per asset
    port_vol_annual: float | None          # pre-scale annualized vol of the risk-parity book
    vol_scale: float                       # the de-risk-only vol-target multiplier (≤ 1)
    status: str = "ok"                     # "ok" | "insufficient_data"
    notes: list[str] = field(default_factory=list)


def cross_asset_tsmom(
    panel: pd.DataFrame,
    *,
    lookback: int = 252,
    skip: int = 21,
    vol_lookback: int = 60,
    vol_target: float = 0.10,
    asof: int | None = None,
) -> CrossAssetSleeve:
    """Compute the sleeve weights from a **total-return** price panel (index = dates ascending,
    columns = tickers, values = total-return close). ``asof`` is a row position (default last).
    Never raises — insufficiency is reported via ``status``."""
    if panel is None or panel.empty:
        return _insufficient("empty panel")
    px = panel.sort_index()
    pos = (len(px) - 1) if asof is None else asof
    need = skip + lookback  # need a price `skip+lookback` rows back for the 12-1 window
    if pos < need or pos < vol_lookback:
        return _insufficient(
            f"need ≥{max(need, vol_lookback) + 1} rows before as-of; have {pos + 1}"
        )

    cols = [c for c in px.columns]
    # --- 1. 12-1 momentum (252 ending 21d ago) + long/flat trend ---
    p_skip = px.iloc[pos - skip]
    p_base = px.iloc[pos - skip - lookback]
    momentum = {c: float(p_skip[c] / p_base[c] - 1.0) for c in cols
                if p_base[c] and np.isfinite(p_base[c]) and np.isfinite(p_skip[c])}

    # --- 2. risk-parity (1/vol over 60d) across in-trend, usable-vol assets ---
    rets = px[cols].pct_change().iloc[pos - vol_lookback + 1: pos + 1]
    vol = rets.std()  # daily sample std per asset
    in_trend = [
        c for c in cols
        if momentum.get(c, -1.0) > 0.0 and np.isfinite(vol.get(c, np.nan)) and vol[c] > _EPS_VOL
    ]
    if not in_trend:
        return CrossAssetSleeve(
            weights={c: 0.0 for c in cols}, gross=0.0, cash=1.0, in_trend=[],
            momentum=momentum, port_vol_annual=0.0, vol_scale=0.0,
            notes=["no asset in an uptrend → all cash (the defensive state)"],
        )
    inv_vol = np.array([1.0 / float(vol[c]) for c in in_trend])
    rp = inv_vol / inv_vol.sum()  # risk-parity weights, sum to 1 over in-trend

    # --- 3. portfolio vol-target (de-risk only) ---
    cov = rets[in_trend].cov().to_numpy()  # daily covariance
    port_vol_daily = float(np.sqrt(max(rp @ cov @ rp, 0.0)))
    port_vol_annual = port_vol_daily * np.sqrt(_TRADING_DAYS)
    vol_scale = min(1.0, vol_target / port_vol_annual) if port_vol_annual > 0 else 1.0

    weights = {c: 0.0 for c in cols}
    for c, w in zip(in_trend, rp, strict=True):
        weights[c] = float(vol_scale * w)
    gross = float(sum(weights.values()))
    return CrossAssetSleeve(
        weights=weights, gross=gross, cash=1.0 - gross, in_trend=in_trend,
        momentum=momentum, port_vol_annual=port_vol_annual, vol_scale=float(vol_scale),
    )


def _insufficient(reason: str) -> CrossAssetSleeve:
    return CrossAssetSleeve(
        weights={}, gross=0.0, cash=1.0, in_trend=[], momentum={},
        port_vol_annual=None, vol_scale=0.0, status="insufficient_data", notes=[reason],
    )
