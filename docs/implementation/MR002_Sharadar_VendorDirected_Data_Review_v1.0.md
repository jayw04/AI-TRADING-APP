# MR-002 — Vendor-Directed Data Review v1.0 (SHARADAR/INDICATORS + underlying ACTIONS data)

**Date:** 2026-08-17
**Status:** READ-ONLY EVIDENCE RETRIEVAL. Implementation changed: NO. Gate changed: NO. Validation read: NO. OOS read: NO. Host started: NO. Fifth opening requested: NO. `relation` and `spinoff` remain **KNOWN_UNADJUDICATED** — nothing in this document is a classification; adjudication under `ProspectiveLabelAdjudication_v1.0` (`ed56601c…`) remains the owner's.

## Context

Five open questions were escalated to `connect@sharadar.com` (see `MR002_Sharadar_Official_Documentation_Semantic_Closure_v1.0.md`). Sharadar's reply, 2026-08-17, verbatim in substance:

> They are answered by reviewing SHARADAR/INDICATORS and looking at the underlying data.

This document executes exactly that instruction, inside the frozen admissibility frame: SHARADAR/INDICATORS is **vendor documentation** (admissible), and "the underlying data" is read **only** through the dev snapshot `apps/backend/data/mr002_research.duckdb`, hard-bounded `2013-01-02..2019-10-02` on **every** table reference including both sides of every join, read-only connection, no price table touched (admissible for **structural facts only**). The vendor's instruction is itself a semantic fact: Sharadar considers the published INDICATORS definitions **complete**, and considers data-level structure an authorized basis for the remaining answers. That materially changes the standing of the frame's earlier prohibition on inferring semantics from co-occurrence — for these specific questions the vendor has now *directed* that reading — but whether to accept it is the owner's call.

## A. Evidence retrieved

| artifact | sha256 | where |
|---|---|---|
| `SHARADAR/INDICATORS?table=ACTIONS` (7 rows) | `6ccd6f47…` | `docs/implementation/evidence/sharadar_indicators/indicators_actions.json` |
| `SHARADAR/INDICATORS?table=ACTIONTYPES` (19 rows, full action vocabulary) | `f85a7443…` | `…/indicators_actiontypes.json` |
| `SHARADAR/INDICATORS` table list | `2053b2b0…` | `…/indicators_tables_list.json` |
| Bounded structural facts, dev snapshot | `e9915892db17005075fd93ced55c44a3b049930bb07cd449e42f0655b8a71f6b` | `docs/implementation/evidence/sharadar_underlying_structural/actions_structural_facts_devbound.json` |

Retrieval manifest with sanitized requests (API key `<REDACTED>`, key-leak check PASS): `docs/implementation/evidence/sharadar_indicators/retrieval_manifest.json`. The INDICATORS content is **byte-for-byte consistent in substance** with the 2026-08-14 `descriptions` API sweep (`786f22e`) — INDICATORS adds **no new wording** for `relation`; the vocabulary is the same 19 labels.

## B. Findings, mapped to the five escalated questions

### Q1 — does `relation` carry any economic/price/identity consequence?

- **INDICATORS (vendor doc):** `relation` = "Provides linkage between multiple securities issued by the same issuer." Unittype **N/A**. It is the only label of the 19 that defines **neither** its `value` **nor** its `date` field (every delisting-family label defines both; `initiated` defines `date`; every transaction label defines both).
- **Underlying data (bounded, structural):** `value` is populated in **0 of 98** relation rows (0 distinct values). `name = contraname` in **98 of 98** rows — every relation row links two securities of the *same issuer*, exactly as documented.
- **Read together with the vendor's reply:** the published definition is the complete definition — linkage, nothing more. The data carries no economic scalar. **This is evidence of informational-only linkage; declaring the t+1 consequence NONE remains a required owner decision** (the frame permits NONE but demands it be stated, not assumed).

### Q2 — what does `relation.date` mean; can `relation.value` be populated?

