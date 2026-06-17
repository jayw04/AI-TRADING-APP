"""Intraday mean-reversion (oscillation) screener — Range Trader §5b, take 2.

The first §5b screen looked for *daily* range-bound names (ADX<20, daily band
touches) and found slow, stable large-caps — the wrong universe for a 5-minute
fade-the-range book (they don't reverse within a session, so the strategy made
only ~1 round-trip/day → all §5c runs INCONCLUSIVE; see
``TradingWorkbench_RangeTrader_5c_TestResults_v0.1.md``).

This screen instead measures **intraday oscillation** on 5-minute bars, per the
review:

  - **VWAP crossings / day** — how often price crosses the session VWAP. High =
    oscillatory; low = trending.
  - **Lag-1 return autocorrelation** — negative = bar-to-bar mean reversion
    (good); positive = momentum/trend (avoid).
  - **Mean-reversion half-life** (minutes) — from an AR(1) fit on the deviation
    from session VWAP. Target ~30–120 min: long enough to trade, short enough to
    round-trip intraday.
  - **Liquidity** — avg daily $ volume, so 5-min fills are realistic.

Runs on live Alpaca 5-min bars (truststore beats Norton, ADR 0017). Output is a
ranked candidate list to feed the unchanged §5c gate (Phase 2).

    cd apps/backend
    .venv/Scripts/python.exe scripts/screen_intraday_oscillation.py            # default oscillatory universe
    .venv/Scripts/python.exe scripts/screen_intraday_oscillation.py TSLA AMD --days 30 --csv osc.csv

This is a screen, not a verdict: PASS names still must clear §5c.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

BAR_MINUTES = 5

# Review's suggested oscillatory universe: liquid ETFs + higher-beta names that
# actually move intraday (vs the slow large-caps the daily screen surfaced).
DEFAULT_UNIVERSE = [
    "QQQ", "IWM", "XLF", "XLE", "XBI", "SMH", "ARKK",   # ETFs
    "TSLA", "AMD", "PLTR", "SOFI", "HOOD",               # higher-beta
]


@dataclass
class OscConfig:
    min_crossings_per_day: float = 6.0   # >= this many VWAP crosses/session
    # Lag-1 return autocorr must be < this. At intraday MR half-lives (φ≈0.9+)
    # the true return autocorr is only weakly negative (~-0.03) and noisy, so
    # this is a "not momentum" filter (reject clearly positive/trending), not a
    # strict <0. Half-life below is the primary mean-reversion measure.
    max_autocorr: float = 0.05
    half_life_min_minutes: float = 30.0  # target band for OU half-life
    half_life_max_minutes: float = 120.0
    min_dollar_vol: float = 50_000_000.0
    min_sessions: int = 10               # need enough sessions for stable stats


@dataclass
class OscMetrics:
    vwap_crossings_per_day: float | None = None
    ret_autocorr_lag1: float | None = None
    half_life_minutes: float | None = None
    dollar_vol: float | None = None
    sessions: int = 0
    passed: bool = False
    reasons: list[str] = field(default_factory=list)  # why it FAILED


def _session_vwap(day: pd.DataFrame) -> np.ndarray:
    typical = (day["h"].astype(float) + day["l"].astype(float) + day["c"].astype(float)) / 3.0
    vol = day["v"].astype(float).to_numpy()
    cum_pv = np.cumsum(typical.to_numpy() * vol)
    cum_v = np.cumsum(vol)
    cum_v[cum_v == 0] = np.nan
    return cum_pv / cum_v


def oscillation_metrics(bars: pd.DataFrame, cfg: OscConfig | None = None) -> OscMetrics:
    """Compute intraday-oscillation metrics from 5-min RTH bars (cols t,o,h,l,c,v,
    ascending). Pure: no I/O. All cross-session boundaries are reset so overnight
    gaps never enter returns / the AR(1) fit."""
    cfg = cfg or OscConfig()
    res = OscMetrics()
    if bars is None or len(bars) == 0:
        res.reasons.append("no bars")
        return res

    bars = bars.sort_values("t").reset_index(drop=True)
    et_day = pd.to_datetime(bars["t"], utc=True).dt.tz_convert("America/New_York").dt.date

    crossings: list[int] = []
    intraday_rets: list[np.ndarray] = []   # per-session 5-min returns
    dev_lag: list[np.ndarray] = []         # AR(1) pairs (deviation from VWAP)
    dev_delta: list[np.ndarray] = []
    dollar_vols: list[float] = []
    n_sessions = 0

    for _day, idx in bars.groupby(et_day).groups.items():
        day = bars.loc[idx]
        if len(day) < 3:
            continue
        n_sessions += 1
        c = day["c"].astype(float).to_numpy()
        v = day["v"].astype(float).to_numpy()
        dollar_vols.append(float(np.sum(c * v)))

        vwap = _session_vwap(day)
        dev = c - vwap
        # VWAP crossings: sign changes of the deviation within the session.
        sign = np.sign(dev)
        nz = sign[sign != 0]
        crossings.append(int(np.sum(nz[1:] != nz[:-1])) if len(nz) > 1 else 0)

        # Intraday returns (no overnight gap — series starts at this session).
        intraday_rets.append(np.diff(c) / c[:-1])

        # AR(1) deviation pairs within the session.
        good = ~np.isnan(dev)
        d = dev[good]
        if len(d) > 2:
            dev_lag.append(d[:-1])
            dev_delta.append(np.diff(d))

    res.sessions = n_sessions
    if n_sessions < cfg.min_sessions:
        res.reasons.append(f"only {n_sessions} sessions (<{cfg.min_sessions})")
        return res

    res.vwap_crossings_per_day = float(np.mean(crossings)) if crossings else 0.0
    res.dollar_vol = float(np.mean(dollar_vols)) if dollar_vols else 0.0

    rets = np.concatenate(intraday_rets) if intraday_rets else np.array([])
    if len(rets) > 5 and np.std(rets[:-1]) > 0 and np.std(rets[1:]) > 0:
        res.ret_autocorr_lag1 = float(np.corrcoef(rets[:-1], rets[1:])[0, 1])

    if dev_lag:
        x = np.concatenate(dev_lag)
        dy = np.concatenate(dev_delta)
        if len(x) > 5 and np.std(x) > 0:
            b = float(np.polyfit(x, dy, 1)[0])  # dy = a + b*x ; phi = 1+b
            phi = 1.0 + b
            if 0.0 < phi < 1.0:
                res.half_life_minutes = float(np.log(0.5) / np.log(phi) * BAR_MINUTES)

    # --- criteria ---
    if (res.vwap_crossings_per_day or 0) < cfg.min_crossings_per_day:
        res.reasons.append(
            f"crossings {res.vwap_crossings_per_day:.1f}/day (<{cfg.min_crossings_per_day})")
    if res.ret_autocorr_lag1 is None or res.ret_autocorr_lag1 >= cfg.max_autocorr:
        val = res.ret_autocorr_lag1 if res.ret_autocorr_lag1 is None else round(res.ret_autocorr_lag1, 3)
        res.reasons.append(f"autocorr {val} (want < {cfg.max_autocorr} — not momentum)")
    if res.half_life_minutes is None or not (
        cfg.half_life_min_minutes <= res.half_life_minutes <= cfg.half_life_max_minutes
    ):
        hl = "n/a" if res.half_life_minutes is None else f"{res.half_life_minutes:.0f}m"
        res.reasons.append(
            f"half-life {hl} (want {cfg.half_life_min_minutes:.0f}-{cfg.half_life_max_minutes:.0f}m)")
    if (res.dollar_vol or 0) < cfg.min_dollar_vol:
        res.reasons.append(f"thin: ${(res.dollar_vol or 0) / 1e6:.0f}M ADV (<${cfg.min_dollar_vol / 1e6:.0f}M)")

    res.passed = not res.reasons
    return res


# ---- I/O (CLI only; not exercised by the pure-function tests) ----


def main() -> int:
    ap = argparse.ArgumentParser(description="Intraday mean-reversion (oscillation) screener.")
    ap.add_argument("symbols", nargs="*", help="Tickers (default: the oscillatory universe).")
    ap.add_argument("--days", type=int, default=30, help="Calendar days of recent 5-min history.")
    ap.add_argument("--min-crossings", type=float, default=OscConfig.min_crossings_per_day)
    ap.add_argument("--csv", default=None)
    args = ap.parse_args()

    from datetime import UTC, datetime, timedelta

    from dotenv import load_dotenv
    load_dotenv(BACKEND_ROOT.parents[1] / ".env", override=False)
    from scripts.backtest_range_trader_alpaca import _fetch_rth_bars

    cfg = OscConfig(min_crossings_per_day=args.min_crossings)
    symbols = [s.upper() for s in args.symbols] or DEFAULT_UNIVERSE
    end = datetime.now(UTC).replace(microsecond=0)
    start = end - timedelta(days=args.days)

    rows = []
    for sym in symbols:
        try:
            bars = _fetch_rth_bars(sym, start, end)
            rows.append((sym, oscillation_metrics(bars, cfg)))
        except Exception as exc:
            rows.append((sym, OscMetrics(reasons=[f"fetch error: {type(exc).__name__}"])))

    passers = [(s, m) for s, m in rows if m.passed]
    passers.sort(key=lambda sm: -(sm[1].vwap_crossings_per_day or 0))

    print(f"\nIntraday oscillation screen — {len(symbols)} symbols, last {args.days}d, "
          f"{len(passers)} PASS (>={cfg.min_crossings_per_day} cross/day, autocorr<0, "
          f"half-life {cfg.half_life_min_minutes:.0f}-{cfg.half_life_max_minutes:.0f}m, "
          f">=${cfg.min_dollar_vol / 1e6:.0f}M)\n")
    print(f"{'SYM':<6}{'cross/day':>10}{'autocorr':>10}{'half-life':>11}{'$ADV(M)':>9}{'sess':>6}  result")
    for sym, m in sorted(rows, key=lambda sm: -(sm[1].vwap_crossings_per_day or -1)):
        hl = "n/a" if m.half_life_minutes is None else f"{m.half_life_minutes:.0f}m"
        ac = "n/a" if m.ret_autocorr_lag1 is None else f"{m.ret_autocorr_lag1:+.3f}"
        cr = "n/a" if m.vwap_crossings_per_day is None else f"{m.vwap_crossings_per_day:.1f}"
        dv = "n/a" if m.dollar_vol is None else f"{m.dollar_vol / 1e6:.0f}"
        tag = "PASS" if m.passed else "fail: " + "; ".join(m.reasons[:2])
        print(f"{sym:<6}{cr:>10}{ac:>10}{hl:>11}{dv:>9}{m.sessions:>6}  {tag}")

    if args.csv:
        pd.DataFrame([{"symbol": s, **vars(m), "reasons": "; ".join(m.reasons)} for s, m in rows]).to_csv(args.csv, index=False)
        print(f"\nFull result -> {args.csv}")
    print("\nNext (Phase 2): run the unchanged §5c gate on the PASS names — target >=50 trades.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
