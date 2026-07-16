# MR-002 — Pre-Registration v0.5 (DRAFT, delta to v0.4) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Authority:** v0.4 (build-
authorizing, owner-approved) + **owner build-pilot review** (`Docs/implementation/comments.md`
2026-07-11, archived at `evidence/mr_002/MR002_OwnerReview_BuildPilot_2026-07-11.md`).
**Supersedes v0.4 only where stated below** — everything not amended here is unchanged from v0.4.
**Status:** 🟡 **DRAFT — NOT FROZEN.** Corrected status statement (owner §3):

> **No conceptual strategy-design items remain. Research-Design Freeze remains blocked by completion
> and acceptance of the historical identity crosswalk, full-universe V1/V2 builds, mapping-table
> countersign, required manual validation cases, coverage gates, and §8a.**
> **The strategy rules are closed. The data implementation is not.**

## 1. V1 event-time semantics — CORRECTED (critical; replaces the v0.4 §4 session rules)

The v0.4 rule ("in-session or ambiguous acceptance = BMO") was **not PIT-safe**: a filing accepted
*during* session `s` classified as BMO would prohibit execution at the `s` open — an open that traded
**before the information existed**. Frozen replacement (owner wording):

> The event time is the **earliest independently verified public earnings-release timestamp**. When no
> reliable release timestamp is available, the **EDGAR acceptance timestamp is used as a conservative
> availability proxy**.
> If the event or filing is available **before the regular-session open** on session `s`, prohibited
> execution opens are **`s` and `s+1`**.
> If it becomes available **during the session or after the close** on `s`, prohibited execution opens
> are **`s+1` and `s+2`**.
> **No execution that occurred before the recorded availability timestamp is retroactively cancelled.**

Registered storage & terminology:

- Every anchor stores **`event_time_basis` ∈ {`verified_release_timestamp`, `edgar_acceptance_proxy`}**.
  Acceptance-time classifications are **never labelled true BMO/AMC**; the availability classes are
  **`PRE_OPEN` / `IN_SESSION` / `POST_CLOSE` / `DATE_ONLY_CONSERVATIVE`** (a date-only timestamp is
  treated as available at end-of-day `s` → prohibited opens `s+1`, `s+2` — the PIT-safe direction; the
  v0.4 "ambiguous ⇒ BMO" mapping is retired).
- The same availability instant drives the 70-day blackout reset and the cooling window; blackout
  *exits* still fire at the first executable open **after** availability (never retroactively).
- **Pilot-match wording corrected (owner §8):** *"Item 2.02 anchor dates show complete agreement with
  Sharadar code-22 dates in the pilot; exact earnings-event identification and market-session timing
  remain subject to independent manual validation."* Before freeze, a stratified manual sample is
  compared against archived release timestamps (press-release exhibits), reporting separately: correct
  event identification · correct calendar date · correct session classification · % using the
  acceptance proxy. **Manually validated V1 precision is a coverage gate (§4).**

## 2. Historical identity crosswalk — SCHEMA + SOURCE PRECEDENCE FROZEN (blocker; full build may not start before this is registered)

**Schema (frozen):** `permaticker · ticker · cik · effective_from · effective_to · relationship_type ·
source · source_record_id · confidence · mapping_rationale`, with `relationship_type ∈ {direct,
ticker_rename, share_class, predecessor_cik, successor_cik, spin_off, acquisition, manual_override}`.

**Source precedence (frozen, deterministic):** 1) Sharadar security metadata + `secfilings` identifier
→ 2) EDGAR submissions + filing-header identity → 3) corporate-action / predecessor-successor evidence
→ 4) archived historical ticker mappings → 5) manually reviewed override table. Every manual override
carries evidence, effective dates, and reviewer approval. **Unresolved periods are excluded — never
inherit the current issuer's CIK.**

**Mandatory identity tests before the full run:** TWTR (delisted) · FB (retired ticker) ·
Google→Alphabet (predecessor/successor CIK chain) · GOOG/GOOGL (share-class) · one spin-off
parent/child boundary (GEHC or KVUE).

## 3. Preliminary-universe sequence — registered (prevents crawl circularity)

