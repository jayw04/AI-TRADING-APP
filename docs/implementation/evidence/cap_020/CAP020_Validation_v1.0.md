# CAP-020 Regime-Overlay Validation — Result v1.0

| Field | Value |
|---|---|
| Study | CAP-020 (FI-001 Phase 4 `regime_gross`): eqw combined book, gross → g when proxy < N-day SMA |
| Plan | `TradingWorkbench_FI001_CAP020_RegimeOverlayValidation_v0.2.md` (owner-approved 9.7/10) |
| Harness | `scripts/cap020_regime_validation.py` (+ `tests/scripts/test_cap020_regime_validation.py`, 17 tests) |
| Date | 2026-07-04 |
| **Verdict** | **Inconclusive (data-gated)** — CAP-020 remains *"Promising, not Validated."* |

## Bottom line

The validation harness is built, tested, and correct, and was run against the live-box factor store
(`data/factor_data.duckdb`, bounds 1997-12-31…2026-06-12). It returns **Inconclusive (data-gated)**: the
factor store does **not** contain enough overlapping multi-book history to validate a *regime* overlay.

The equal-weight combined book requires all four validated books (momentum / low-vol / trend / sector)
to have returns on the same days. In this store, low-vol / trend / sector have **no usable rebalances
before ~2024-05** (`backtest_skipped_thin_rebalances` — 283–309 skipped per book, last skip 2024-05-31),
so the four-book intersection collapses to:

- **Usable window: 2024-12-10 → 2026-06-12 (1.5 years, 377 daily marks).**
- **1 regime flip** in the OOS segment (the overlay essentially never acts).
- **No drawdown/bear environment** in the window (2024-25 was a strong bull).

A regime overlay whose entire purpose is to de-risk in bear regimes **cannot be validated on a window
that contains no bear regime.** The harness's data-sufficiency gate (≥ 4y usable window, ≥ 4 OOS flips,
≥ 1 bear environment) correctly refuses to issue a deployment verdict on this sliver.

## Descriptive numbers (NOT a verdict — the window is data-gated)

At the headline point (SMA 200, gross 0.5, 10 bps, OOS 2025-08…2026-06):

| Metric | Value | Read |
|---|---|---|
| ΔMaxDD vs eqw | **+5.22 pp** reduction, CI [3.65, 11.04] | drawdown reduction *is* significant even here |
| ΔCalmar vs eqw | −0.30, CI [−4.29, 1.12] | **CI spans zero** — no Calmar improvement |
| ΔSharpe | +0.08 | ~flat |
| ΔCAGR | **−32.2 pp** | de-risking in a raging bull = pure drag |
| Robustness | **0 / 9** grid cells pass | — |

These are exactly what a bull-only, one-flip window produces: the overlay trims a shallow drawdown (so
ΔMaxDD is "significant") but forfeits a third of the CAGR, so Calmar does not improve. **Do not cite
these as CAP-020's performance** — they are an artifact of the data gate, not a measurement of the edge.

## Root cause & the Phase 4 discrepancy

FI-001 Phase 4 reported CAP-020 over "2019–2026" (Sharpe 1.17, maxDD −24%). This run's four-book
overlap is only 2024-12→2026-06. Either the factor store has changed since Phase 4 executed (factor
ingestion depth for low-vol/trend/sector), or Phase 4's equal-weight book was itself computed over a
similarly-intersected window and its date range labels the *request*, not the *usable* span. **Flagged
to verify** — it does not change this study's conclusion (the current store is data-gated) but it should
be reconciled before Phase 4's numbers are cited as the CAP-020 baseline. See [[factor_data_staleness_gap]].

## What the real validation needs

A factor store with **≥ 4 years of overlapping low-vol / trend / sector history that includes the 2020
and 2022 drawdowns.** Concretely: deepen the factor-store ingestion for those three books (SF1 / DAILY
depth — subject to the Sharadar 2016Q1 floor, see the data-access memory) so the four-book intersection
spans at least 2018–2026. The harness then produces a real Validated / Conditionally-Promising /
Rejected verdict **with no code change** — it is ready and waiting on data.

## Decision

- **CAP-020 stays "Promising, not Validated"** (registry unchanged on the merits).
- The registry entry is annotated: *validation attempted 2026-07-04, Inconclusive (data-gated) — harness
  ready, blocked on ≥4y overlapping multi-book history incl. bear regimes.*
- Durable deliverables: the reproducible validation harness + data-sufficiency gate + the owner-approved
  acceptance framework (Calmar-primary hierarchy + deployment decision matrix). This mirrors PORT-001,
  where the reproduction harness shipped ahead of the data-gated real reproduction.

## Reproducibility

| | |
|---|---|
| git commit | (run in-container; harness committed at the PR below) |
| python | 3.12.13 · numpy 2.2.6 · pandas 2.3.3 · scipy n/a |
| bootstrap seed | 17 (fixed → deterministic CIs) |
| dataset | factor store 1997-12-31…2026-06-12, universe n=150, sector coverage 21,679; usable book days 377 |
| artifact | `data/cap020/cap020_validation_results.json` (on the box) |

_v1.0 — 2026-07-04. Companion to the plan doc; evidence for the FI-001 registry CAP-020 line._
