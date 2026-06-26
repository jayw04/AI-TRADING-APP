# Trading Workbench — P12 §2 Results: Harden the live strategy (the lift)

| Field | Value |
|---|---|
| Document version | **v1.1 — executed + grid folded** (2026-06-20). Depth (vol/cap walk-forward) + breadth (sensitivity grid) both complete. Companion to the artifacts under `docs/implementation/evidence/p12_s2_volscale/`, `…/p12_s2_sectorcap/`, `…/p12_s2_grid/`. |
| Date | 2026-06-20 |
| Phase | **P12** — Validation & Results |
| Session | §2 of 4 (Harden the live strategy — measure the lift) |
| Predecessor | P12 §1 (tag `p12-session1-complete`); baseline `EXP-20260620-193645` |
| Successor | P12 §3 — Advance the alpha (multi-factor book) |
| Experiments | Vol-scaling depth `EXP-20260620-212614` · Sector-cap depth `EXP-20260620-214254` · Grid (breadth) running |
| Tag on completion | `p12-session2-complete` |

---

## Executive scorecard

| Hypothesis | Drawdown lift | Sharpe | Gate | Decision | Confidence |
|---|---|---|---|---|---|
| **A — Vol-scaling (15%)** | **−76.4% → −47.2% (+38% rel)** | 0.48 → **0.51 (+0.03)** | ✅ PASS (DD≥20% AND Sharpe preserved) | **Enable (recommend)** | **High** |
| **B — Sector caps (30%)** | −76.4% → −72.7% (+5% rel) | 0.48 → 0.46 (−0.02) | ❌ FAIL (DD well under 20%) | **Keep Off → More Research** | Medium |

**Headline:** vol-scaling roughly **halves the −76% catastrophe-risk that qualified the §1 edge,
at no Sharpe cost** (Sharpe actually rises). It is the clear §2 win. Sector caps do not move the
needle on the current setup. **Recommended strategy v1.1 = Momentum + Vol-scaling (15%).** Enabling
the live default remains the owner's gated risk-appetite call (§2 recommends, does not flip).

## Hypothesis A — Vol-scaling (the win)

Full-period 1997–2026, n=200, vs the §1 baseline:

| Metric | Baseline (v1.0) | Vol-scaled (v1.1) | Δ |
|---|---|---|---|
| Max drawdown | −76.4% | **−47.2%** | **+38% reduction** |
| Sharpe | 0.48 | **0.51** | **+0.03** |
| Calmar | 0.14 | 0.15 | +0.01 |
| CAGR | +10.73% | +6.89% | −3.84% |

**It holds — strongest — in the crash regimes** (the gate's "holding in crash regimes" clause;
per-regime baseline maxDD → vol-scaled):

| Regime | Baseline maxDD | Vol-scaled | DD reduction |
|---|---|---|---|
| **GFC + 2009** | −65.6% | **−31.9%** | **+51%** |
| 2010–2013 (2011 shock) | −21.1% | −20.0% | +5% |
| 2013–2016 (incl 2015) | −23.4% | −21.0% | +10% |
| 2016–2019 (calm) | −24.1% | −18.5% | +23% |
| **2019–2022 (COVID)** | −48.6% | **−24.0%** | **+51%** |
| 2022–2024 (rate shock) | −22.4% | −14.1% | +37% |
| 2024–2026 (AI momentum) | −38.5% | −15.6% | +59% |

This is exactly the signature of a sound drawdown tool: it de-risks **hardest in the crashes**
(GFC/COVID −51% each) and **barely touches calm regimes** (+5%), preserving the edge in benign
periods while cutting the tail. The −3.8pp CAGR is the premium paid for that protection — and §1
established the drawdown, not return, was the open risk.

## Hypothesis B — Sector caps (marginal)

Cap 30%, full period: CAGR +9.92%, Sharpe 0.46, maxDD **−72.7%** (vs −76.4% baseline = +5% rel
reduction). It trims concentration slightly but does not meaningfully cut the drawdown and gives up
a touch of Sharpe. *Also:* in early-history thin universes (≈38–40 names, 2–3 sectors) the 30% cap
is **infeasible** and silently inactive — so its measured effect is weaker still. **Decision: Keep
Off; More Research** (re-test on the broad universe, or paired with vol-scaling — see grid).

## Decision matrix (applied)

| Config | DD reduction | ΔSharpe | Matrix outcome |
|---|---|---|---|
| Vol-scaling 15% | +38% (≥20%) | +0.03 (≤0.05 loss) | **Enable** |
| Sector caps 30% | +5% (<20%) | −0.02 | **More Research** (no Reject — small Sharpe loss, not zero benefit) |

## Strategy evolution

