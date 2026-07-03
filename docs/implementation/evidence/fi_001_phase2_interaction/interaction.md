# FI-001 Phase 2 — Interaction (Evidence)

_Survivorship-free, `run_momentum_backtest(score_fn=…)` per book · equal-weight return-level blends · n=150 · 2019-01-01..2026-06-13 · weekly, long-only, equal-weight · store 1997-12-31..2026-06-16. H2 gate = paired circular-block Sharpe-diff bootstrap CI vs standalone momentum._

> FI-001 Phase 2 per the pre-registered plan: does **combining** the validated books help? Each pair
> (and the 3-way set) is blended 50/50 (equal-weight daily returns) and tested against standalone
> Momentum on the platform's H2 gate — Δ-Sharpe CI must exclude zero for a real risk-adjusted uplift.

## Standalone books (2019–2026)

| Book | CAGR | Sharpe | MaxDD | Calmar |
|---|---:|---:|---:|---:|
| Momentum | +31.5% | 1.04 | −38.3% | 0.82 |
| Low-Vol | +12.0% | 0.83 | −30.2% | 0.40 |
| Trend | +24.8% | 1.13 | −29.8% | 0.83 |

## Blends vs standalone momentum

| Blend (eqw) | CAGR | Sharpe | MaxDD | Calmar | ΔSharpe vs mom [95% CI] | ΔMaxDD (pp) | Verdict |
|---|---:|---:|---:|---:|---:|---:|---|
| Momentum + Low-Vol | +22.4% | 1.10 | −31.1% | 0.72 | **+0.054** [−0.163, 0.333] | **+7.1** | Diversifies (DD-only) |
| Momentum + Trend | +28.4% | 1.11 | −31.9% | 0.89 | **+0.064** [−0.069, 0.215] | **+6.4** | Diversifies (DD-only) |
| Low-Vol + Trend | +18.6% | 1.09 | −29.8% | 0.62 | +0.046 [−0.371, 0.602] | +8.5 | Diversifies (DD-only) |
| **Momentum + Low-Vol + Trend** | +23.3% | **1.13** | **−30.7%** | 0.76 | **+0.081** [−0.153, 0.372] | **+7.6** | Diversifies (DD-only) |

## H2 verdict: **Diversification Confirmed (DD-only)** — the pre-registered modal outcome

Every blend does the same two things: it **materially reduces drawdown** (6.4–8.5pp shallower than
standalone momentum's −38.3%) while delivering a **small, positive, but not statistically decisive Sharpe
uplift** (+0.05 to +0.08; every CI spans zero). This is exactly the H2 prior — and the platform's
consistent pattern across MF-001 / SEC-001 / LOW-001 blends: **combining independent-ish books buys risk
reduction, not alpha.** The gate holds the line: no blend earns an "IMPROVES" (Sharpe-CI-excludes-zero)
verdict, so none is promoted as a risk-adjusted *edge*.

The **3-way equal blend (Momentum + Low-Vol + Trend)** is the best all-round book: the highest blend
Sharpe (1.13, nudging past standalone momentum's 1.04), a drawdown 7.6pp shallower, at a CAGR give-up
from 31.5% to 23.3%. For a drawdown-sensitive allocator that give-up may be worth it; for a
Sharpe-maximizer the evidence does not (yet) justify leaving standalone momentum.

## Nuance: Trend diversifies by *timing*, not by low correlation

Phase 1 flagged Trend as **correlation-redundant** with Momentum (0.90). Phase 2 refines that read:
Momentum + Trend still **cuts drawdown 6.4pp** and has the **tightest ΔSharpe CI** [−0.069, 0.215] of any
pair. Trend reduces drawdown not by being *uncorrelated* day-to-day but by **de-risking to cash in
downtrends** (TREND-001's participation mechanism) — diversification via *drawdown timing*, a different
axis than return correlation. So the Phase 1 "Trend is redundant → drop it" read is too strong: Trend is
redundant on *correlation* but still *useful on drawdown*. Low-Vol remains the cleanest low-correlation
diversifier; Trend is a drawdown-timer. A combined book plausibly wants both, for different reasons.

## What Phase 2 hands to Phase 3

Equal-weight blending already delivers the drawdown benefit but **leaves the Sharpe gate uncleared**.
Phase 3 (Allocation) tests whether a *smarter* weighting can do better than naive equal weight:
- **ERC / risk-parity** — down-weight the higher-vol books; likely deepens the DD reduction.
- **Dynamic vol-targeting** — the overlay already in `run_momentum_backtest`; may lift Sharpe.
- **Correlation-aware** — motivated directly by Phase 1's finding that pairwise correlation is
  *regime-dependent* (Mom↔Low rolling-63d swings −0.16..0.95); a static blend understates tail
  correlation, so a correlation-adaptive weight is the most promising route to clearing the Sharpe gate.

## Reproduce

```
cd apps/backend
.venv/Scripts/python.exe scripts/fi001_phase2_interaction.py \
    --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase2/
```

Artifacts: `apps/backend/research/fi001/phase2/`. Deterministic (bootstrap seed 17). Pure-helper tests
in `apps/backend/tests/scripts/test_fi001_phase2.py`. Sector interaction pending the sector-populated
store (box).

## Phase 2 verdict (Interaction)

**Combining the validated books reduces drawdown ~6–8pp with a small, non-significant positive Sharpe
uplift — Diversification Confirmed, not an alpha edge.** Best equal-weight book = Momentum + Low-Vol +
Trend. Low-Vol diversifies by low correlation; Trend diversifies by drawdown timing. Next: **Phase 3 —
Allocation** (ERC / risk-parity / dynamic-vol / correlation-aware) to test whether a principled weight
clears the Sharpe gate or deepens the drawdown reduction beyond equal weight.
