# SEC-001 Sector Rotation — Evidence (B — Diversifier)

_git 181dbbb · EXP-20260621-223842-sec001 · SEP survivorship-free + Sharadar tickers.sector (11 sectors) · 2000-01-01..2026-06-12 · n=200 · V1 top-quintile of strong sectors · 4048.3s_

> Pre-registered (SEC-001 plan v0.2). The question: *does Sector Rotation add value to the platform?* — as a standalone strategy (H1) or a diversifier of momentum (H2).

## Books

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Equal-weight (benchmark) | +5.63% | 0.35 | -69.2% | 0.08 |
| Momentum (v1.1) | +7.39% | 0.39 | -76.4% | 0.10 |
| **Sector Rotation** | +10.36% | 0.51 | -64.8% | 0.16 |
| Momentum+Sector blend | +10.44% | 0.48 | -66.8% | 0.16 |

## H1 — standalone edge (sector vs equal-weight)
- **dSharpe +0.16, paired 95% CI [-0.03, 0.366]** — includes zero -> no standalone edge.
- Walk-forward: sector beats equal-weight in **3/5** windows.

## H2 — diversifier (correlation / blend)
- corr(momentum, sector) = **0.379** (low = diversifier).
- blend vs momentum-alone dSharpe +0.09, CI [-0.045, 0.233]; sector maxDD -64.8% vs momentum -76.4%.

## Cost sweep (sector Sharpe)
  5bps 0.53 · 10bps 0.51 · 20bps 0.47 · 50bps 0.35

## Outcome: **B — Diversifier** → momentum+sector blend candidate (evidence-gated)

_Per ADR 0014 + the SEC-001 gate. 12-1 frozen (no optimization). Whatever the verdict, the evidence package is the deliverable — the Evidence Engineering moat._
