"""Momentum-Daily — STAGE 4 BACKTEST: regime filter (proposal v1.1 §7, §9).

Holds the Stage-3 winner fixed (N5 / hybrid 50-50 inverse-vol / no sector cap / §5.1 daily conditional)
and compares four regime-filter variants (A binary / B buffered / C graduated / D none-control). See
PREREG_Stage4_Regime_v1.0.md (FROZEN before this runs).

SPY is absent from the SEP store, so the regime gauge is a broad equal-weight market-proxy index built
from the same PIT spine (see PREREG §2 — a disclosed substitution; Stage 4 decides the *variant*).

    WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data_full.duckdb \\
        .venv/Scripts/python.exe scripts/backtest_momentum_stage4.py \\
            --start 2005-01-01 --end 2026-06-13 --report-dir docs/implementation/evidence/momentum_daily_stage2_4
"""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import statistics
import sys
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

import duckdb
import pandas as pd

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(BACKEND_ROOT), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_momentum_stage2 import (  # noqa: E402
    BACKSTOP_DAYS,
    CRASH_WINDOWS,
    INITIAL_EQUITY,
    TURNOVER_COST_BPS,
    WEIGHT_DRIFT_PCT,
    DayScores,
    compute_day,
)
from backtest_momentum_stage3 import select_n, weigh  # noqa: E402

from app.factor_data.backtest import _CachedPriceStore, _summary  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import universe_asof  # noqa: E402

CASH = "$CASH"
N = 5
SIZING = "hybrid_50_50"
CAP_ON = False
MA_DAYS = 200
# variant params (frozen, PREREG §3)
B_BUFFER = 0.01
B_CONFIRM = 2
C_BAND = 0.02
C_GROSS = {"above": 0.98, "mid": 0.60, "below": 0.15}


# ---- market-proxy regime gauge --------------------------------------------------
def build_market_proxy(store: FactorDataStore, trading_days: list[date], db_path: str) -> pd.DataFrame:
    """Broad equal-weight market-proxy index + 200d MA (disclosed SPY substitution, PREREG §2)."""
    # month-end sample of the top-500 PIT liquid universe -> union basket
    month_ends: list[date] = []
    for i, d in enumerate(trading_days):
        nxt = trading_days[i + 1] if i + 1 < len(trading_days) else None
        if nxt is None or (nxt.year, nxt.month) != (d.year, d.month):
            month_ends.append(d)
    basket: set[str] = set()
    for d in month_ends:
        with contextlib.suppress(Exception):
            basket |= set(universe_asof(store, d, n=500))
    tickers = sorted(basket)
    con = duckdb.connect(db_path, read_only=True)
    ph = ",".join("?" * len(tickers))
    rows = con.execute(
        f"select date, ticker, closeadj from sep where ticker in ({ph}) and closeadj is not null",
        tickers,
    ).fetchall()
    con.close()
    df = pd.DataFrame(rows, columns=["date", "ticker", "close"])
    df["date"] = pd.to_datetime(df["date"])
    panel = df.pivot_table(index="date", columns="ticker", values="close")
    panel = panel.reindex(pd.to_datetime(pd.Index(trading_days))).sort_index()
    rets = panel.pct_change()
    mkt = rets.mean(axis=1, skipna=True).fillna(0.0)
    idx = (1.0 + mkt).cumprod()
    ma = idx.rolling(MA_DAYS, min_periods=MA_DAYS).mean()
    out = pd.DataFrame({"idx": idx, "ma": ma})
    out.index = [d.date() for d in out.index]
    return out


def gross_series(proxy: pd.DataFrame, variant: str) -> dict[date, float]:
    """Per-day gross exposure for a regime variant. Warm-up (no MA yet) = 1.0 (fail open)."""
    g: dict[date, float] = {}
    prev_state = 1.0  # for buffered hold-prior
    below_run = above_run = 0
    for d, row in proxy.iterrows():
        lvl, ma = row["idx"], row["ma"]
        if pd.isna(ma) or pd.isna(lvl) or ma <= 0:
            g[d] = 1.0
            continue
        rel = lvl / ma - 1.0
        if variant == "D":
            g[d] = 1.0
        elif variant == "A":
            g[d] = 1.0 if rel >= 0 else 0.0
        elif variant == "B":
            below_run = below_run + 1 if rel <= -B_BUFFER else 0
            above_run = above_run + 1 if rel >= B_BUFFER else 0
            if below_run >= B_CONFIRM:
                prev_state = 0.0
            elif above_run >= B_CONFIRM:
                prev_state = 1.0
            g[d] = prev_state
        elif variant == "C":
            g[d] = (C_GROSS["above"] if rel > C_BAND
                    else C_GROSS["below"] if rel < -C_BAND else C_GROSS["mid"])
        else:
            g[d] = 1.0
    return g


