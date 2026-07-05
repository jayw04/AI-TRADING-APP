"""TV-001-SUPERTREND validation study (pre-registered — see
docs/implementation/TradingWorkbench_TV001_Supertrend_Validation_v0.1.md).

Runs the pass the TV-001 import test prescribed for its only surviving candidate: does the Supertrend
(KivancOzbilgic, ATR 10 / mult 3.0, 15m, stop-and-reverse) timing edge **generalize** beyond the
fit-selected MSFT/PLTR, net of realistic cost, across a broad symbol set / walk-forward windows /
timeframes — or was it symbol/window cherry-picking? Benchmark = buy-and-hold the same symbol.

Offline research: no live book, no order path. Data (intraday RTH bars) fetched from Alpaca on the box
in time-chunks (avoids the 10k-page intraday truncation). Pure signal/backtest functions are unit-tested
offline; only the fetch + grid run needs the box.

    cd apps/backend
    python scripts/tv001_supertrend_validation.py --report-dir research/tv001_supertrend/
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

import numpy as np
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# --- study configuration (pre-registered) ----------------------------------
UNIVERSE = ["MSFT", "PLTR", "AMD", "NVDA", "AAPL", "TSLA", "AMZN", "META", "GOOGL",
            "JPM", "XOM", "WMT", "JNJ", "SPY", "QQQ"]
FIT_WINNERS = {"MSFT", "PLTR"}          # the symbols the import test selected — watch these vs the rest
ATR_PERIOD, ATR_MULT = 10, 3.0
# Parameter-stability grid (review #2): a validated edge must not collapse on nearby params; a robust
# REJECTION is confirmed when no neighbour setting rescues it either (not a single-point artifact).
PARAM_GRID = [(8, 2.5), (8, 3.0), (8, 3.5), (10, 2.5), (10, 3.0), (10, 3.5), (12, 2.5), (12, 3.0), (12, 3.5)]
COST_SWEEP_BPS = [0, 5, 10, 20]          # per-side, charged on turnover
DEFAULT_COST_BPS = 10                    # the pass/fail call is made here
BARS_PER_YEAR = {"5Min": 19656, "15Min": 6552, "30Min": 3276, "1Hour": 1638}  # ~RTH bars/yr
GENERALIZATION_BAR = 0.60                # H1: beat buy-hold on >= 60% of the universe
BOOTSTRAP_SEED = 17


# --- pure signal + backtest (offline-testable) ------------------------------

def _wilder_atr(high: np.ndarray, low: np.ndarray, close: np.ndarray, period: int) -> np.ndarray:
    """Wilder ATR (ta.atr): RMA of True Range."""
    n = len(close)
    tr = np.empty(n)
    tr[0] = high[0] - low[0]
    for i in range(1, n):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1]))
    # RMA / Wilder smoothing == ewm(alpha=1/period, adjust=False)
    return pd.Series(tr).ewm(alpha=1.0 / period, adjust=False).mean().to_numpy()


def supertrend_trend(high: np.ndarray, low: np.ndarray, close: np.ndarray,
                     period: int = ATR_PERIOD, mult: float = ATR_MULT) -> np.ndarray:
    """Faithful recon of the Pine Supertrend: hl2 source, Wilder ATR, trailing bands, trend ∈ {+1,-1}.
    Matches `supertrend_kivanc_recon.pine` (trend flips use the PREVIOUS adjusted band and current close)."""
    n = len(close)
    hl2 = (high + low) / 2.0
    atr = _wilder_atr(high, low, close, period)
    up_raw = hl2 - mult * atr
    dn_raw = hl2 + mult * atr
    up = up_raw.copy()
    dn = dn_raw.copy()
    trend = np.ones(n, dtype=int)
    for i in range(1, n):
        up1 = up[i - 1]
        up[i] = max(up_raw[i], up1) if close[i - 1] > up1 else up_raw[i]
        dn1 = dn[i - 1]
        dn[i] = min(dn_raw[i], dn1) if close[i - 1] < dn1 else dn_raw[i]
        prev = trend[i - 1]
        if prev == -1 and close[i] > dn1:
            trend[i] = 1
        elif prev == 1 and close[i] < up1:
            trend[i] = -1
        else:
            trend[i] = prev
    return trend


@dataclass
class BtResult:
    strat_ret: float          # total return of the strategy (net cost)
    strat_sharpe: float
    strat_maxdd: float
    bh_ret: float             # buy-and-hold total return
    bh_sharpe: float
    d_ret: float              # strat - buy-hold (net)
    beats_bh: bool
    n_trades: int
    trades_per_year: float    # turnover (review #3)
    avg_hold_bars: float      # mean bars held per trade
    trade_rets: list          # per-trade net returns (for bootstrap)


def backtest(close: np.ndarray, trend: np.ndarray, *, cost_bps: float, allow_short: bool,
             ann_factor: float) -> BtResult:
    """Bar-to-bar backtest of the Supertrend positions. Position at bar i-1 earns bar i's return; a
    position change costs ``cost_bps`` per unit turnover (per-side). Overnight gaps included when held.

    long/flat: pos = 1 in uptrend, 0 in downtrend. long/short: pos = ±1. No look-ahead (pos lagged)."""
    n = len(close)
    ret = np.zeros(n)
    ret[1:] = close[1:] / close[:-1] - 1.0
    pos = np.where(trend == 1, 1.0, (-1.0 if allow_short else 0.0))
    held = np.zeros(n)
    held[1:] = pos[:-1]                        # act on the prior bar's signal (no look-ahead)
    turn = np.abs(np.diff(np.concatenate([[0.0], held])))
    cost = turn * (cost_bps / 1e4)
    strat = held * ret - cost
    bh = ret.copy()                           # buy-and-hold (always long), no timing cost

    strat_curve = np.cumprod(1.0 + strat)
    bh_curve = np.cumprod(1.0 + bh)

    def _sharpe(r):
        s = r.std()
        return float(r.mean() / s * np.sqrt(ann_factor)) if s > 0 else 0.0

    def _mdd(curve):
        peak = np.maximum.accumulate(curve)
        return float((curve / peak - 1.0).min())

    # per-trade net returns + holding lengths: segments where held is constant and nonzero
    trade_rets: list[float] = []
    hold_lens: list[int] = []
    i = 1
    while i < n:
        if held[i] != 0 and (i == 1 or held[i] != held[i - 1]):
            j = i
            while j < n and held[j] == held[i]:
                j += 1
            trade_rets.append(float(np.prod(1.0 + strat[i:j]) - 1.0))
            hold_lens.append(j - i)
            i = j
        else:
            i += 1

    strat_ret = float(strat_curve[-1] - 1.0)
    bh_ret = float(bh_curve[-1] - 1.0)
    years = max(n / ann_factor, 1e-9)
    return BtResult(
        strat_ret=round(strat_ret, 4), strat_sharpe=round(_sharpe(strat), 3),
        strat_maxdd=round(_mdd(strat_curve), 4), bh_ret=round(bh_ret, 4),
        bh_sharpe=round(_sharpe(bh), 3), d_ret=round(strat_ret - bh_ret, 4),
        beats_bh=strat_ret > bh_ret, n_trades=len(trade_rets),
        trades_per_year=round(len(trade_rets) / years, 1),
        avg_hold_bars=round(float(np.mean(hold_lens)) if hold_lens else 0.0, 1),
        trade_rets=[round(t, 5) for t in trade_rets])


def bootstrap_mean_ci(xs: list[float], *, seed: int = BOOTSTRAP_SEED, n_resamples: int = 2000
                      ) -> tuple[float, float, float]:
    """Percentile bootstrap CI of the mean of ``xs`` (per-trade net returns). (delta, lo, hi)."""
    import random
    if len(xs) < 5:
        return (round(float(np.mean(xs)), 5) if xs else 0.0, float("nan"), float("nan"))
    rng = random.Random(seed)
    arr = list(xs)
    means = sorted(float(np.mean([arr[rng.randrange(len(arr))] for _ in arr])) for _ in range(n_resamples))
    return (round(float(np.mean(arr)), 5), round(means[int(0.025 * n_resamples)], 5),
            round(means[min(int(0.975 * n_resamples), n_resamples - 1)], 5))


def classify(frac_beat: float, agg_ci: tuple[float, float, float], robust: bool) -> str:
    """Pre-registered verdict mapping (design doc §Acceptance)."""
    _, lo, hi = agg_ci
    ci_pos = lo == lo and lo > 0          # excludes zero, positive
    if frac_beat >= GENERALIZATION_BAR and robust and ci_pos:
        return "Approved"
    if frac_beat >= 0.5 and ci_pos:
        return "Diversifier / Candidate-Promising"
    return "Rejected (Evidenced)"


# --- data + driver (box) ----------------------------------------------------

def _fetch_intraday(symbol: str, timeframe: str, start: datetime, end: datetime) -> pd.DataFrame:
    """RTH intraday bars from Alpaca IEX, fetched in yearly chunks (avoids the 10k-page truncation)."""
    from alpaca.data.enums import DataFeed
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame, TimeFrameUnit

    from app.market_data.bar_cache import load_credentials
    from app.utils.tls_trust import enable_os_trust_store

    tf = {"5Min": TimeFrame(5, TimeFrameUnit.Minute), "15Min": TimeFrame(15, TimeFrameUnit.Minute),
          "30Min": TimeFrame(30, TimeFrameUnit.Minute), "1Hour": TimeFrame(1, TimeFrameUnit.Hour)}[timeframe]
    enable_os_trust_store()
    creds = load_credentials()
    client = StockHistoricalDataClient(api_key=creds.api_key, secret_key=creds.api_secret)
    frames = []
    cur = start
    while cur < end:
        chunk_end = min(datetime(cur.year + 1, 1, 1, tzinfo=UTC), end)
        req = StockBarsRequest(symbol_or_symbols=symbol, timeframe=tf, start=cur, end=chunk_end,
                               feed=DataFeed.IEX, limit=None)
        data = client.get_stock_bars(req).data.get(symbol, [])
        if data:
            frames.append(pd.DataFrame([{"t": b.timestamp, "o": b.open, "h": b.high, "l": b.low,
                                         "c": b.close} for b in data]))
        cur = chunk_end
    if not frames:
        return pd.DataFrame()
    df = pd.concat(frames, ignore_index=True)
    ts = pd.to_datetime(df["t"], utc=True).dt.tz_convert("America/New_York")
    rth = (ts.dt.time >= pd.Timestamp("09:30").time()) & (ts.dt.time < pd.Timestamp("16:00").time())
    df = df[rth].reset_index(drop=True)
    df["ny"] = ts[rth].reset_index(drop=True)
    return df


def _windows(index: pd.Series, months: int = 6) -> list[tuple[int, int]]:
    """Contiguous ~`months`-block [start,end) index ranges for walk-forward."""
    if len(index) == 0:
        return []
    out = []
    t0 = index.iloc[0]
    start_i = 0
    for i, t in enumerate(index):
        if (t - t0).days >= months * 30:
            out.append((start_i, i))
            start_i, t0 = i, t
    if len(index) - start_i > 20:
        out.append((start_i, len(index)))
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="TV-001-SUPERTREND validation.")
    ap.add_argument("--start", default="2023-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--timeframes", default="15Min", help="comma list, e.g. 15Min,5Min,30Min,1Hour")
    ap.add_argument("--symbols", default=",".join(UNIVERSE))
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    start = datetime.fromisoformat(args.start).replace(tzinfo=UTC)
    end = datetime.fromisoformat(args.end).replace(tzinfo=UTC)
    symbols = [s.strip().upper() for s in args.symbols.split(",") if s.strip()]
    timeframes = [t.strip() for t in args.timeframes.split(",") if t.strip()]

    results: dict = {"config": {"atr_period": ATR_PERIOD, "atr_mult": ATR_MULT,
                                "cost_bps_call": DEFAULT_COST_BPS, "start": args.start, "end": args.end},
                     "by_timeframe": {}}
    for tf in timeframes:
        ann = BARS_PER_YEAR[tf]
        per_symbol = {}
        print(f"\n=== timeframe {tf} ===", flush=True)
        for sym in symbols:
            df = _fetch_intraday(sym, tf, start, end)
            if len(df) < ann // 4:
                print(f"  {sym}: insufficient bars ({len(df)})")
                continue
            close = df["c"].to_numpy(dtype=float)
            trend = supertrend_trend(df["h"].to_numpy(float), df["l"].to_numpy(float), close)
            # walk-forward windows + full-sample, long/flat @ default cost
            wf = _windows(df["ny"])
            wf_dret = []
            for a, b in wf:
                if b - a < 20:
                    continue
                r = backtest(close[a:b], trend[a:b], cost_bps=DEFAULT_COST_BPS, allow_short=False, ann_factor=ann)
                wf_dret.append(r.d_ret)
            full = backtest(close, trend, cost_bps=DEFAULT_COST_BPS, allow_short=False, ann_factor=ann)
            cost_curve = {c: backtest(close, trend, cost_bps=c, allow_short=False, ann_factor=ann).d_ret
                          for c in COST_SWEEP_BPS}
            short = backtest(close, trend, cost_bps=DEFAULT_COST_BPS, allow_short=True, ann_factor=ann)
            hi, lo_ = df["h"].to_numpy(float), df["l"].to_numpy(float)
            param_beat = {
                f"atr{p}_m{m}": backtest(close, supertrend_trend(hi, lo_, close, p, m),
                                         cost_bps=DEFAULT_COST_BPS, allow_short=False, ann_factor=ann).beats_bh
                for p, m in PARAM_GRID}
            per_symbol[sym] = {"full_longflat": asdict(full), "wf_dret": wf_dret,
                               "cost_sweep_dret": cost_curve, "longshort_dret": short.d_ret,
                               "param_beat": param_beat, "trades_per_year": full.trades_per_year,
                               "avg_hold_bars": full.avg_hold_bars,
                               "n_bars": len(df), "is_fit_winner": sym in FIT_WINNERS}
            print(f"  {sym:5} bars={len(df):6} dRet(vs B&H)={full.d_ret:+.3f} "
                  f"beats={full.beats_bh} trades/yr={full.trades_per_year} hold={full.avg_hold_bars}bars "
                  f"wf_beat={sum(1 for d in wf_dret if d > 0)}/{len(wf_dret)}"
                  + ("  <fit-winner>" if sym in FIT_WINNERS else ""))
        results["by_timeframe"][tf] = per_symbol

    # verdict on the primary timeframe (first listed), long/flat @ default cost
    primary = timeframes[0]
    ps = results["by_timeframe"].get(primary, {})
    beats = [s for s, v in ps.items() if v["full_longflat"]["beats_bh"]]
    frac_beat = len(beats) / len(ps) if ps else 0.0
    all_trades = [t for v in ps.values() for t in v["full_longflat"]["trade_rets"]]
    agg_ci = bootstrap_mean_ci(all_trades)
    # robust = >=50% of walk-forward windows positive across the universe (no sign-flip dominance)
    wf_all = [d for v in ps.values() for d in v["wf_dret"]]
    robust = (sum(1 for d in wf_all if d > 0) / len(wf_all) >= 0.5) if wf_all else False
    verdict = classify(frac_beat, agg_ci, robust)
    winners_vs_rest = {"fit_winners_beat": [s for s in beats if s in FIT_WINNERS],
                       "other_beat": [s for s in beats if s not in FIT_WINNERS]}
    # parameter stability (review #2): frac of universe beating B&H at each ATR×mult; the BEST setting
    # tells us whether ANY neighbour rescues the edge (robust rejection if none clears the bar).
    param_frac = {f"atr{p}_m{m}": round(sum(1 for v in ps.values()
                  if v["param_beat"].get(f"atr{p}_m{m}")) / len(ps), 3) for p, m in PARAM_GRID} if ps else {}
    best_param_frac = max(param_frac.values()) if param_frac else 0.0
    tpy = [v["trades_per_year"] for v in ps.values()]
    turnover = {"median_trades_per_year": round(float(np.median(tpy)), 1) if tpy else 0.0,
                "median_hold_bars": round(float(np.median([v["avg_hold_bars"] for v in ps.values()])), 1)
                if ps else 0.0}
    results["verdict"] = {"primary_tf": primary, "frac_beat_bh": round(frac_beat, 3),
                          "beats": beats, "agg_trade_mean_ci": agg_ci, "robust_wf": robust,
                          "verdict": verdict, "winners_vs_rest": winners_vs_rest,
                          "generalization_bar": GENERALIZATION_BAR,
                          "param_stability_frac_beat": param_frac, "best_param_frac_beat": best_param_frac,
                          "turnover": turnover}

    print(f"\n=== VERDICT ({primary}, long/flat, {DEFAULT_COST_BPS}bps, net of cost) ===")
    print(f"  beats buy-and-hold: {len(beats)}/{len(ps)} = {frac_beat:.0%} (bar {GENERALIZATION_BAR:.0%})")
    print(f"  fit-winners that beat: {winners_vs_rest['fit_winners_beat']}; others: {winners_vs_rest['other_beat']}")
    print(f"  aggregate per-trade mean net return + CI: {agg_ci}")
    print(f"  walk-forward robust: {robust}")
    print(f"  param-stability: BEST setting beats B&H on {best_param_frac:.0%} of the universe "
          f"(bar {GENERALIZATION_BAR:.0%}) — no neighbour rescues it" if best_param_frac < GENERALIZATION_BAR
          else f"  param-stability: best setting reaches {best_param_frac:.0%}")
    print(f"  turnover: median {turnover['median_trades_per_year']} trades/yr, "
          f"median hold {turnover['median_hold_bars']} bars")
    print(f"\n  >>> {verdict}")

    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "tv001_supertrend_results.json").write_text(json.dumps(results, indent=2, default=str))
        print(f"\n  wrote {d / 'tv001_supertrend_results.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
