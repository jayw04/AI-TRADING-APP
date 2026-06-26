# SEC-001 V2 Pure Sector Baskets — Evidence (B — Diversifier (confirmed))

_git 22f34f8 · EXP-20260622-010112-sec001v2 · SEP survivorship-free + Sharadar tickers.sector · 2000-01-01..2026-06-12 · n=200 · V2 sector-neutral top-3 equal-weight baskets · 1380 rebalances · 715.8s_

> Pre-registered (SEC-001 **V2** plan v0.2). V2 changes ONLY construction vs V1 (stock-level -> sector-neutral baskets); signal/universe/window/cost are V1's. Question: does construction turn the V1 **diversifier (B)** into a **standalone edge (A)**?

## Books

| Book | CAGR | Sharpe | maxDD | Calmar |
|---|---|---|---|---|
| All-sector baskets (H1 control) | +7.47% | 0.45 | -55.7% | 0.13 |
| Equal-weight universe (continuity) | +5.63% | 0.35 | -69.2% | 0.08 |
| Momentum (v1.1) | +7.39% | 0.39 | -76.4% | 0.10 |
| V1 — stock-level (prior) | +10.83% | 0.53 | -63.4% | 0.17 |
| **V2 — pure sector baskets** | +9.19% | 0.49 | -66.8% | 0.14 |
| Momentum+Sector blend (50/50) | +8.78% | 0.45 | -66.0% | 0.13 |

## H1 — standalone edge
- **vs all-sector baskets (primary): dSharpe +0.04, 95% CI [-0.165, 0.244]** — includes zero -> no standalone edge.
- vs equal-weight universe (continuity): dSharpe +0.14, CI [-0.056, 0.351].
- Walk-forward: V2 beats all-sector baskets in **4/5** windows.

## H2 — diversifier
- corr(sector signal, single-name momentum) = **0.378** (low = diversifier).
- 50/50 momentum+sector blend vs momentum-alone dSharpe +0.07, CI [-0.086, 0.22]; V2 maxDD -66.8% vs momentum -76.4%.

## H3 — construction isolation (read-only; informs the stopping rule)
- **dSharpe(V2 - V1) -0.04, CI [-0.179, 0.093]** — CI spans zero (construction-neutral).

## Robustness band (K, NOT tuned — headline K=3)
  K=2 Sharpe 0.50 · K=4 Sharpe 0.53 · K=3 Sharpe 0.49

## Cost sweep (V2 Sharpe)
  5bps 0.51 · 10bps 0.49 · 20bps 0.45 · 50bps 0.34

## Outcome: **B — Diversifier (confirmed)** → momentum+sector blend / overlay candidate (evidence-gated)

**Stopping rule:** ARCHIVE Sector Rotation construction: V2 did not achieve a standalone edge and H3 shows no construction benefit (dSharpe(V2-V1) CI spans zero). Per the v0.2 stopping rule, further work requires a fundamentally different hypothesis, not more construction tuning.

_Per ADR 0014 + the SEC-001 V2 gate. No parameter introduced solely to improve historical performance. Whatever the verdict, the evidence package is the deliverable._
