# MR-002 — Pre-Registration **v1.0 FREEZE CANDIDATE** · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** Planning →
**Running (on signature)** · **Status:** 🟢 **FREEZE CANDIDATE — awaiting the owner's Research-Design
Freeze signature.** All data gates are MET; §8a is fully populated; every artifact is hashed and
sealed.

**Authority chain (all archived in `evidence/mr_002/`):** owner proposal → reviews 1–2 → v0.3 (S1–S4)
→ v0.4 (build-authorizing) → v0.5–v0.6 (crawl-release governance) → v0.7–v0.9 (countersign rounds) →
V1/V2 validation → predecessor-remedy countersign (21/21 approved, 2026-07-11).

> **Strategy rules are unchanged and closed since v0.3.** Hypothesis, z-thresholds (A 1.75 / **B 2.00
> primary** / C 2.25), 5-session hold, universe breadth, sealed-OOS structure, and all pass gates are
> exactly as pre-registered. This document freezes the DATA layer that v0.4 §0 required before the
> Research-Design Freeze.

---

## §8a — FROZEN DATA WINDOW & SNAPSHOT REGISTER (complete; no empty fields)

| Field | Value |
|---|---|
| **Trading calendar** | Sharadar SEP session dates (AAPL, continuously listed) — registered proxy for the NYSE session sequence |
| **First / last eligible session** | **2013-01-02** / **2026-07-10** (3,400 sessions) |
| **Start-date rule applied** | earliest month whose V1+V2 coverage thresholds hold for 12 consecutive months, after warm-up (universe warm-up runs from 2010) → **2013-01**; later coverage dips never move the start (registered) |
| **Development (50%)** | **2013-01-02 → 2019-10-02** (1,700 sessions) |
| **Walk-forward validation (25%)** | **2019-10-03 → 2023-02-16** (850 sessions; 5 contiguous near-equal folds, remainder to the final fold) |
| **Sealed OOS (25%)** | **2023-02-17 → 2026-07-10** (850 sessions) — **B only, exactly once** |
| **Partial first/last calendar-year treatment** | included; both are complete-month bounded (2013-01 first; 2026-07 last complete month) |
| **Preliminary universe** | 163 months (2013-01 → 2026-07), **40,750 universe-months**, 754 securities · `mr002_preliminary_universe.csv.gz` |
| **Stock-data (SEP) snapshot** | bulk export sha256 `47d049ab1b010ea5298f3f1acc2e38434a7f7534913d55c1579996ff3d48605c` (46,172,468 rows) |
| **Security metadata (TICKERS) snapshot** | sha256 `b5ae57284230956bc087ccf66a4c79a6e4a9ddbce67b4e06c4ef5b5435faf0f8` |
| **ETF (sector-proxy) data** | Yahoo adjusted close — pinned at harness build (research-grade, TREND precedent) |
| **Corporate-event (ACTIONS) snapshot** | pinned at harness build (used only for announcement-dated exclusions) |
| **V1 earnings anchors (PIT blackout)** | 40,153 anchors · `stage2/anchors.csv.gz` — hash in the sealed manifest |
| **V2 PIT-SIC observations / segments** | stage-2 + supplemental (repaired) · hashes in the sealed manifest |
| **Identity crosswalk** | `identity_crosswalk_v0.1.csv` (1,068 intervals) + `crosswalk_manual_overrides_v0.3.csv` (approved) |
| **Predecessor-override registry** | `predecessor_override_registry_v1.0.csv` — **21/21 owner-countersigned**; artifact `667af36e…`, canonical `93df8c46…` |
| **SIC→sector mapping / security overrides** | `sic_sector_etf_mapping_v0.8.csv` · `security_sector_overrides_v0.6.csv` (countersigned) |
| **All artifact hashes** | `MR002_SealedManifest_v1.0.json` (15 artifacts, artifact + canonical pairs) |
| **Extraction code** | hardened fetcher + registered modules; smoke suite = required pre-flight gate |

## Data Availability Gate — RESULTS

| Gate | Result |
|---|---|
| **V1 (PIT estimated earnings-risk blackout)** | ✅ **MET** — 39,690 / 40,750 = **97.40%** (≥95%); every year ≥90% (min 94.50%). Reproduction **100.000%** (40,153/40,153, independent EDGAR rebuild). |
| **V2 (PIT SIC)** | ✅ **MET** — 40,132 / 40,750 = **98.48%** (≥98%); every year ≥95% (min 97.14%). Deterministic rebuild reproduces exactly. |
| **Integrity** | ✅ 0 same-day conflicts · 0 pre-observation fills · 0 invalid/non-contiguous segments · 0 unsupported boundaries · 0 duplicate keys · 0 different-CIK crosswalk overlaps |
| **Identity** | ✅ 99.98% of universe-months resolve via (permaticker, date); 23/23 identity tests |

**Accepted exclusions (unchanged, disclosed):** DHR 163 (needs_revision — archive evidence owed) ·
excluded_low 353 · identity-unresolved 9 · residual no-SIC/pre-observation 93. **No forward-fill.**

## Countersigned limitations carried into the freeze (permanent provenance)

- **PSKY** — filing-entity succession only; does **not** authorize combining operating fundamentals.
- **DD** — interval-bounded to the 2017-08-31 merger; later spin-offs require their own events; no
  observation may cross a later split boundary because of this row.
- **AGN** — acquired Allergan Inc. (CIK 850693) remains **outside** the chain. **Permanent rule:
  ticker equality never overrides issuer lineage.**
- **OVV** — FPI status is not an identity break; disclosure handled via 20-F/40-F form coverage.
- **MR-002 finding (recorded):** non-atomic cache writes survived reconciliation as apparently
  successful cached reads. Hardened atomic-write path fixes the defect; the smoke suite is the
  permanent pre-flight gate.

## What the freeze signature authorizes

Research-Design Freeze v1.0 → **Running**. Development sample may then be built on the frozen window;
**Implementation Freeze** follows before validation; the sealed OOS opens **once**, on config B, at the
end. No parameter adjustment after sealed results (a substantive revision is **MR-003**). No signals or
backtests have been run to date.

---

*Prepared 2026-07-11. Awaiting owner signature.*
