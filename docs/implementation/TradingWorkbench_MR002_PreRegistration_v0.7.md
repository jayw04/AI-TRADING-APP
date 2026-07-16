# MR-002 — Pre-Registration v0.7 (DRAFT, delta to v0.6) · Sector-Neutral Residual Reversion

**Date:** 2026-07-11 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Authority:** v0.6 + **owner
countersign review** (`Docs/review/comments.md` 2026-07-11, archived at
`evidence/mr_002/MR002_OwnerReview_Countersign1_2026-07-11.md`). **Supersedes v0.6 only where stated.**
**Status:** 🟡 **DRAFT — NOT FROZEN.** The review approved the crosswalk architecture/tests and held
both CSVs on substantive corrections. **All required corrections are now implemented and re-verified**
(§1–§6); the corrected artifacts await final countersign. Full-universe crawl remains **HELD**;
preliminary-universe construction and mapping-impact analysis **may proceed** (owner disposition).

## 1. Google 2014 boundary — CORRECTED (record date ≠ symbol transition)

The v0.1 overrides used **2014-03-27 (the stock-dividend record date)** as the symbol boundary. Per
Alphabet's SEC disclosure: Class C distributed **2014-04-02**; Class A traded as GOOGL beginning
**2014-04-03**. Overrides **v0.2** (`crosswalk_manual_overrides_v0.2.csv`):

- perma 195146 · GOOG → `effective_to = 2014-04-02` · GOOGL → `effective_from = 2014-04-03`.
- perma 119496 · GOOG Class C keeps `effective_from = 2014-03-27` under the reviewer's documented
  exception: **Sharadar SEP verifiably contains Class C prices 2014-03-27 → 2014-04-02** (checked
  2026-07-11) — **when-issued trading** between record date and distribution; regular-way from
  04-03. Excluding those days would orphan genuine SEP rows; the series joins via permaticker.
- **Expected ambiguity registered:** ticker "GOOG" denotes two securities 2014-03-27 → 04-02; per the
  frozen invariant a ticker/date lookup returns **unresolved + a recorded ambiguity** there (the
  `ambiguities` channel is separate from unexplained `conflicts`, which remain a 0-tolerance gate).
- **Owner-required boundary tests added** (2014-04-02, 2014-04-03, 2015-10-01, 2015-10-02 + the
  when-issued window): crosswalk suite now **23/23 PASS, 0 conflicts, 0 integrity errors**.
- **Interval convention FROZEN: inclusive `effective_from` / inclusive `effective_to`** (owner:
  acceptable if consistent), applied uniformly across crosswalk, overrides, and mapping.

## 2. Mapping v0.3 — all classification corrections applied (87 rows: 26 HIGH / 52 MEDIUM / 9 LOW)

- **KVUE fix (confirmed error):** 2840–2899 split → **2840–2844 → XLP (HIGH)** · 2845–2899 → XLB.
  Pilot re-run confirms **KVUE → Consumer Staples/XLP**.
- **Splits per review:** 2400–2499 XLB / 2500–2599 XLY / 2600–2699 XLB · 3600–3629 XLI / 3630–3639
  XLY / 3640–3649 XLI / 3650–3659 XLY / 3660–3679 XLK / **3680–3699 LOW (excluded)** · 4000–4609 XLI /
  **4610–4619 XLE (pipelines)** / 4620–4799 XLI · 4900–4949 XLU / **4950–4959 XLI (refuse/sanitary)**
  / 4960–4999 XLU · 7800–7849 XLY→XLC at the boundary / 7850–7899 XLY / **7900–7999 XLY in ALL
  periods** (recreation is not XLC).
- **7370 policy:** pre-2018 downgraded to MEDIUM; **post-2018 downgraded to LOW (= excluded)** — SIC
  cannot separate internet content from IT services; verified issuers resolve via the **new frozen
  `security_sector_overrides_v0.1.csv`** (META/GOOGL/GOOG → XLC from 2018-06-19; security override >
  SIC mapping > excluded; extended at the gate only with per-name verification + countersign).
  Pilot re-run: **META resolves via `security_override`**, not the generic row.
