> **MEETING-SAFE COPY (PU-1, owner ruling 2026-10-12).** Derived from `RANGE-002_A-SCREEN_Amendment_v0.2.md`. The only change is that the SIP probe counts and dates in section 4 are replaced by a statement that Jay holds them. Method, decisions, criteria and open questions are unchanged. The original is Jay's private record and is not for circulation.

# RANGE-002 A-SCREEN — weekly-meeting workflow revision

**Updated:** 2026-10-12. Technical excerpts below are retained from the supplied amendment revision 2; they are historical inputs, not verification of today's code or numerical adoption.

## Company workflow — weekly meeting decisions

**Effective direction: Jay Wang, 2026-10-12.** The team discusses issues at its weekly meeting. The meeting minutes are the company's decision and approval record. Separate role appointments, role rosters, signature forms, countersignatures, ceremonies, witness assignments, eligibility-verifier appointments and cryptographic signing infrastructure are not prerequisites for this workflow.

Use one short meeting record: date, attendees, issue, decision (approved / revise / defer / stop), scope or strategy version, relevant test/code/data references, and next action. Do not infer a decision from attendance or silence. Record specific objections and unresolved questions. A named next-action contact is task coordination, not a formal role appointment.

Execute work already covered by recorded decisions without repeating approvals. Discuss new material choices in the weekly meeting. Jay's explicit instructions between meetings authorize their stated scope and can be summarized in the next minutes; do not require a separate signature ceremony.

Keep strategy versions, frozen pre-result assumptions, reproducibility, tests, costs, data quality, data-use permissions, protected holdout separation and operational risk controls. Build, data fetching, research runs and broker activation remain distinct scopes, recorded plainly in the minutes. Changing this document does not itself execute any of them or override tool-enforced permissions.

Existing role/signature checks in code must be migrated to a meeting-decision reference with explicit scope and version binding. Do not fill legacy signature fields with invented names or signatures. No formal P0 approval is inferred from this workflow change, and no strategy performance result is created.

## BUILD and RUN scope

Prepare and test the isolated screening kernel, loader fixtures, restricted profile and guard changes in parallel. Keep the screen restricted to its authorized development/replay partitions; do not promote it into P3B, P4, P5 or broker permission.

For RUN, require correct code and applicable checks, a versioned baseline, actual meeting decision covering the run, permitted data use, verified coverage/provenance, exposure record and prior run registration. Do not require Research Lead appointment, independent-validator appointment, three sign-off strings, human-role attestations or production signing infrastructure.

Freeze assumptions before returns are viewed. Meeting minutes record baseline adoption; hashes bind the actual code/spec/data version, not a signature ceremony. Later selection or portfolio evaluation must preserve the distinction between exploratory and independent evidence.

## Implementation migration

Replace FrozenSpec/load_frozen/results_guard dependence on governance.roles, economic-thesis signatures and signoff.owner/trading_expert/independent_validator with a scoped meeting-decision reference. Preserve hash/version binding, required technical fields, capability revocation, partitions, attempts and exposure controls. Do not use placeholder signers to satisfy old code.

Reconcile this migration in the current repository amendment; do not overwrite newer technical code or baseline decisions with this attachment's older excerpts.

## 3. BUILD: executed engineering result (not a performance result)

Package `app/research/range002/screen/` (7 files, about 760 lines; `engine/` left untouched for ENG-A1). Every public callable carries the existing `@requires_capability`; Q-B2 is not involved.

| Module | Content |
|---|---|
| `params.py` | Typed extraction from a parsed spec; verifies content hash equals the capability's spec hash; fails closed naming every null/unsupported field (R9); nothing defaulted |
| `simulate.py` | OR levels and completeness, buy-stop entry at OR high + tick, stop at OR low, gap fills, same-bar worst case, time/fixed-R/trailing/scale-out exits, half-day EOD, all-in per-side costs (base and stress), funnel with reconciliation, data-defect validation (feed, timestamp convention, order, OHLC, authorized date range) |
| `causal.py` | Look-ahead check: replaces every bar after a cut with extreme values and requires every decision visible at the cut to be unchanged |
| `report.py` | R-unit metrics: n, traded days, mean/total net R at base and stress, PF (undefined when no losses), drawdown, top-5 removal, best-day share, per-year, ambiguity counts. No bootstrap, no verdict |
| `types.py`, `errors.py` | Data records and typed refusals |

**Tests (synthetic only):** 27 in `tests/research/range002/screen/`, all passing: parameter binding and fail-closed cases; range, entry, gap-open, entry-window, completeness and narrow-range cases; stop, target, same-bar ambiguity, stop gap, entry-bar stop, trailing and scale-out arithmetic including cost; half-day; funnel reconciliation and mismatch refusal; five data-defect classes; capability required on every entry point; closed run revokes use; causality passes the kernel **and fails two deliberately look-ahead variants**. The whole `tests/research/range002` suite, including the existing Level-1 import lint and `check_research_plane_isolation.py`, passes; ruff and mypy are clean on the new package.

**Estimate revision:** first milestone took one working session rather than 1-2 days. Remaining BUILD (not yet built): portfolio-constrained chronological scheduler, day-clustered bootstrap and max-statistic selection test (blocked on D06 values), return-blind coverage validator, the loader (below). Estimate for these: 2-3 working days, dominated by the unresolved bootstrap specification.

