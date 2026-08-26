# SEC-001 V3 — Governed Weekly-Grid Classification-Coverage Measurement v1.0

**Status:** MEASURED 2026-08-26. The measurement is complete and the frozen decision rule has been
applied **once, mechanically**, as §3 of the coverage freeze requires.

> ## ⚠ OUTCOME — the frozen coverage gate **FAILS**. Freeze §3 step 3 ⇒ **STOP / REDESIGN** under §10.3.
>
> Overall ticker-week coverage **92.801%**. Only **425 of 1,247** rebalances meet `θ_name = 0.95`.
> **No trailing span of any length** satisfies `θ_window = 0.95`, so the evaluation period cannot be
> re-frozen forward and the earliest-qualifying-start rule has nothing to select from.
>
> This is a **coverage determination, not an economic result.** No return, Sharpe, drawdown or
> sector quantity was computed, and none may be inferred from it. §19's three states apply: this is
> **BLOCKED**, not STOP-on-evidence and not GO.

**Governing definition:** `SEC001_V3_PreCrawl_CoverageFreeze_v1_0.md` §2 (four clauses) and §3
(θ values and the decision rule), sealed 2026-08-23 **before** any coverage table existed.
**Join rule:** owner adjudication 2026-08-26 (F-2) — `ticker/week → frozen CIK resolution →
effective-dated CIK classification → attach the ticker identity back`. The segment filename ticker
is never used as a join key.
**Source epoch:** `SUCCESSOR_EPOCH_0_1167`, ruled COMPLETE / INTEGRITY PASS —
`SEC001_V3_SuccessorEpoch_TerminalIntegrityReport_v1_0.md`.

---

## 1. Inputs — every one pinned by SHA-256

