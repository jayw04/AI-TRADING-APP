# Momentum-crash study — 12m book (R3, pre-live risk evidence)

Store `1997-12-31..2026-06-16`; 12m book (lookback 252/skip 0); `[2016-01-01..2026-06-16]`; n=200, turnover 10.0bps. Full-sample maxDD -33.03%, Sharpe 1.30.

> Winner-biased liquid universe + a momentum-friendly sample — read the **shape** of the downside (depth, recovery, concentration), not the absolute levels.

## Worst 20 drawdowns

| # | peak | trough | recovery | depth | days→trough | days underwater |
|---|---|---|---|---|---|---|
| 1 | 2020-02-19 | 2020-03-23 | 2020-07-02 | -33.03% | 33 | 134 |
| 2 | 2025-02-14 | 2025-04-08 | 2025-07-16 | -32.09% | 53 | 152 |
| 3 | 2021-11-08 | 2022-06-17 | 2023-06-28 | -27.13% | 221 | 597 |
| 4 | 2018-10-01 | 2018-12-24 | 2019-03-21 | -24.15% | 84 | 171 |
| 5 | 2025-10-31 | 2025-11-20 | 2026-01-12 | -19.43% | 20 | 73 |
| 6 | 2021-02-12 | 2021-03-08 | 2021-10-29 | -18.15% | 24 | 259 |
| 7 | 2024-07-10 | 2024-08-07 | 2024-10-14 | -17.78% | 28 | 96 |
| 8 | 2026-02-25 | 2026-03-30 | 2026-04-08 | -15.94% | 33 | 42 |
| 9 | 2023-09-01 | 2023-10-26 | 2023-11-14 | -14.74% | 55 | 74 |
| 10 | 2026-06-02 | 2026-06-10 | 2026-06-15 | -12.55% | 8 | 13 |
| 11 | 2024-03-25 | 2024-04-19 | 2024-05-15 | -12.20% | 25 | 51 |
| 12 | 2020-09-02 | 2020-09-08 | 2020-10-09 | -11.39% | 6 | 37 |
| 13 | 2018-01-26 | 2018-02-08 | 2018-03-07 | -11.16% | 13 | 40 |
| 14 | 2026-01-28 | 2026-02-05 | 2026-02-24 | -10.88% | 8 | 27 |
| 15 | 2018-03-12 | 2018-04-25 | 2018-06-05 | -10.80% | 44 | 85 |
| 16 | 2020-10-13 | 2020-10-30 | 2020-11-06 | -9.73% | 17 | 24 |
| 17 | 2025-10-15 | 2025-10-22 | 2025-10-29 | -9.42% | 7 | 14 |
| 18 | 2025-01-06 | 2025-01-13 | 2025-01-17 | -8.65% | 7 | 11 |
| 19 | 2023-12-27 | 2024-01-03 | 2024-01-29 | -8.20% | 7 | 33 |
| 20 | 2026-05-14 | 2026-05-19 | 2026-05-22 | -7.87% | 5 | 8 |

## Worst rolling returns

| window | worst return |
|---|---|
| 1-month | -12.75% |
| 3-month | -17.00% |
| 6-month | -18.00% |

## Market correlation (monthly returns)

| benchmark | correlation |
|---|---|
| SPY | 0.77 |
| QQQ | 0.79 |
| equal-weight universe | 0.82 |

## Sector concentration during the 5 deepest drawdowns

- trough 2020-03-23 (-33.0%): 35 names, top sector **Technology 37%** ({'Technology': 13, 'Healthcare': 8, 'Consumer Defensive': 4, 'Consumer Cyclical': 3})
- trough 2025-04-08 (-32.1%): 34 names, top sector **Technology 24%** ({'Technology': 8, 'Consumer Cyclical': 5, 'Communication Services': 5, 'Financial Services': 4})
- trough 2022-06-17 (-27.1%): 37 names, top sector **Healthcare 35%** ({'Healthcare': 13, 'Technology': 9, 'Energy': 6, 'Consumer Defensive': 3})
- trough 2018-12-24 (-24.1%): 34 names, top sector **Technology 38%** ({'Technology': 13, 'Healthcare': 8, 'Consumer Cyclical': 5, 'Real Estate': 2})
- trough 2025-11-20 (-19.4%): 39 names, top sector **Technology 56%** ({'Technology': 22, 'Industrials': 4, 'Basic Materials': 3, 'Financial Services': 3})

## Overlay effect (R3 — vol-targeting)

- raw 12m book: maxDD **-33.03%**, Sharpe 1.30
- vol-targeted (0.15): maxDD **-18.61%**, Sharpe 1.28
- See `momentum_overlays_findings.md` — vol-targeting roughly halves drawdown at flat Sharpe; the recommended pre-live mitigation.
