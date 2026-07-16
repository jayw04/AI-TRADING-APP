# MR-002 — V1/V2 Build Pilot & Validation-Sample Record v0.1

**Date:** 2026-07-11 · **Pre-reg:** v0.4 §8 (owner-authorized builds) · **Status:** pilot complete;
full-universe runs + owner countersign of the mapping table pending (hashes remain PROVISIONAL until
then, per the owner control: *hashes are generated after manual validation and before the gate*).

**Artifacts:** `apps/backend/app/altdata/mr002/{earnings_anchors,sic_history}.py` ·
runners `apps/backend/scripts/mr002_build_{earnings_anchors,sic_history}.py` ·
store `apps/backend/data/mr002_provenance.duckdb` (tables: `earnings_anchors`, `anchor_rejections`,
`cik_permaticker_crosswalk`, `sic_observations`, `sic_segments`, `sic_conflicts`) ·
metrics `v1_anchor_metrics.json`, `v2_sic_metrics.json` ·
mapping `sic_sector_etf_mapping_v0.2.csv` (DRAFT — review fields added per the build-pilot review:
confidence HIGH 27 / MEDIUM 41 / LOW 7 rows, LOW excluded from primary construction; not yet
frozen/hashed; v0.1 retained for lineage).

## V1 pilot — earnings anchors (10-ticker sample, since 2012)

- **363 anchors** across 8 issuers (9 securities — GOOG/GOOGL share one issuer); TWTR explicitly
  unresolved (below). 2 anchors amended by 8-K/A (folded, no new anchors); 0 duplicates collapsed;
  0 rejections; 0 amendment-without-original exceptions.
- **Date agreement (owner-corrected wording, v0.5 §1):** *Item 2.02 anchor dates show complete
  agreement with Sharadar code-22 dates in the pilot* (META 42/42, AAPL 43/43, GOOGL 43/43, GEHC
  15/15, KVUE 13/13, AMT 42/42, NFLX 44/44, VZ 42/42, ±1 day); *exact earnings-event identification
  and market-session timing remain subject to independent manual validation* against archived release
  timestamps (both records may derive from the same 8-K). Our anchor counts exceed EVENTS counts
  because EDGAR reaches **pre-2016** — the anchors relieve the EVENTS depth floor.
- **Interval distribution (the false-anchor detector):** median **91 days** (clean quarterly cadence);
  1.97% of intervals < 60d and 3.94% > 110d — small tails, to be itemized per-case in the full-universe
  run report.
- **Availability classes (re-run under the v0.5 §1 PIT-safe semantics):** **142 PRE_OPEN / 0
  IN_SESSION / 221 POST_CLOSE / 0 DATE_ONLY_CONSERVATIVE**; every anchor's `event_time_basis` =
  `edgar_acceptance_proxy` — acceptance-based rows are never labelled true BMO/AMC. The stratified
  manual timing validation and its error rate remain owed (a v0.5 §4 coverage gate).

## V2 pilot — effective-dated SIC history (9 tickers, 365 filings, since 2012)

- **365/365 filings yielded a PIT SIC** (0 missing) after adding the ranged-fallback header fetch:
  accessions before ~2014 have no `-index-headers.html` (404) — the SGML header is read from the first
  4 KB of the full-submission `.txt` via an HTTP Range request instead. 0 same-day conflicts.
- Every sampled issuer shows **one stable SIC segment** across the window (SIC changes are rare, as
  expected); all sector transitions therefore come from the **mapping table's effective dating** — the
  correct mechanism per the owner's design.

## Validation-sample results (pre-reg v0.4 §8 mandatory set)

