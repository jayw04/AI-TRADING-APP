# MR-002 — Predecessor-CIK Remedy: Evidence Package v1.0

**Date:** 2026-07-11 · **Authority:** owner GO (conditional) 2026-07-11 · **Status:** ⏳ **PROVISIONAL
— pending owner countersign of the override registry.** Gates, denominator (40,750), the 98% overall
floor, the 95% annual floor, and the no-pre-observation-forward-fill prohibition are **unchanged**.

## Headline

| Metric | Before | After | Gate |
|---|---|---|---|
| **Final V2 coverage** | 39,240 / 40,750 = **96.29%** | **40,132 / 40,750 = 98.48%** | ≥ 98% ✅ |
| **Worst annual year** | 2013 = 92.83% (fail) | **2026 = 97.14%** (min) | ≥ 95% every year ✅ |
| Integrity violations | 0 | **0** (all re-run from scratch) | ✅ |

## The 985 gap months had FOUR causes, not one (honest refinement of the approved remedy)

| Cause | Securities | Months | Remedy applied |
|---|---|---|---|
| **A — predecessor-CIK chain** | 21 | 751 | Effective-dated identity overrides (the approved mechanism) |
| **B — FPI form-coverage gap** | 6 (+Encana) | 181 | Extended the form set to 20-F/40-F — **same CIK, no identity bridging** |
| **C — bankruptcy / failure** | 4 | 33 | **Left uncovered** (HTZGQ, WFTIQ, ENDPQ, FRCB) — continuity not established |
| **D — truncated cache (disk incident)** | 2 (+2 CIKs) | 20 | Re-fetched 43 accessions with the hardened fetcher — a **data-integrity repair** |

Cause B was *not* an identity problem: NXPI/TEVA/TEAM/CPRI/CRON/CGC filed **20-F/40-F under the same
CIK** during their gap years (foreign private issuers that later became domestic filers). Treating them
as identity overrides would have been wrong; extending the form set is strictly more conservative.

Cause D was a **defect in our own stage-2 artifacts**: the pre-hardening fetcher wrote cache objects
non-atomically, so the disk-full window left **truncated files**; the rerun served them from cache
(no fetch, no failure logged — which is why the reconciliation looked clean) and 43 filings across 4
CIKs parsed as `sic=NULL`. Fresh fetches parse perfectly (RTX 2010 10-K → SIC 3724). **The owner's
append-safe ordering fix (tmp → fsync → atomic rename) makes this impossible in the hardened fetcher**
— and the supplemental crawl proves the repair: missing-SIC filings fell 43 → 3.

## Owner conditions — compliance

1. **Effective-dated, not timeless** ✅ — each security's crosswalk interval is **split at the
   documented reorganization event date**: predecessor `[start, event−1]`, successor `[event, …]`.
   No overlaps (verified: `crosswalk_different_cik_overlap = 0`), no gaps.
2. **Per-row evidence** ✅ — `predecessor_override_registry_v0.1.csv` carries permaticker, predecessor
   CIK, successor CIK, effective dates, event type, authoritative evidence (8-K12B / S-4 + the
   **legal effective date, not the filing date**), continuity rationale, baton test, predecessor entity
   name/SIC/filing range, gap months, flags, manifest-inclusion, and `review_status=pending_countersign`.
3. **Continuity vs replacement** ✅ — 21 continuous cases (1:1 holdco conversions, redomiciliations,
   combinations). **Four flagged for your scrutiny**: PSKY (merger, new control), DD (merger with
   subsequent spin-offs), AGN (ticker reused after a target acquisition — the acquired Allergan Inc,
   CIK 850693, is explicitly **NOT** bridged), OVV (predecessor was an FPI filer). The four
   bankruptcy/failure securities are **not** bridged and remain uncovered.
   **Verification caught two errors in the curated map** (QDEL had resolved to DexCom, PRGO to HLTH
   Corp) — corrected to Quidel Corp (353569) and Perrigo Co (820096). **Baton test: 21/21 PASS.**
4. **Predecessor-only supplemental crawl** ✅ — pinned manifest (SHA-256), hardened fetcher +
   truststore, **smoke pre-flight PASS immediately before the crawl**, partial-report enabled, no
   unrelated issuer refresh. 1,491 requests; 133.7MB uncompressed → **12.7MB stored (10.5× ratio)**;
   no oversized objects (read cap held).
5. **Provenance preserved** ✅ — every observation is stored under **the CIK that actually filed it**.
   Nothing is rewritten as though the successor had filed it; the security attachment happens at gate
   time through the effective-dated override.
6. **All integrity tests re-run** (not carried forward) ✅ — segments rebuilt from scratch on the merged
   observation set:

| Check | Result |
|---|---|
| Same-day conflicts | **0** |
| Segments before first observation (pre-observation fill) | **0** |
| Non-contiguous / negative-duration segments | **0** |
| Boundary without matching observation | **0** |
| Duplicate observation keys (after dedupe) | **0** |
| Crosswalk different-CIK interval overlap | **0** |
| Merge collisions deduped (stage-2 ∩ supplemental) | 66 — all CIK 30554 (EIDP), identical filings/SIC; deduped, reported |

## Coverage funnel (fixed 40,750 denominator)

| Tier | Before | After |
|---|---|---|
| HIGH | 25,992 | 26,696 |
| MEDIUM | 10,703 | 10,816 |
| Security override | 2,545 | 2,620 |
| **Final V2 eligible** | **39,240 (96.29%)** | **40,132 (98.48%)** |
| Pre-first-observation / no SIC | 985 | **93** |
| excluded_low | 353 | 353 *(unchanged)* |
| needs_revision (DHR) | 163 | 163 *(unchanged — archive evidence still owed)* |
| identity unresolved | 9 | 9 *(unchanged — delisting tails)* |

**Annual coverage, every year ≥ 95%:** 2013 97.47 · 2014 97.67 · 2015 98.33 · 2016 99.20 · 2017 99.07
· 2018 98.80 · 2019 98.80 · 2020 98.87 · 2021 98.67 · 2022 99.10 · 2023 99.17 · 2024 98.47 · 2025 97.47
· 2026 97.14.

**Residual 93 uncovered months:** HTZGQ 23, WFTIQ 7, ENDPQ 2 (bankruptcy — deliberately not bridged) ·
VTRS 29, AVGO 17, DD 3, CI 2, DIS 2, MRVL 2, BLK 2 (short residual windows where the predecessor's own
first filing post-dates the security's earliest universe month — **no forward-fill applied**, honestly
left uncovered).

## Artifacts

`predecessor_override_registry_v0.1.csv` (countersign artifact) ·
`predecessor_registry_verification.json` (EDGAR evidence per row) · `gap_cause_classification.json` ·
`predecessor_discovery.json` · `supplemental/` (pinned manifest + SHA-256, run report, observations,
segments, response manifest) · `MR002_PITSIC_Gate_v2.0.json` (recomputed gate) ·
`MR002_HardenedSmoke_Report.json` (pre-flight PASS).

**Not declared passed. Not frozen.** Awaiting your countersign of the 21 registry rows (including the
four scrutiny flags), after which the Data Availability Gate, §8a, and the v1.0 freeze candidate follow.