| artifact | origin | bytes | sha256 |
|---|---|---|---|
| `governed_grid.json` | S3 `sealed/2026-08-24/`, VersionId `.l3F3H_f3YrP0CeCbsd7I64WPcheuuAe` | 22,452 | `8c962f2e2d370ecd…` |
| `pit200_membership_v2.json` | S3 `sealed/2026-08-24/`, VersionId `Yp4_vEljByrXunNWH8abpziMi0FHD1Pa` | 2,038,984 | `985672ff3cf49a59…` |
| frozen identity rows (from `SEC001_V3_FROZEN_IDENTITY_ORDER.json` `e8445b0b…`) | epoch host `/opt/epoch/manifest` | 47,150 | `82f317acb791cc94…` |
| classification segments projection (from the epoch's 1,146 per-CIK segment files) | epoch host | 83,066 | `90d7d9f7b55482ea…` |
| countersigned `sic_mapping` (110 rows, Jay Wang 2026-07-11) | `mr002_research.duckdb` | 52,158 | `633dc4cfa4ee9e7f…` |

Supporting identities re-verified at read time: grid internal `grid_sha256`
`baf0da7c20bed590…` (matches the value the PIT-200 union artifact records as its upstream);
CIK-resolution artifact `1f7d523b9419301a…`; PIT-200 union `d338e65f9ece1ff7…`; full segments
canonical digest `678e6b540ee796c5…` (1,146 files, 307,115 B).

**Grid.** `SEC001_V3_MONDAY_RTH_V1` — Monday 10:24 America/New_York, 2000-01-01 → 2026-06-12,
**1,247 slots**, 133 holiday Mondays skipped, 0 thin sessions. Every slot carries exactly **200**
PIT-200 names ⇒ denominator **249,400 ticker-slot cells**, which reconciles exactly with the union
artifact's summed `slot_count` of 249,400.

⚠ `pit200_membership_v2.json` holds **1,380** keys — the 1,247 governed slots **plus the 133 holiday
Mondays**. Only the 1,247 governed slots were measured. A measurement that iterated the membership
file's keys would silently inflate the denominator by 26,600 cells.

**Close-t cutoff.** `et_close_cutoff_iso` (`app/research/mr002/spq1/phase2b/cutoff.py`) — 16:00
America/New_York converted to UTC, applied verbatim.

---

## 2. The four clauses, as implemented

Implemented exactly as frozen; no clause relaxed, added, or reordered.

1. **Identity** — the slot's ticker resolves to a permanent identity in the frozen 1,167-identity
   population. All 1,167 tickers are distinct, so the map is 1:1.
2. **Crosswalk** — that permaticker maps to a CIK. The governed artifact resolves **1,167 / 1,167 as
   `RESOLVED_CIK`, 0 unresolved, 0 conflicts**, so this clause never fails. ⚠ See §5 F-C1: the
   artifact is **snapshot-resolved and self-describes as "NOT an effective-dated CIK history"**, and
   that limitation is load-bearing for the result.
3. **PIT SIC** — the latest SIC observation for that CIK with `accepted_utc <= close t`, from the
   epoch's effective-dated segments; a same-timestamp disagreement fails closed as
   `SECTOR_EFFECTIVE_DATE_CONFLICT`.
4. **Mapping** — the resolved SIC falls in a `sic_mapping` row covering it and effective at t (latest
   `effective_from` governs; NULL ranks below any dated row), whose `review_status` is **not**
   `excluded_low`.

`R(t) = resolved names / 200`.

---

## 3. Result

### 3.1 Ticker-week coverage — the V3-RC eligibility denominator

```
governed rebalances                     1,247
ticker-slot cells (denominator)       249,400
resolved cells    (numerator)         231,446
unresolved cells                       17,954
overall ticker-week coverage          92.801%

rebalances meeting theta_name = 0.95      425 / 1,247  = 34.082%
R(t)   min 0.0000   p05 0.8550   median 0.9400   p95 0.9650   max 0.9800
```

⭐ **`R(t)` never reaches 1.0 anywhere in 26 years.** The best rebalance in the record resolves
196 of 200.

### 3.2 CIK-week coverage — diagnostic only

```
cik-slot cells                        247,004
resolved                              229,535
overall CIK-week coverage             92.928%
ticker-slot minus cik-slot              2,396   = the shared-CIK duplicate cells (F-2's population)
```

The two figures differ by 0.127 pp. **The shared-CIK effect is real but small**, and under the ruled
CIK join it is resolved rather than scored unclassified — which is exactly what F-2 was raised to
prevent. Had the measurement joined on the segment filename ticker, 21 identities including GOOG,
MRK, CMCSA, BRK.A, JCI, HCA, CHTR, PBR, Z and AAL would have been scored unclassified for every slot
they were in.

### 3.3 Sources of uncovered cells

| class | cells | % of all cells | % of unresolved |
|---|---|---|---|
| C3 — no SIC accepted by close t | 12,670 | 5.080% | 70.6% |
| C4 — mapping row `review_status = excluded_low` | 5,224 | 2.095% | 29.1% |
| C3 — CIK has no SIC segment at all (`GX`, `FRCB`, `LHSP`) | 60 | 0.024% | 0.3% |
| C1 / C2 — identity or crosswalk failure | **0** | — | — |
| C3 / C4 — `SECTOR_EFFECTIVE_DATE_CONFLICT` | **0** | — | — |
| **total unresolved** | **17,954** | **7.199%** | 100% |

⭐ **Clauses 1 and 2 never fail, and no resolution anywhere in 249,400 cells hits a
`SECTOR_EFFECTIVE_DATE_CONFLICT`.** The identity chain and the frozen resolver are not the problem.

### 3.4 Per-year profile

| year | slots | cells | resolved | R_year | slots ≥ 0.95 |
|---|---|---|---|---|---|
| 2000 | 47 | 9,400 | 6,263 | 66.63% | 0 |
| 2001 | 48 | 9,600 | 8,314 | 86.60% | 0 |
| 2002 | 48 | 9,600 | 8,617 | 89.76% | 0 |
| 2003 | 48 | 9,600 | 8,861 | 92.30% | 0 |
| 2004 | 47 | 9,400 | 8,765 | 93.24% | 0 |
| 2005 | 46 | 9,200 | 8,613 | 93.62% | 0 |
| 2006 | 46 | 9,200 | 8,636 | 93.87% | 0 |
| 2007 | 48 | 9,600 | 9,081 | 94.59% | 18 |
| 2008 | 48 | 9,600 | 9,078 | 94.56% | 21 |
| 2009 | 48 | 9,600 | 9,131 | 95.11% | 37 |
| 2010 | 47 | 9,400 | 8,821 | 93.84% | 0 |
| 2011 | 46 | 9,200 | 8,671 | 94.25% | 10 |
| 2012 | 47 | 9,400 | 8,931 | 95.01% | 33 |
| 2013 | 48 | 9,600 | 9,087 | 94.66% | 26 |
| 2014 | 48 | 9,600 | 8,994 | 93.69% | 6 |
| 2015 | 48 | 9,600 | 9,132 | 95.12% | 33 |
| 2016 | 46 | 9,200 | 8,885 | **96.58%** | **46 / 46** |
| 2017 | 46 | 9,200 | 8,874 | 96.46% | **46 / 46** |
| 2018 | 48 | 9,600 | 9,107 | 94.86% | 32 |
| 2019 | 48 | 9,600 | 8,955 | 93.28% | 0 |
| 2020 | 48 | 9,600 | 8,899 | 92.70% | 0 |
| 2021 | 47 | 9,400 | 8,638 | 91.89% | 0 |
| 2022 | 45 | 9,000 | 8,492 | 94.36% | 15 |
| 2023 | 45 | 9,000 | 8,634 | 95.93% | **45 / 45** |
| 2024 | 48 | 9,600 | 9,146 | 95.27% | 39 |
| 2025 | 48 | 9,600 | 9,046 | 94.23% | 15 |
| 2026 | 20 | 4,000 | 3,775 | 94.38% | 3 |

Coverage is **not** monotonically improving. It peaks in 2016–2017, collapses across 2019–2021, and
degrades again through 2025–2026. The late-period decay matters most: it is what makes the gate
unrecoverable by moving the start date forward.

---

## 4. Freeze §3 decision rule — applied once, mechanically

`θ_name = 0.95` · `θ_window = 0.95` · `θ_span_min = 20 years` (a start later than 2006-06-12 is a STOP).

**Lemma used, so that the outcome does not depend on window boundaries.** The five regenerated
windows *partition* the span, so "all five windows ≥ 0.95" implies "span-wide pass fraction ≥ 0.95".
A span whose own pass fraction is below 0.95 therefore cannot have five admissible windows under any
boundary placement. The V2 window helper is consequently **not needed to decide the gate** — it would
only be needed to *seal* an admissible span. No window was constructed, so no window boundary could
have been influenced by anything.

| trailing span start | rebalances | span (yrs) | pass fraction | meets 0.95? |
|---|---|---|---|---|
| 2000-01-03 | 1,247 | 26.4 | 34.082% | no |
| 2006-06-12 (θ_span_min limit) | 944 | 20.0 | 45.021% | no |
| 2010-01-04 | 773 | 16.4 | 45.149% | no |
| 2015-01-05 | 537 | 11.4 | 51.024% | no |
| 2020-01-06 | 301 | 6.4 | 38.870% | no |
| 2023-01-09 | 161 | 3.4 | 63.354% | no |
| 2025-01-06 | 68 | 1.4 | 26.471% | no |
| **best trailing span, 2022-10-31** | **169** | **3.6** | **65.089%** | **no** |

**Trailing spans satisfying `θ_window` span-wide: 0 of 1,247.** The best any start date achieves is
65.089% against a required 95%. The earliest-qualifying-start rule has an empty candidate set, and
`θ_span_min` is never reached because no span qualifies at any length.

⇒ **Freeze §3 step 3: the outcome is STOP / REDESIGN under §10.3.**

**How wide is the miss.** `θ_name` permits at most 10 unresolved of 200 at a rebalance. Observed
unresolved-per-rebalance: min 4, p05 7, **median 12**, p95 29, max 200. The **median rebalance misses
the gate by 2 names.** The failure is *narrow in magnitude and broad in incidence* — 822 of 1,247
rebalances exceed the 10-name budget, most of them barely. That shape is what makes the attribution
below decisive rather than academic: two identified classes, either one of which would change the
verdict.

---

## 5. Attribution — what the gate is actually lost to

### F-C1 — successor-CIK identity lineage: **10,800 cells (60.2% of all unresolved), 150 names**

The frozen population addresses every permanent identity by the CIK it resolves to **today**. Where an
issuer re-registered under a new CIK — inversion, holdco reorganisation, merger-of-equals, spin — the
identity's PIT-200 membership *pre-dates the first filing of the CIK it is addressed by*, and no SIC
exists for it before that date.

**366 of 1,167 identities have PIT-200 membership earlier than their CIK's first in-window filing.**
Largest contributors, in unresolved cells:

| ticker | resolved CIK | first PIT-200 slot | CIK's first in-window filing | unresolved cells |
|---|---|---|---|---|
| DIS | 1744489 | 2000-01-03 | 2019-05-08 | 899 |
| APA | 1841666 | 2000-08-21 | 2021-05-07 | 661 |
| MDT | 1613103 | 2000-02-28 | 2015-02-27 | 621 |
| PSKY | 2041610 | 2000-06-05 | 2025-05-14 | 581 |
| ESRX | 1532063 | 2000-01-03 | 2012-05-10 | 548 |
| GOOGL | 1652044 | 2004-08-23 | 2015-10-29 | 529 |
| CI | 1739940 | 2000-01-03 | 2019-02-28 | 442 |
| BLK | 2012383 | 2010-11-22 | 2024-11-06 | 391 |
| MRVL | 1835632 | 2001-07-09 | 2021-06-09 | 380 |
| AVGO | 1730168 | 2009-09-14 | 2018-06-14 | 366 |
| ICE | 1571949 | 2005-12-12 | 2013-08-07 | 356 |
| WBA | 1618921 | 2002-12-23 | 2014-12-29 | 341 |
| ORCL | 1341439 | 2000-01-03 | 2006-04-10 | 295 |

⭐ **The countersigned crosswalk does not close this.** Of the top 20 contributors, **only GOOGL** has
a crosswalk that carries the earlier CIK (`1288776` 2004-08-19 → 2015-10-01, then `1652044`). For DIS,
APA, MDT, CI, ORCL and the rest the crosswalk asserts the *current* CIK back to 1986-01-01 — the same
identity semantics as the snapshot. Across the whole crosswalk only **2 of 754 permatickers** carry
more than one CIK, against 21 approved `predecessor_overrides`.

⛔ **This cannot be repaired by re-joining existing evidence.** The predecessor CIKs were never in the
population, so their filings were never acquired and no SIC observation for them exists anywhere in
the epoch. Closing it requires (a) governed predecessor-CIK lineage resolution and (b) a further
acquisition. Both are redesign decisions, not measurement decisions.

### F-C2 — `excluded_low` mapping rows: **5,224 cells (29.1%), 11 SIC codes**

Working exactly as the freeze intends — §2 states that `excluded_low` rows count as unresolved, and
§3.1 records the owner's reasoning that a low-confidence mapping is not classification. Recorded here
because it is the second of the two classes that decide the gate:

| SIC | mapping row's sector | cells | distinct names | examples |
|---|---|---|---|---|
| 7370 | Communication Services | 2,485 | 16 | GOOG, GOOGL, META, BIDU, SNAP, APP, FLUT, DJT |
| 3823 | Industrials | 895 | 5 | DHR, EMR, ROP, FTV, CGNX |
| 3812 | Industrials | 680 | 5 | NOC, LHX, RTN, GRMN, FLIR |
| 3829 | Industrials | 524 | 1 | TMO |
| 4899 | Communication Services | 339 | 6 | AMT, CCI, ASTS, DTV1, XMSR |
| 3822 / 3861 / 3825 / 3690 / 3821 / 0700 | — | 301 | 9 | TT, KODK, A, TER, QS, NEWP1 |

⭐ **SIC 7370 alone accounts for 13.8% of all unresolved cells** and covers Alphabet and Meta for
their entire history in the index. Under the frozen rule these are correctly unresolved; the question
of whether `7370` deserves a confident mapping belongs to the taxonomy/coverage-freeze adjudication,
**not to this measurement**, and it must not be revisited to rescue this result (freeze §4: no value
may be revised after a coverage table has been inspected).

### F-C3 — crawl-window warm-up: **1,870 cells (10.4%), 213 names, entirely inside 2000**

`CRAWL_SINCE = 2000-01-01`, so no SIC is available until each issuer's first in-window filing.
`R(2000-01-03) = 0.0000` — nothing has been filed yet — rising through H1-2000 as issuers report.
Confined to 46 slots, all in 2000, and structural rather than defective: it is the boundary of the
frozen crawl window.

### F-C4 — three CIKs with no segment at all: **60 cells**

`0001071189:GX` and `0001132979:FRCB` (no in-scope filing in the window) and `0001002131:LHSP`
(6 filings, all NO_SIC). Carried from terminal-report F-3.

### Attribution arithmetic

Diagnostic decomposition of the *measured* result. **These are not gate re-runs** — the gate was
applied once, above, and its outcome stands.

| scenario | coverage | rebalances ≥ 0.95 |
|---|---|---|
| **as measured (frozen definition)** | **92.801%** | **425 / 1,247** |
| warm-up class set aside | 93.551% | 425 / 1,247 |
| `excluded_low` class set aside | 94.896% | 834 / 1,247 |
| lineage class set aside | 97.132% | 1,034 / 1,247 |
| lineage **and** `excluded_low` set aside | 99.226% | 1,229 / 1,247 |
| all three set aside | 99.976% | 1,247 / 1,247 |

⭐ **The acquisition is not the problem.** Where the addressed CIK has a SIC and the mapping is
confident, classification resolves at **99.2%+**, and with the warm-up boundary also removed the
epoch classifies essentially every ticker-week in 26 years. The gate is lost to one identity-lineage
limitation and one deliberate mapping policy — neither of which the crawl could have fixed.

---

## 6. Observations recorded for the taxonomy/coverage-freeze adjudication

Recorded, **not interpreted**, per the owner's F-6 instruction.

**Foreign-private-issuer filings step at 2002.** Acquired filings by accession year show `40-F`
**exactly zero in 2000 and 2001**, then 16 in 2002 and a stable ~17–22/yr for 24 years; `20-F` shows
11 and 16, then 59 in 2002 and 58–90/yr thereafter. Of 141 FPI/mixed-filer CIKs, **122 have no
acquired filing before 2002**; of 117 FPI-only CIKs, only 13 have a first segment in 2000–2001
against 46 in 2002. A stable ~21-issuer 40-F population with literally zero filings for two years is
not credible as issuer behaviour, so either EDGAR does not hold those filings electronically or the
crawl did not see them. **The internal evidence favours the source:** every filing the submissions API
listed was acquired (`filings_seen == observations == 76,821`, `acquisition_header_incomplete = 0`),
and `older_shard_urls` skips a shard only when its `filingTo < since`, which cannot drop 2000–2001.
⛔ Not settled here — settling it requires an EDGAR check outside a read-only measurement.

**Annual-form deficit before 2003.** `10-K` counts run 395 (2000), 427 (2001), 476 (2002), then step
to 668 in 2003 and hold ~620–680 for two decades, while `10-Q` is already at steady level in 2000
(1,904 vs ~1,960). 654 CIKs have an acquired filing in 2000, so ~660 annual filings would be
expected. The step lands exactly where form **`10-K405`** was discontinued, and `10-K405` is not in
the frozen `FORMS` tuple. ⭐ **This does not create coverage holes** — 10-Q acquisition is complete
across those years, so each issuer's SIC is still observed quarterly. It reduces observation
redundancy only. Flagged for confirmation.

**F-4 measured on the governed grid** — NO_SIC 1,449 of 76,821 observations (1.886%), 660 of 1,167
units, per-unit max 7 (`GENZ1`). Only `LHSP` is left with no segment at all.

**F-5 carried** — `PEG` and `EXC` at 19 segments each from 4931 ⇄ 4911 oscillation; 206 of 1,146 CIKs
are multi-segment. No repair before measurement, as ruled.

**F-6 preserved, uninterpreted** — `sic_field_present_inside_sec_header` True 41,458 / False 35,363,
against `sic_field_present_anywhere` True 75,372. The 98.1% observation-level SIC rate rests on the
"anywhere" acceptance rule.

---

## 7. What this measurement does **not** establish

* ⛔ It computes **no** return, Sharpe, drawdown, or sector-level economic quantity, per freeze §4.
  Nothing economic may be inferred from any number in it.
* ⛔ It does **not** establish that the resolved SIC values are **correct** — only that a SIC was
  present, resolvable under the frozen resolver, and mapped by a countersigned row.
* ⛔ It does **not** revise `θ_name`, `θ_window`, `θ_span_min`, or the treatment of `excluded_low`.
  Freeze §4 forbids revising them now that a coverage table has been inspected; if they look wrong
  that is a successor design decision.
* ⛔ It does **not** open a new trial. Per freeze §5, V3-RC remains trial #1 — no economic outcome has
  been observed.
* ⛔ It does **not** propose a redesign. §10.3 is the owner's adjudication.

---

## 8. What the owner now has to decide (§10.3)

The measurement is finished; the following are the live questions and they are **not** answered here.

1. **Identity lineage (F-C1)** — whether to build governed predecessor-CIK lineage and acquire those
   CIKs. This is the single largest class (60.2%) and the only one whose closure requires new
   acquisition. Note the tension with freeze §4: re-measuring after the coverage table has been seen
   is exactly what the anti-peek control was written to constrain, so the sequencing of any repair
   needs its own ruling.
2. **`excluded_low` (F-C2)** — 29.1% of unresolved cells, SIC 7370 alone 13.8%. Whether the
   countersigned mapping's low-confidence rows should be revisited is a taxonomy-freeze question, and
   revisiting them *because* they cost the gate is precisely what §4 forbids.
3. **Warm-up boundary (F-C3)** — whether a coverage definition measured from the first slot of the
   crawl window is the right construction, or whether the span should begin after issuers have filed
   once inside the window.
4. **The §1 window-regeneration ruling** — untouched and unused. No window was constructed, so no
   boundary has been exposed to any result.

---

## Appendix — method and reproducibility

Computed from the five SHA-256-pinned inputs in §1 by `apps/backend/scripts/sec001_v3_coverage_measure.py`.
The frozen semantics are taken from the repository, not reimplemented: the close-t cutoff from
`app/research/mr002/spq1/phase2b/cutoff.py`, and the covering-row / latest-`effective_from` /
same-effective-conflict rules from `app/research/mr002/spq1/phase2b/sic_sector.py`. The epoch's
segment evidence was read **read-only over the epoch volume via SSM**; nothing was written to it and
the crawl was not re-run.

The tool fails closed on any input whose digest does not match its pin, and it applies the §3 decision
rule itself (`span_decision`), so the STOP outcome is produced by the same run that produces the
coverage numbers rather than by a separate judgement. Result artifact `coverage_result_v1.json`
(sha256 `788755facfc2f2056dcfb4b19db0a3e4a80a03ce3dfa2f47e963c2a78ee24988`) carries all 1,247 per-slot
rows plus the decision, and is owed to S3 custody together with the epoch evidence.

Reproduce with:

```bash
python apps/backend/scripts/sec001_v3_coverage_measure.py --inputs <dir> --out coverage_result_v1.json
```