`SEP price/liquidity/type filters → preliminary monthly universe → union of all preliminary-universe
permatickers → historical identity crosswalk → V1/V2 EDGAR builds → V1/V2 eligibility exclusions →
final monthly eligible universe.`

The top-250/150 construction is explicitly the **preliminary price-and-security-type universe**, built
before any V1/V2 eligibility is applied, so missing-anchor/missing-sector exclusions can never change
which issuers get crawled.

## 4. Coverage acceptance gates — REGISTERED BEFORE the full-universe output is inspected

| Area | Pre-freeze minimum |
|---|---|
| CIK/permaticker resolution | ≥ 99% of preliminary universe-months |
| Valid V1 earnings anchor | ≥ 95% of universe-months after warm-up |
| Valid V2 PIT sector mapping | ≥ 98% of universe-months |
| Any individual calendar year | V1 ≥ 90% · V2 ≥ 95% |
| Manually validated V1 precision | ≥ 98% |
| Critical false-positive earnings anchors | 0 in the validation sample |
| Unexplained identity conflicts | 0 |
| Silent current-sector fallbacks | 0 |

**Deterministic research-start-date rule (frozen):** the first eligible research month is the earliest
month, after all required warm-up history, for which the registered V1 and V2 coverage thresholds are
met for **12 consecutive months**; the final date is the last complete month in the pinned snapshots.
The 50%/25%/25% split then applies to the resulting eligible session sequence. **The start date is
never selected after inspecting which years look favorable.**

## 5. Mapping table v0.2 — review fields added; countersign package

`sic_sector_etf_mapping` gains: `mapping_confidence` (HIGH = direct & historically well-supported ·
MEDIUM = broad but economically coherent · LOW = ambiguous across sectors) · `mapping_specificity` ·
`review_status` · `reviewer` · `review_date` · `source_reference`. **LOW-confidence rows are excluded
from the primary construction** (their stocks are unmapped-excluded for those periods) and reported
separately — never silently forced into a sector ETF. The CSV itself ships in the review package for
countersign (`evidence/mr_002/sic_sector_etf_mapping_v0.2.csv`); the owner reviews all rows affecting
the actual preliminary universe before hashing.

## 6. Full-run provenance controls (registered)

Preliminary-universe permaticker manifest · complete accession-request manifest · cached raw EDGAR
documents or content hashes · HTTP failure/retry log · extraction-version hash · crosswalk version +
hash · mapping-table version + hash · per-security rejection/exclusion reasons · checkpoint/resume
state · final row-count reconciliation. **No individual filing is regenerated from live EDGAR after
the snapshot is pinned unless the entire affected snapshot is re-versioned.**

## 7. Pilot verdicts (registered status; supersedes any "closure" reading of the pilot)

| Component | Status |
|---|---|
| V1 extraction pipeline | ✅ Technical pilot passed |
| V1 event identification | 🟡 Preliminary validation passed |
| V1 exact session timing | 🟡 Not yet validated |
| V2 SIC extraction pipeline | ✅ Technical pilot passed |
| V2 effective-dated mapping | 🟡 Pilot cases passed |
| Historical identity crosswalk | 🔴 Unresolved |
| V2 genuine SIC-change case | 🔴 Not yet exercised |
| Mapping-table approval | 🟡 Pending owner countersign |

## 8. Authorized order of work (owner final recommendation)

1. ✅ Correct the V1 in-session timing rule (this doc §1 + `earnings_anchors.py`, pilot re-run).
2. ✅ Freeze the crosswalk schema + source precedence (§2 — implementation follows).
3. ✅ Freeze coverage thresholds + the deterministic start-date rule (§4).
4. Resolve TWTR, FB, Google→Alphabet as mandatory identity tests.
5. Review + countersign the SIC mapping table (v0.2 CSV in the package).
6. Run the full preliminary-universe V1/V2 builds (§3 sequence, §6 provenance).
7. Independent V1 timing validation + a genuine SIC-change case.
8. Re-run V1/V2 verification ("Approved alternative implemented" labelling).
9. Data Availability Gate → populate §8a.
10. Present the completed v1.0 freeze candidate.

---

*v0.5 delta → items 4–10 above → Research-Design Freeze v1.0. Everything not amended here is
unchanged from v0.4; the strategy rules remain closed since v0.3.*
