# MR-002 — Validation-Phase Findings v1.0 (V1 re-verification + PIT-SIC gate)

**Date:** 2026-07-11 · **Reports:** `MR002_V1_ReVerification_v1.0.json` ·
`MR002_PITSIC_Gate_v1.0.json` · **Denominator:** fixed **40,750** universe-months throughout (never
shrunk by excluding difficult cases).

## PIT-SIC integrity (owner's higher-risk review) — ALL CLEAN

| Check | Result |
|---|---|
| No forward-fill before first observed SIC | ✅ enforced structurally + verified (coverage counts a month only under a segment valid AS OF that month) |
| Effective dates monotonic (ordered, non-overlapping, contiguous boundaries) | ✅ zero violations |
| Same-day conflicts | ✅ **0** (re-verified from raw observations) |
| SIC changes internally consistent (every boundary matches an observation carrying the new SIC) | ✅ zero violations |

**Stratified review of the 89 SIC-changing issuers:** 68 one-change · 21 multiple-change · 7 within
180d of a taxonomy boundary · 10 changes established by amendment filings · 9 issuers with
same-quarter conflicting filings (transition quarters — same-day conflicts remain zero).
**UBER:** 7372 [2019-06-03 → 2019-11-05) → 7389 [2019-11-05 → open) — the valid pipeline
demonstration; sector pinned Industrials by the approved security override. **BKNG:** 7389
[2010-02-18 → 2019-11-07) → 4700 [2019-11-07 → open) — sector pinned XLY by the approved override.

## FINAL PIT-SIC coverage gate — DOES NOT CLEAR YET (honest result, cause identified)

| | Universe-months | % of 40,750 |
|---|---|---|
| HIGH | 25,992 | 63.78% |
| MEDIUM | 10,703 | 26.27% |
| Security override | 2,545 | 6.25% |
| **Final V2 eligible** | **39,240** | **96.29% — below the 98% gate** |
| Pre-first-observation gap / no PIT SIC | 985 | 2.42% |
| excluded_low | 353 | 0.87% |
| needs_revision (DHR) | 163 | 0.40% |
| identity unresolved | 9 | 0.02% |

Annual coverage: 2013 = 92.83% and 2014 = 93.47% **fail the ≥95%/year minimum**; 2015+ all ≥94.97%
(2015 marginal), improving to 97–98.7% in later years. **The gate was NOT lowered and the denominator
was NOT shrunk** — per the registered rule this is a stop-and-review finding.

### Root cause — a systematic, already-solved identity pattern

Every one of the top-15 pre-first-observation securities is a **corporate-reorganization
predecessor-CIK chain**: the crosswalk maps the security to its CURRENT CIK for all history, but the
current CIK only exists from a holding-company reorg / merger / redomiciliation, so pre-reorg SIC (and
V1) history sits under an unregistered predecessor CIK — **exactly the Google→Alphabet case** the
crosswalk's manual-override mechanism was built for:

| Security | Gap months | Current CIK first obs | Reorg event |
|---|---|---|---|
| BLK | 143 | 2024-11 | 2024 holding-company reorg |
| PSKY | 100 | 2025-05 | 2025 Paramount–Skydance merger |
| DIS | 77 | 2019-05 | 2019 TWDC holding-company reorg |
| NXPI | 68 | 2019-10 | NXP re-registration |
| VTRS | 64 | 2020-05 | 2020 Mylan/Upjohn combination |
| TEVA | 62 | 2018-02 | filer-entity change |
| APA | 61 | 2021-05 | 2021 APA Corp holdco |
| DD | 59 | 2017-11 | 2017 DowDuPont |
| CI | 50 | 2019-02 | 2018 Cigna holdco |
| AVGO | 42 | 2018-06 | 2018 Broadcom Inc |
| TEAM | 41 | 2022-11 | 2022 US redomiciliation |
| MRVL | 34 | 2021-06 | 2021 holdco |
| MDT | 26 | 2015-02 | 2015 Medtronic plc |
| WBA | 24 | 2014-12 | 2014 Walgreens Boots holdco |
| HTZGQ | 23 | 2016-08 | 2016 Hertz holdco |

(+ a tail of smaller cases; full list derivable from the gate JSON.)

### Proposed remedy (owner decision required — the registered mechanism)

1. Research + draft **effective-dated predecessor-CIK crosswalk overrides** for every
   pre-first-observation issuer (same schema/evidence discipline as the approved Google→Alphabet
   rows; each row owner-countersigned).
2. **Supplemental crawl** of the predecessor CIKs only (small: tens of CIKs; pinned-manifest +
   hardened fetcher + smoke pre-flight gate).
3. Recompute the gate. Projection: recovering the ~985 predecessor months alone lifts coverage to
   ~98.7% and repairs the 2013/2014 annual failures (the gaps concentrate early — before the reorg
   dates the history exists under the predecessors).
4. Independent items unchanged: DHR stays excluded pending the owner's archive evidence; excluded_low
   (353) stays excluded by policy; the 9 identity-unresolved months are the known delisting tails.

**No SIC forward-filling and no gate/denominator adjustment is proposed — the remedy is identity
completion through the countersigned override channel.**

## V1 re-verification — "Approved alternative implemented: PIT estimated earnings-risk blackout"

**Reproduction: 100.000%.** The V1 set was REBUILT independently from EDGAR (fresh fetches through the
hardened fetcher) and matched the stage-2 snapshot **40,153 / 40,153 anchors, zero divergence in
either direction** — the strongest available evidence that the anchor pipeline is deterministic and
the stage-2 data faithful.

**The 534-class records — complete taxonomy, zero unexplained:**

| Category | Count |
|---|---|
| Duplicate anchors collapsed (same-(CIK, period) 2.02 filings; earliest acceptance kept) | **534** |
| Amendments folded into their originals (8-K/A; never a new anchor) | **269** |
| Amendment-without-original (first PIT knowledge; kept as flagged anchor) | 52 |
| Missing dates / unmatchable / empty / unexpected formats / other | **0** |

534 + 269 = 803 = candidates (40,956) − accepted (40,153) — arithmetic closes exactly. The collapses
are economically justified (same-period semantics, not syntactic dedup), and **same-period duplicates
AFTER collapse = 0**. (An initial draft double-counted the 534 from two ledgers; corrected.)

**Temporal correctness (no leakage):** availability-class and session-date re-derivations = **0
mismatches** across 40,153 anchors. 408 anchors (1.0%) carry a report-period label dated after
acceptance — the furnish-the-evening-before pattern; **no leakage risk** because blackout/cooling key
on the ACCEPTANCE availability instant, never the label date. 26 period-ordering anomalies + 5
stale-period labels flagged for the manual sample. `event_time_basis` = EDGAR_ACCEPTANCE_PROXY for
100% (verified-release timestamps remain the registered future upgrade). Late-information exceptions
in-build: 52 (the amendment-without-original class, all flagged).

**V1 coverage gate (fixed 40,750 denominator): 39,690 covered = 97.40% ≥ the 95% overall gate ✅;
every year ≥ the 90% annual minimum ✅** (min 94.50% in 2013, rising to 100% in 2026). Issuers with
anchors: 742; without: 4. The residual no-prior-anchor months are dominated by the SAME
predecessor-CIK chains as the V2 shortfall — the proposed identity remedy lifts both gates together.
