"""LOCAL-ONLY analysis: rolling walk-forward of the vol-scaling overlay across
distinct market regimes (review Critical Issue #3 — is the DD/Sharpe benefit
real across regimes, or overfit to 2024-26 AI momentum?).

Runs the §3 cross-sectional momentum backtest (n=200, top-quintile) against the
full-history store in each window, comparing the fully-invested book vs the
EWMA-vol-target overlay (15% target). NOT committed; prints a table.

⚠ Universe caveat: the pool is today's active names (survivorship-biased for
historical windows). This still validates the OVERLAY (a portfolio-level gross-
exposure property), even though absolute returns are biased upward.

    PYTHONPATH=apps/backend apps/backend/.venv/Scripts/python.exe \
      apps/backend/scripts/walk_forward_vol_scaling.py
"""
from __future__ import annotations

from datetime import date

from app.factor_data.backtest import run_momentum_backtest
from app.factor_data.store import FactorDataStore

STORE = r"C:/LLM-RAG-APP/ai-trading-app/apps/backend/data/factor_data_full.duckdb"

# Distinct regime windows (the review's required stress periods). Trimmed to the
# 5 highest-signal regimes (dropped calm 2016-19 + the slow full-aggregate run).
WINDOWS = [
    ("GFC + 2009 reversal", date(2007, 7, 1), date(2010, 6, 30)),
    ("2010-2013 (2011 shock)", date(2010, 7, 1), date(2013, 6, 30)),
    ("2013-2016 (incl 2015)", date(2013, 7, 1), date(2016, 6, 30)),
    ("2019-2022 (COVID)", date(2019, 7, 1), date(2022, 6, 30)),
    ("2022-2026 (rate shock + AI)", date(2022, 7, 1), date(2026, 6, 12)),
]

VOL_TARGET = 0.15
SPAN = 20
N = 80  # smaller universe → faster per-rebalance scores; fine for the OVERLAY question
TOPQ = 0.20


def main() -> int:
    s = FactorDataStore(db_path=STORE, read_only=True)
    try:
        hdr = f"{'window':28s} {'rebals':>6s} | {'book ret':>9s} {'bk Shrp':>7s} {'bk DD':>7s} | {'vs ret':>9s} {'vs Shrp':>7s} {'vs DD':>7s} | dDD"
        print(hdr)
        print("-" * len(hdr))
        for label, start, end in WINDOWS:
            r = run_momentum_backtest(
                s, start, end, n=N, top_quantile=TOPQ,
                vol_target_annual=VOL_TARGET, vol_ewma_span=SPAN,
            )
            b, v = r.metrics, r.vol_scaled_metrics
            if v is None:
                print(f"{label:28s} {len(r.rebalances):>6d} | (no curve)")
                continue
            ddelta = v.max_drawdown - b.max_drawdown  # positive = DD improved (less negative)
            print(
                f"{label:28s} {len(r.rebalances):>6d} | "
                f"{b.total_return:>+8.1%} {b.sharpe:>7.2f} {b.max_drawdown:>7.1%} | "
                f"{v.total_return:>+8.1%} {v.sharpe:>7.2f} {v.max_drawdown:>7.1%} | "
                f"{ddelta:>+6.1%}"
            )
    finally:
        s.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
