<!--
STANDARD EVIDENCE PACKAGE TEMPLATE — v1.0
Copy this file to docs/implementation/evidence/<program>/EvidencePackage_<PROGRAM>_vX.Y.md and fill it in.
Every completed research program emits this package + a one-page Executive Summary
(see RNG-001_Executive_Summary.md for the summary template).

This template is the concrete, fill-in instantiation of the canonical Evidence Package shape defined in
docs/methodology/EvidenceEngineering_Methodology_v1.0.md §7 / §7a. Keep the section order; a package that
omits Data Integrity, Limitations, the Verdict, or the Decision is INCOMPLETE (methodology §7). Italic
"guidance" notes are instructions — delete them as you fill each section.
-->

# `<PROGRAM-ID>` Evidence Package — v`<X.Y>`

> **Honest verdict (carried on every artifact — methodology §6/§7):** `<one line, e.g. "Diversifier (B) —
> portfolio-level; combining validated factors reduces drawdown, it is not standalone alpha.">`

| Field | Value |
|---|---|
| Program | `<PROGRAM-ID>` — `<name>` |
| Evidence type | `<Research | Proposal | Operational | Continuous>` evidence (methodology §7a) |
| Experiment ID | `EXP-YYYYMMDD-NNNNNN` |
| Status · Verdict · Confidence | `<Completed>` · `<Approved / Rejected / Diversifier (B) / Inconclusive / Validated (capability)>` · `<High / Medium / n/a>` |
| Evidence versioning (5 coordinates) | dataset `<v>` · code `<git SHA>` · factor `<v>` · walk-forward `<v>` · report `<v>` |
| Reproducibility metadata | Python `<v>` · DuckDB `<v>` · dataset SHA `<…>` · seed `<int>` · host `<…>` · generated `<ISO>` |
| Evidence dir | `evidence/<program>/` |

---

## 1. Research Summary

*Guidance: Objective + hypothesis + the one-line answer. What question did this program ask, and what did
the evidence conclude? State the verdict up front — the reader should know the answer before the tables.*

- **Question:** `<the single question this program answered>`
- **Hypothesis (pre-registered):** `<what was pre-registered, frozen before results — methodology §5>`
- **Answer:** `<No / Yes / Diversifier — bounded to the tested universe, regimes, and variants>`

## 2. Data Integrity (ADR 0033 — fail-closed)

*Guidance: A backtest is only as trustworthy as its data. Record the dataset-health gate result BEFORE any
result is trusted. A red flag blocks the run (methodology §7); do not report results computed on a dataset
that did not pass.*

- **Dataset:** `<survivorship-free store + window>`
- **Dataset-health gate:** `<PASS / FAIL>` — date coverage/gaps `<…>` · row count `<…>` · missing-price %
  `<…>` · delisted % `<…>` · split/dividend sanity `<…>` · **point-in-time validation** `<…>` ·
  **survivorship validation** `<…>`
- **Historical Data Integrity (ADR 0033):** coverage asserted for the full window (no page-limit
  truncation, no poisoned `.empty` gaps); `<confirm the intraday/cold-fetch caches are complete>`.

## 3. Methodology & Reproducibility

*Guidance: How the study was run, and why a re-run reproduces it byte-for-byte (invariant 5 — reproducible
forever or it is not evidence).*

- **Harness / construction:** `<the production backtest engine used, construction rules, rebalance, costs>`
- **Pre-registered gate (§5):** `<the frozen promotion criteria — e.g. trades > 100, PF > 1.2, win rate >
  50%, drawdown ≤ baseline, positive expectancy, bootstrap CI above zero>`
- **Statistical standard (§6):** `<block-bootstrap CIs, "excludes zero" significance, seeded>`
- **Reproducibility:** `script → JSON → Markdown`, seeded (`seed=<int>`) and deterministic — same inputs
  produce byte-identical output. `<script path>` → `<JSON>` → this report.

## 4. Results

*Guidance: The measured numbers with confidence intervals — never P&L alone. Tables + the key statistics.*

| Metric | Value | CI / significance |
|---|---|---|
| `<Sharpe / edge / …>` | `<…>` | `<CI [lo, hi], p=…>` |

## 5. Operating Envelope

*Guidance: MANDATORY for any capability that reaches Validated (methodology §7 / §4b) — "works" is never
certified without "where it works." A Capability Strength Map (★ per market × volatility regime) + a
Confidence Map (∈ [0,1] per regime). For a Rejected/Inconclusive verdict, note "n/a — not validated."*

`<Strength Map + Confidence Map, or "n/a — not validated">`

## 6. Evidence Correction Report

*Guidance: If a data-quality or methodology fault was found in this program's own pipeline after results
existed, disclose it here — do NOT silently re-run. Correcting one's own faults in the open is a trust
signal (ADR 0033). If none, state "None — no correction was required." Template for a correction:*

- **None — no correction was required.**

*…or, if a fault was found:*

- **What was wrong:** `<the defect>`
- **What it biased:** `<which results, how>`
- **Correction:** `<what was fixed; link the ADR if it escalated, e.g. → ADR 0033>`
- **Re-run outcome:** `<did the verdict hold / change after correction?>`

## 7. Limitations & honest caveats

*Guidance: An evidence doc that skips Limitations is incomplete (§7). State what the evidence does NOT
claim, and where the result is bounded (universe, regime, window, data availability).*

- `<bounded to the tested universes / regimes / variants; what a genuine reopen would require>`

## 8. Final Verdict & Decision

*Guidance: The two-axis outcome (research verdict × platform contribution — every result is value). A
rejection and a diversifier are both assets.*

- **Research verdict:** `<Approved / Rejected / Diversifier (B) / Inconclusive / Validated (capability)>`
  · **Confidence:** `<High / Medium>` (basis: `<CI / significance>`)
- **Platform contribution:** `<Reusable Capability / Methodology Improvement / Negative Finding (preserved)
  / Risk Discovery / Operational Improvement>`
- **Recommendation:** `<Deploy (sleeve) / Archive — Rejected / Reserve / Follow-on study>`
- **Decision record:** `<Research Registry row + Decision Register entry>` · **Capability IDs:** `<CAP-NNN…>`

## 9. Lessons Learned

*Guidance: The durable, reusable takeaway — what the next researcher inherits so they build from this
result rather than repeat it. Reusable assets/harnesses produced; the one-sentence lesson.*

- **Reusable assets produced:** `<harnesses, instrumentation, capabilities — count them>`
- **Lesson:** `<the one durable sentence, e.g. "Diversification comes from independent factors, not from
  reshaping the same factor.">`

---

*This package is stored in the Evidence Registry and referenced by the Capability Registry and the Research
Program Registry (methodology §9) — so a one-off study becomes a compounding institutional asset:
Research → Evidence → Decision → Knowledge.*