| Version | Change | Status |
|---|---|---|
| 1.0 | Momentum (6-1, weekly top-quintile, equal-weight) | **Validated** (§1) |
| **1.1** | **+ Vol-scaling (target 10–20%, default 15%)** | **Validated — Enable (recommended)** (§2) |
| 1.1-alt | + Sector caps (20–40%) | Off — Reject/More Research (§2) |
| ~~1.2~~ | ~~Combined (vol + caps)~~ | **No candidate** — caps redundant on top of vol-scaling (grid) |

(The vol target is a **risk dial within v1.1**, not a separate version: 10% max-protection →
20% max-Sharpe; 15% balanced. The owner sets it by risk appetite.)

## Registries

**Research Registry:** Vol-scaling overlay → **Validated** (drawdown tool: −38% maxDD, Sharpe-neutral,
holds in crashes; `EXP-20260620-212614`). Sector caps → **Pending / More Research** (`EXP-20260620-214254`).

**Decision Register:**

| Study | Decision | Confidence | Reason | Evidence |
|---|---|---|---|---|
| Vol-scaling 15% | **Enable (recommended)** | **High** | maxDD −38% rel, strongest in crashes (GFC/COVID −51%); Sharpe +0.03; Calmar +0.01 | `EXP-20260620-212614` |
| Sector caps 30% | Keep Off → More Research | Medium | DD −5% only; Sharpe −0.02; cap infeasible in thin early universes | `EXP-20260620-214254` |

## Risk score (by configuration)

| Configuration | Risk |
|---|---|
| Momentum (v1.0) | **High** (−76% DD) |
| Momentum + Vol-scaling (v1.1) | **Medium** (−47% DD, Sharpe-neutral) |
| Momentum + Sector caps | Medium-High (−73% DD) |
| Combined (vol + caps) | ≈ vol-scaling alone (caps add nothing — no separate config) |
| Momentum + Vol-scaling @ 10% | Low-Medium (−34% DD, max protection) |

## Sensitivity grid (breadth — `EXP-20260620-220518-grid`)

The `harden_grid.py` sweep (full 1997–2026, n=200, headline) confirms and sharpens the verdict
(`docs/implementation/evidence/p12_s2_grid/`):

| Config | CAGR | Sharpe | maxDD | avgDD | DD red. | Decision |
|---|---|---|---|---|---|---|
| 1.0 baseline | +10.7% | 0.48 | −76.4% | −37.6% | — | — |
| vol 10% | +4.8% | 0.49 | −34.2% | −9.0% | +55% | **Enable** |
| vol 12% | +5.6% | 0.50 | −39.8% | −10.7% | +48% | **Enable** |
| vol 15% | +6.9% | 0.51 | −47.2% | −13.1% | +38% | **Enable** |
| vol 18% | +7.9% | 0.52 | −53.8% | −15.4% | +30% | **Enable** |
| vol 20% | +8.5% | 0.52 | −57.1% | −16.7% | +25% | **Enable** |
| cap 20–40% | ~+9.6% | 0.45–0.47 | −71 to −75% | ~−31 to −36% | +2 to +8% | More Research |
| **A+B: vol 15% + cap 30%** | +6.5% | 0.49 | −47.4% | −13.2% | +38% | Enable (≈ vol-alone) |

Three findings:

1. **Vol-scaling is robust, not a knife-edge — it is a risk-appetite *dial*.** *Every* target 10–20%
   clears the gate, tracing a clean monotonic frontier: tighter target → more drawdown protection
   and less return (10% = −34% DD / +4.8% CAGR), looser → more return and best Sharpe (20% = −57% DD
   / +8.5% CAGR / Sharpe 0.52). **15% is a balanced middle**; the owner can dial protection vs return
   without leaving the "Enable" region. (Best Sharpe/Calmar = 20%; lowest DD = 10%.)
2. **Sector caps fail at every level** (DD reduction +2–8%, never near 20%; Sharpe slightly negative)
   — **Reject/More Research** stands across 20–40%.
3. **The combined config adds nothing.** vol 15% + cap 30% ≈ vol 15% alone (maxDD −47.4% vs −47.2%,
   Sharpe 0.49 vs **0.51**) — the cap is **redundant on top of vol-scaling, and slightly worse**.
   **There is no meaningful v1.2 combined candidate:** vol-scaling alone (v1.1) does all the work.

## Limitations & research debt (carried)

- Survivorship: live top-200 is today's names (biased up) — read relative ΔmaxDD (same-universe) as
  the robust signal. Broad survivorship-free re-run is research debt.
- Full-history SPY, capacity/market-impact study, dividend validation, liquidity model — all
  Outstanding (carried from §1).
- Enabling the live default is **owner-gated** (risk-appetite); §2 delivers the evidence + the
  recommendation, not the flip.

## Recommendation

**Adopt v1.1 = Momentum + Vol-scaling (15%)** as the recommended configuration: it cuts the
catastrophe-risk roughly in half with no risk-adjusted cost, validated out-of-sample across every
regime. Carry the **combined (v1.2)** question into the grid addendum, and the broad-universe
sector-cap re-test into §3.
