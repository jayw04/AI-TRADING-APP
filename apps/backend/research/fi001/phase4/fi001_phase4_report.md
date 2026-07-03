# FI-001 Phase 4 — Adaptive Portfolio (v1)

Universe 150 - 2019-01-01..2026-06-13 - store 1997-12-31..2026-06-16. Regime = equal-weight universe vs its 200d SMA (no look-ahead); risk-off gross 0.5; corr de-risk threshold 0.6 (trailing 63d). Books: momentum, low_vol, trend.

| strategy | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs eqw [95% CI] | dSharpe vs mom [95% CI] | dMaxDD vs eqw (pp) |
|---|---|---|---|---|---|---|---|
| static_eqw | 23.3% | 1.125 | -30.7% | 0.759 | 0.0 [0.0, 0.0] | 0.081 [-0.153, 0.372] | 0.0 |
| regime_gross | 19.5% | 1.166 | -24.2% | 0.805 | 0.041 [-0.189, 0.228] | 0.122 [-0.116, 0.358] | 6.44 |
| regime_tilt | 23.4% | 1.071 | -31.9% | 0.733 | -0.054 [-0.178, 0.044] | 0.027 [-0.151, 0.241] | -1.25 |
| corr_adaptive | 15.6% | 1.066 | -24.5% | 0.637 | -0.058 [-0.347, 0.202] | 0.023 [-0.225, 0.277] | 6.16 |

## Reading (H4 adaptive)

- **beats eqw** = dSharpe-vs-equal-weight CI excludes zero (adaptation earns its keep over the static Phase 3 winner). **beats mom** = same vs standalone momentum.
- All regime signals use only past data (200d SMA / trailing corr, shifted 1 day).

> Sector arm SKIPPED: store has no sector data (run on the box).