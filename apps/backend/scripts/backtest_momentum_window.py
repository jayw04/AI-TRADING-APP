"""R1 book-level evidence: which momentum WINDOW should the production book trade?

The factor study (PR #142, `factor_research.py`) found — at the IC / long-short
level — that **mom_12** (12-month total return) is the only OOS-positive momentum
variant, while **mom_6_1** (the window the deployed `momentum_portfolio.py` uses,
105/21) is the *weakest*. That study measures the raw signal cross-sectionally; it
does NOT simulate the actual weekly long-only top-quintile **book** (turnover cost,
ISO-week rebalance, equity curve, passive baseline).

This driver closes that gap: it runs the production-aligned book backtest
(`app.factor_data.backtest.run_momentum_backtest`) for each candidate window, split
IS vs OOS, on the same PIT survivorship-free store the book reads. So the
recommendation to flip 6-1 → 12m is backed by a book-level OOS comparison, not just
an IC table — the §5c / OOS discipline that killed RangeTrader, applied to R1.

Windows compared (matched to the factor study's definitions; see
`factor_research._factor_matrices`):
  - **6-1**  lookback=105 skip=21  — current production default (`momentum.py`)
  - **12m**  lookback=252 skip=0   — study's strongest OOS variant
  - **12-1** lookback=231 skip=21  — 12-month return skipping the last month

Caveats (equal across windows, so the RELATIVE ranking is robust):
  - the harness book is uncapped top-quintile equal-weight; the deployed book caps
    at max_names/max_position_pct and adds a SPY-200d regime filter + optional
    vol-scaling. Those overlays are orthogonal to the signal-window choice.
  - universe = the top-N liquid store as of each rebalance (winner bias) → absolute
    CAGRs are inflated; the cross-window comparison is the takeaway.
  - the store's `tickers.lastpricedate` lags the SEP max by a few days, so the final
    partial week's rebalance is skipped (empty PIT universe) — negligible.

    cd apps/backend
    .venv/Scripts/python.exe scripts/backtest_momentum_window.py \
        --n 200 --is-start 2016-01-01 --split 2023-01-01 --report-dir research/

Outputs a console table + (with --report-dir) momentum_window_backtest.md + .json.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from datetime import date, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# (label, lookback_days, skip_days) — matched to factor_research._factor_matrices.
WINDOWS: list[tuple[str, int, int]] = [
    ("6-1 (current)", 105, 21),
    ("12m", 252, 0),
    ("12-1", 231, 21),
]


@dataclass
class Segment:
    window: str
    lookback_days: int
    skip_days: int
    span: str  # 'IS' | 'OOS'
    start: str
    end: str
    rebalances: int
    skipped: int
    book_total_return: float
    book_cagr: float
    book_sharpe: float
    book_max_drawdown: float
    book_ann_turnover: float  # annualized one-way name turnover
    base_cagr: float
    base_sharpe: float
    base_max_drawdown: float


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def _annualized_turnover(holdings: list) -> float:
    """Annualized one-way book turnover from the per-rebalance selected sets.

    The book is equal-weight, so at each rebalance the one-way turnover is
    0.5·Σ|w_cur − w_prev| with w = 1/k per name. Averaged over rebalances and
    scaled by the realized rebalances-per-year (from the holdings' date span) to
    annualize. Returns 0.0 when there are fewer than two rebalances to compare."""
    if len(holdings) < 2:
        return 0.0
    per: list[float] = []
    for prev, cur in zip(holdings[:-1], holdings[1:], strict=False):
        a, b = set(prev.tickers), set(cur.tickers)
        ka, kb = len(a) or 1, len(b) or 1
        s = 0.0
        for t in a | b:
            wa = 1.0 / ka if t in a else 0.0
            wb = 1.0 / kb if t in b else 0.0
            s += abs(wb - wa)
        per.append(0.5 * s)
    mean_one_way = sum(per) / len(per)
    span_days = (holdings[-1].rebalance_date - holdings[0].rebalance_date).days
    years = span_days / 365.25 if span_days > 0 else 0.0
    rebals_per_year = (len(holdings) - 1) / years if years > 0 else 0.0
    return mean_one_way * rebals_per_year


def _run_segment(store, label, lookback, skip, span, start, end, *, n, top_quantile,
                 turnover_cost_bps, initial_equity) -> Segment:
    from app.factor_data.backtest import run_momentum_backtest

    rep = run_momentum_backtest(
        store, start, end, n=n, lookback_days=lookback, skip_days=skip,
        top_quantile=top_quantile, turnover_cost_bps=turnover_cost_bps,
        initial_equity=initial_equity,
    )
    return Segment(
        window=label, lookback_days=lookback, skip_days=skip, span=span,
        start=start.isoformat(), end=end.isoformat(),
        rebalances=len(rep.rebalances), skipped=len(rep.skipped_rebalances),
        book_total_return=rep.metrics.total_return, book_cagr=rep.metrics.cagr,
        book_sharpe=rep.metrics.sharpe, book_max_drawdown=rep.metrics.max_drawdown,
        book_ann_turnover=_annualized_turnover(rep.holdings),
        base_cagr=rep.baseline_metrics.cagr, base_sharpe=rep.baseline_metrics.sharpe,
        base_max_drawdown=rep.baseline_metrics.max_drawdown,
    )


def main() -> int:
    ap = argparse.ArgumentParser(description="Momentum-window book backtest (IS/OOS).")
    ap.add_argument("--n", type=int, default=200, help="universe size (top-N by dollar volume).")
    ap.add_argument("--is-start", default="2016-01-01", help="in-sample start (YYYY-MM-DD).")
    ap.add_argument("--split", default="2023-01-01", help="IS/OOS boundary (YYYY-MM-DD).")
    ap.add_argument("--oos-end", default=None, help="OOS end; default = latest store price date.")
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--turnover-cost-bps", type=float, default=10.0)
    ap.add_argument("--initial-equity", type=float, default=100_000.0)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    from app.factor_data.store import FactorDataStore

    store = FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        if latest is None:
            print("No price data — check the factor store / backfill.", file=sys.stderr)
            return 1
        is_start = _parse(args.is_start)
        split = _parse(args.split)
        oos_end = _parse(args.oos_end) if args.oos_end else latest
        # IS = [is_start, split); OOS = [split, oos_end]. The split day itself is the
        # first OOS rebalance candidate, so IS ends the trading day before it.
        is_end = split - timedelta(days=1)

        segments: list[Segment] = []
        for label, lookback, skip in WINDOWS:
            for span, s, e in (("IS", is_start, is_end), ("OOS", split, oos_end)):
                segments.append(_run_segment(
                    store, label, lookback, skip, span, s, e,
                    n=args.n, top_quantile=args.top_quantile,
                    turnover_cost_bps=args.turnover_cost_bps,
                    initial_equity=args.initial_equity,
                ))
    finally:
        store.close()

    print(f"Store {floor}..{latest}. IS [{is_start}..{is_end}] / OOS [{split}..{oos_end}], "
          f"n={args.n}, top_quantile={args.top_quantile}, turnover={args.turnover_cost_bps}bps\n")
    hdr = (f"{'window':16}{'span':5}{'rebal':>6}{'skip':>5}{'tot.ret':>9}"
           f"{'CAGR':>8}{'Sharpe':>8}{'maxDD':>8}{'turnov':>8}{'base.CAGR':>10}{'base.Shrp':>10}")
    print(hdr)
    for sg in segments:
        print(f"{sg.window:16}{sg.span:5}{sg.rebalances:>6}{sg.skipped:>5}"
              f"{sg.book_total_return:>9.2%}{sg.book_cagr:>8.2%}{sg.book_sharpe:>8.2f}"
              f"{sg.book_max_drawdown:>8.2%}{sg.book_ann_turnover:>8.2f}"
              f"{sg.base_cagr:>10.2%}{sg.base_sharpe:>10.2f}")

    if args.report_dir:
        import json
        from dataclasses import asdict
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "momentum_12m_backtest.json").write_text(
            json.dumps([asdict(s) for s in segments], indent=2, default=str),
            encoding="utf-8",
        )
        lines = [
            "# Momentum 12-month upgrade — book backtest (R1, 6-1 → 12m)\n",
            f"Store `{floor}..{latest}`; IS `[{is_start}..{is_end}]` / OOS `[{split}..{oos_end}]`; "
            f"n={args.n}, top_quantile={args.top_quantile}, turnover {args.turnover_cost_bps}bps, "
            f"initial_equity ${args.initial_equity:,.0f}.\n",
            "Production-aligned weekly long-only top-quintile book "
            "(`run_momentum_backtest`), survivorship-free PIT store. Regime filter / "
            "name caps / vol-scaling are NOT applied (orthogonal to the window choice; "
            "equal across rows). Universe = today's top-N liquid names → absolute CAGRs "
            "are inflated by winner bias; the **cross-window OOS ranking** is the robust "
            "takeaway. `turnov` = annualized one-way name turnover.\n",
            "| window | span | rebal | skip | tot.ret | CAGR | Sharpe | maxDD | turnover | base CAGR | base Sharpe |",
            "|---|---|---|---|---|---|---|---|---|---|---|",
        ]
        for sg in segments:
            lines.append(
                f"| {sg.window} | {sg.span} | {sg.rebalances} | {sg.skipped} | "
                f"{sg.book_total_return:.2%} | {sg.book_cagr:.2%} | {sg.book_sharpe:.2f} | "
                f"{sg.book_max_drawdown:.2%} | {sg.book_ann_turnover:.2f} | "
                f"{sg.base_cagr:.2%} | {sg.base_sharpe:.2f} |"
            )
        (d / "momentum_12m_backtest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nWrote {d/'momentum_12m_backtest.md'} and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
