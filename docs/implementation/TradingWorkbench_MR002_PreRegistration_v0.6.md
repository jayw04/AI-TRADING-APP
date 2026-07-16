# MR-002 — Pre-Registration v0.6 (DRAFT, delta to v0.5) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Authority:** v0.5 + **owner
crosswalk-go review** (`Docs/implementation/comments.md` 2026-07-11, archived at
`evidence/mr_002/MR002_OwnerReview_CrosswalkGo_2026-07-11.md`). **Supersedes v0.5 only where stated;
everything else unchanged.** The review APPROVED: the v0.5 governance additions, the crosswalk
implementation (go), the mapping methodology, the coverage gates, the start-date rule, and the
provenance controls — with the additions registered below.
**Status:** 🟡 **DRAFT — NOT FROZEN.** **GO executed:** the historical identity crosswalk is
implemented and **all 16 mandatory identity tests pass** (§2). **HOLD (owner):** the full-universe
crawl does not start until the mapping CSV **and** the crosswalk override rows are countersigned.

## 1. V1 field terminology (registered — separate fields, never overloaded)

Every anchor stores **five separate fields**: `event_time` (the availability instant driving the
blackout/cooling rules) · `event_time_basis` ∈ {**VERIFIED_RELEASE_TIMESTAMP**,
**EDGAR_ACCEPTANCE_PROXY**, **DATE_ONLY_PROXY**} · `availability_class` ∈ {**PRE_OPEN**,
**IN_SESSION**, **POST_CLOSE**, **DATE_ONLY**} · `cooling_start_session` · `cooling_end_session`
(the last two populated at the gate stage once the frozen trading calendar is pinned).
`availability_class` is never an assertion about when the company actually released earnings — only
VERIFIED_RELEASE_TIMESTAMP-basis rows may claim that. Implemented in `earnings_anchors.py`; pilot
re-run: 363 anchors → 142 PRE_OPEN / 0 IN_SESSION / 221 POST_CLOSE / 0 DATE_ONLY, all
EDGAR_ACCEPTANCE_PROXY.

## 2. Historical identity crosswalk — IMPLEMENTED; invariants frozen in code; 16/16 tests pass

`app/altdata/mr002/crosswalk.py` + `scripts/mr002_build_crosswalk.py`. **Interval-integrity invariants
enforced in code** (`integrity_check`): per (permaticker, ticker) intervals never overlap · a
permaticker's overlapping intervals never carry different CIKs (each trading date resolves to ≤ 1 CIK)
· gaps exist only as explicit unresolved periods · a lower-precedence source never silently overwrites
a higher-precedence interval (overlaps are errors, not merges) · every interval stores
`source (resolution source) · source_record_id · relationship_type · confidence · review_status`.

**Mandatory identity-test results (2026-07-11 run, 15 rows, 0 conflicts, 0 integrity errors):**

| Required outcome (owner table) | Test(s) | Result |
|---|---|---|
| Google→Alphabet: two CIK intervals, no overlap/history loss | predecessor/successor + classC window | ✅ 1288776 pre-2015-10-02, 1652044 after |
| FB→META: continuous issuer history across rename | 3 tests | ✅ same permaticker 194817; FB resolves only historically |
| TWTR: historical CIK despite current-map disappearance | 2 tests | ✅ CIK 1418091 from Sharadar `secfilings` (precedence 1) |
| GOOG/GOOGL: same issuer, separate permatickers | 2 tests | ✅ + the time-ambiguous GOOG symbol resolves by date (195146 in 2010 → 119496 in 2020) |
| Spin-off: no parent history inherited pre-separation | GEHC ×3 | ✅ excluded pre-spin; parent-GE evidence recorded |
| Acquisition: no successor backfill into predecessor dates | TWTR | ✅ nothing resolves after delisting |
| Unresolved identity: explicit exclusion, never current-map fallback | 2 tests | ✅ pre-existence + unknown symbols → None |

Artifacts: `evidence/mr_002/identity_crosswalk_v0.1.csv` (review export) ·
`crosswalk_manual_overrides_v0.1.csv` (5 Google/Alphabet rows, `pending_owner_review`) ·
`crosswalk_identity_tests.json` (report + **provisional** crosswalk/override hashes — frozen after
countersign). The full-universe crosswalk adds effective-dated CIK links wherever reorg cases surface;
unresolved periods stay excluded.

## 3. Mapping table — automated validation PASS; reconciliation resolved; eligibility policy registered

