# TREND-001 Trend Following — Evidence (B - Diversifier / Defensive)

_git b335c6e · EXP-20260624-161616-trend001 · SEP survivorship-free (full-cycle 2000-2026) · 2000-01-01..2026-06-12 · n=200 · V1 per-name close>200d SMA, in-trend equal-weight (1/N), cash rest · 3521.2s_

> Pre-registered (TREND-001 plan v0.2). The question: *does a per-name time-series trend signal add value beyond the portfolio-level regime filter the platform already runs?* — standalone edge (H1), incremental diversifier (H2), or downside/participation (H3). Honest prior: the existing SPY-regime filter already de-risks the book, so Rejected (40%) was the modal pre-registered outcome.

## Books

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| Equal-weight (benchmark) | +5.63% | 0.35 | -69.2% | 0.08 |
| Momentum (v1.1) | +7.39% | 0.39 | -76.4% | 0.10 |
| **Trend Following** | +4.73% | 0.46 | -46.2% | 0.10 |
| Momentum+Trend blend | +6.80% | 0.43 | -62.6% | 0.11 |
| Regime-filter eqw (control) | +4.90% | 0.39 | -61.1% | 0.08 |

Participation: trend gross exposure mean **0.618**, min **0.015** (falls in downtrends = the mechanism).

## H1 — standalone risk-adjusted edge (trend vs equal-weight)
- **dSharpe +0.11, paired 95% CI [-0.111, 0.33]** — includes zero -> no standalone edge.
- Walk-forward: trend beats equal-weight in **4/5** windows.

## H2 — diversifier (correlation / blend)
- corr(momentum, trend) = **0.871**.
- blend vs momentum-alone dSharpe +0.04, CI [-0.095, 0.165].

## H3 — downside protection & the competing-explanation A/B
- trend maxDD vs momentum: **+30.2%** (positive = shallower).
- trend maxDD vs equal-weight: **+23.0%**.
- **vs the existing regime filter** — maxDD +14.9%, Sharpe +0.06: per-name trend BEATS the portfolio-level filter.
- shallower drawdown than equal-weight in **5/5** windows.

## Cost sweep (trend Sharpe)
  5bps 0.47 · 10bps 0.46 · 20bps 0.43 · 50bps 0.35

## Outcome: **B - Diversifier / Defensive** → participation sleeve / momentum+trend blend candidate (evidence-gated)

_Per ADR 0014 + the TREND-001 gate. 200-day SMA frozen (no optimization). No parameter introduced solely to improve historical performance. The evidence package is the deliverable._