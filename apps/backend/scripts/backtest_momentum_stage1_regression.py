"""Momentum v0.9.0 — STAGE 1 REGRESSION BACKTEST (proposal v1.1 §4, §9 "Stage 1 — Correctness").

    "Re-run the baseline backtest before/after (including a 252/0 as-was reference run); changes here
     are semantic fixes, and any performance delta is REPORTED but not optimized."

This is a correctness check, not an optimization. It runs the SAME production-aligned weekly
long-only book under three configurations and attributes the delta between them:

    REF   252/0, z-score floor only        the LITERAL v0.8 running config (the "as-was" reference)
    A3    252/21, z-score floor only        + the window fix alone (drop the contaminating last month)
    V09   252/21, dual momentum filter      + the raw-momentum floor  ==  the corrected v0.9 book

So REF -> A3 isolates A3 (the window), and A3 -> V09 isolates A1 (the dual filter). No parameter is
tuned to a result; the split and windows are fixed here before the run.

WHAT THIS HARNESS MODELS, AND WHAT IT DELIBERATELY DOES NOT
----------------------------------------------------------
The book engine (`run_momentum_backtest`) simulates weekly rebalancing of an equal-weight top-N book
on the survivorship-free PIT store, against a passive equal-weight-universe baseline. The v0.9 fixes
map onto it as follows:

  A1  dual momentum filter    MODELLED. `score_fn` returns only names with raw momentum > 0 AND
                              z-score >= 0, so a raw-negative name can never be selected. In a broad
                              drawdown with no raw-positive names the book correctly goes to cash.
  A3  12-1 window             MODELLED. A different lookback/skip in `score_fn`.
  A2  rank hysteresis         NOT modelled, and this is CONSERVATIVE: hysteresis + the 2-close
                              confirmation only REDUCE turnover while tracking the same top ranks, so
                              omitting them can only understate v0.9's net return (turnover costs are
                              charged here at 10bps). The equal-weight top-N book rebalances fully
                              each week — an upper bound on turnover.
  A5  bounded regime fallback NOT modelled, and this has ZERO backtest effect: it fires only on
                              MISSING market data, which a complete store never produces.
  regime filter (SPY 200d)    NOT applied — UNCHANGED between v0.8 and v0.9 (A5 changes only the
                              fallback, not the filter when data is present), so it is orthogonal and
                              omitted equally from all three configs, exactly as the prior
                              window-study harness does.

So the measurable Stage-1 delta is A1 + A3. A2 and A5 are correctness/robustness fixes whose effect
is either turnover-conservative or invisible to a clean-data backtest, and that is stated rather than
hidden.

CAVEATS (equal across all three configs, so the RELATIVE deltas are robust):
  - universe = today's top-N liquid names -> absolute CAGRs carry winner bias; the config-to-config
    delta is the takeaway, not the level.
  - 5-name book (matches the live v0.8 config, proposal §3), 10bps one-way turnover cost.

    WORKBENCH_FACTOR_DATA_DB_PATH=data/factor_data_full.duckdb \\
        .venv/Scripts/python.exe scripts/backtest_momentum_stage1_regression.py --report-dir research/
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


# (label, lookback_days, skip_days, dual_filter) — the three configs, fixed before the run.
CONFIGS: list[tuple[str, int, int, bool]] = [
    ("REF 252/0 z-only (as-was)", 252, 0, False),
    ("A3 252/21 z-only", 252, 21, False),
    ("V09 252/21 dual-filter", 252, 21, True),
]


@dataclass
class Segment:
    config: str
    lookback_days: int
    skip_days: int
    dual_filter: bool
    span: str
    start: str
    end: str
    rebalances: int
    skipped: int
    cash_rebalances: int          # rebalances the dual filter drove fully to cash
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float
    calmar: float
    ann_turnover: float
    avg_holding_days: float
    base_cagr: float
    base_sharpe: float
    base_max_drawdown: float


def _score_fn(lookback: int, skip: int, dual: bool, n: int, min_names: int):
    """A selection score frame for `run_momentum_backtest`: the ranked ELIGIBLE names at date `d`.

    The engine takes the top-N of `list(frame.index)`, so filtering here IS the eligibility gate.
    An empty frame after filtering means 'no eligible name today' -> the book holds cash, which is
    precisely the A1 behaviour in a broad drawdown. `momentum_scores` still raises on a genuinely
    thin cross-section, which the engine records as a skipped rebalance."""
    from app.factor_data.factors.engine import momentum_scores

    def fn(store, d: date):
        df = momentum_scores(store, d, n=n, lookback_days=lookback, skip_days=skip,
                             min_names=min_names)
        df = df[df["zscore"] >= 0.0]                      # the z-score floor (both v0.8 and v0.9)
        if dual:
            df = df[df["momentum"] > 0.0]                # A1: the RAW floor (v0.9 only)
        return df.sort_values("score", ascending=False)

    return fn


def _ann_turnover(holdings) -> float:
    if len(holdings) < 2:
        return 0.0
    per = []
    for prev, cur in zip(holdings[:-1], holdings[1:], strict=False):
        a, b = set(prev.tickers), set(cur.tickers)
        ka, kb = len(a) or 1, len(b) or 1
        per.append(0.5 * sum(abs((1.0 / kb if t in b else 0.0) - (1.0 / ka if t in a else 0.0))
                             for t in a | b))
    span_days = (holdings[-1].rebalance_date - holdings[0].rebalance_date).days
    years = span_days / 365.25 if span_days > 0 else 0.0
    return (sum(per) / len(per)) * ((len(holdings) - 1) / years) if years > 0 else 0.0


def _run(store, label, lookback, skip, dual, span, start, end, *, n, top_n, cost_bps,
         initial_equity, min_names) -> Segment:
    from app.factor_data.backtest import run_momentum_backtest

    rep = run_momentum_backtest(
        store, start, end, n=n, lookback_days=lookback, skip_days=skip, top_n=top_n,
        turnover_cost_bps=cost_bps, initial_equity=initial_equity, min_names=min_names,
        score_fn=_score_fn(lookback, skip, dual, n, min_names),
    )
    m = rep.metrics
    turn = _ann_turnover(rep.holdings)
    calmar = (m.cagr / abs(m.max_drawdown)) if m.max_drawdown else float("nan")
    hold_days = (365.25 / turn) if turn > 0 else float("nan")
    cash = sum(1 for h in rep.holdings if not h.tickers)
    return Segment(
        config=label, lookback_days=lookback, skip_days=skip, dual_filter=dual,
        span=span, start=start.isoformat(), end=end.isoformat(),
        rebalances=len(rep.rebalances), skipped=len(rep.skipped_rebalances), cash_rebalances=cash,
        total_return=m.total_return, cagr=m.cagr, sharpe=m.sharpe, max_drawdown=m.max_drawdown,
        calmar=calmar, ann_turnover=turn, avg_holding_days=hold_days,
        base_cagr=rep.baseline_metrics.cagr, base_sharpe=rep.baseline_metrics.sharpe,
        base_max_drawdown=rep.baseline_metrics.max_drawdown,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Momentum v0.9 Stage-1 regression backtest.")
    ap.add_argument("--n", type=int, default=200, help="universe size (top-N liquid).")
    ap.add_argument("--top-n", type=int, default=5, help="names held (5 = the live v0.8 book).")
    ap.add_argument("--is-start", default="2016-01-01")
    ap.add_argument("--split", default="2023-01-01")
    ap.add_argument("--oos-end", default=None)
    ap.add_argument("--stress-start", default="2022-01-01", help="momentum-crash stress window start.")
    ap.add_argument("--stress-end", default="2022-12-31")
    ap.add_argument("--turnover-cost-bps", type=float, default=10.0)
    ap.add_argument("--initial-equity", type=float, default=100_000.0)
    ap.add_argument("--min-names", type=int, default=20)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    from app.factor_data.store import FactorDataStore

    store = FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        if latest is None:
            print("No price data in the factor store.", file=sys.stderr)
            return 1
        is_start = date.fromisoformat(args.is_start)
        split = date.fromisoformat(args.split)
        oos_end = date.fromisoformat(args.oos_end) if args.oos_end else latest
        is_end = split - timedelta(days=1)
        spans = [
            ("IS", is_start, is_end),
            ("OOS", split, oos_end),
            ("STRESS-2022", date.fromisoformat(args.stress_start),
             date.fromisoformat(args.stress_end)),
        ]
        segs: list[Segment] = []
        for label, lb, sk, dual in CONFIGS:
            for span, s, e in spans:
                segs.append(_run(store, label, lb, sk, dual, span, s, e, n=args.n,
                                 top_n=args.top_n, cost_bps=args.turnover_cost_bps,
                                 initial_equity=args.initial_equity, min_names=args.min_names))
    finally:
        store.close()

    print(f"Store {floor}..{latest}.  IS [{is_start}..{is_end}] / OOS [{split}..{oos_end}] / "
          f"STRESS 2022.  {args.top_n}-name book, n={args.n}, {args.turnover_cost_bps}bps.\n")
    hdr = (f"{'config':30}{'span':13}{'rebal':>6}{'cash':>5}{'tot.ret':>9}{'CAGR':>8}"
           f"{'Sharpe':>8}{'maxDD':>8}{'Calmar':>8}{'turnov':>8}{'base.CAGR':>10}")
    print(hdr)
    for sp in ("IS", "OOS", "STRESS-2022"):
        for sg in [x for x in segs if x.span == sp]:
            print(f"{sg.config:30}{sg.span:13}{sg.rebalances:>6}{sg.cash_rebalances:>5}"
                  f"{sg.total_return:>9.1%}{sg.cagr:>8.1%}{sg.sharpe:>8.2f}{sg.max_drawdown:>8.1%}"
                  f"{sg.calmar:>8.2f}{sg.ann_turnover:>8.2f}{sg.base_cagr:>10.1%}")
        print()

    # Attribution: REF -> A3 -> V09, per span (semantic-fix delta, reported not optimized).
    print("=== delta attribution (Sharpe / CAGR / maxDD) ===")
    for sp in ("IS", "OOS", "STRESS-2022"):
        by = {x.config.split()[0]: x for x in segs if x.span == sp}
        ref, a3, v09 = by["REF"], by["A3"], by["V09"]
        print(f"  {sp:12} A3-window : dSharpe {a3.sharpe-ref.sharpe:+.2f}  dCAGR "
              f"{a3.cagr-ref.cagr:+.1%}  dMaxDD {a3.max_drawdown-ref.max_drawdown:+.1%}")
        print(f"  {'':12} A1-filter : dSharpe {v09.sharpe-a3.sharpe:+.2f}  dCAGR "
              f"{v09.cagr-a3.cagr:+.1%}  dMaxDD {v09.max_drawdown-a3.max_drawdown:+.1%}")
        print(f"  {'':12} NET v0.9  : dSharpe {v09.sharpe-ref.sharpe:+.2f}  dCAGR "
              f"{v09.cagr-ref.cagr:+.1%}  dMaxDD {v09.max_drawdown-ref.max_drawdown:+.1%}")

    if args.report_dir:
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "momentum_stage1_regression.json").write_text(
            json.dumps({
                "purpose": "v0.9 Workstream A Stage-1 correctness regression; deltas reported, NOT "
                           "optimized",
                "store_bounds": [str(floor), str(latest)],
                "config": {"n": args.n, "top_n": args.top_n, "turnover_cost_bps":
                           args.turnover_cost_bps, "is": [args.is_start, is_end.isoformat()],
                           "oos": [args.split, oos_end.isoformat()]},
                "modelled": {"A1_dual_filter": True, "A3_window": True},
                "not_modelled": {"A2_hysteresis": "turnover-conservative (omission understates v0.9)",
                                 "A5_regime_fallback": "zero effect on complete-data backtest",
                                 "regime_filter": "unchanged v0.8<->v0.9; omitted equally"},
                "segments": [asdict(s) for s in segs],
            }, indent=2, default=str), encoding="utf-8")
        print(f"\nWrote {d/'momentum_stage1_regression.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