`scripts/mr002_validate_mapping.py` → `evidence/mr_002/mapping_validation_report.json`: **0 errors,
0 warnings** across the owner's required checks (range/period overlaps, single-ETF, proxy-inception
discipline incl. no open-start rows on XLC/XLRE, transition-date consistency, MEDIUM-rationale
specificity). **Row reconciliation:** v0.1 and v0.2 hold the **same 75-row key set** (pure
field-addition transform; no range split, no boundary change, no eligibility change) — the earlier
record's "74 rows" was a prose miscount, now corrected. **Canonical hash rule registered:** SHA-256
over rows sorted by `sic_start, sic_end, effective_from, effective_to, research_sector, sector_etf`;
final hash generated only after countersign.

**Primary-construction eligibility (registered):** **HIGH and reviewed-MEDIUM rows are eligible; LOW
excluded; unreviewed MEDIUM excluded until reviewed.** LOW matches return an explicit
EXCLUDED_LOW_CONFIDENCE outcome (logged + reported separately), never a silent null or forced ETF.
**MEDIUM impact review (gate stage, before countersign completes):** securities and universe-months
per confidence tier · top-20 securities by MEDIUM exposure · MEDIUM rows at XLC/XLRE boundaries ·
multi-sector-plausible MEDIUM ranges · a MEDIUM-removed sector-coverage diagnostic (a data-coverage
diagnostic — **no strategy signals**).

## 4. Coverage denominator discipline (registered)

All coverage percentages use one predeclared denominator: **preliminary price/liquidity/type-qualified
universe-months, before any V1 or V2 exclusion** (V1 coverage is never computed only among V2-resolved
names, or vice versa). The gate reports the full funnel — `preliminary_universe_months →
identity_resolved_months → v1_anchor_eligible_months → v2_sector_eligible_months →
joint_v1_v2_eligible_months → final_eligible_months` — plus exclusions by reason without
double-counting: identity unresolved · no prior earnings anchor · earnings blackout · SIC unavailable ·
mapping unavailable · LOW-confidence mapping · sector ETF not yet live.

## 5. Start-date rule clarification (registered)

Once the earliest qualifying 12-consecutive-month sequence determines the start month, **later
temporary coverage deterioration does not move the research start date** — later months remain in the
sample with affected names excluded under the frozen eligibility rules, unless the registered
individual-calendar-year minimum-coverage gate fails, which stops the entire Data Availability Gate.
The system never searches for a later, cleaner interval after seeing the full history.

## 6. Provenance store additions (registered for the full crawl)

Each retrieval record stores: EDGAR response-body hash · request URL / accession identifier ·
retrieval timestamp · HTTP status · parser version · extraction-result hash · rejection reason · retry
count · cached-vs-newly-retrieved flag. **After snapshot pinning, a missing or corrupt filing FAILS
the build** — never an unrecorded live refetch.

## 7. Pilot verdict table (owner-updated)

V1 extraction ✅ · V1 date/event identification 🟡 strong preliminary · V1 availability semantics ✅
(PIT rule corrected) · V1 independently verified release timing 🟡 sample-validation dependent ·
V2 SIC extraction ✅ · V2 effective-date transitions ✅ · **historical identity crosswalk 🟡 → tests
now 16/16 ✅ (implementation done; countersign pending)** · genuine SIC-change case 🔴 still required ·
mapping methodology ✅ · mapping content 🟡 pending CSV countersign · full-universe coverage 🔴 not yet
run · Research-Design Freeze 🔴 not yet eligible.

## 8. Order of work (owner list, updated status)

1. ✅ Implement the historical identity crosswalk. 2. ✅ Pass all mandatory identity tests (16/16).
3. ✅ Reconcile the 74-vs-75 row question (same key set; prose miscount). 4. ⏳ **Owner review of every
HIGH and MEDIUM mapping row + override countersign** (the HOLD gate for the crawl). 5. ⏳ Genuine
SIC-change case (full-universe run). 6. ⏳ Freeze + hash crosswalk and mapping (canonical order).
7. ⏳ Preliminary universe (§3 v0.5 sequence). 8. ⏳ Full V1/V2 builds + coverage gate (§4 funnel).
9. ⏳ §8a. 10. ⏳ v1.0 freeze candidate.

---

*v0.6 delta → owner countersign (mapping rows + overrides) → full-universe builds → gate → §8a → v1.0.
Strategy rules unchanged and closed since v0.3.*
