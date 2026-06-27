# PORT-001 Evidence Package — v1.0 (Onboarding Gate, Construction-Verification)

| Field | Value |
|---|---|
| Capability | **PORT-001 — "Risk-Balanced Multi-Asset Portfolio"** (Combined Book) |
| Evidence type | Reproduction / Onboarding Gate (ADR 0030 §4; the Capability Onboarding lifecycle) |
| Date | 2026-06-27 |
| Result | **Onboarding Gate PASSED** — Lifecycle Fidelity **98.8%**, 6/6 criteria |
| Scope | **Construction-verification** — the platform's PCE/ERC reproduces the origin combined book from the origin's own sleeve return series. The self-stack (Alpaca total-return + platform momentum) end-to-end data-fidelity port is a separate tracked study. |
| Reproducible by | `apps/backend/scripts/run_port001_reproduction.py --from-sibling <claude-trading-view>` |
| Artifacts | `port001_construction_verification.json` (full gate result) · `LifecycleFidelity_CONSTRUCTION_VERIFICATION.md` (scorecard) · `sibling_reference.json` (origin reference) |

## What was reproduced

The origin (sibling `claude-trading-view`) Combined Book is two sleeves blended at a **fixed 0.40 equity + 0.60 cross-asset**:
- **Equity sleeve** — crash-protected 12-1 momentum, 150 names, monthly, vol-target 12% (`factor_backtest_2026-06-25.json`, `results.crash_engine.daily`, 2604 days, Sharpe 0.835).
- **Cross-asset sleeve** — 8-ETF TSMOM (SPY/EFA/EEM/TLT/IEF/GLD/DBC/UUP), risk-parity, vol-target 10% (`cross_asset_momentum_2026-06-15.json`, `results.daily`, Sharpe 0.704).

**Construction-verification** (the chosen reproduce-first approach) feeds the origin's *own* committed daily sleeve return series through the **platform's** Portfolio Construction Engine (`construct_portfolio` / `portfolio_evidence_package` — multi-sleeve ERC + look-through evidence) and compares the result to the origin combined book through the **Onboarding Gate**. This isolates the *construction engine being onboarded* from data-source noise (the origin priced cross-asset off Yahoo; the platform's stack is Alpaca + Sharadar — a deliberate divergence per ADR 0030 #2, validated separately).

Common window: **2016-02-04 → 2026-06-11** (2,603 trading days).

## Onboarding Gate scorecard

| Criterion | Candidate (Workbench PCE) | Reference (origin) | Δ / value | Threshold | Pass |
|---|---|---|---|---|---|
| Sharpe | 0.9001 | 0.9015 | 0.0014 | ±0.05 | ✓ |
| Max drawdown | 0.1166 | 0.1157 | 0.0009 | ±0.02 | ✓ |
| Daily-return corr | — | — | **0.99994** | ≥0.98 | ✓ |
| Weight corr | — | — | **0.99981** | ≥0.99 | ✓ |
| Trade count | 0 | 0 | n/a (construction-verification feeds return series; no rebalance sim) | ±10% | ✓ |
| Determinism | — | — | identical inputs → identical outputs | required | ✓ |

**Lifecycle Fidelity: 98.8%.** The platform's ERC blend **independently lands at equity 0.41 / cross_asset 0.59** — i.e. it re-derives the origin's pinned 40/60 from the sleeve covariance, rather than being told it. The combined daily-return stream tracks the origin at 0.99994 correlation; Sharpe and max-drawdown match within tolerance.

## Honest verdict (carried on every artifact — spec §6)

**Crash-protected BETA + diversification, NOT alpha.** Combined-book residual alpha is statistically insignificant (t = 0.82); the equity sleeve's stock-selection alpha was **refuted under point-in-time data**. The product's value is drawdown reduction (origin MaxDD −11.6% vs equity-only −23.5%) and diversification, not selection skill. The #1 operational risk is the **diversification thesis weakening** (sleeve correlation 0.68 → 0.77).

## Method notes & honest caveats

1. **Two harness bugs were found and fixed by this run** (not tuned to pass — the underlying data matched throughout): (a) the gate compared the candidate's *negative* drawdown to a *positive* reference, spuriously doubling the diff → now compares **magnitudes**; (b) `construct_portfolio` upper-cases ticker keys, so a differently-cased reference weight anti-correlated → `_aligned` now **upper-cases both sides**. Both are covered by regression tests.
2. **Weight reference** uses the origin's live look-through weights (§7, with the λ>0 correlation-aware tilt). The tilt is small at the sleeve level, so weight corr is 0.99981; a λ=0 untilted reference would be even closer. This does not affect the return-stream criteria.
3. **Scope boundary.** This is construction-verification. It does **not** assert the platform's *own data stack* reproduces the book end-to-end — that is the self-stack study (`--db` real mode: Sharadar momentum + the §1 Total-Return Adapter over Alpaca), which will read against a looser, attributed tolerance because it crosses data vendors (Alpaca vs Yahoo) and rebalance cadence.

## What this advances

Onboarding Gate **L1 + L2 = ✅** (construction). `programs.py` status promoted **planned → validated**. Capability Certificate re-issued **v1.0 (Gate-Passed)**. Next: §4 live `combined_book` template + dedicated paper account (L3, owner-gated); the self-stack data-fidelity study; §5 Continuous Evidence (L4).
