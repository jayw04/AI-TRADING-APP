# SEC-001 V3 — Sector-Classification Disposition Ruling v1.0

**Rules on:** §5.1a disposition, informed by the §5.1b investigation (executed read-only 2026-08-23)
**Governing design:** `docs/design/SEC-001/TradingWorkbench_SEC001_V3_Design_Implementation_v0_3.md`
**Date:** 2026-08-23 · **Authority:** owner

---

## Ruling

**DISPOSITION 1 — ADOPTED.** SEC-001 V3 will use a genuine effective-dated sector-classification spine
built on the surviving MR-002 EDGAR SIC machinery (filing-time classification, acceptance-timestamp
precedence, fail-closed resolvers, countersigned `sic_mapping`). Disposition 2 is declined: the §5.1b
META demonstration and Finding A's measured ~8.4% sector-boundary-crossing rate make restated
classification a demonstrated, material, directional leak into the grouping variable of a momentum
signal — not an acceptable recorded limitation.

The V3-RC run blocker narrows accordingly: from "rule" to "execute the rider below."

## Rider — conditions of the adoption

1. **Taxonomy consequence (Finding B) ruled explicitly:** V3's "sector" is the GICS-11 of the
   countersigned mapping. The §9.3 SEC-001 V2 pure-baskets structural reference is **recomputed under
   the same taxonomy** before the validation run, so all three comparison arms share one grouping
   variable. The §10.1 relative gates bind against the recomputed reference. The historical
   Morningstar-taxonomy V2 figures remain in the record as context, not as the gate baseline.
2. **Governed re-measurement:** the §5.1b coverage figures are directional (laptop copies). The Q5
   table is re-measured on the governed `ec2-paper` store before any pre-registration field freezes.
3. **Post-crawl coverage sufficiency check:** after the registered crawl (item 4), the Q5 resolution
   table is re-run per frozen walk-forward window against a minimum resolved-fraction threshold frozen
   **before** the crawl results are inspected. If early windows remain insufficiently covered,
   shortening the §9.4 evaluation period to the spine's coverage is a **pre-authorized legitimate
   re-freeze** (coverage is not performance data; no outcome has been observed). Selecting or trimming
   windows after observing returns remains prohibited, permanently.
4. **Registered changes authorized (three, exactly as scoped in §5.1b):** extend the crawl form list
   to 20-F / 40-F (foreign private issuers, 3.5–10% of the PIT-200); ingest `permaticker` into the
   store `tickers` projection; extend the crawl to 2000-01-01 across the ~800-name PIT-200 union
   (floor; weekly grid will exceed it). One unattended crawl at the SEC request ceiling; no purchase.
5. **Resolver path:** V3 uses the Phase-2B path (`phase2b/sic_sector.py` — hash-bound mapping,
   fail-closed refusals) exclusively. The Phase-2A adapter (`pit_sector_adapter.py::sic_to_sector`,
   silent MATERIALS default contradicting its own docstring) is **scheduled for a removal/guard
   quarantine review** alongside the platform's other never-default violations. V3 never imports it.
6. **Unresolved names** carry `SECTOR_PIT_IDENTITY_MISSING` / `sector_unclassified` semantics exactly
   as §5.1a specifies: excluded from every sector's score and breadth, with reason, never defaulted.

## Custody

`TradingWorkbench_SEC001_V3_Design_Implementation_v0_3.md` (now carrying the §5.1b evidence record) is
**staged and committed** to its ADR-0050 Git path immediately, per GITHUB-OPS-001 — custody now, review
at its own pace. This ruling record is committed alongside it.

## What this ruling does not do

It does not authorize the V3-RC validation run. The run remains gated on: rider items 1–4 complete,
the §5.1a classification fields frozen from the proven spine, and the remaining §9.4/§10 freezes
already in place. It does not reopen any frozen value (signal, K, cap, gates, windows, cost model).
It transfers no MR-002 evidence — machinery and reference data only, per the standing cross-program
rule.

---

*Owner signature constitutes the Disposition-1 adoption and authorizes rider items 2–5 as developer
work. Rider item 1's recomputed reference and item 3's threshold freeze return to the owner as
recorded artifacts before the run.*