- **8731 → MEDIUM** · 5200–5399 rationale now names the staples-retailer exception and requires
  security-level overrides before reliance (affected-security review at the gate).
- **XLC/XLRE wording corrected:** 2018-06-19 / 2015-10-08 are the **first usable sector-factor return
  dates following inception** (inceptions 2018-06-18 / 2015-10-07) — never called inception dates; the
  validator now enforces this wording.
- Validator on v0.3: **PASS, 0 errors/warnings**; every v0.2→v0.3 added/removed key listed in the
  reconciliation block of `mapping_validation_report.json`.

## 3. Hash reconciliation (registered — never a bare `sha256` again)

Every artifact report now carries **both** `artifact_sha256` (raw file bytes) and
`canonical_data_sha256` (canonically sorted rows), plus an explicit `canonicalization` block:
`canonicalization_version` (1) · `canonical_fields` · `canonical_sort_key` · `line_ending_policy`.
The earlier hash divergence was exactly raw-file vs canonical-row hashing — now explicit. All hashes
remain PROVISIONAL until countersign.

## 4. V1 anchors re-run through the finalized crosswalk — TWTR extracted

The anchors runner now resolves identity **crosswalk-first** (current-map fallback). Pilot re-run:
**10/10 tickers resolved (all via crosswalk)** — including **TWTR: 37 Item-2.02 candidates → 36
anchors (1 amended)** across its 2013–2022 life, previously unresolvable. Total 399 anchors. V1 status
remains preliminary per the owner table: extraction ✅ · availability rule ✅ · independent
release-timing precision and the manual error-rate gate still pending (stratified sample at the gate).

## 5. Genuine SIC-change cases — EXERCISED (two found)

| Case | Old SIC segment | Acceptance-driven change | New SIC segment | Mapping before → after |
|---|---|---|---|---|
| **UBER (flagship)** | 7372 prepackaged software, 2019-06-04 → 2019-11-05 | 10-Q accepted 2019-11-05 | 7389 business services, 2019-11-05 → open | **XLK → XLI** (changes with the SIC) |
| BKNG | 7389, 2012-02-27 → 2019-11-07 | 10-Q accepted 2019-11-07 | 4700 transportation services, open | XLI → XLI (SIC change, sector stable) |

Both demonstrate the five required properties: old effective interval preserved (no retrospective
replacement) · change effective at the filing acceptance timestamp · new interval forward-filled ·
sector mapping evaluated before and after under the frozen table · segments stored with source
accessions. Evidence: `evidence/mr_002/v2_sic_change_hunt.json`.

## 6. Review-status vocabulary (registered)

Mapping/override `review_status` values: `pending` → **`approved_high` / `approved_medium` /
`excluded_low` / `needs_revision`**; every approved row carries reviewer, review date, and a review
note or evidence reference. All rows currently `pending` — by design, countersign is the owner's act.

## 7. Remaining before the crawl unblocks (owner criteria)

1. **Final countersign** of `sic_sector_etf_mapping_v0.3.csv`, `crosswalk_manual_overrides_v0.2.csv`,
   and `security_sector_overrides_v0.1.csv` (review package refreshed at
   `Docs/review/mr002-countersign/`). 2. Final hashes (canonical order) after countersign.
3. **May proceed now:** preliminary-universe construction + the mapping-impact-by-universe-months
   report (HIGH / MEDIUM / LOW-excluded / unmapped) feeding the countersign. Still held: full-universe
   crawl · Data Availability Gate finalization · §8a · any MR-002 signal or backtest.

---

*v0.7 delta → preliminary universe + impact report → final countersign → hashes freeze → full V1/V2
builds → gate → §8a → v1.0. Strategy rules unchanged and closed since v0.3.*
