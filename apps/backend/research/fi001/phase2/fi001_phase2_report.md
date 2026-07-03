# FI-001 Phase 2 — Interaction (pairwise blends vs standalone)

Universe 150 - 2019-01-01..2026-06-13 - store 1997-12-31..2026-06-16. Equal-weight return-level blends; H2 gate = paired Sharpe-diff bootstrap CI vs standalone momentum.

## Standalone books
| book | CAGR | Sharpe | MaxDD | Calmar |
|---|---|---|---|---|
| momentum | 31.5% | 1.044 | -38.3% | 0.822 |
| low_vol | 12.0% | 0.833 | -30.2% | 0.398 |
| trend | 24.8% | 1.131 | -29.8% | 0.831 |

## Blends vs standalone momentum

| blend (eqw) | CAGR | Sharpe | MaxDD | Calmar | dSharpe vs mom [95% CI] | dMaxDD (pp) | verdict |
|---|---|---|---|---|---|---|---|
| momentum+low_vol | 22.4% | 1.097 | -31.1% | 0.72 | 0.054 [-0.163, 0.333] | 7.14 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| momentum+trend | 28.4% | 1.107 | -31.9% | 0.893 | 0.064 [-0.069, 0.215] | 6.43 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| low_vol+trend | 18.6% | 1.09 | -29.8% | 0.623 | 0.046 [-0.371, 0.602] | 8.47 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |
| momentum+low_vol+trend | 23.3% | 1.125 | -30.7% | 0.759 | 0.081 [-0.153, 0.372] | 7.63 | DIVERSIFIES (DD-only; Sharpe CI spans 0) |

## Reading (H2)

- **IMPROVES** = the blend's Sharpe-diff CI vs standalone momentum excludes zero (a real risk-adjusted uplift).
- **DIVERSIFIES (DD-only)** = Sharpe CI spans zero but the blend's max drawdown is >=3pp shallower than momentum (the modal, pre-registered outcome).
- **NO HELP** = neither.

> Sector arm SKIPPED: store has no sector data (run on the box).