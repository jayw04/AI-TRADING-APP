# FI-001 Phase 3 — Allocation

Universe 150 - 2019-01-01..2026-06-12 - store 1997-12-31..2026-06-12. Weights estimated from a trailing 126d window, monthly rebalance, no look-ahead. Books: momentum, low_vol, trend, sector. Vol-target overlay = 12% annual on the ERC book.

| method | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dSharpe vs eqw [95% CI] | dMaxDD vs mom (pp) |
|---|---|---|---|---|---|---|---|
| equal_weight | 30.6% | 1.228 | -24.0% | 1.274 | 0.048 [-0.526, 0.679] | 0.0 [0.0, 0.0] | 14.27 |
| inverse_vol | 17.9% | 0.961 | -23.3% | 0.768 | -0.218 [-0.858, 0.522] | -0.266 [-0.607, 0.166] | 15.02 |
| erc | 15.1% | 0.88 | -23.2% | 0.651 | -0.3 [-1.006, 0.577] | -0.348 [-0.872, 0.315] | 15.09 |
| min_variance | -0.2% | 0.051 | -21.9% | 0.008 | -1.129 [-2.223, 0.035] | -1.177 [-2.255, -0.171] | 16.43 |
| erc_voltarget | 13.4% | 1.147 | -13.4% | 0.999 | -0.057 [-0.849, 0.709] | -0.091 [-0.737, 0.556] | 24.88 |

## Reading (H4)

- **Beats momentum** = dSharpe-vs-mom CI excludes zero (a real risk-adjusted edge over the incumbent). **Beats eqw** = dSharpe-vs-equal-weight CI excludes zero (the principled weight is worth its complexity over naive 1/N).
- Weights are trailing-estimated (no look-ahead); `erc_voltarget` adds a daily EWMA vol-target gross-exposure overlay on the ERC book.