# P12 §2 — Harden sensitivity grid (EXP-20260620-220518-grid)

_Window 1997-12-31..2026-06-12 · n=200 · gate: DD reduced >=20% AND Sharpe down <=0.05 · 5608.62s_

Decision matrix: **Enable** (DD reduced >=gate AND Sharpe preserved) · **Keep Off** (DD reduced but Sharpe cost) · **Reject** (no improvement) · **More Research** (mixed).

| Config | Hypothesis | CAGR | Sharpe | maxDD | avgDD | t.underwater | worst12m | Calmar | DD red. | dSharpe | Decision |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1.0 baseline (Momentum) | - | +10.7% | 0.48 | -76.4% | -37.6% | 97% | -61.4% | 0.14 | +0% | +0.00 | baseline |
| A: vol 10% | A vol-scaling | +4.8% | 0.49 | -34.2% | -9.0% | 96% | -21.9% | 0.14 | +55% | +0.01 | Enable |
| A: vol 12% | A vol-scaling | +5.6% | 0.50 | -39.8% | -10.7% | 96% | -25.8% | 0.14 | +48% | +0.01 | Enable |
| A: vol 15% | A vol-scaling | +6.9% | 0.51 | -47.2% | -13.1% | 96% | -31.1% | 0.15 | +38% | +0.03 | Enable |
| A: vol 18% | A vol-scaling | +7.9% | 0.52 | -53.8% | -15.4% | 96% | -36.2% | 0.15 | +30% | +0.03 | Enable |
| A: vol 20% | A vol-scaling | +8.5% | 0.52 | -57.1% | -16.7% | 96% | -38.9% | 0.15 | +25% | +0.04 | Enable |
| B: cap 20% | B sector-caps | +9.6% | 0.46 | -71.3% | -30.6% | 97% | -59.5% | 0.13 | +7% | -0.03 | More Research |
| B: cap 25% | B sector-caps | +10.2% | 0.47 | -70.4% | -30.3% | 97% | -59.6% | 0.14 | +8% | -0.01 | More Research |
| B: cap 30% | B sector-caps | +9.9% | 0.46 | -72.7% | -33.7% | 97% | -59.3% | 0.14 | +5% | -0.02 | More Research |
| B: cap 35% | B sector-caps | +9.5% | 0.45 | -74.4% | -35.9% | 97% | -59.4% | 0.13 | +3% | -0.04 | More Research |
| B: cap 40% | B sector-caps | +9.6% | 0.45 | -75.1% | -36.3% | 97% | -59.6% | 0.13 | +2% | -0.03 | More Research |
| A+B: vol 15% + cap 30% | combined | +6.5% | 0.49 | -47.4% | -13.2% | 96% | -30.6% | 0.14 | +38% | +0.00 | Enable |

## Best by objective (different objectives, not one 'best')
- Best Sharpe: **A: vol 20%**
- Lowest max-drawdown: **A: vol 10%**
- Best Calmar (risk-adjusted): **A: vol 20%**
- Lowest worst-12m: **A: vol 10%**

## Strategy evolution

| Version | Change | Status |
|---|---|---|
| 1.0 | Momentum (6-1, weekly top-quintile) | Validated (§1) |
| 1.1 | + Vol-scaling | _decided from this grid + §2 walk-forward_ |
| 1.1 | + Sector caps | _decided from this grid_ |
| 1.2 | Combined (vol + caps) | _candidate if interaction clears_ |
