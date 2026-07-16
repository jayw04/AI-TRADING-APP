"""Momentum-Daily — STAGE 3 BACKTEST: portfolio construction (proposal v1.1 §6, §9).

Holds the Stage-2 winner fixed — signal 12-1 + **daily conditional §5.1 rebalance policy** — and
sweeps CONSTRUCTION: name count {5,8,10} x sizing {equal, hybrid 50/50 inverse-vol} x sector cap
{off,on} = 12 configs (see PREREG_Stage3_Construction_v1.0.md, FROZEN before this runs).

Reuses the Stage-2 daily-scores core (single-sourced eligibility) + the app weighting/sector primitives;
adds a parametric, sector-aware §5.1 selection and the §6.3 hybrid sizing with per-name bounds.

    WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data_full.duckdb \\
        .venv/Scripts/python.exe scripts/backtest_momentum_stage3.py \\
            --start 2005-01-01 --end 2026-06-13 --report-dir docs/implementation/evidence/momentum_daily_stage2_4
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time as _time
from collections import Counter
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = Path(__file__).resolve().parent
for _p in (str(BACKEND_ROOT), str(SCRIPTS_DIR)):
    if _p not in sys.path:
        sys.path.insert(0, _p)

from backtest_momentum_stage2 import (  # noqa: E402  (single-source the daily-scores core)
    CRASH_WINDOWS,
    INITIAL_EQUITY,
    REPLACE_ADVANTAGE,
    TURNOVER_COST_BPS,
    DayScores,
    compute_day,
)

from app.factor_data.backtest import (  # noqa: E402
    _apply_sector_cap,
    _CachedPriceStore,
    _summary,
    _trailing_vol,
)
from app.factor_data.store import FactorDataStore  # noqa: E402

EXIT_CONFIRM_CLOSES = 2
WEIGHT_DRIFT_PCT = 0.04
BACKSTOP_DAYS = 10
VOL_LOOKBACK = 63


# ---- parametric, sector-aware §5.1 selection ------------------------------------
def select_n(ds: DayScores, held: set[str], prev_rank: dict[str, int] | None,
             n: int, sectors: dict[str, str | None], cap_on: bool) -> list[str]:
    """momentum_daily §5.1 selection generalized to an N-name book (entry_rank=N,
    hold_rank=2N) with an optional max-2-holdings-per-sector selection constraint."""
    entry_rank, hold_rank = n, 2 * n
    ranked = ds.ranked
    if not ranked:
        return []
    pos, score_of = ds.rank, ds.score

    def exit_confirmed(h: str) -> bool:
        if EXIT_CONFIRM_CLOSES <= 1:
            return True
        if not prev_rank:
            return False
        r = prev_rank.get(h)
        return r is not None and r > hold_rank

    book = [h for h in held
            if pos.get(h) is not None and (pos[h] <= hold_rank or not exit_confirmed(h))]
    sec_ct: Counter[str] = Counter(sectors.get(t) for t in book if sectors.get(t))

    def can_add(t: str) -> bool:
        if not cap_on:
            return True
        s = sectors.get(t)
        return s is None or sec_ct.get(s, 0) < 2  # unknown-sector names are exempt

    for t in ranked[:entry_rank]:
        if len(book) >= n:
            break
        if t not in book and can_add(t):
            book.append(t)
            if sectors.get(t):
                sec_ct[sectors[t]] += 1
    for t in ranked[:entry_rank]:
        if t in book or not can_add(t):
            continue
        weakest = max((b for b in book if b in score_of), key=lambda b: -score_of[b], default=None)
        if weakest is None:
            break
        if score_of[t] >= score_of[weakest] + REPLACE_ADVANTAGE:
            if sectors.get(weakest):
                sec_ct[sectors[weakest]] -= 1
            book[book.index(weakest)] = t
            if sectors.get(t):
                sec_ct[sectors[t]] += 1
    chosen = set(book)
    return [t for t in ranked if t in chosen][:n]


# ---- §6.3 sizing ----------------------------------------------------------------
def weigh(store: FactorDataStore, chosen: list[str], d: date, *, sizing: str, n: int,
          cap_on: bool, sectors: dict[str, str | None]) -> dict[str, float]:
    if not chosen:
        return {}
    if sizing == "equal_weight":
        w = {t: 1.0 / len(chosen) for t in chosen}
    else:  # hybrid_50_50: 0.5 EW + 0.5 inverse-vol, per-name bounds, renormalized
        vols = {t: _trailing_vol(store, t, d, VOL_LOOKBACK) for t in chosen}
        present = [v for v in vols.values() if v]
        med = statistics.median(present) if present else 1.0
        inv = {t: 1.0 / (vols[t] if vols[t] and vols[t] > 0 else med) for t in chosen}
        tot = sum(inv.values()) or 1.0
        ew = 1.0 / len(chosen)
        w = {t: 0.5 * ew + 0.5 * inv[t] / tot for t in chosen}
        lo, hi = (0.0, 0.20) if n == 5 else (0.075, 0.15)
        for _ in range(8):  # iterative clamp-to-bounds + renormalize
            w = {t: min(hi, max(lo, x)) for t, x in w.items()}
            s = sum(w.values()) or 1.0
            w = {t: x / s for t, x in w.items()}
            if all(lo - 1e-9 <= x <= hi + 1e-9 for x in w.values()):
                break
    if cap_on:
        w = _apply_sector_cap(store, w, max_sector_pct=(0.40 if n == 5 else 0.30))
        s = sum(w.values()) or 1.0
        w = {t: x / s for t, x in w.items()}
    return w


@dataclass
class ConfigResult:
    name_count: int
    sizing: str
    sector_cap: bool
    label: str = ""
    cagr: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    annualized_turnover: float = 0.0
    avg_holding_days: float = 0.0
    worst_single_name_gap: float = 0.0
    trades: int = 0
    final_equity: float = 0.0
    crash_windows: dict[str, float] = field(default_factory=dict)


def simulate(store: FactorDataStore, trading_days: list[date], day_scores: dict[date, DayScores],
             sectors: dict[str, str | None], *, n: int, sizing: str, cap_on: bool) -> ConfigResult:
    window_start, window_end = trading_days[0], trading_days[-1]
    pxcache: dict[str, dict[date, float]] = {}

    def pxmap(t: str) -> dict[date, float]:
        if t not in pxcache:
            df = store.get_prices(t, window_start, window_end, adjusted=True)
            pxcache[t] = {dt.date(): float(c) for dt, c in zip(df["date"], df["close"], strict=False)
                          if c is not None and float(c) > 0}
        return pxcache[t]

    equity = INITIAL_EQUITY
    sleeves: dict[str, float] = {}
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
    prev_rank: dict[str, int] | None = None

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
            equity = sum(sleeves.values())
        curve.append((d, equity))

        ds = day_scores.get(d)
        if ds is None:
            since += 1
            continue

        target = select_n(ds, held, prev_rank, n, sectors, cap_on)
        prev_rank = ds.rank
        changed = set(target) != held
        drift = False
        if held and equity > 0 and target_w:
            drift = max(abs(sleeves.get(tk, 0.0) / equity - target_w.get(tk, 0.0)) for tk in held) > WEIGHT_DRIFT_PCT
        if not (changed or drift or since >= BACKSTOP_DAYS):
            since += 1
            continue

        neww = weigh(store, target, d, sizing=sizing, n=n, cap_on=cap_on, sectors=sectors)
        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0) for tk in set(sleeves) | set(neww)}
        turnover = 0.5 * sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0)) for k in set(neww) | set(curw))
        total_turnover += turnover
        equity *= 1.0 - (TURNOVER_COST_BPS / 1e4) * turnover

        for tk in held - set(neww):
            if tk in entry_date:
                holding_periods.append((d - entry_date[tk]).days)
        for tk in set(neww) - held:
            entry_date[tk] = d

        sleeves = {tk: w * equity for tk, w in neww.items()}
        last_px = {tk: (pxmap(tk).get(d) or 0.0) for tk in neww}
        target_w = dict(neww)
        held = set(neww)
        trades += 1
        since = 0

    summ = _summary(curve, INITIAL_EQUITY)
    years = (curve[-1][0] - curve[0][0]).days / 365.25 if len(curve) > 1 else 0.0
    for tk in held:
        if tk in entry_date:
            holding_periods.append((curve[-1][0] - entry_date[tk]).days)
    res = ConfigResult(
        name_count=n, sizing=sizing, sector_cap=cap_on,
        label=f"N{n}/{'hyb' if sizing != 'equal_weight' else 'ew'}/{'cap' if cap_on else 'nocap'}",
        cagr=summ.cagr, sharpe=summ.sharpe,
        calmar=(summ.cagr / abs(summ.max_drawdown)) if summ.max_drawdown else 0.0,
        max_drawdown=summ.max_drawdown,
        annualized_turnover=(total_turnover / years if years > 0 else 0.0),
        avg_holding_days=(statistics.mean(holding_periods) if holding_periods else 0.0),
        worst_single_name_gap=worst_gap, trades=trades,
        final_equity=curve[-1][1] if curve else INITIAL_EQUITY,
    )
    for name, (ws, we) in CRASH_WINDOWS.items():
        seg = [(dd, e) for dd, e in curve if ws <= dd <= we]
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

    store = FactorDataStore(read_only=True)
    trading_days = store.trading_days(start, end)
    cached = _CachedPriceStore(store)
    print(f"[stage3] window {trading_days[0]}..{trading_days[-1]} {len(trading_days)} days", flush=True)

    t0 = _time.perf_counter()
    day_scores: dict[date, DayScores] = {}
    for i, d in enumerate(trading_days):
        ds = compute_day(cached, d)
        if ds is not None:
            day_scores[d] = ds
        if (i + 1) % 500 == 0:
            el = _time.perf_counter() - t0
            print(f"[stage3] scored {i+1}/{len(trading_days)} {el/60:.1f}m "
                  f"ETA {el/(i+1)*(len(trading_days)-i-1)/60:.1f}m", flush=True)
    print(f"[stage3] scores done: {len(day_scores)} usable, {(_time.perf_counter()-t0)/60:.1f}m", flush=True)

    # sectors for every ticker that ever appears (one batch fetch)
    all_tk = sorted({t for ds in day_scores.values() for t in ds.ranked})
    sectors = store.get_sectors(all_tk)
    print(f"[stage3] sectors: {sum(1 for v in sectors.values() if v)}/{len(all_tk)} known", flush=True)

    results: list[ConfigResult] = []
    for n in (5, 8, 10):
        for sizing in ("equal_weight", "hybrid_50_50"):
            for cap_on in (False, True):
                tv = _time.perf_counter()
                res = simulate(cached, trading_days, day_scores, sectors,
                               n=n, sizing=sizing, cap_on=cap_on)
                results.append(res)
                print(f"[stage3] {res.label}: CAGR {res.cagr:.2%} Sharpe {res.sharpe:.2f} "
                      f"Calmar {res.calmar:.2f} maxDD {res.max_drawdown:.2%} "
                      f"turn {res.annualized_turnover:.1f}x trades {res.trades} "
                      f"({_time.perf_counter()-tv:.1f}s)", flush=True)

    payload = {
        "schema": "mr_momentum_daily.stage3.v1",
        "prereg": "PREREG_Stage3_Construction_v1.0.md",
        "inherits_stage2_winner": "C_daily_conditional",
        "window": {"start": str(trading_days[0]), "end": str(trading_days[-1]),
                   "trading_days": len(trading_days), "usable_score_days": len(day_scores)},
        "sector_note": "tickers.sector is static-current (not PIT); see PREREG §5",
        "configs": [asdict(r) for r in results],
    }
    if args.report_dir:
        rd = Path(args.report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        out = rd / f"MR_MomentumDaily_Stage3_{args.tag}.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[stage3] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
