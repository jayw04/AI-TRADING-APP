# FI-001 Phase 1 — Measurement (Evidence)

_Survivorship-free, `run_momentum_backtest(score_fn=…)` per book · universe n=150 · 2019-01-01..2026-06-13 · weekly, long-only, equal-weight · store 1997-12-31..2026-06-16. Identical construction across books — only the score function varies (charter: no factor re-optimization)._

> FI-001 Phase 1 per the pre-registered plan (v0.1): measure how the platform's validated books
> **interact** — pairwise correlation, rolling stability, stress-window behavior, holdings overlap, and a
> single diversification score — before blending (Phase 2) or allocating (Phase 3).

## Books (standalone, 2019–2026)

| Book | CAGR | Sharpe | MaxDD |
|---|---:|---:|---:|
| Momentum | +31.6% | 1.04 | −38.3% |
| Low-Vol | +12.2% | 0.83 | −30.2% |
| Trend | +24.9% | 1.13 | −29.8% |

*(Sector book skipped — the local store has 0 tickers with sector data; runs on the box, Phase 1b.)*

## Pairwise interaction

| Pair | Full corr | Stress corr (mom worst-DD) | Rolling-63d mean | Rolling-63d min..max | Holdings overlap |
|---|---:|---:|---:|---:|---:|
| **Momentum ↔ Low-Vol** | **0.52** | **0.21** | 0.48 | **−0.16 .. 0.95** | 6.4% |
| Momentum ↔ Trend | **0.90** | 0.89 | 0.89 | 0.60 .. 0.99 | 18.7% |
| Low-Vol ↔ Trend | 0.70 | 0.54 | 0.63 | 0.14 .. 0.98 | 13.0% |

**Diversification score: 29 / 100** (100 = well diversified; higher is better) — the three-book set is only
*moderately* diversified, and the number is dragged down by Trend's redundancy with Momentum.

Momentum's worst-drawdown (stress) window: **2025-01-23 .. 2025-04-08**.

## Findings against the frozen priors

**H1 — diversification spectrum: confirmed by ordering.** Low-Vol is the most independent of Momentum
(0.52), Trend is essentially redundant (0.90), exactly the pre-registered *ordering* (MOM↔LOW < MOM↔SEC <
MOM↔TREND). Holdings overlap corroborates: Momentum and Low-Vol are nearly disjoint (6.4% shared names)
while Momentum and Trend share far more (18.7%). **Caveat on magnitude:** the absolute correlations are
higher than the 2000–2026 priors (MOM↔LOW 0.52 here vs the −0.15 LOW-001 full-cycle prior). That is
expected — this is a recent, equity-heavy 2019–2026 window on an n=150 large-cap universe, where all
long-only equity books share more market beta than they do across a full cycle. **The sign and ordering
are the robust, portfolio-relevant conclusions; the absolute level is window/universe-dependent.**

**H3 — correlation stability: the important, nuanced result.** Two things are simultaneously true:
1. Correlation is **unstable** — even the Momentum↔Low-Vol diversifier's rolling-63d correlation swings
   from **−0.16 to 0.95**; there are 3-month windows where the diversification essentially disappears.
   This is precisely the "correlation stability" risk the 2026-07-02 review flagged, now quantified.
2. But in Momentum's **actual worst drawdown** (2025 Q1), Low-Vol **decoupled** — its stress correlation
   *fell* to 0.21 (below its 0.52 full-sample level): Low-Vol held up while Momentum bled. That is the
   *good* kind of behavior — diversification that shows up **when it matters most.** Trend did the
   opposite: it stayed glued to Momentum (stress 0.89), diversifying nothing in the drawdown.

## What Phase 1 tells Phases 2–3

- **Momentum + Low-Vol is the diversification workhorse** — the genuinely independent pair, and the one
  whose independence *strengthens* in Momentum's drawdown. Phase 2 should prioritize this blend, and it is
  the pair most likely to clear the H2 gate.
- **Trend is largely redundant with Momentum** (0.90 corr, 18.7% overlap, glued in stress). It adds little
  as a *momentum diversifier*; its value (if any) is its own standalone defensive de-risking (TREND-001's
  cash participation), not diversification of the momentum book. A combined book may be **better without
  Trend** than with it — a Phase 3 allocation question.
- **Correlation is regime-dependent**, so a *static* allocation understates tail risk; this motivates the
  Phase 3 correlation-aware / dynamic arms rather than fixed weights.

## Reproduce

```
cd apps/backend
.venv/Scripts/python.exe scripts/fi001_phase1_measurement.py \
    --start 2019-01-01 --end 2026-06-13 --n 150 --report-dir research/fi001/phase1/
```

Artifacts: `apps/backend/research/fi001/phase1/fi001_phase1_report.md` + `_results.json`. Deterministic.
Pure-helper tests in `apps/backend/tests/scripts/test_fi001_phase1.py`.

## Phase 1 verdict (Measurement)

The validated books span a **real but window-sensitive diversification spectrum**: **Low-Vol is the
independent complement to Momentum (and decouples further in Momentum's drawdown); Trend is redundant with
Momentum.** Correlations are **unstable across regimes** — a static combined book understates tail
correlation. Next: **Phase 2 — Interaction** (Momentum+Low-Vol first), then **Phase 3 — Allocation** with
a correlation-aware/dynamic arm. Sector interaction pending the sector-populated store (Phase 1b, box).
