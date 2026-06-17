"""R3 evidence: do risk overlays improve the 12-month momentum book?

The reviewer's "best next build" is survivability, not signal. This runs the
production 12-month momentum book (the R1 winner) and applies each gross-exposure
overlay at the portfolio-return level, IS and OOS, comparing CAGR / Sharpe / max
drawdown:

  - **none**        — the raw 12m book (baseline).
  - **vol-target**  — EWMA-vol targeting to ``--vol-target`` annualized
    (``_vol_target_overlay``; mirrors MomentumPortfolio._gross_scale).
  - **drawdown**    — drawdown-control exposure bands (``_drawdown_overlay``).
  - **both**        — vol-target then drawdown.

Overlays de-risk; they trade some upside for shallower drawdowns. The decision
they inform: turn them on in the deployed book? (Same discipline as the 12m flip —
backtest first, then flip.) The numbers here also feed the momentum-crash study.

    cd apps/backend
    .venv/Scripts/python.exe scripts/backtest_momentum_overlays.py \
        --is-start 2016-01-01 --split 2023-01-01 --report-dir research/
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import asdict, dataclass
from datetime import date, timedelta
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# 12-month momentum window (the R1 winner): lookback 252, skip 0.
MOM12_LOOKBACK, MOM12_SKIP = 252, 0


@dataclass
class Row:
    span: str        # 'IS' | 'OOS'
    overlay: str     # none | vol-target | drawdown | both
    total_return: float
    cagr: float
    sharpe: float
    max_drawdown: float


def _parse(d: str) -> date:
    return date.fromisoformat(d)


def _variants(curve, initial_equity, *, vol_target, span, dd_bands):
    from app.factor_data.backtest import _drawdown_overlay, _vol_target_overlay
    vol = _vol_target_overlay(curve, vol_target_annual=vol_target, span=span, initial_equity=initial_equity)
    dd = _drawdown_overlay(curve, bands=dd_bands, initial_equity=initial_equity)
    both = _drawdown_overlay(vol, bands=dd_bands, initial_equity=initial_equity)
    return {"none": curve, "vol-target": vol, "drawdown": dd, "both": both}


def main() -> int:
    ap = argparse.ArgumentParser(description="Momentum 12m book — risk-overlay comparison (IS/OOS).")
    ap.add_argument("--n", type=int, default=200)
    ap.add_argument("--is-start", default="2016-01-01")
    ap.add_argument("--split", default="2023-01-01")
    ap.add_argument("--oos-end", default=None)
    ap.add_argument("--top-quantile", type=float, default=0.20)
    ap.add_argument("--turnover-cost-bps", type=float, default=10.0)
    ap.add_argument("--initial-equity", type=float, default=100_000.0)
    ap.add_argument("--vol-target", type=float, default=0.15, help="annualized vol target for the overlay")
    ap.add_argument("--vol-ewma-span", type=int, default=20)
    ap.add_argument("--report-dir", default=None)
    args = ap.parse_args()

    from app.factor_data.backtest import DEFAULT_DD_BANDS, _summary, run_momentum_backtest
    from app.factor_data.store import FactorDataStore

    store = FactorDataStore(read_only=True)
    try:
        floor, latest = store.price_date_bounds()
        if latest is None:
            print("No price data — check the factor store / backfill.", file=sys.stderr)
            return 1
        is_start, split = _parse(args.is_start), _parse(args.split)
        oos_end = _parse(args.oos_end) if args.oos_end else latest
        is_end = split - timedelta(days=1)

        rows: list[Row] = []
        for span, s, e in (("IS", is_start, is_end), ("OOS", split, oos_end)):
            rep = run_momentum_backtest(
                store, s, e, n=args.n, lookback_days=MOM12_LOOKBACK, skip_days=MOM12_SKIP,
                top_quantile=args.top_quantile, turnover_cost_bps=args.turnover_cost_bps,
                initial_equity=args.initial_equity,
            )
            variants = _variants(
                rep.equity_curve, args.initial_equity,
                vol_target=args.vol_target, span=args.vol_ewma_span, dd_bands=DEFAULT_DD_BANDS,
            )
            for overlay, curve in variants.items():
                m = _summary(curve, args.initial_equity)
                rows.append(Row(span, overlay, m.total_return, m.cagr, m.sharpe, m.max_drawdown))
    finally:
        store.close()

    print(f"Store {floor}..{latest}. 12m book, IS [{is_start}..{is_end}] / OOS [{split}..{oos_end}], "
          f"n={args.n}, vol_target={args.vol_target}, dd_bands={DEFAULT_DD_BANDS}\n")
    print(f"{'span':5}{'overlay':12}{'tot.ret':>10}{'CAGR':>9}{'Sharpe':>8}{'maxDD':>9}")
    for r in rows:
        print(f"{r.span:5}{r.overlay:12}{r.total_return:>10.2%}{r.cagr:>9.2%}{r.sharpe:>8.2f}{r.max_drawdown:>9.2%}")

    if args.report_dir:
        import json
        d = Path(args.report_dir)
        d.mkdir(parents=True, exist_ok=True)
        (d / "momentum_overlays_backtest.json").write_text(
            json.dumps([asdict(r) for r in rows], indent=2, default=str), encoding="utf-8")
        lines = [
            "# Momentum 12m book — risk-overlay comparison (R3)\n",
            f"Store `{floor}..{latest}`; 12m book (lookback {MOM12_LOOKBACK}/skip {MOM12_SKIP}); "
            f"IS `[{is_start}..{is_end}]` / OOS `[{split}..{oos_end}]`; n={args.n}, "
            f"turnover {args.turnover_cost_bps}bps, vol_target {args.vol_target}, dd_bands {DEFAULT_DD_BANDS}.\n",
            "Overlays applied at the portfolio-return level (no leverage; cap 1.0). 'both' = "
            "vol-target then drawdown. Same winner-biased universe / single OOS regime caveats as "
            "the other studies — read the **relative** effect, not absolute CAGRs.\n",
            "| span | overlay | tot.ret | CAGR | Sharpe | maxDD |",
            "|---|---|---|---|---|---|",
        ]
        for r in rows:
            lines.append(f"| {r.span} | {r.overlay} | {r.total_return:.2%} | {r.cagr:.2%} | "
                         f"{r.sharpe:.2f} | {r.max_drawdown:.2%} |")
        (d / "momentum_overlays_backtest.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
        print(f"\nWrote {d/'momentum_overlays_backtest.md'} and .json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
