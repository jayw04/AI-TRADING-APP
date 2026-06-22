# LOW-001 Low Volatility — Evidence (B - Diversifier / Defensive)

_git dded451 · EXP-20260622-013311-low001 · SEP survivorship-free (full-cycle 2000-2026) · 2000-01-01..2026-06-12 · n=200 · V1 top-quintile lowest 252d realized vol, equal-weight · 5446.6s_

> Pre-registered (LOW-001 plan v0.2). The question: *does Low Volatility add value to the platform?* — standalone risk-adjusted edge (H1), a diversifier of momentum (H2), or downside protection (H3). Honest prior: low-vol was negative on the narrow 2016-26 mega-cap window; this is the full-cycle 2000-2026 test.

## Books

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Equal-weight (benchmark) | +5.63% | 0.35 | -69.2% | 0.08 |
| Momentum (v1.1) | +7.39% | 0.39 | -76.4% | 0.10 |
| **Low Volatility** | +7.73% | 0.59 | -39.0% | 0.20 |
| Momentum+LowVol blend | +6.93% | 0.48 | -45.3% | 0.15 |

## H1 — standalone risk-adjusted edge (low-vol vs equal-weight)
- **dSharpe +0.24, paired 95% CI [-0.029, 0.53]** — includes zero -> no standalone edge.
- Walk-forward: low-vol beats equal-weight in **3/5** windows.

## H2 — diversifier (correlation / blend)
- corr(momentum, low-vol) = **-0.153** (negative/low = defensive diversifier).
- blend vs momentum-alone dSharpe +0.10, CI [-0.165, 0.359].

## H3 — downside protection (the low-vol signature)
- low-vol maxDD vs momentum: **+37.4%** (positive = shallower than momentum's -76.4%).
- low-vol maxDD vs equal-weight: **+30.2%**.
- Shallower drawdown than equal-weight in **5/5** windows.

## Cost sweep (low-vol Sharpe)
  5bps 0.6 · 10bps 0.59 · 20bps 0.57 · 50bps 0.52

## Outcome: **B - Diversifier / Defensive** → defensive sleeve / momentum+low-vol blend candidate (evidence-gated)

_Per ADR 0014 + the LOW-001 gate. 252-day realized vol frozen (no optimization). No parameter introduced solely to improve historical performance. The evidence package is the deliverable._
