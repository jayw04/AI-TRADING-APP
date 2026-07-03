# FI-001 Phase 2 — Interaction (pairwise blends vs standalone)

Universe 150 - 2019-01-01..2026-06-12 - store 1997-12-31..2026-06-12. Equal-weight return-level blends; H2 gate = paired Sharpe-diff bootstrap CI vs standalone momentum.

## Standalone books
| book | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| momentum | 53.5% | 1.18 | -38.3% | 1.397 |
| low_vol | 5.3% | 0.513 | -11.4% | 0.463 |
| trend | 42.1% | 1.48 | -23.2% | 1.814 |
| sector | 18.6% | 0.741 | -28.9% | 0.646 |

## Blends vs standalone momentum

| blend (eqw) | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dMaxDD (pp) | verdict |
|---|---|---|---|---|---|---|---|
| momentum+low_vol | 30.1% | 1.207 | -24.6% | 1.223 | 0.027 [-0.305, 0.439] | 13.69 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| momentum+trend | 48.8% | 1.324 | -30.6% | 1.594 | 0.144 [-0.136, 0.425] | 7.7 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| momentum+sector | 36.7% | 1.089 | -31.5% | 1.166 | -0.091 [-0.622, 0.454] | 6.82 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| low_vol+trend | 23.2% | 1.372 | -16.7% | 1.394 | 0.192 [-0.786, 1.246] | 21.64 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| momentum+low_vol+trend+sector | 30.6% | 1.228 | -24.0% | 1.274 | 0.048 [-0.526, 0.679] | 14.27 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |

## Reading (H2)

- **IMPROVES** = the blend's Sharpe-diff CI vs standalone momentum excludes zero (a real risk-adjusted uplift).
- **DIVERSIFIES (DD-only)** = Sharpe CI spans zero but the blend's max drawdown is >=3pp shallower than momentum (the modal, pre-registered outcome).
- **NO HELP** = neither.