**Loader exemption (smallest change, no guard change):** (a) a fetch/store module that writes immutable, manifest-pinned bars and coverage **counts only**, added to the lint's `REVIEWED_PURE`/`REVIEWED_PURE_IO` list by a reviewed one-line test change, with an AST test that it imports nothing from `screen/` or `stats/`; (b) reading bars into the screen only through a capability-gated function that verifies manifest hash and that every session lies inside the capability's date range (the range check already exists in `simulate.py`). Nothing in `results_guard.py` changes.

## 4. Data feasibility (workstream B)

**Return-blind probe, executed on ec2-paper 2026-10-12** (counts and timestamps only; no price or volume value printed or stored; no service modified; script not in the repo). Counts are not reproduced in this copy (PU-1):

| Finding | Evidence |
|---|---|
| Availability of SIP 1-minute bars over the intended development window was confirmed by Jay in a private check; figures are held by Jay and are not shown (PU-1) | held by Jay |
| Earliest available date was established privately; the development window starts at 2016-01-01 as already specified | held by Jay |
| Fields returned: open, high, low, close, volume, trade_count, vwap, symbol, timestamp | `fields_seen` |
| A probe procedure error was corrected and the check repeated; no result was affected | n/a |

**Not established by the probe (do not assume):** delisted and small-cap coverage and the 98% OR-completeness rate for an N = 100 universe; adjustment convention in force (probe used RAW only); rate limits beyond 32 sequential requests; **any right to retain or store a historical dataset** (successful API access is not storage permission); the 2022-2025 range was deliberately not requested.

**Questions for Jay / the vendor (O-7):** (1) Does the subscription provide SIP minute bars for 2016-2021, and from what date exactly? (2) Fields and adjustment conventions (split/dividend; raw vs adjusted; delisted names)? (3) May bars be stored/cached locally for research, with what retention limits? (4) May they be used on the AWS host? (5) Request/rate limits and any bulk-history cost? (6) Restrictions on sharing the data or derived outputs (for example reports shown to the validator or team)? Repo documentation checked: SIP-CACHE-001 contract v1.0.1 and the ATP plans document entitlement of *recent* SIP and a 15-minute delay; they do **not** document minute-bar depth, storage or redistribution rights, so (3)-(6) remain open.

**If coverage proves insufficient for the N = 100 universe:** narrow within 2016-2021 only, keep selection before confirmation, state the sample loss; do not use IEX as qualifying data and do not touch 2022-2025.

## Screening criteria — reconcile against the latest meeting decision before RUN

P3a results select candidates for further evaluation; they are **not** independent confirmation. Preliminary results are reported even when counts are short.

| Condition | Class | Treatment |
|---|---|---|
| Causal failure, non-SIP data, unreconciled funnel | **DEFECT** | Repair and rerun; no strategy verdict |
| OR completeness < 98% | **DEFECT (data-quality blocker)** | Denominator = eligible symbol-days (universe member, session open, at least one print); missing sessions count as incomplete, never dropped; report overall, by year and month, first 30 minutes |
| < 300 trades or < 100 traded days | **INSUFFICIENT EVIDENCE** | Report results; do not advance |
| Day-clustered bootstrap interval spans zero | **INSUFFICIENT EVIDENCE** | Method and unit frozen before the run: stationary bootstrap over trading-day clusters, percentile, fixed seeds, replications >= 10,000, mean block length fixed a priori in days (D06 baseline; discuss in the weekly meeting) |
| Max-statistic test (over the 7-candidate family K, same bootstrap) fails one-sided alpha 0.10 | **INSUFFICIENT EVIDENCE** | Not proof of failure; family and method frozen first |
| Mean net R <= 0 at 5 bps per side | **STOP THIS VERSION** | Investigate whether a revision is justified (new registration, R4) |
| Positive at 5 bps, non-positive at 15 bps | **REVISE** | Cost fragility: revise/restrict applicability; not auto-reject unless 15 bps is expected execution cost |
| PF (base) < 1.15 with mean > 0 | **REVISE** | Advancement threshold only; withholds ADVANCE |
| Net profit <= 0 after removing top 5, or best day > 20% of net | **REVISE (warning)** | Targeted review before advancement; if total net <= 0 the concentration test is undefined and the mean rule governs |
| Neighbouring candidate PF < 1.0 | **REVISE (warning)** | Neighbour = the other member of the same family pair (E2a/E2b, E3a/E3b, E4a/E4b), base cost; E1 has none |
| Mean net R <= 0 in >= 2 of 4 years | **REVISE (warning)** | Temporal-instability review; not automatic rejection |
| None of the above | **ADVANCE TO P3b** | Subject to the meeting review of any warnings |

Report in every case: net performance at base and stress cost, trades, traded days, daily drawdown in R, top-5/best-day concentration, per-year table, all 7 candidates (not only the selected), control comparison as diagnostic. The take-profit/exit is chosen **only** by the declared selection rule inside P3a; P3b is its unbiased evaluation. Variants and exposure go to the trial and exposure ledgers.

## Meeting decision queue

Use one compact table of the still-open numerical/technical choices. Keep the existing proposals as planning inputs; record adoption explicitly before RUN. Remove appointment, witness, verifier, ceremony and separate signature items from the queue.

## Timing

Track elapsed time to first performance result, blocked time by cause and executed engineering increments. Prioritize substantive tests and usable data. Avoid additional governance tooling and document packages.
