# MR-002 — Preliminary Universe & Mapping-Impact Report v0.1

**Date:** 2026-07-11 · **Pre-reg:** v0.8 §3.3–3.4 (owner-approved to proceed) · **Built on:** temp EC2
`mr002-temp-build` (t3.xlarge, us-east-1, terminated after the run; production box untouched).
**Inputs:** SHARADAR SEP bulk (46,172,468 rows, zip sha256 `47d049ab…`) + TICKERS (62,454 rows,
`b5ae5728…`) · mapping **v0.4** · security overrides **v0.2 (approved)**. Artifacts:
`mr002_preliminary_universe.csv.gz` (41,000 rows, sha256 `8f5110b4…`) · `mr002_impact_report.json`.

> ⚠ **SECTOR SOURCE = CURRENT TICKERS `siccode` — an APPROXIMATION for coverage planning only**
> (PIT SIC histories arrive with the held V2 crawl; this report is recomputed then). It informs the
> mapping countersign; it never enters research construction.

## Preliminary universe (frozen v0.5 §3 first stage — SEP filters only)

**164 monthly universes (2013-01 → 2026-08) × top-250 = 41,000 universe-months, 755 distinct
securities.** Filters exactly per pre-reg §2: first-trading-day effective, computed at prior
month-end; trailing 60-session median `close × volume` ranking; > $10; > $25M; ≥ 252 sessions;
`Domestic Common Stock%` only; top-150 flagged as the short universe. No V1/V2 eligibility applied
(anti-circularity sequence).

## Impact by tier (the owner's key countersign input)

| Tier | Universe-months | % |
|---|---|---|
| HIGH | 27,063 | **66.0%** |
| MEDIUM | 12,315 | **30.0%** |
| EXCLUDED_LOW_CONFIDENCE | 1,328 | 3.2% |
| SECURITY_OVERRIDE (approved) | 294 | 0.7% |
| UNMAPPED / NO_SICCODE | 0 | 0.0% |

**Headline: the mapping fully covers the liquid universe (zero unmapped), but 30% of universe-months
ride on MEDIUM rows — and they are mega-caps, not tail names.** Under the frozen policy (unreviewed
MEDIUM = excluded), primary coverage would be only ~63–68% per year until the MEDIUM rows are
countersigned — the coverage gates (V2 ≥ 98%) are unreachable without that review. Year-by-year
coverage with MEDIUM removed: 63.3–68.5% (stable; no cliff years).

## Top MEDIUM-exposed securities (164 months each unless noted)

GE (3600) · AMZN (5961) · WMT (5331) · CAT (3531) · MCD (5812) · HD (5211) · BKNG (4700) · DIS (7990)
· SBUX (5810) · V (7389) · LOW (5211) · MA (7389) · BA (3721) · RTX (3724) · COST (5331) · TGT (5331)
· UPS (4210) · DE (3523) · TJX (5651) · NKE (3021).

**Security-override candidates surfaced by the data (owner verification required before any are
added — none added unilaterally):**

- **V, MA (SIC 7389 → currently XLI MEDIUM):** GICS has them in Information Technology historically
  and **Financials from the 2023 GICS revision** — the generic business-services row cannot express
  either. Strong candidates for effective-dated security overrides.
- **DIS (7990 → XLY per the owner's recreation rule):** GICS moved Disney to **Communication
  Services in 2018** — an XLC security-override candidate (the 79xx range itself stays XLY, per your
  rule that recreation ≠ XLC).
- **SHW (5231 paint stores, in the 5200–5399 exposure list):** GICS classifies Sherwin-Williams as
  **Materials** — a security-override candidate the 52xx retail range cannot express.
- **Staples retailers (your flagged 5200–5399 review, now quantified):** WMT 164 · COST 164 · TGT 164
  · DG 151 · DLTR 111 universe-months — the XLP-vs-XLY security-override set you anticipated.

## Flagged-row exposure (your review items, quantified)

| Flagged row | Top-250 exposure |
|---|---|
| 5200–5399 (staples retailers) | **material** — WMT/HD/LOW/COST/TGT/DG/SHW/DLTR/M/KSS + 4 others |
| 5045 (tech distributors) | HPE, 26 months — small |
| 5047 · 5171 · 7375 · 1500–1519 | **zero top-250 exposure** (current-SIC basis) — reviews immaterial for the liquid universe; recheck under PIT SIC after the crawl |
| MEDIUM at the XLC boundary | OMC only (advertising — GICS-consistent) |

## Recommended countersign path (owner decision)

1. Countersign the v0.4 HIGH rows (66% of universe-months) and the MEDIUM rows — the 30% MEDIUM share
   is concentrated in ~20 mega-caps whose rows are GICS-coherent (machinery/aerospace/trucking → XLI,
   retail/restaurants/apparel → XLY); the genuinely questionable names are the override candidates
   above, not the ranges.
2. Decide the four override candidates (V/MA · DIS · SHW · the staples-retailer set) — each needs your
   verification + effective dating; I'll draft the rows on your go.
3. Then: final reviewer fields + the one-event final hashes → full-universe crawl unblocks.
