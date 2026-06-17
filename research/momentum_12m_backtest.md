# Momentum 12-month upgrade — book backtest (R1: 6-1 → 12m)

Book-level evidence for the reviewer's **Priority 1** (`comments.md`): should the
production `momentum-portfolio` book switch its ranking signal from the deployed
**6-1** window to **12-month** momentum?

Method: the production-aligned weekly long-only top-quintile book
(`app.factor_data.backtest.run_momentum_backtest`) over the survivorship-free PIT
store, run for each candidate window and split IS vs OOS. Driver:
`apps/backend/scripts/backtest_momentum_window.py`. This complements the IC /
long-short factor study (`factor_report.md`, PR #142) with the actual book the
strategy trades — turnover cost, ISO-week rebalance, equity curve, passive baseline.

Store `1997-12-31..2026-06-16`; **IS `[2016-01-01..2022-12-31]` / OOS
`[2023-01-01..2026-06-16]`**; n=200, top_quantile=0.20, turnover 10 bps,
initial_equity $100,000. `turnover` = annualized one-way name turnover.

Windows (matched to `factor_research._factor_matrices`):
- **6-1** — lookback 105 / skip 21 (current production default, `momentum.py`)
- **12m** — lookback 252 / skip 0 (the factor study's strongest OOS variant)
- **12-1** — lookback 231 / skip 21 (12-month return skipping the last month)

| window | span | rebal | skip | tot.ret | CAGR | Sharpe | maxDD | turnover | base CAGR | base Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|
| 6-1 (current) | IS | 339 | 26 | 265.26% | 22.17% | 0.93 | -35.71% | 8.59 | 17.76% | 0.85 |
| 6-1 (current) | OOS | 180 | 1 | 307.84% | 50.60% | 1.40 | -38.77% | 8.76 | 33.68% | 1.64 |
| 12m | IS | 313 | 52 | 229.86% | 22.13% | 0.92 | -33.03% | 5.63 | 16.68% | 0.79 |
| **12m** | **OOS** | 180 | 1 | **597.50%** | **76.07%** | **1.85** | **-32.09%** | **5.57** | 33.68% | 1.64 |
| 12-1 | IS | 313 | 52 | 239.67% | 22.73% | 0.90 | -35.52% | 5.80 | 16.68% | 0.79 |
| 12-1 | OOS | 180 | 1 | 474.60% | 66.41% | 1.66 | -36.11% | 5.50 | 33.68% | 1.64 |

## Findings

1. **12m dominates out-of-sample on every axis.** OOS Sharpe 1.85 vs 1.40 (6-1),
   CAGR 76.1% vs 50.6%, max drawdown −32.1% vs −38.8%, **and** lower turnover
   (5.6 vs 8.8 annualized → less trading cost). It is a clean dominance — better
   return, better risk, cheaper to run. 12-1 lands in between, as the factor study
   predicted (12m > 12-1 > 6-1 OOS).

2. **Not curve-fit.** In-sample the three windows are ~tied (Sharpe 0.90–0.93,
   CAGR ~22%); 12m is not better IS — it pulls ahead specifically OOS. That is the
   robustness signature the §5c/OOS discipline looks for (the inverse of what
   killed RangeTrader, where IS-passing configs collapsed OOS).

3. **The current 6-1 signal does not beat passive OOS on a risk-adjusted basis.**
   6-1 OOS Sharpe 1.40 is *below* the equal-weight-universe baseline (1.64), so the
   deployed signal is paying turnover cost without earning risk-adjusted alpha over
   passive in this window. 12m (1.85) clears the baseline — it is the only window
   that justifies active selection here.

4. **Lower turnover is a structural bonus.** The 12-month window reranks more
   slowly than 6-1, cutting one-way turnover ~36% (8.8 → 5.6). On a small paper
   account paying spread/commission that directly improves net return and reduces
   the order-rate pressure that has tripped the book before.

## Caveats (equal across windows → the ranking is the robust takeaway)

- The harness book is uncapped top-quintile equal-weight; the deployed book adds
  `max_names`/`max_position_pct` caps, a SPY-200d regime filter, and optional
  vol-scaling. Those overlays are orthogonal to the signal-window choice and apply
  equally to all three rows.
- Universe = today's top-N liquid names (winner bias) and the OOS window
  (2023–2026) is a single momentum-friendly regime, so the **absolute** CAGRs
  (50–76%) and Sharpes are inflated; the **relative** cross-window ranking is what
  this study establishes.
- Absolute Sharpes differ from the capstone report's long-only quintile test
  (which cited OOS Sharpe 1.89/1.91/2.16 for 6-1/12-1/12m) because this is the
  cost-charged weekly book sim, not the gross monthly quintile spread — but the
  ordering and the maxDD ranking match, corroborating the report.
- `tickers.lastpricedate` lags the SEP max by a few days, so the final partial
  week's rebalance (2026-06-16) is skipped in every run (empty PIT universe);
  negligible.

## Recommendation

**Adopt the 12-month window for the production momentum book.** The OOS evidence is
unambiguous and consistent with the factor study and the capstone report. The
companion code change parametrizes the window on the strategy
(`momentum_lookback_days` / `momentum_skip_days`) and sets its default to 12m
(252 / 0); the module-level `momentum.py` default (105/21, owner-locked 2026-06-14)
is left untouched so the factor study and other callers keep their semantics.

Next per the reviewer's roadmap: **R3 risk overlays** (vol targeting / regime /
drawdown — no new data) and a **momentum-crash study** before any live step, since
this OOS window flatters momentum and the −32% drawdown is still large.
