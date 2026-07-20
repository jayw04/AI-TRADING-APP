# MR-002 Increment 3 — Phase-0 Portfolio-Rule Census (v1.0)

**Status: submitted for owner rulings. Census only — no loader/selection/normalization/cascade/replay
code; no evaluator code changed; no data read; no performance.** Machine-readable companion:
`MR002_Portfolio_Rule_Census_v1.0.json` (`91eec262…`); rule-registry draft
`MR002_Increment3_RuleRegistry_Draft_v1.0.json` (`02e5cf6b…`, NON-BINDING).

## Governing sources (hashes machine-verified in the JSON, `source_validation.match = true` for all)

| id | file | sha256 |
|---|---|---|
| v0.3 design | `docs/implementation/TradingWorkbench_MR002_PreRegistration_v0.3.md` | `1007db82…` |
| v1.0 FROZEN | `…/governing_sources/…_v1.0_FROZEN.md` | `70108c11…` |
| v1.0 FREEZE CANDIDATE | `…/governing_sources/…_v1.0_FREEZE_CANDIDATE.md` | `7b5ee09c…` |
| prereg v1.0.4 | `docs/review/mr002/MR002_ValidationOOS_Preregistration_v1.0.4.json` | `b2a042d4…` |
| trial ledger | `docs/review/mr002/MR002_DSR_TrialLedger_v1.0.json` | `deda5cec…` |

The v0.3 construction table (§3–§5) is frozen **unchanged** into the owner-signed v1.0 (`70108c11`);
`prereg.exposure_limits_frozen` + `cost_model_frozen_values` are its machine-readable mirrors. v0.3
`1007db82` == `prereg.governing_gate_source.v0.3_gate_table_sha256`.

## Rule-by-rule status matrix (27 rules; full 10-field records in the JSON)

Status ∈ **FROZEN** (explicit in governing text) · **DERIVED_MECHANIC** (arithmetic on frozen inputs)
· **OPEN** (needs a ruling) · **OUT_OF_SCOPE** (not authorized / secondary).

| id | economic meaning | status | citation (v0.3 unless noted) |
|---|---|---|---|
| PR-01 | Gross-exposure ceiling (100% NAV max, unused→cash) | FROZEN | §5 L135-136 |
| PR-02 | Exits-before-entries + one-position-per-symbol | FROZEN | §5.1 L140-141 |
| PR-03 | Inverse-residual-vol weighting (rule) | FROZEN | §5.2 L142-143 |
| PR-04 | `raw_inverse_vol_weight = 1/registered_sigma_resid` | DERIVED_MECHANIC | §5.2 L142 |
| PR-05 | Within-side normalization | DERIVED_MECHANIC | §5.2 L142-143 |
| PR-06 | Long/short allocation (entry dollar-neutrality) | FROZEN | §5.3 L144-146 |
| PR-07 | Entry-neutrality timing (at order time) | FROZEN | §5.3 L144 |
| PR-08 | Position cap 1.5% NAV | FROZEN | §5 L162 |
| PR-09 | Sector caps (net 5% / gross 20% of gross) | FROZEN | §5 L163 |
| PR-10 | Beta constraint + signed-weighted aggregation | FROZEN | §5 L164-165; §3 L60-66 |
| PR-11 | Constraint-removal ORDER (pos→sector→beta→none) | FROZEN | §5.4 L147-148 |
| PR-12 | Constraint repair (remove smallest \|z\|) | FROZEN | §5.4 L149-151 |
| PR-13 | Removal tie-break (older signal→permanent id) | FROZEN | §5.4 L150-151 |
| PR-14 | No upward renormalization / no replacement | FROZEN | §5.4 L148-149 |
| PR-15 | Drift-repair ordering (\|entry z\|→oldest→id) | FROZEN | §5 drift L154-158 |
| PR-16 | Fixed shares until exit | FROZEN | §5.5 L152 |
| PR-17 | Cash treatment (unused/removed/clipped→cash) | FROZEN | §5 L135-136, L148-149 |
| PR-18 | Candidate eligibility rules | FROZEN | §4 L91-113 |
| PR-19 | Signal-strength ordering (within-side percentile) | FROZEN | §4 L94-98 |
| PR-20 | A/B/C differ ONLY in Z_entry 1.75/2.00/2.25 | FROZEN | ledger + §4 |
| PR-21 | Pending-exit account treatment | FROZEN | §4 halts L120-125; §5.1/§5.5 |
| **PR-22** | **Target-vs-executed exposure (three-state)** | **OPEN** | §5 + prereg cost_model → **RC-2** |
| **PR-23** | **1.5% cap at two enforcement points** | **OPEN** | §5 L162 + prereg → **RC-4** |
| PR-24 | Sector taxonomy source (PIT or frozen mapping) | FROZEN | §2/V2 L230, L38-45 |
| PR-25 | Residual / z / volatility computation | OUT_OF_SCOPE | §3 L47-73 |
| PR-26 | Volatility overlay (secondary only) | OUT_OF_SCOPE | §5a L169+ |
| PR-27 | ADV/NAV execution clips (2% / 1.5%) | DERIVED_MECHANIC | prereg cost_model (Increment 2) |

