# MR-002 Workstream C — SPQ-1 Phase 0 — Rule Census v1.1

**Supersedes census v1.0** (sha `7b5aa756`). `MR002_SPQ1_RuleCensus_v1.1.json` sha `87602e7c` is the
machine-authoritative record. Incorporates the **12 owner rulings** (2026-07-20,
`MR002_SPQ1_Phase0_OwnerRulings_v1.0.json` sha `d8a9071d`), the **three ratifications** (OWNER-A/B/C),
and the **three internal-consistency corrections**. **No rule remains OPEN** — final states are
FROZEN / DERIVED_MECHANIC / RESOLVED_BY_OWNER / OUT_OF_SCOPE.

**Boundary unchanged:** synthetic-only; no real data, no vendor adapter, no computation, no tuning, no
result-driven selection. Specification, not implementation.

## Ratified 2026-07-20

- **OWNER-A** — first scoreable boundary = **125 registered return sessions** (earliest return index
  `t−124`) and **126 registered price observations** `[t−125, t]`. Min-history (SIG-24) inherits it.
- **OWNER-B** — ADV = **MEDIAN of raw close × raw volume**, two windows (60-session selection screen;
  20-session cap = `trailing_adv_dollars`). Frozen V3 §4 controls.
- **OWNER-C** — missing close **with** governed halt/absence evidence → `INELIGIBLE:KNOWN_MARKET_ABSENCE`;
  an **unexplained** hole → `INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE`.

## Three internal-consistency corrections applied

1. **SIG-33 → SIG-27.** The dangling cross-reference in SIG-02/SIG-22 (and the generator) now points to
   the registered decision/execution seam rule SIG-27. Pure cross-reference fix.
2. **Missing-input taxonomy frozen into four non-collapsing codes** so halt / young-security /
   interior-hole / factor-identity cannot merge:
   - `INELIGIBLE:OLS_WINDOW_INSUFFICIENT` — security lacks the required registered history (IPO/young).
     *(moved out of the INTEGRITY_STOP family.)*
   - `INTEGRITY_STOP:OLS_WINDOW_INCOMPLETE` — interior stock-return hole **without** governed evidence
     (fails closed; must not be concealed as an ordinary exclusion).
   - `INELIGIBLE:KNOWN_MARKET_ABSENCE` — missing close **with** governed halt/absence evidence.
   - `REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH` — missing SPY/sector factor.
   - `RETURN_INPUT_MISSING` is **retired, non-emittable** (`DEPRECATED_NON_EMITTABLE`).
   New matrix cases **SPQM-40** (halt with evidence → `KNOWN_MARKET_ABSENCE`) and **SPQM-41** (same
   missing close without evidence → `OLS_WINDOW_INCOMPLETE`) prove the distinction.
3. **Close-t eligibility no longer includes the t+1 gap filter.** SIG-20 is now two-stage: close-t
   `decision_eligibility_status` = {security/universe eligibility, earnings clearance, corporate-action
   clearance, liquidity, required signal inputs+provenance}; z-threshold / percentile / portfolio
   construction are **downstream selection**; official-open / gap filter / execution constraints are
   **open-t+1 admissibility**. The gap outcome lives in
   `ExecutionEnrichedCandidateRecord.execution_admissibility_status`
   (`ADMISSIBLE | CANCELLED_GAP | CANCELLED_MISSING_OPEN | …`). New matrix case **SPQM-42**.

## Status roll-up — 32 rules · **20 FROZEN · 10 RESOLVED_BY_OWNER · 2 DERIVED_MECHANIC · 0 OPEN**

| ID | Rule | Status | Resolved by |
|----|------|--------|-------------|
| SIG-01/02/03/05 | calendar/timing/price-policy-V3/total-return returns | FROZEN | — |
| SIG-04 | 60 valid sessions; 4 non-collapsing missing-input codes | RESOLVED | R1 |
| SIG-06 | interior missing session: never bridge → OLS_WINDOW_INCOMPLETE | RESOLVED | R1 |
| SIG-07/08 | Step-1 sector factor `u_Sector`; Step-2 stock residual | FROZEN | — |
| SIG-09 | **beta = β̂_m coefficient** | FROZEN | — |
| SIG-10 | deterministic LSQ; singular→OLS_DESIGN_SINGULAR; preregister solver+tolerance | RESOLVED | R2 |
| SIG-11 | unresolvable sector→excluded | FROZEN | — |
| SIG-12/13 | `R5 = Σ ε_{t−4..t}` consecutive; missing→INELIGIBLE, never bridge | FROZEN/RESOLVED | R4 |
| SIG-14/15/16 | z-norm 60 R5 ending t−1, ddof=1, current excluded, one pass; z; σ | FROZEN | R5 |
| SIG-17 | z/σ single-pass consistency | DERIVED | R5 |
| SIG-18/19 | sector taxonomy; PIT effective-date + succession | FROZEN/RESOLVED | R7+R8 |
| SIG-20 | **two-stage eligibility** (close-t decision vs t+1 admissibility) | FROZEN | R9 |
| SIG-21/22 | earnings-clearance V1; gap filter (execution-time) | FROZEN | R9 |
| SIG-23 | eligibility precedence + evidence binding | RESOLVED | R9 |
| SIG-24 | min-history=warm-up (125/126); type/exchange/halt eligibility | RESOLVED | R10 |
| SIG-25 | **ADV = MEDIAN(raw close × raw volume), two windows** | RESOLVED | R11 |
| SIG-26 | official next-open + missing-open (execution-session only) | FROZEN | R10 |
| SIG-27 | decision/execution seam; future field→FUTURE_INFORMATION_DETECTED | DERIVED | — |
| SIG-28/29 | permanent id / lineage; `candidate_id ≠ permanent_security_id` | RESOLVED/FROZEN | R8+R12 |
| SIG-30/31 | SPY + sector-ETF frozen input identities | FROZEN | — |
| SIG-32 | **first scoreable session / warm-up = 125 return / 126 price** | RESOLVED | R6 |

## Owner-rulings artifact

`MR002_SPQ1_Phase0_OwnerRulings_v1.0.json` (sha `d8a9071d`) binds R1–R12 to affected rule IDs,
decision, rationale, required refusal/ineligibility code, required tests, sources, owner, date, plus the
`ratifications` block.

## Schema v1.1 + matrix v1.1

`SignalDecisionRecord` carries the composed `candidate_id`, `decision_eligibility_status`,
`eligibility_precedence_rank`, the 20-session-median `trailing_adv_dollars`, and
`warmup_return_sessions=125 / warmup_price_observations=126`; future fields remain structurally
forbidden. `ExecutionEnrichedCandidateRecord` adds `execution_admissibility_status` and byte-preserves
the decision record. Matrix now **37 cases** (`MR002_SPQ1_QualificationMatrix_Draft_v1.1.json` sha
`560cbe68`) — all owner-required tests plus SPQM-40/41 (halt-evidence distinction) and SPQM-42 (gap
filter is not close-t eligibility). Open-questions register (sha `058d22f0`) — all ten
`RESOLVED_BY_OWNER`, zero `REMAINS_OPEN`.

## Phase-0 stop

Package regenerated with the three corrections; OWNER-A/B/C ratified. **No production signal modules or
tests.** Awaiting your final Phase-0 technical closure. SPQ-1 implementation, real-data access,
validation/OOS, performance, and tuning remain **NOT AUTHORIZED**.