- `value`: never populated in the bounded window (0/98). INDICATORS assigns unittype N/A. No admissible source shows it can be populated.
- `date`: INDICATORS defines only the generic ACTIONS column ("The date of the corporate action"). Structurally, **91 of 98** relation rows stand alone on their `(ticker, date)` — no co-dated action row exists on either the primary or the contra side for them, so the date is *not* generally an alias for another event's date. The remaining 7 rows co-date with `delisted` (5), `acquisitionby` (3), `dividend` (2) pairs. **The precise meaning of `date` for a standalone relation row is still not stated anywhere** — this is the one question the vendor's cited sources genuinely do not answer.

### Q3 — what relationship classes does `relation` represent?

All bounded rows are same-issuer, and the observed classes are (structural, from the 98 rows):

- **Dual share classes:** e.g. `CMCSA↔CMCSK`, `WWAV/WWAV.B`, `FWONA/FWONB` — including **reciprocal rows** (both directions published on the same date).
- **Preferred share series:** `PSA-PO1/-PP1/-PQ1/-PR1`, `MET-PB`, `OCR-PA/-PB`, `BAC-PZ`, `WY-PA`, `UTX-PA`.
- **Exchange-traded units/notes-type securities:** `DCUA`/`DCUB` (Dominion units), `GSF`, `DFF`, `MHM`, `SWU`.

Not observed in the window: ADR-vs-ordinary linkage, predecessor/successor lineage (that is carried by `tickerchangefrom/to`, which remain the **only** labels with a vendor "Must be viewed in conjunction with" instruction).

### Q4 — can `relation` coexist with other action rows on the same ticker/date?

**Yes** — 7 of 98 rows do (pairs: `delisted` 5, `acquisitionby` 3, `dividend` 2). The vendor publishes no precedence or composition rule for these; each label's own definition is self-contained. 91/98 stand alone.

### Q5 — `spinoff` vs `spinoffdividend` vs `spunofffrom` composition

Bounded counts: `spinoff` 75 · `spinoffdividend` 65 · `spunofffrom` 14; `value` populated **100%** in all three.

- **Both parent-side records fire for one event:** joined on the full key `(ticker, date, contraticker)` — **65 of 75** spinoff rows have a matching `spinoffdividend` row; **10** are spinoff-only; **0** spinoffdividend rows exist without a matching spinoff. `spinoffdividend` never appears alone.
- **They are complementary, not alternative or independent:** identical keys, and the values are the two vendor-defined denominations of the same distribution — `spinoff.value` = child shares per parent share (ratio), `spinoffdividend.value` = dollar value of those shares per parent share (e.g. `ABT→ABBV 2013-01-02`: ratio 1.0, $34.65; `VLO→CST`: ratio 0.11111, $3.356). One event, two measures.
- **`spunofffrom` is the sparse child-side mirror:** 13 of 75 spinoffs have a `spunofffrom` row on the child with the parent as contraticker, **same date and identical ratio value in all 13**; 1 bounded `spunofffrom` row lacks a bounded parent-side match (parent action outside the window is the structural explanation available). The mirror exists only when the spun-off company is itself a covered ticker.

## C. Still open after executing the vendor's instruction

1. The meaning of `date` on a **standalone** `relation` row (Q2, date limb) — defined nowhere, and 91/98 rows are standalone.
2. Whether `relation.value` can ever be populated **outside** the bounded window — 0/98 inside it; the containment discipline forbids checking the rest of the table.
3. Whether the 10 spinoff-only rows are events where Sharadar simply did not publish a dollar value, or a distinct sub-case — not stated.

These are narrow enough that the owner can adjudicate with a stated assumption, or return them to Sharadar as a single follow-up.

## D. Containment attestation

Read-only duckdb connection; every SQL reference to `actions` (including both sides of every join and every `NOT EXISTS`) carries `date >= '2013-01-02' AND date <= '2019-10-02'`; no price/anchor/universe table read; no Sharadar market-data endpoint called (INDICATORS is metadata-only); API key loaded from `.env`, never printed, absent from every evidence file (asserted programmatically).
