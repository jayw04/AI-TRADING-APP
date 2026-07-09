"""GAPPER-001 shadow ledger — forward-observation intraday outcomes (pre-registration v0.2 §8).

Applies the **locked primary design** to cached 1-min bars and logs, per candidate per day: whether it
triggered (30-min opening-range-high break by 11:00 ET, **above VWAP**, **market & sector positive**),
the trigger time, entry/exit, and gross same-day-close return in bps. Rolls up to the daily
equal-weight candidate book (≤5) with the pre-registered slippage grid + breakeven slippage.

**FORWARD OBSERVATION ONLY — Backtest Pending, not a verdict:** no bootstrap, no CI, no promotion. The
CI-gated replay runs only when the ≥40-date / ≥100-event sample gate clears (v0.2 §5). **Cost note:** the
entry-time bid/ask *spread* is not observable from OHLCV bars, so the half-spread entry model + the 25bps
spread gate (v0.2 §7) are deferred to a quote-data source; this ledger uses the pre-registered **slippage
grid** (5–100 bps/side) as the cost model and reports **breakeven slippage** — which is what tells a user
whether the pattern is *usable*, not just present.
"""
from __future__ import annotations

from datetime import time
from typing import Any

import pandas as pd

_ET = "America/New_York"
OR_END = time(10, 0)          # opening range = 09:30–10:00 ET
ENTRY_CUTOFF = time(11, 0)    # no new entries after 11:00 ET (v0.2 §3)
SLIPPAGE_GRID_BPS = (5, 10, 25, 50, 100)
MAX_POSITIONS = 5             # v0.2 §3


def _to_et(bars: pd.DataFrame | None) -> pd.DataFrame:
    """Add an ET-localised ``_et`` column and sort. Bars arrive RTH-only from Alpaca."""
    cols = ["t", "o", "h", "l", "c", "v", "_et"]
    if bars is None or len(bars) == 0:
        return pd.DataFrame(columns=cols)
    d = bars.copy()
    d["_et"] = pd.to_datetime(d["t"], utc=True).dt.tz_convert(_ET)
    return d.sort_values("_et").reset_index(drop=True)


def _vwap(d: pd.DataFrame) -> pd.Series:
    tp = (d["h"] + d["l"] + d["c"]) / 3.0
    cv = d["v"].cumsum()
    return (tp * d["v"]).cumsum() / cv.where(cv > 0)


def _price_at(d: pd.DataFrame, et_ts) -> float | None:
    """Close of the last bar at or before ``et_ts`` (None if none)."""
    if d.empty:
        return None
    sub = d[d["_et"] <= et_ts]
    return float(sub.iloc[-1]["c"]) if not sub.empty else None


def candidate_outcome(
    cand_bars: pd.DataFrame, spy_bars: pd.DataFrame, sector_bars: pd.DataFrame,
    *, spy_prev_close: float | None, sector_prev_close: float | None,
) -> dict[str, Any]:
    """Per-candidate primary-design outcome from 1-min bars → one ledger row."""
    c = _to_et(cand_bars)
    if c.empty:
        return {"triggered": False, "reason": "no_intraday"}
    or_bars = c[c["_et"].dt.time < OR_END]
    if or_bars.empty:
        return {"triggered": False, "reason": "no_opening_range"}
    or_high = float(or_bars["h"].max())
    c = c.assign(_vwap=_vwap(c))
    window = c[(c["_et"].dt.time >= OR_END) & (c["_et"].dt.time < ENTRY_CUTOFF)]
    brk = window[window["h"] > or_high]
    if brk.empty:
        return {"triggered": False, "reason": "no_or_break", "or_high": round(or_high, 4)}
    bar = brk.iloc[0]
    et = bar["_et"]
    vwap_ok = bool(pd.notna(bar["_vwap"]) and float(bar["c"]) > float(bar["_vwap"]))
    spy_at = _price_at(_to_et(spy_bars), et)
    sec_at = _price_at(_to_et(sector_bars), et)
    market_ok = bool(spy_at is not None and spy_prev_close and spy_at > spy_prev_close)
    sector_ok = bool(sec_at is not None and sector_prev_close and sec_at > sector_prev_close)
    triggered = vwap_ok and market_ok and sector_ok
    entry_px, exit_px = or_high, float(c.iloc[-1]["c"])
    gross_bps = (exit_px / entry_px - 1.0) * 1e4
    fails = [n for n, ok in (("below_vwap", vwap_ok), ("market_not_positive", market_ok),
                             ("sector_not_positive", sector_ok)) if not ok]
    return {"triggered": bool(triggered), "reason": None if triggered else "+".join(fails),
            "or_high": round(or_high, 4), "entry_time": et.isoformat(),
            "entry_px": round(entry_px, 4), "exit_px": round(exit_px, 4),
            "gross_bps": round(gross_bps, 1), "vwap_ok": vwap_ok,
            "market_ok": market_ok, "sector_ok": sector_ok}


def day_book(outcomes: list[dict], *, confidences: dict[str, float] | None = None) -> dict[str, Any]:
    """Daily equal-weight book of the triggered candidates (≤5, capped by Discovery Confidence): gross
    bps + the slippage grid (round-trip = 2×/side) + breakeven slippage. Idle day → 0."""
    trig = [o for o in outcomes if o.get("triggered")]
    if confidences and len(trig) > MAX_POSITIONS:
        trig = sorted(trig, key=lambda o: confidences.get(o.get("ticker", ""), 0.0), reverse=True)
    trig = trig[:MAX_POSITIONS]
    n = len(trig)
    gross = sum(o["gross_bps"] for o in trig) / n if n else 0.0
    grid = {f"{s}bps": round(gross - 2 * s, 1) for s in SLIPPAGE_GRID_BPS}
    return {"n_triggered": n, "book_gross_bps": round(gross, 1), "net_by_slippage_per_side": grid,
            "breakeven_slippage_per_side_bps": round(gross / 2, 1) if n else 0.0}
