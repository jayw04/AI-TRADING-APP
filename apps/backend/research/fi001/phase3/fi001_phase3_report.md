# FI-001 Phase 3 — Allocation

Universe 150 - 2019-01-01..2026-06-13 - store 1997-12-31..2026-06-16. Weights estimated from a trailing 126d window, monthly rebalance, no look-ahead. Books: momentum, low_vol, trend. Vol-target overlay = 12% annual on the ERC book.

| method | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dSharpe vs eqw [95% CI] | dMaxDD vs mom (pp) |
|---|---|---|---|---|---|---|---|
| equal_weight | 23.3% | 1.125 | -30.7% | 0.759 | 0.081 [-0.153, 0.372] | 0.0 [0.0, 0.0] | 7.63 |
| inverse_vol | 20.0% | 1.102 | -30.5% | 0.655 | 0.059 [-0.286, 0.526] | -0.022 [-0.152, 0.165] | 7.82 |
| erc | 19.5% | 1.096 | -30.5% | 0.64 | 0.053 [-0.309, 0.547] | -0.028 [-0.185, 0.192] | 7.81 |
| min_variance | 15.2% | 0.992 | -30.2% | 0.503 | -0.052 [-0.611, 0.667] | -0.133 [-0.513, 0.35] | 8.05 |
| erc_voltarget | 14.2% | 1.2 | -14.2% | 1.001 | 0.159 [-0.269, 0.559] | 0.08 [-0.28, 0.423] | 24.11 |

## Reading (H4)

- **Beats momentum** = dSharpe-vs-mom CI excludes zero (a real risk-adjusted edge over the incumbent). **Beats eqw** = dSharpe-vs-equal-weight CI excludes zero (the principled weight is worth its complexity over naive 1/N).
- Weights are trailing-estimated (no look-ahead); `erc_voltarget` adds a daily EWMA vol-target gross-exposure overlay on the ERC book.

> Sector arm SKIPPED: store has no sector data (run on the box).