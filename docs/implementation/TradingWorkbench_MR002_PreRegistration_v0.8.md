# MR-002 — Pre-Registration v0.8 (DRAFT, delta to v0.7) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Authority:** v0.7 + **owner
countersign decision** (`Docs/review/comments.md` 2026-07-11, archived at
`evidence/mr_002/MR002_OwnerCountersign_Overrides_2026-07-11.md`). **Supersedes v0.7 only where stated.**
**Status:** 🟡 **DRAFT — NOT FROZEN.**

## 1. Countersign results (recorded)

| Artifact | Decision | Recorded as |
|---|---|---|
| Crosswalk manual overrides | ✅ **APPROVED (all 5 rows)** — corrected intervals internally consistent; when-issued exception properly documented; inclusive/inclusive convention accepted | `crosswalk_manual_overrides_v0.3.csv` — `confidence=approved_manual · review_status=approved · reviewer=Jay Wang · review_date=2026-07-11`; crosswalk suite re-ran **23/23** against the approved rows |
| Security-sector overrides | ✅ **APPROVED (all 3 rows)** — META/GOOGL/GOOG are core XLC constituents; precedence stays security override → SIC mapping → explicit exclusion (a generic SIC row can never overwrite a security override) | `security_sector_overrides_v0.2.csv` — approved fields completed |
| SIC mapping v0.3 | 🟡 **HELD** — four semantic corrections + one downgrade | **v0.4 issued** (§2), resubmitted for countersign |
| Preliminary universe + impact report | ✅ **PROCEED** | next work item |
| Full-universe crawl | ⏸ hold remains | until mapping countersign + final hashes |

Owner verified all three raw artifact hashes matched the review package. The 23/23 boundary/identity
test report ships beside the final hashes at freeze.

## 2. Mapping v0.4 (101 rows: 27 HIGH / 64 MEDIUM / 10 LOW) — the four splits + downgrade

1. **Coal out of metal mining:** 1000–1099 → XLB · **1200–1299 → XLE** (GICS Coal & Consumable Fuels
   = Energy) · **1100–1199 explicitly unmapped** — excluded, never absorbed.
2. **Homebuilding out of construction:** 1500–1519 → XLI MEDIUM (impact-report review) ·
   **1520–1539 → XLY HIGH** (residential contractors/operative builders — DHI class, GICS
   Homebuilding, XLY holdings) · 1540–1799 → XLI.
3. **Health-care distributors out of wholesale:** **5122 → XLV HIGH** (McKesson/Cencora class) ·
   5045 → XLK, 5047 → XLV, 5171 → XLE carved out as MEDIUM single-SIC rows requiring impact-report
   review · surrounding wholesale stays XLI.
4. **Commercial printing out of publishing:** 2700–2749 media (pre-2018 XLY / post-2018 XLC — both
   **MEDIUM** per the mixed-subclass rule) · **2750–2799 → XLI** (GICS Commercial Printing; never XLC).
5. **737x downgrade:** 7371–7374 → XLK HIGH · **7375 → LOW (excluded — information-retrieval too
   heterogeneous; security-level review)** · 7376–7379 → XLK MEDIUM.

Validator on v0.4: **PASS, 0 errors/warnings**; every v0.3→v0.4 added/removed key listed in the
reconciliation block. Pilot spot-checks unchanged and correct (KVUE → XLP; META via
`security_override`). Provisional hashes: artifact
`3c93ea09600625a30c6396acaac9e0c904bbab239c7003503d25d5ed55ea508a` · canonical
`f98ce294ef80765cdb25106a9eb5a1ca55408c9ca58ad3eeb19800a8da028881`.

## 3. Order of work (updated)

1. ✅ Record countersigns (overrides v0.3 · security overrides v0.2). 2. ✅ Mapping v0.4 with the four
splits + 7375 downgrade; validator rerun PASS. 3. ⏳ **Preliminary-universe construction** (v0.5 §3
sequence — SEP price/liquidity/type filters only, before any V1/V2 eligibility). 4. ⏳ **Mapping-impact
report by security and universe-month** (HIGH / MEDIUM / LOW-excluded / unmapped; resolves the flagged
1500–1519 / 5045 / 5047 / 5171 reviews; surfaces additional security-override candidates). 5. ⏳ 7375 /
affected-security review from the impact data. 6. ⏳ Final reviewer fields + final artifact & canonical
hashes (all three files, one hash event). 7. ⏳ Mapping resubmission → countersign. 8. ⏳ Full-universe
V1/V2 crawl (box; §6 v0.6 provenance controls) → coverage gate → §8a → v1.0 freeze candidate.

---

*Strategy rules unchanged and closed since v0.3. No signals or backtests before Research-Design Freeze.*
