# Momentum 12-month upgrade — book backtest (R1, 6-1 → 12m)

Store `1997-12-31..2026-06-16`; IS `[2016-01-01..2022-12-31]` / OOS `[2023-01-01..2026-06-16]`; n=200, top_quantile=0.2, turnover 10.0bps, initial_equity $100,000.

Production-aligned weekly long-only top-quintile book (`run_momentum_backtest`), survivorship-free PIT store. Regime filter / name caps / vol-scaling are NOT applied (orthogonal to the window choice; equal across rows). Universe = today's top-N liquid names → absolute CAGRs are inflated by winner bias; the **cross-window OOS ranking** is the robust takeaway. `turnover` = annualized one-way name turnover; `hold(wk)` = avg position holding period in rebalance periods (weeks).

| window | span | rebal | skip | tot.ret | CAGR | Sharpe | maxDD | turnover | hold(wk) | base CAGR | base Sharpe |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 6-1 (current) | IS | 339 | 26 | 265.26% | 22.17% | 0.93 | -35.71% | 8.59 | 6.0 | 17.76% | 0.85 |
| 6-1 (current) | OOS | 180 | 1 | 307.84% | 50.60% | 1.40 | -38.77% | 8.76 | 5.9 | 33.68% | 1.64 |
| 12m | IS | 313 | 52 | 229.86% | 22.13% | 0.92 | -33.03% | 5.63 | 9.1 | 16.68% | 0.79 |
| 12m | OOS | 180 | 1 | 597.50% | 76.07% | 1.85 | -32.09% | 5.57 | 9.1 | 33.68% | 1.64 |
| 12-1 | IS | 313 | 52 | 239.67% | 22.73% | 0.90 | -35.52% | 5.80 | 8.8 | 16.68% | 0.79 |
| 12-1 | OOS | 180 | 1 | 474.60% | 66.41% | 1.66 | -36.11% | 5.50 | 9.2 | 33.68% | 1.64 |