@dataclass
class VariantResult:
    variant: str
    label: str = ""
    cagr: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    annualized_turnover: float = 0.0
    avg_holding_days: float = 0.0
    worst_single_name_gap: float = 0.0
    trades: int = 0
    pct_days_risk_off: float = 0.0
    final_equity: float = 0.0
    crash_windows: dict[str, float] = field(default_factory=dict)


def simulate(store: FactorDataStore, trading_days: list[date], day_scores: dict[date, DayScores],
             sectors: dict[str, str | None], gross: dict[date, float], variant: str,
             label: str) -> VariantResult:
    ws, we = trading_days[0], trading_days[-1]
    pxcache: dict[str, dict[date, float]] = {}

    def pxmap(t: str) -> dict[date, float]:
        if t not in pxcache:
            df = store.get_prices(t, ws, we, adjusted=True)
            pxcache[t] = {dt.date(): float(c) for dt, c in zip(df["date"], df["close"], strict=False)
                          if c is not None and float(c) > 0}
        return pxcache[t]

    equity = INITIAL_EQUITY
    sleeves: dict[str, float] = {}          # invested name sleeves
    cash = 0.0
    target_w: dict[str, float] = {}
    last_px: dict[str, float] = {}
    held: set[str] = set()
    entry_date: dict[str, date] = {}
    curve: list[tuple[date, float]] = []
    holding_periods: list[int] = []
    total_turnover = 0.0
    worst_gap = 0.0
    trades = 0
    since = 0
    risk_off_days = 0
    prev_rank: dict[str, int] | None = None
    applied_gross = 1.0

    for d in trading_days:
        if held:
            for tk in held:
                p = pxmap(tk).get(d)
                if p is not None:
                    lp = last_px.get(tk, 0.0)
                    if lp > 0:
                        r = p / lp - 1.0
                        sleeves[tk] *= 1.0 + r
                        if r < worst_gap:
                            worst_gap = r
                    last_px[tk] = p
            equity = sum(sleeves.values()) + cash
        curve.append((d, equity))
        g = gross.get(d, 1.0)
        if g < 1.0:
            risk_off_days += 1

        ds = day_scores.get(d)
        if ds is None:
            since += 1
            continue

        target = select_n(ds, held, prev_rank, N, sectors, CAP_ON)
        prev_rank = ds.rank
        changed = set(target) != held
        regime_flip = abs(g - applied_gross) > 1e-9
        drift = False
        if held and equity > 0 and target_w:
            drift = max(abs(sleeves.get(tk, 0.0) / equity - target_w.get(tk, 0.0)) for tk in held) > WEIGHT_DRIFT_PCT
        if not (changed or regime_flip or drift or since >= BACKSTOP_DAYS):
            since += 1
            continue

        # gross-scaled target: invested weights sum to g, remainder cash
        if g <= 0.0 or not target:
            neww = {}
        else:
            base = weigh(store, target, d, sizing=SIZING, n=N, cap_on=CAP_ON, sectors=sectors)
            neww = {tk: w * g for tk, w in base.items()}
        cash_w = 1.0 - sum(neww.values())

        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0) for tk in set(sleeves) | set(neww)}
        cur_cash_w = cash / equity if equity > 0 else 0.0
        turnover = 0.5 * (sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0)) for k in set(neww) | set(curw))
                          + abs(cash_w - cur_cash_w))
        total_turnover += turnover
        equity *= 1.0 - (TURNOVER_COST_BPS / 1e4) * turnover

        for tk in held - set(neww):
            if tk in entry_date:
                holding_periods.append((d - entry_date[tk]).days)
        for tk in set(neww) - held:
            entry_date[tk] = d

        sleeves = {tk: w * equity for tk, w in neww.items()}
        cash = cash_w * equity
        last_px = {tk: (pxmap(tk).get(d) or 0.0) for tk in neww}
        target_w = dict(neww)
        held = set(neww)
        applied_gross = g
        trades += 1
        since = 0

    summ = _summary(curve, INITIAL_EQUITY)
    years = (curve[-1][0] - curve[0][0]).days / 365.25 if len(curve) > 1 else 0.0
    for tk in held:
        if tk in entry_date:
            holding_periods.append((curve[-1][0] - entry_date[tk]).days)
    res = VariantResult(
        variant=variant, label=label, cagr=summ.cagr, sharpe=summ.sharpe,
        calmar=(summ.cagr / abs(summ.max_drawdown)) if summ.max_drawdown else 0.0,
        max_drawdown=summ.max_drawdown,
        annualized_turnover=(total_turnover / years if years > 0 else 0.0),
        avg_holding_days=(statistics.mean(holding_periods) if holding_periods else 0.0),
        worst_single_name_gap=worst_gap, trades=trades,
        pct_days_risk_off=risk_off_days / max(len(trading_days), 1),
        final_equity=curve[-1][1] if curve else INITIAL_EQUITY,
    )
    for name, (cs, ce) in CRASH_WINDOWS.items():
        seg = [(dd, e) for dd, e in curve if cs <= dd <= ce]
        res.crash_windows[name] = (seg[-1][1] / seg[0][1] - 1.0) if len(seg) >= 2 else 0.0
    return res


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--report-dir", default=None)
    ap.add_argument("--tag", default="full")
    args = ap.parse_args()
    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()
    db_path = os.environ["WORKBENCH_FACTOR_DATA_DB_PATH"]

    store = FactorDataStore(read_only=True)
    trading_days = store.trading_days(start, end)
    cached = _CachedPriceStore(store)
    print(f"[stage4] window {trading_days[0]}..{trading_days[-1]} {len(trading_days)} days", flush=True)

    t0 = _time.perf_counter()
    proxy = build_market_proxy(store, trading_days, db_path)
    valid_ma = int(proxy["ma"].notna().sum())
    print(f"[stage4] market proxy built: {valid_ma} days with 200d MA ({(_time.perf_counter()-t0)/60:.1f}m)", flush=True)

    day_scores: dict[date, DayScores] = {}
    for i, d in enumerate(trading_days):
        ds = compute_day(cached, d)
        if ds is not None:
            day_scores[d] = ds
        if (i + 1) % 1000 == 0:
            print(f"[stage4] scored {i+1}/{len(trading_days)} {(_time.perf_counter()-t0)/60:.1f}m", flush=True)
    print(f"[stage4] scores done: {len(day_scores)} usable, {(_time.perf_counter()-t0)/60:.1f}m", flush=True)

    all_tk = sorted({t for ds in day_scores.values() for t in ds.ranked})
    sectors = store.get_sectors(all_tk)

    variants = {"A": "Binary (SPY-proxy 200d)", "B": "Buffered binary (±1%/2d)",
                "C": "Graduated (0.98/0.60/0.15)", "D": "None (control)"}
    results: list[VariantResult] = []
    for v, label in variants.items():
        g = gross_series(proxy, v)
        tv = _time.perf_counter()
        res = simulate(cached, trading_days, day_scores, sectors, g, v, label)
        results.append(res)
        print(f"[stage4] {v} {label}: CAGR {res.cagr:.2%} Sharpe {res.sharpe:.2f} Calmar {res.calmar:.2f} "
              f"maxDD {res.max_drawdown:.2%} turn {res.annualized_turnover:.1f}x "
              f"riskoff {res.pct_days_risk_off:.0%} trades {res.trades} ({_time.perf_counter()-tv:.1f}s)",
              flush=True)

    payload = {
        "schema": "mr_momentum_daily.stage4.v1",
        "prereg": "PREREG_Stage4_Regime_v1.0.md",
        "inherits_stage3_winner": "N5_hybrid_nocap",
        "regime_gauge": "broad equal-weight market proxy (SPY substitution, PREREG §2)",
        "window": {"start": str(trading_days[0]), "end": str(trading_days[-1]),
                   "trading_days": len(trading_days), "proxy_ma_days": valid_ma},
        "variants": [asdict(r) for r in results],
    }
    if args.report_dir:
        rd = Path(args.report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        out = rd / f"MR_MomentumDaily_Stage4_{args.tag}.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[stage4] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
