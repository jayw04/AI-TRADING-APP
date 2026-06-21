# Trading Workbench — P12 §3 Results: Multi-factor (infrastructure + exploratory)

| Field | Value |
|---|---|
| Document version | **v1.0 — executed** (2026-06-20). Companion to `docs/implementation/evidence/p12_s3_explore/`. |
| Date | 2026-06-20 |
| Phase | **P12** — Validation & Results |
| Session | §3 of 4 (Advance the alpha — multi-factor book) |
| Predecessor | P12 §2 (tag `p12-session2-complete`); momentum v1.1 |
| Successor | P12 §4 — Operational-proof window / phase close (Strategy Evidence Book + Platform Capability Report) |
| Experiment | Exploratory `EXP-20260621-002659-mf` (FMP, 2021–2026, n=200) |
| Tag on completion | `p12-session3-complete` |

---

## Executive scorecard — three kinds of success

| Dimension | Result |
|---|---|
| **Engineering** | ✅ **Complete** — composite engine + factor-agnostic backtest, 9 tests, ruff/mypy clean |
| **Platform** | ✅ **Validated** — any factor/blend is now researchable, comparable, governable through one harness, no arch change |
| **Research (investment)** | 🟡 **Inconclusive** — multi-factor *looks* better on FMP data but not decisively; **Deferred → SF1** |

**Headline:** §3's durable win is the **platform** — the reusable multi-factor research capability.
The **investment** signal is *promising but inconclusive*: on the testable data a momentum + value/
quality book improved risk-adjusted return, but the evidence cannot settle it. Keep **v1.1**; the
signal **justifies acquiring SF1** for a verdict.

## Deliverable A — Research infrastructure (✅ shipped)

- **`composite_scores()`** — blends standardized (winsorize + z-score) factors (momentum + the 7
  value/quality factors) equal-weight; missing-factor impute(z=0)/drop; PIT + deterministic.
- **`factor_zscores()`** — the tickers × factors z-matrix (the correlation-matrix input).
- **Factor-agnostic backtest** — `run_momentum_backtest(score_fn=…)`; default = momentum,
  byte-identical to §1/§2. The §1 harness now backtests *any* factor/composite.
- **9 tests** (momentum-order match, roe ranks by fundamentals, impute/drop, FactorUnavailable,
  default == momentum, accepts composite score_fn, z-matrix shape). ruff/mypy clean.

## Deliverable B — Exploratory validation (FMP — *current evidence, not a verdict*)

> **Caveats (load-bearing):** fundamentals are FMP — **~5 yr, top-200 mega-cap, NOT survivorship-
> free, one regime** (2021–2026, incl. the value-favorable 2022). This is *exploratory*; it cannot
> settle the value/quality question.

### Factor-correlation matrix (the reason §3 exists)

Averaged over 43 monthly cross-sections:

- **corr(momentum, value) = −0.044**, **corr(momentum, quality) = +0.003** → **near-zero.**

On this universe/window, value/quality are *genuine diversifiers* of momentum (near-uncorrelated) —
**not** the strongly-negative "momentum's opposite" the earlier mega-cap study found. (Different
question + window: the prior measured each factor's standalone IC/LS-Sharpe OOS 2023–26; this
measures the blended **book's** risk-adjusted return 2021–2026.)

### Composite vs momentum

| Book | CAGR | Sharpe | Max DD | Calmar |
|---|---|---|---|---|
| Momentum (v1.1 base) | +29.27% | 1.00 | −38.8% | 0.75 |
| **Multi-factor (mom + value + quality)** | +25.31% | **1.23** | **−21.4%** | **1.18** |

The multi-factor book improved Sharpe (**+0.23**), **roughly halved the drawdown** (−38.8% → −21.4%),
and lifted Calmar (0.75 → **1.18**), at ~4pp of CAGR — value/quality de-risking momentum's crashes.

### …but it is **not decisive**

The multi-factor Sharpe 95% CI is **[0.46, 2.00]** — *wide, and it overlaps momentum's 1.00*. Over a
~5-yr single-regime mega-cap window the improvement is **not statistically distinguishable from
noise**. Combined with the survivorship/regime caveats: **promising, not proven.**

## Decision (success matrix)

| Outcome on the testable data | Research state | Action |
|---|---|---|
| Multi-factor *looks* better (Sharpe +0.23, DD halved) but CI overlaps + data-limited | **Inconclusive** | **Deferred → acquire SF1**; keep v1.1; do **not** build v2.0 |

**Research Registry:** Value, Quality, Multi-factor composite → **Inconclusive** (promising on FMP;
decisive verdict gated on SF1). `EXP-20260621-002659-mf`.

**Decision Register:**

| Study | Decision | Confidence | Reason | Evidence |
|---|---|---|---|---|
| Multi-factor (mom+value+quality) | **Deferred** (keep v1.1) | Low (data-limited) | Sharpe +0.23 / DD halved BUT CI [0.46,2.00] overlaps momentum; ~5yr, 1 regime, mega-cap, non-survivorship-free | `EXP-20260621-002659-mf` |

## The two conclusions (different audiences)

- **Investment conclusion** (*should we trade this?*): On the testable FMP data, a momentum + value/
  quality book **appears** to improve risk-adjusted return — value/quality are near-uncorrelated
  diversifiers that halve the drawdown. But the evidence is **Inconclusive** (wide CI, one regime,
  mega-cap, ~5 yr). **Momentum v1.1 remains the production book; no v2.0.** The promising signal is
  strong enough to **justify the SF1 data investment** for a decisive verdict — a *positive*
  exploratory outcome, not a flat rejection.
- **Platform conclusion** (*why adopt TradingWorkbench?*): The composite multi-factor engine + the
  factor-agnostic backtest are **validated on real fundamentals data**. Any factor or blend
  (momentum · value · quality · growth · low-vol · ESG · custom · AI) is now researchable,
  comparable, and governable through the same harness **with no architectural change** — and the
  platform produced an honest *Inconclusive*, which is itself a credibility signal.

## Research-debt table

| Item | Blocking the verdict? | Priority |
|---|---|---|
| **SF1 (deep, broad, survivorship-free fundamentals)** | **Yes** — the decisive value/quality verdict | **High** |
| Broader-universe FMP ingest (top-500/1000) | Partially (extends breadth, not depth/survivorship) | Medium |
| Capacity / market-impact study | No | Medium |
| Liquidity model · dividend validation | No | Low |

## Platform-value matrix — every outcome created value

| This session's outcome | Investment value | Platform value |
|---|---|---|
| Multi-factor **Inconclusive** (promising, undecisive) | Keep v1.1; justifies SF1 | ✅ Composite engine + factor-agnostic backtest validated; honest *Inconclusive* demonstrated |

## Recommendation

**Bank the platform; defer the verdict.** Ship the composite engine + factor-agnostic backtest
(done). Record the multi-factor signal as **Inconclusive → Deferred**, and treat **SF1 acquisition**
as the High-priority research-debt item that converts a *promising* signal into a *decisive* one.
Proceed to **§4 (operational-proof window)** and the two P12 final deliverables (Strategy Evidence
Book + **Platform Capability Report**).
