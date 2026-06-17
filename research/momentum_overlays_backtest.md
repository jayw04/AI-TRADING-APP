# Momentum 12m book — risk-overlay comparison (R3)

Store `1997-12-31..2026-06-16`; 12m book (lookback 252/skip 0); IS `[2016-01-01..2022-12-31]` / OOS `[2023-01-01..2026-06-16]`; n=200, turnover 10.0bps, vol_target 0.15, dd_bands ((-0.1, 0.66), (-0.15, 0.5), (-0.2, 0.33)).

Overlays applied at the portfolio-return level (no leverage; cap 1.0). 'both' = vol-target then drawdown. Same winner-biased universe / single OOS regime caveats as the other studies — read the **relative** effect, not absolute CAGRs.

| span | overlay | tot.ret | CAGR | Sharpe | maxDD |
|---|---|---|---|---|---|
| IS | none | 229.86% | 22.13% | 0.92 | -33.03% |
| IS | vol-target | 130.33% | 15.00% | 0.98 | -18.61% |
| IS | drawdown | 128.93% | 14.88% | 0.82 | -24.21% |
| IS | both | 115.14% | 13.69% | 0.96 | -16.41% |
| OOS | none | 597.50% | 76.07% | 1.85 | -32.09% |
| OOS | vol-target | 149.45% | 30.51% | 1.78 | -13.59% |
| OOS | drawdown | 392.08% | 59.06% | 1.73 | -23.69% |
| OOS | both | 141.63% | 29.30% | 1.74 | -13.25% |
