# CAP-020 Regime-Overlay Validation — Result v1.1

| Field | Value |
|---|---|
| Study | CAP-020 (FI-001 Phase 4 `regime_gross`): eqw combined book, gross → g when proxy < N-day SMA |
| Plan | `TradingWorkbench_FI001_CAP020_RegimeOverlayValidation_v0.2.md` (owner-approved 9.7/10) |
| Harness | `scripts/cap020_regime_validation.py` (+ 17 tests) |
| Data | Factor store **deepened to 2017** (Option A, active-name universe) — see `CAP020_DataDeepening_Scope_v0.1.md` |
| Date | 2026-07-04 |
| **Verdict (Option A)** | **Conditionally Promising** — the pre-committed escalation rule fires → **escalate to Option B** |

> *"This validation uses the active-name universe available in the current factor store. Results are suitable for engineering validation and research prioritization but are **not** considered the final survivorship-free evidence package. If the outcome is borderline, validation will be repeated using the full historical survivorship-free universe."*

## Arc: data-gated → deepened → real verdict

**v1.0 (data-gated):** the first run was Inconclusive — the store's 4-book overlap was only 1.5y
(2024-12→2026-06, bull-only, 1 flip) because SEP prices covered the universe only from 2024.

**Deepened (Option A):** re-ingested SEP for the ~1,254 active names back to 2017 (2.7M rows, one pass —
the rate limit never bit). The 4-book overlap now spans **2019-01 → 2026-06 (7.4y, 1,868 days)** with all
three environments present (**covid_2020, bear_2022, bull_2023_24**) and **14 regime flips**. The
data-sufficiency gate **clears** — this is a real study.

## Result (OOS 2022-08→2026-06, headline SMA 200 / gross 0.5 / 10 bps)

Benchmark (eqw, overlay OFF, OOS): CAGR 31.9%, Sharpe 1.39, MaxDD −24.9%, Calmar 1.28.

| Metric | Δ vs benchmark | CI | Read |
|---|---|---|---|
| **Calmar (primary)** | **−0.224** | [−1.15, 0.63] | negative; CI spans zero — **no improvement** |
| MaxDD (supporting) | +2.17 pp | [−4.62, 6.90] | small reduction; CI spans zero |
| Sharpe (guardrail) | **−0.146** | — | **fails** the ≥ −0.05 guardrail |
| CAGR (guardrail) | −7.9 pp | — | overlay gives up return |
| Robustness | **0 / 9** grid cells pass | — | ΔCalmar negative in **every** cell (−0.07 … −0.49) |
| Cost sensitivity | ΔCalmar −0.21 → −0.32 across 5→50 bps | — | ~52% degradation |

## The key insight — the overlay works *in crashes*

Per-environment (headline cell) shows the overlay doing exactly its job when regimes are sharp:

| Environment | ΔMaxDD | ΔCalmar | ΔSharpe |
|---|---|---|---|
| **covid_2020** | **+14.75 pp** | **+0.258** | +0.053 |
| **bear_2022** | **+12.06 pp** | −0.022 | −0.086 |
| bull_2023_24 | +0.96 pp | −0.040 | +0.074 |

The overlay **cut the COVID drawdown ~15pp and the 2022 drawdown ~12pp** — it protects capital in real
bears. Over the full window it still loses on Calmar/Sharpe because this **survivorship-biased** active
universe has a strong benchmark whose *pooled* drawdowns aren't deep enough for the protection to pay,
and the de-risking forfeits recovery/bull return.

## Verdict + escalation (pre-committed rule)

**Conditionally Promising.** The owner's pre-committed escalation triggers fire:
1. Verdict = Conditionally Promising ✔
2. A primary-metric CI spans zero (ΔCalmar **and** ΔMaxDD CIs include zero) ✔
4. Cost sensitivity high (ΔCalmar degrades ~52% 5→50 bps) ✔

→ **Escalate to Option B (full survivorship-free universe).** This is substantively — not just
procedurally — warranted: survivorship-free history has **deeper drawdowns**, exactly where the overlay
demonstrably pays (COVID/2022), so it could flip the primary (Calmar) result. Revised feasibility: the
rate limit did not bite on 2.7M rows, so the full 14,150-name pool (~34M rows) is **~1–3 days, not weeks**.

## Reproducibility

Python 3.12.13 · numpy 2.2.6 · pandas 2.3.3 · bootstrap seed 17 · store deepened to 2017 (active-name
universe, 1,868 book-days over 2019–2026). Artifact: `data/cap020/cap020_validation_results.json` (box).
Harness dry-run executed on the **staging** deepen copy (`factor_data.deepen.duckdb`) — live store untouched.

_v1.1 — 2026-07-04. Supersedes the v1.0 data-gated finding; feeds the FI-001 registry CAP-020 line._
