"""Momentum-Daily — STAGE 2 BACKTEST: rebalance policy (proposal v1.1 §5, §9).

Isolates the REBALANCE POLICY. Everything else is held identical across four variants
(see PREREG_Stage2_RebalancePolicy_v1.0.md — FROZEN before this runs):

    universe top-200 PIT-liquid · 12-1 signal (252/21) · eligibility raw>0 AND z>=0 ·
    5 names equal-weight · sector cap OFF · regime OFF · 10 bps one-way · $100k.

    A  Weekly           rebalance to top-5 on the last trading day of each ISO week
    B  Trade-on-change  daily eval; rebalance whenever the top-5 eligible SET changes
    C  Daily conditional daily eval; trade only when a §5.1 trigger fires
    D  Biweekly         rebalance to top-5 every second ISO week

All four run through ONE simulator (identical daily-marking + turnover math) so the only
difference is the trade schedule. Daily momentum scores are computed once and shared.

    WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data_full.duckdb \\
        .venv/Scripts/python.exe scripts/backtest_momentum_stage2.py \\
            --start 2005-01-01 --end 2026-06-13 --report-dir docs/implementation/evidence/momentum_daily_stage2_4
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import time as _time
from dataclasses import asdict, dataclass, field
from datetime import date, datetime
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.factor_data.backtest import _CachedPriceStore, _summary  # noqa: E402
from app.factor_data.factors.engine import FactorUnavailable, momentum_scores  # noqa: E402
from app.factor_data.store import FactorDataStore  # noqa: E402
from app.factor_data.universe import UniverseUnavailable  # noqa: E402

# ---- FROZEN controls (§1 of the pre-reg) ----------------------------------------
UNIVERSE_N = 200
LOOKBACK_DAYS = 252
SKIP_DAYS = 21
Z_FLOOR = 0.0            # eligibility: zscore >= 0
RAW_FLOOR = 0.0          # eligibility: momentum > 0
MAX_NAMES = 5
ENTRY_RANK = 5
HOLD_RANK = 10
REPLACE_ADVANTAGE = 0.30
EXIT_CONFIRM_CLOSES = 2
WEIGHT_DRIFT_PCT = 0.04
BACKSTOP_DAYS = 10
TURNOVER_COST_BPS = 10.0
INITIAL_EQUITY = 100_000.0
MIN_NAMES = 30

CRASH_WINDOWS = {
    "2008_gfc": (date(2008, 6, 1), date(2009, 6, 30)),
    "2020_covid": (date(2020, 2, 15), date(2020, 6, 30)),
    "2022_drawdown": (date(2022, 1, 1), date(2022, 12, 31)),
}


# ---- selection core (faithful to momentum_daily._eligible / ._select_targets) ---
@dataclass
class DayScores:
    ranked: list[str]                  # eligible tickers, best score first
    score: dict[str, float]
    rank: dict[str, int]               # ticker -> 1-based rank among eligible


def compute_day(store: FactorDataStore, d: date) -> DayScores | None:
    """Eligible, score-ranked cross-section on ``d`` (raw>0 AND z>=0). None when thin."""
    try:
        df = momentum_scores(store, d, n=UNIVERSE_N, lookback_days=LOOKBACK_DAYS,
                             skip_days=SKIP_DAYS, min_names=MIN_NAMES)
    except (FactorUnavailable, UniverseUnavailable):
        return None
    e = df[(df["zscore"] >= Z_FLOOR) & (df["momentum"] > RAW_FLOOR)]
    e = e.sort_values("score", ascending=False, kind="stable")
    ranked = list(e.index)
    return DayScores(ranked=ranked, score=e["score"].to_dict(),
                     rank={t: i + 1 for i, t in enumerate(ranked)})


def top5(ds: DayScores) -> list[str]:
    return ds.ranked[:MAX_NAMES]


def conditional_select(ds: DayScores, held: set[str],
                       prev_rank: dict[str, int] | None) -> list[str]:
    """Replicate momentum_daily._select_targets: hold-band carry with 2-close exit
    confirmation, fill to entry_rank<=5, then 0.30-z displacement of the weakest."""
    ranked = ds.ranked
    if not ranked:
        return []
    pos, score_of = ds.rank, ds.score

    def exit_confirmed(h: str) -> bool:
        # need = EXIT_CONFIRM_CLOSES (2) -> require the single prior close to also breach.
        if EXIT_CONFIRM_CLOSES <= 1:
            return True
        if not prev_rank:
            return False
        r = prev_rank.get(h)
        return r is not None and r > HOLD_RANK

    keep = [h for h in held
            if pos.get(h) is not None and (pos[h] <= HOLD_RANK or not exit_confirmed(h))]
    book = list(keep)
    for t in ranked[:ENTRY_RANK]:
        if len(book) >= MAX_NAMES:
            break
        if t not in book:
            book.append(t)
    for t in ranked[:ENTRY_RANK]:
        if t in book:
            continue
        weakest = max((b for b in book if b in score_of),
                      key=lambda b: -score_of[b], default=None)
        if weakest is None:
            break
        if score_of[t] >= score_of[weakest] + REPLACE_ADVANTAGE:
            book[book.index(weakest)] = t
    chosen = set(book)
    return [t for t in ranked if t in chosen][:MAX_NAMES]


# ---- rebalance-date calendars (weekly / biweekly) -------------------------------
def iso_week_last_days(days: list[date]) -> list[date]:
    """Last trading day within each ISO (year, week)."""
    out: list[date] = []
    for i, d in enumerate(days):
        wk = d.isocalendar()[:2]
        nxt = days[i + 1] if i + 1 < len(days) else None
        if nxt is None or nxt.isocalendar()[:2] != wk:
            out.append(d)
    return out


# ---- the one shared simulator ---------------------------------------------------
@dataclass
class VariantResult:
    variant: str
    label: str
    total_return: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    annualized_turnover: float = 0.0
    avg_holding_days: float = 0.0
    n_completed_holdings: int = 0
    worst_single_name_gap: float = 0.0
    trades: int = 0
    final_equity: float = 0.0
    crash_windows: dict[str, float] = field(default_factory=dict)


def simulate(store: FactorDataStore, trading_days: list[date],
             day_scores: dict[date, DayScores], policy, variant: str, label: str,
             weekly_days: set[date], biweekly_days: set[date]) -> VariantResult:
    window_start, window_end = trading_days[0], trading_days[-1]
    pxcache: dict[str, dict[date, float]] = {}

    def pxmap(t: str) -> dict[date, float]:
        if t not in pxcache:
            df = store.get_prices(t, window_start, window_end, adjusted=True)
            pxcache[t] = {d.date(): float(c) for d, c in zip(df["date"], df["close"], strict=False)
                          if c is not None and float(c) > 0}
        return pxcache[t]

    equity = INITIAL_EQUITY
    sleeves: dict[str, float] = {}
    last_px: dict[str, float] = {}
    held: set[str] = set()
    entry_date: dict[str, date] = {}
    curve: list[tuple[date, float]] = []
    holding_periods: list[int] = []
    total_turnover = 0.0
    worst_gap = 0.0
    trade_days: list[date] = []
    days_since_trade = 0
    prev_rank: dict[str, int] | None = None

    for d in trading_days:
        # 1. mark held sleeves to today's close
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
            days_since_trade += 1
            continue

        do_trade, target = policy(d, ds, held, prev_rank, sleeves, equity,
                                  days_since_trade, weekly_days, biweekly_days)
        prev_rank = ds.rank  # update AFTER the policy consumed the prior day's ranks

        if not do_trade or target is None:
            days_since_trade += 1
            continue

        target = list(target)
        neww = {tk: 1.0 / len(target) for tk in target} if target else {}
        curw = {tk: (sleeves.get(tk, 0.0) / equity if equity > 0 else 0.0)
                for tk in set(sleeves) | set(neww)}
        turnover = 0.5 * sum(abs(neww.get(k, 0.0) - curw.get(k, 0.0))
                             for k in set(neww) | set(curw))
        total_turnover += turnover
        equity *= 1.0 - (TURNOVER_COST_BPS / 1e4) * turnover

        for tk in held - set(target):
            if tk in entry_date:
                holding_periods.append((d - entry_date[tk]).days)
        for tk in set(target) - held:
            entry_date[tk] = d

        sleeves = {tk: neww[tk] * equity for tk in target}
        last_px = {tk: (pxmap(tk).get(d) or 0.0) for tk in target}
        held = set(target)
        trade_days.append(d)
        days_since_trade = 0

    summ = _summary(curve, INITIAL_EQUITY)
    years = (curve[-1][0] - curve[0][0]).days / 365.25 if len(curve) > 1 else 0.0
    mdd = summ.max_drawdown
    calmar = (summ.cagr / abs(mdd)) if mdd else 0.0
    # completed holdings + any still open at the end
    for tk in held:
        if tk in entry_date:
            holding_periods.append((curve[-1][0] - entry_date[tk]).days)
    avg_hold = statistics.mean(holding_periods) if holding_periods else 0.0

    res = VariantResult(
        variant=variant, label=label,
        total_return=summ.total_return, cagr=summ.cagr, sharpe=summ.sharpe,
        calmar=calmar, max_drawdown=mdd,
        annualized_turnover=(total_turnover / years if years > 0 else 0.0),
        avg_holding_days=avg_hold, n_completed_holdings=len(holding_periods),
        worst_single_name_gap=worst_gap, trades=len(trade_days),
        final_equity=curve[-1][1] if curve else INITIAL_EQUITY,
    )
    # crash-window returns from the equity curve
    for name, (ws, we) in CRASH_WINDOWS.items():
        seg = [(d, e) for d, e in curve if ws <= d <= we]
        res.crash_windows[name] = (seg[-1][1] / seg[0][1] - 1.0) if len(seg) >= 2 else 0.0
    return res


# ---- the four policies -----------------------------------------------------------
def policy_weekly(d, ds, held, prev_rank, sleeves, equity, since, weekly, biweekly):
    if d in weekly:
        return True, top5(ds)
    return False, None


def policy_biweekly(d, ds, held, prev_rank, sleeves, equity, since, weekly, biweekly):
    if d in biweekly:
        return True, top5(ds)
    return False, None


def policy_on_change(d, ds, held, prev_rank, sleeves, equity, since, weekly, biweekly):
    target = top5(ds)
    return (set(target) != held), target


def policy_conditional(d, ds, held, prev_rank, sleeves, equity, since, weekly, biweekly):
    target = conditional_select(ds, held, prev_rank)
    changed = set(target) != held
    drift = False
    if held and equity > 0:
        eq_w = 1.0 / len(held)
        drift = max(abs(sleeves.get(tk, 0.0) / equity - eq_w) for tk in held) > WEIGHT_DRIFT_PCT
    backstop = since >= BACKSTOP_DAYS
    return (changed or drift or backstop), target


POLICIES = {
    "A": ("Weekly (v0.9 baseline)", policy_weekly),
    "B": ("Trade-on-change", policy_on_change),
    "C": ("Daily conditional (§5.1)", policy_conditional),
    "D": ("Biweekly", policy_biweekly),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default="2005-01-01")
    ap.add_argument("--end", default="2026-06-13")
    ap.add_argument("--variants", default="A,B,C,D")
    ap.add_argument("--report-dir", default=None)
    ap.add_argument("--tag", default="")
    args = ap.parse_args()

    start = datetime.strptime(args.start, "%Y-%m-%d").date()
    end = datetime.strptime(args.end, "%Y-%m-%d").date()

    store = FactorDataStore(read_only=True)
    trading_days = store.trading_days(start, end)
    if len(trading_days) < 2:
        print("ERROR: window too short", file=sys.stderr)
        return 1
    cached = _CachedPriceStore(store)

    weekly_days = set(iso_week_last_days(trading_days))
    wk_last = sorted(weekly_days)
    biweekly_days = set(wk_last[::2])

    print(f"[stage2] window {trading_days[0]}..{trading_days[-1]}  "
          f"{len(trading_days)} trading days  "
          f"weekly={len(weekly_days)} biweekly={len(biweekly_days)}", flush=True)

    # one shared daily-scores pass (the expensive part)
    t0 = _time.perf_counter()
    day_scores: dict[date, DayScores] = {}
    usable = 0
    for i, d in enumerate(trading_days):
        ds = compute_day(cached, d)
        if ds is not None:
            day_scores[d] = ds
            usable += 1
        if (i + 1) % 250 == 0:
            el = _time.perf_counter() - t0
            eta = el / (i + 1) * (len(trading_days) - i - 1)
            print(f"[stage2] scored {i+1}/{len(trading_days)} usable={usable} "
                  f"{el/60:.1f}m elapsed, ETA {eta/60:.1f}m", flush=True)
    print(f"[stage2] daily scores done: {usable} usable days, "
          f"{(_time.perf_counter()-t0)/60:.1f}m", flush=True)

    results: list[VariantResult] = []
    for v in args.variants.split(","):
        v = v.strip().upper()
        if v not in POLICIES:
            continue
        label, policy = POLICIES[v]
        tv = _time.perf_counter()
        res = simulate(cached, trading_days, day_scores, policy, v, label,
                       weekly_days, biweekly_days)
        results.append(res)
        print(f"[stage2] variant {v} {label}: CAGR {res.cagr:.2%} Sharpe {res.sharpe:.2f} "
              f"Calmar {res.calmar:.2f} maxDD {res.max_drawdown:.2%} "
              f"turnover {res.annualized_turnover:.1f}x trades {res.trades} "
              f"({_time.perf_counter()-tv:.1f}s)", flush=True)

    payload = {
        "schema": "mr_momentum_daily.stage2.v1",
        "prereg": "PREREG_Stage2_RebalancePolicy_v1.0.md",
        "window": {"start": str(trading_days[0]), "end": str(trading_days[-1]),
                   "trading_days": len(trading_days), "usable_score_days": usable},
        "controls": {
            "universe_n": UNIVERSE_N, "lookback_days": LOOKBACK_DAYS, "skip_days": SKIP_DAYS,
            "z_floor": Z_FLOOR, "raw_floor": RAW_FLOOR, "max_names": MAX_NAMES,
            "entry_rank": ENTRY_RANK, "hold_rank": HOLD_RANK,
            "replace_advantage": REPLACE_ADVANTAGE, "exit_confirm_closes": EXIT_CONFIRM_CLOSES,
            "weight_drift_pct": WEIGHT_DRIFT_PCT, "backstop_days": BACKSTOP_DAYS,
            "turnover_cost_bps": TURNOVER_COST_BPS, "initial_equity": INITIAL_EQUITY,
            "sector_cap": None, "regime_filter": "off",
        },
        "variants": [asdict(r) for r in results],
    }
    print("\n" + json.dumps(payload["variants"], indent=2), flush=True)

    if args.report_dir:
        rd = Path(args.report_dir)
        rd.mkdir(parents=True, exist_ok=True)
        tag = f"_{args.tag}" if args.tag else ""
        out = rd / f"MR_MomentumDaily_Stage2{tag}.json"
        out.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        print(f"[stage2] wrote {out}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
