# MR-002 Workstream C — Signal & Data-Production Qualification (SPQ-1), Phase 0

**Rule census — specification package.** `MR002_SPQ1_RuleCensus_v1.0.json` sha
`7b5aa756…` is the machine-authoritative record; this MD is the readable companion.

**Boundary (Phase 0):** synthetic-only. No real/dev/validation/OOS data opened, no vendor adapter
imported, no residual/z/σ/beta/sector/ADV/eligibility computed, no metric run, no parameter tuned, and
no rule chosen because it produces better results. This is the **specification** for the upstream layer
that *produces* the candidate facts Increment 3 already consumes — not its implementation.

## What SPQ-1 must produce (the candidate facts)

`permanent_security_id · decision_session · signal_origin_session · registered_signal_value ·
registered_sigma_resid · sector_id · beta · eligibility_status · eligibility_evidence_identity ·
official_next_open_price · trailing_adv_dollars · configuration_id`

## Governing chain bound (by SHA-256)

v0.3 design `1007db82` · v1.0_FROZEN `70108c11` · prereg v1.0.4 `b2a042d4` · trial ledger `deda5cec` ·
DSR resolution `30b812f1` · DSR dispersion `7a601f5b` · portfolio census `91eec262` · Increment-3
registry `edb7ff22` · Phase-0 resolution `860c8cde` · Increment-3 qualification `0c077c38` ·
Increment-3 accepted output `42c5cee0` · OQ-1 manifest `7b6eb07d` · OQ-1 closeout `f47f92dd`.

## Four owner-accepted Phase-0 clarifications (baked in as FROZEN/REQUIRED)

1. **Beta (SIG-09) — FROZEN.** `beta_i = β̂_m,i`, the market-beta **coefficient** of the *same* §3
   Step-2 60-session stock regression that produces the residual. Benchmark SPY, sector regressor
   `u_Sector`, window 60 ending t−1, intercept included. No separate beta model.
2. **registered_sigma_resid (SIG-16) — FROZEN = the z-normalization denominator** `σ_i,t−1` (ddof=1
   std of the 60 overlapping R5 ending t−1). **z and σ must come from one deterministic pass**
   (SIG-17, REQUIRED): qualification proves both share the same normalization-window identity + a
   single computation record.
3. **Decision/execution seam (SIG-27) — REQUIRED.** Two structurally distinct records:
   `SignalDecisionRecord` (cutoff = close t; **cannot** carry `official_next_open_price` /
   `actual_execution_session` / any post-close-t field) and `ExecutionEnrichedCandidateRecord` (t+1;
   appends the official open + execution timestamp without recomputing decision facts). Any post-cutoff
   field in a decision record → `INTEGRITY_STOP:FUTURE_INFORMATION_DETECTED`. **Increment 3 stays
   closed and unchanged;** the enriched record is the adapter seam into its accepted replay contract.
4. **Frozen input identities (SIG-30/31) — REQUIRED.** SPY total-return series, sector-ETF proxy
   mapping table (hash ships in evidence), sector-ETF source series, session calendar, price/return
   adjustment. Mismatch → `REFUSED_CODE_OR_DATA_IDENTITY:SIGNAL_INPUT_IDENTITY_MISMATCH`.

## Status matrix (31 rules — 20 FROZEN · 9 OPEN · 2 DERIVED_MECHANIC)

