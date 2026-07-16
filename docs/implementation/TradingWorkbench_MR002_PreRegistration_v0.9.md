# MR-002 — Pre-Registration v0.9 (DRAFT, delta to v0.8) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Authority:** v0.8 + **owner
countersign review 2** (`Docs/review/comments.md`, archived at
`evidence/mr_002/MR002_OwnerCountersign2_TaxonomyDates_2026-07-11.md`). **Supersedes v0.8 only where
stated.** **Status:** 🟡 **DRAFT — NOT FROZEN.** All three review-2 corrections implemented and
re-verified; the **≥98% coverage gate is now demonstrably reachable (99.38%)**. Revised artifacts
await final countersign. Full-universe crawl remains HELD.

## 1. August-2026 universe — root-caused and fixed (labeling/logic, not vendor data)

The partial current month (data through 2026-07-10) generated an "August" universe from a **mid-month
as-of** — violating the prior-month-END rule. No future-dated vendor rows were involved. Fix: the
reconstitution SQL now requires a **complete** source month (`HAVING month(max(date)) < month(global
max date)`). Corrected universe: **163 months (2013-01 → 2026-07), 40,750 universe-months, 744
securities**; impact recomputed on the corrected set.

## 2. Taxonomy effective dates separated from ETF availability (mapping v0.5)

Registered correction: **the mapping changes when the GICS classification became effective — never
when the ETF became usable.** Communication Services: implemented after the **2018-09-28** close →
boundary **2018-10-01** (was 2018-06-19). Real Estate: effective after the **2016-08-31** close →
boundary **2016-09-01** (was 2015-10-08). ETF availability (XLC first usable return 2018-06-19; XLRE
2015-10-08) is stored as a **separate registered property** and continues to gate universe
eligibility only. The validator now enforces classification-date boundaries + wording; the META/
Alphabet security overrides were corrected to 2018-10-01 (the earlier 2018-06-19 approval was
superseded by the owner). Pilot verification: META flips XLK→XLC at **2018-10-01** (security
override); AMT flips XLF→XLRE at **2016-09-01**.

## 3. Approved security overrides drafted (v0.3 → v0.4, 27 rows, pending countersign)

Per the owner's approvals: **V / MA** (XLK through 2023-03-17 → XLF from 2023-03-20, the GICS 2023
transaction-processing move) · **DIS** (XLY through 2018-09-28 → XLC from 2018-10-01) · **SHW** (XLB;
effective_from = earliest research date, flagged for the archived-history check) · **WMT / COST**
(XLP full window, same flag) · **TGT / DG / DLTR** (XLY → XLP at the 2023-03-20 revision).

## 4. LOW-exclusion recovery (mapping v0.6 + overrides v0.4) — the 98% gate now clears

The corrected impact run showed max coverage **96.79%** — short of the registered 98% gate — with the
LOW exposure dominated by the **3800–3839 instruments range** (DHR/TMO/NOC/ILMN/KLAC/TT/RTN/LHX), not
SIC 7370. Per the owner's rule (split where code-coherent; verified security overrides where
security-specific; leave ambiguous names excluded):

- **Mapping v0.6 splits:** **3812 → XLI HIGH** (defense electronics — NOC/RTN/LHX) · **3826 → XLV
  HIGH** (lab analytical — ILMN class) · **3827 → XLK MEDIUM** (KLAC class) · residuals 3800–3811 /
  3813–3825 / 3828–3839 stay **LOW** (3822/3823/3829 genuinely span sectors by security — DHR vs TT
  vs ROP on the same codes). 106 rows: 29 HIGH / 65 MEDIUM / 12 LOW; validator **PASS**.
- **Override recoveries (v0.4):** DHR → XLV · TMO → XLV · TT → XLI (from the 2020-03-02 Trane rename;
  predecessor extension pending archived check) · SNAP & TWTR (XLK → XLC at 2018-10-01, IPO-dated) ·
  PINS → XLC · ZM → XLK. **Deliberately left excluded (owner to decide): ROP, TTD** — plus small
  residuals APP, FLUT, ROK, TER.

**Coverage gate check (registered denominator, corrected 163-month universe):**

| | Universe-months | % |
|---|---|---|
| HIGH | 27,285 | 66.96% |
| MEDIUM | 10,920 | 26.80% |
| SECURITY_OVERRIDE | 2,291 | 5.61% |
| **Eligible (max primary)** | **40,496** | **99.38% ✅ ≥ 98%** |
| EXCLUDED_LOW_CONFIDENCE | 254 | 0.62% |

The 98% gate was **not** lowered; it is met by verified recoveries. Sector source remains the labeled
current-`siccode` approximation until the PIT V2 crawl recomputation.

## 5. Remaining before final countersign (owner checklist status)

☑ August 2026 removed/explained · ☑ XLC → 2018-10-01 · ☑ XLRE → 2016-09-01 · ☑ V/MA + DIS + SHW +
retailer overrides drafted · ☑ LOW-exclusion security report produced · ☑ ≥98% demonstrated (99.38%)
· ⏳ **owner final countersign of `sic_sector_etf_mapping_v0.6.csv` + `security_sector_overrides_
v0.4.csv`** (review package v4) · ⏳ final reviewer fields + one-event final hashes · then the
full-universe V1/V2 crawl unblocks.

---

*Strategy rules unchanged and closed since v0.3. No signals or backtests before Research-Design Freeze.*