## Confirmed frozen — not reopened

Per your directive, and confirmed against the source with **no contradictory text found**: constraint
order (PR-11), constraint repair (PR-12), removal tie-break (PR-13), drift repair (PR-15), replacement
= none/cash (PR-14), beta = \|signed β\|/gross ≤ 0.10 (PR-10), fixed shares (PR-16), exits-before-
entries (PR-02), sector source = PIT or frozen evidence-bound mapping (PR-24).

## Conflicts

**One apparent pair, resolved (not a contradiction):** prereg `cost_model_frozen_values` (execution)
vs v0.3 §5 limits (construction) enforce the **same** economic limits (1.5% per-name, 2% ADV) at two
**stages**. The three-state exposure model (below) reconciles them. No other governing contradictions
found.

## Three-state exposure model (prevents layer "disagreement")

Track **pre-constraint raw target → post-construction intended target → post-execution realized
exposure**. For every constraint, preserve: `raw_value`, `construction_constrained_value`,
`executed_value`, `binding_rule`, `removed_or_clipped_amount`, `cash_remainder`. A post-execution
integrity check recomputes realized per-name/gross/net/sector/beta and refuses (INTEGRITY_STOP or
REFUSED replay) on any target-constraint violation — it **never resizes or substitutes**.

## Four ruling candidates (proposed dispositions, with source evidence)

**RC-1 — Position-sizing interface (BLOCKER).** Evidence: PR-03 needs `1/σ_resid`; the candidate
schema lacks a sizing input; PR-25 makes residual/vol computation out-of-scope. Proposed: candidate
**must carry `registered_sigma_resid`** = 60-session vol of the registered 5-session residual, from
the upstream frozen signal artifact, strictly positive/finite, **not computed by Increment 3**;
Increment 3 computes only `1/registered_sigma_resid` and normalizes; may not calculate residuals or
estimate vol; a candidate-supplied inverse is evidence only (evaluator recomputes + cross-checks);
missing/zero/negative/non-finite → **fail closed**.

**RC-2 — Target vs executed exposure.** Constraints bind to intended **target** weights pre-execution;
Increment-2 clipping may only **reduce** absolute executed exposure; clipped capacity → cash, not
redistributed; after execution, realized exposure is recomputed and verified not to exceed any target
constraint. **Clipping is not assumed always-safe** — asymmetric long/short clipping can worsen net
exposure or normalized beta, so the replay records both target and executed exposures and runs a
post-execution integrity check that **must not resize or substitute**; a violation → INTEGRITY_STOP or
explicit REFUSED replay.

**RC-3 — Pending exits.** A deferred exit remains an **open held position**; its shares, exposure,
sector usage, beta contribution, and capital remain in account state until it fills; the symbol is
**ineligible** for a new position while pending. (Follows from fixed-shares + one-position-per-symbol
+ §4 halts.)

**RC-4 — 1.5% cap at two layers.** Construction sets intended per-name exposure ≤ 1.5% NAV; execution
enforces the **same** 1.5% against executable notional as a safety check; **not multiplied or
compounded**. Execution uses `min(intended shares, 2% ADV cap, 1.5%-NAV executable cap)`; any
reduction → cash. One economic limit, two enforcement points.

## Additional open item (not one of the four RCs; flagged for a ruling before component-6)

**Daily NAV/return marking convention.** The daily net-portfolio-return series feeding the Increment-1
metric family (Sharpe/DSR/stationary bootstrap) needs a frozen marking cadence for held positions
(official opens open-to-open vs close-to-close). §4 fixes *execution* at official opens and labels
close-to-close *execution* "diagnostic only", but the daily NAV *marking* cadence for the return
*series* is not pinned in one place. Recommended (non-binding): mark daily on the registered execution
price series (split-adjusted, non-dividend-adjusted official opens). Surfaced now; ruling needed
before the portfolio-to-ledger → daily-returns integration is built.

## Proposed synthetic candidate schema

`candidate_id · session · symbol · side · registered_signal_value (=z) · registered_sigma_resid (>0,
finite) · sector_id · beta · official_next_open_price · trailing_adv_dollars · eligibility_status ·
configuration_id (A|B|C)` + optional `registered_inverse_vol_weight` (evidence; evaluator recomputes).
Fail-closed on: missing/duplicate `candidate_id`; missing/0/neg/non-finite `registered_sigma_resid`;
missing `sector_id`/`beta` when the corresponding constraint applies; non-finite signal/exposure
input; unknown `configuration_id`.

## Boundary

Validation/OOS **SEALED AND UNREAD**. Phase-0 is census only. **Not authorized:** portfolio
loader/selection/normalization/cascade/replay code, new evaluator tests beyond census validation,
real/sealed-data access, performance. On owner rulings of RC-1..RC-4 (+ the daily-marking item before
component-6), Increment 3 build proceeds per the authorized component list.