| Case | Ticker(s) | Result |
|---|---|---|
| **Sector change WITHOUT SIC change (mandatory)** | **META** | ✅ SIC 7370 constant since 2012; mapping flips XLK → **XLC at 2018-06-19** via the effective-dated 7370 row. GOOGL identical. |
| XLC boundary (media) | NFLX | ✅ SIC 7841 constant; XLY → **XLC at 2018-06-19**. |
| XLC boundary (telecom) | VZ | ✅ SIC 4813 constant; XLK (pre-2018 SPDR taxonomy) → **XLC at 2018-06-19**. |
| **XLRE boundary** | AMT | ✅ SIC 6798 (REIT) constant; XLF → **XLRE at 2015-10-08**. Timeline diagnostic double-boundary artifact fixed in the runner. |
| **Dual-class issuer** | GOOG + GOOGL | ✅ One CIK (1652044) → one anchor set + one SIC history; two tickers/permatickers in the crosswalk. Surfaced by a real PK collision in run 1 → pipeline made **issuer-level by design**. |
| **Identity change (crosswalk must be effective-dated)** | GOOG/GOOGL | ⚠ **Confirmed real:** Alphabet's CIK exists only from the 2015-10 holding-company reorg — pre-2015 Google history lives under a different CIK (1288776). The v0 crosswalk (current `company_tickers.json` + TICKERS permaticker) cannot see this; the **full build must add effective-dated CIK links** for reorg cases. |
| **Spin-offs** | GEHC (2023-01), KVUE (2023-05) | ✅ Anchors and SIC segments begin at first post-spin filings (GEHC 2023-02-15, KVUE 2023-06-02); no pre-spin phantom history. |
| **Acquisition / delisted** | TWTR | ⚠ **Explicitly unresolved** by the current-day `company_tickers.json` (delisted names drop out). No silent mapping (CAP-024 ✓). The **full build needs a historical CIK source** for delisted names (candidates: Sharadar TICKERS `secfilings` URL, EDGAR full-text company search, or a point-in-time company_tickers archive). |
| **Ticker change** | META (was FB, 2022) | ✅ Current map resolves META to the same CIK; anchors/SIC continuous across the rename (CIK-keyed, ticker-independent). A reverse lookup of retired tickers (FB) has the same gap as TWTR — folded into the historical-crosswalk item. |
| **SIC-change company** | — | ❌ **Not yet exercised** — no sampled issuer changed SIC. The full-universe run must surface and manually verify ≥1 genuine SIC-change case. |

## Pilot verdicts (registered in pre-reg v0.5 §7 — the pilot is NOT V1/V2 closure)

| Component | Status |
|---|---|
| V1 extraction pipeline | ✅ Technical pilot passed |
| V1 event identification | 🟡 Preliminary validation passed |
| V1 exact session timing | 🟡 Not yet validated |
| V2 SIC extraction pipeline | ✅ Technical pilot passed |
| V2 effective-dated mapping | 🟡 Pilot cases passed |
| Historical identity crosswalk | 🔴 Unresolved |
| V2 genuine SIC-change case | 🔴 Not yet exercised |
| Mapping-table approval | 🟡 Pending owner countersign (v0.2 CSV; LOW rows excluded from primary) |

## Crosswalk implementation results (2026-07-11, post crosswalk-go review)

**Implemented** (`app/altdata/mr002/crosswalk.py` + runner): **16/16 mandatory identity tests PASS,
0 conflicts, 0 integrity errors** — TWTR resolved via Sharadar `secfilings` CIK; FB→META continuous;
Google→Alphabet two-interval CIK chain via the reviewed override table (5 rows, pending countersign);
GOOG symbol resolves time-dependently (perma 195146 in 2010 → 119496 in 2020); GEHC excluded pre-spin
with parent-GE evidence; no acquisition backfill; unknown/pre-existence symbols → explicit None.
Interval-integrity invariants enforced in code. Mapping validator: **PASS, 0 errors/warnings**;
v0.1↔v0.2 row reconciliation = identical 75-row key sets (the "74 rows" earlier in this record was a
prose miscount). Hashes remain provisional until owner countersign. See pre-reg v0.6.

## Open items before hashing / the gate

1. ✅ **RESOLVED — historical CIK↔ticker crosswalk** implemented with frozen schema + source
   precedence; mandatory identity tests 16/16. Remaining: owner countersign of the 5 override rows,
   then reorg-case expansion during the full-universe build.
2. **Owner countersign of `sic_sector_etf_mapping_v0.2.csv`** (75 rows with rationale + confidence /
   specificity / review fields; 7 LOW-confidence rows excluded from primary construction). Hash frozen
   only after that review; the owner reviews all rows affecting the actual preliminary universe.
3. **A genuine SIC-change validation case** from the full-universe run.
4. **Full-universe builds** (top-250/150 monthly universe → issuer list → anchors + SIC histories) —
   after universe construction at the gate stage; laptop pilot throughput ≈ 8 req/s suggests the full
   crawl belongs on the box or a long background run.
5. V1 re-verification will report **“Approved alternative implemented: PIT estimated earnings-risk
   blackout”** (registered label), not “PASS”.