| ID | Area | Rule | Status |
|----|------|------|--------|
| SIG-01 | 1 session/price | registered exchange calendar / session numbering | **FROZEN** |
| SIG-02 | 1 session/price | decision cutoff = close t; entry t+1 open; time-stop session-6 open | **FROZEN** |
| SIG-03 | 1 session/price | price-series policy V3 (TR signal / split-only exec / dist-adj gap / raw ADV) | **FROZEN** |
| SIG-04 | 1 session/price | IPO/delisting/suspended-session boundaries + interior-window counting | OPEN |
| SIG-05 | 2 return series | daily arithmetic **total** returns; missing ⇒ ineligible; no winsorization | **FROZEN** |
| SIG-06 | 2 return series | interior-missing-session handling within the 60-window | OPEN |
| SIG-07 | 3 OLS residual | Step-1 orthogonalized sector factor `u_Sector` (60-session, ending t−1) | **FROZEN** |
| SIG-08 | 3 OLS residual | Step-2 stock model; residual `ε` from t−1 coefficients; intercept included | **FROZEN** |
| SIG-09 | 3 OLS residual | **beta = β̂_m market coefficient** (owner clarification) | **FROZEN** |
| SIG-10 | 3 OLS residual | OLS solver / tolerance / rank / singular-design handling | OPEN |
| SIG-11 | 3 OLS residual | unresolvable sector ⇒ excluded, never defaulted | **FROZEN** |
| SIG-12 | 4 R5 | `R5 = Σ_{k=0..4} ε_{t−k}` | **FROZEN** |
| SIG-13 | 4 R5 | R5 missing-session / consecutiveness / first-eligible / <5 refusal | OPEN |
| SIG-14 | 5 z-score | `z = (R5−μ)/σ`; 60 overlapping R5 ending t−1; ddof=1; current R5 excluded | **FROZEN** |
| SIG-15 | 5 z-score | `registered_signal_value = z` (no clip/floor/winsor/rank) | **FROZEN** |
| SIG-16 | 6 σ_resid | **`registered_sigma_resid = σ_i,t−1`** (owner clarification) | **FROZEN** |
| SIG-17 | 6 σ_resid | z / σ single-pass consistency | DERIVED_MECHANIC |
| SIG-18 | 7 PIT sector | taxonomy source (PIT history or frozen SIC/NAICS table, hash in evidence) | **FROZEN** |
| SIG-19 | 7 PIT sector | effective-date / availability / same-day / succession mechanics | OPEN |
| SIG-20 | 9 eligibility | entry eligibility conditions (z, 10%, earnings, corp-action, gap, liquidity) | **FROZEN** |
| SIG-21 | 9 eligibility | earnings-clearance rule V1 | **FROZEN** |
| SIG-22 | 9 eligibility | gap filter (execution-time; belongs to enrichment step) | **FROZEN** |
| SIG-23 | 9 eligibility | availability-timestamps / precedence / evidence identity / refusal-vs-INELIGIBLE | OPEN |
| SIG-24 | 9 eligibility | delisting/bankruptcy/halt/min-history/security-type/exchange | OPEN |
| SIG-25 | 10 ADV/open | dollar-volume = raw close × raw volume (frozen pair); ADV window/lag | OPEN |
| SIG-26 | 10 ADV/open | official next-open identity + missing-open (execution-session only) | **FROZEN** |
| SIG-27 | 10 ADV/open | **decision/execution seam** (owner requirement) | DERIVED_MECHANIC |
| SIG-28 | 11 security id | permanent_security_id source / lineage / succession / share-class | OPEN |
| SIG-29 | 11 security id | `candidate_id ≠ permanent_security_id` | **FROZEN** |
| SIG-30 | inputs | SPY market-factor series identity | **FROZEN** |
| SIG-31 | inputs | sector-ETF proxy + source-series identity | **FROZEN** |

## Refusal taxonomy (drafted; classified)

17 codes across three classes — `INTEGRITY_STOP` (calendar/window/singular/non-finite/variance/
sigma/**future-information**), `REFUSED_CODE_OR_DATA_IDENTITY` (input-identity / sector-effective-date /
security-identity), `INELIGIBLE` (return-missing / R5-window / sector-missing / eligibility-evidence /
ADV-window). Full table in `MR002_SPQ1_RuleCensus_v1.0.json.refusal_taxonomy`.
`FUTURE_INFORMATION_DETECTED` is the most severe — a structural `INTEGRITY_STOP`.

## Draft input/output schema

`SignalDecisionRecord` (close-t; future fields structurally forbidden) →
`ExecutionEnrichedCandidateRecord` (t+1; appends open + gap result, decision facts byte-preserved) →
**Increment-3 accepted replay contract (CLOSED)**. See
`MR002_SPQ1_InputOutputSchema_Draft_v1.0.json`.

## Draft qualification matrix

28 synthetic-only cases in `MR002_SPQ1_QualificationMatrix_Draft_v1.0.json` — the exact-60/59-refusal
boundary, decision-session lagging, **future-price leakage rejection**, singular OLS, R5 endpoints,
z/σ zero-variance refusals, z/σ single-pass, PIT-sector effective-date, missing sector, beta first
session, earnings/corp-action/ADV boundaries, A/B/C-differ-only-by-Z_entry, and byte-deterministic
synthetic output. Cases tied to OPEN rules are marked `OPEN-RULING` pending owner decisions.

## Open questions (10 — owner rulings required before SPQ-1 implementation)

`OQ-SPQ-01..10` in `MR002_SPQ1_OpenQuestions_v1.0.json` — IPO/interior-missing-session counting, OLS
solver/singular handling, R5 missing/first-eligible/consecutiveness, PIT-sector effective-date/
succession, eligibility availability-timestamps/precedence, min-history/security-type/exchange/halt,
ADV formula/lookback/lag, permanent-id lineage, and the compounded warm-up length (60-session OLS → 5-day
R5 → 60 R5 for μ/σ) that fixes the first scoreable session. **Multiple ruling rounds are expected and
preferable to silently filling gaps.**

## Phase-0 stop point

Census + schemas + open-question register + draft matrix. **No production signal modules or tests.**
Owner rules the OPEN items → SPQ-1 implementation is then separately authorized. Real-data access,
validation/OOS, performance computation, and production remain **NOT AUTHORIZED**.
