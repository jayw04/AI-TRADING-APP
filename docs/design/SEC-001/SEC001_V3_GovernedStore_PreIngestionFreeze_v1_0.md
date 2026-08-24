# SEC-001 V3 — Governed Research Store: Pre-Ingestion Provenance Freeze v1.0

**Status:** **FROZEN 2026-08-23 (owner).** Sealed **before** any vendor acquisition, ingestion, reconciliation or qualification. That ordering is the control: every rule below is fixed while no difference between artifacts has yet been seen.
**Authorises:** Path 2 — rebuild a deep-history research store from vendor source on a governed host.
**Precedes:** `SEC001_V3_Rider2_CaptureEvidence_v1_0.md` §4 (input-qualification failure) is the finding this freeze answers.
**Governing design:** `TradingWorkbench_SEC001_V3_Design_Implementation_v0_3.md` §5.1, §5.1a, §5.1b · **Coverage freeze:** `5b26ffa209a6…` (unspent)

---

## 1. Why a rebuild, and why the full pull

Rider-2 inspection established that **no existing artifact can serve SEC-001 V3**: the governed production store carries four names per year from 1997–2023 and gains breadth only in 2024; every other box artifact is the same; the sole artifact with a historical cross-section is an ungoverned laptop file that lacks `permaticker` and therefore cannot satisfy the identity clause. The historical PIT universe has no governed provenance at all.

The full vendor pull is **structurally required, not merely preferable**. `universe_asof` ranks by trailing dollar volume across the entire `sep` cross-section, so the top-200 for any date cannot be known without every name that traded then. Acquiring "only the names we need" is circular — the union of PIT-200 names is an *output* of the universe, never an input.

## 2. Governed-rebuild authority rule *(owner)*

> The newly constructed governed SEP+TICKERS store is the **authoritative** SEC-001 V3 research input. The laptop store is **corroborating evidence only** and may never override the governed rebuild.

## 3. Difference classification — frozen before any difference is observed

The rebuild is **expected to differ** from the laptop store by construction. SEP is restated: corporate-action-adjusted historical values move with every subsequent split and dividend, and security lifetime bounds (`firstpricedate` / `lastpricedate`) are revised. A pull today is today's view of history. Differences are therefore normal and must be *classified*, never used to choose an artifact.

Every discrepancy is classified, **before qualification**, as exactly one of:

| Class | Definition |
|---|---|
| **`EXPLAINED_RESTATEMENT`** | Demonstrably attributable to documented vendor restatement behaviour — corporate-action-adjusted historical values, or revised security lifetime bounds. |
| **`UNEXPLAINED_DIFFERENCE`** | Any discrepancy not demonstrably so attributable. |

**Qualification consequence.** Explained restatements are recorded and accepted as expected differences. Any `UNEXPLAINED_DIFFERENCE` affecting **universe construction, identity, or the PIT-200 population blocks store qualification until resolved.** It may **not** be waived, averaged away, or handled by selecting whichever artifact yields the preferred membership or result.

**No artifact election.** The comparison is a **diagnostic of reconstruction integrity, not a contest between two datasets.** The governed rebuild governs even where it differs. The laptop artifact **cannot become authoritative by agreeing with a later result.**

## 4. Universe point-in-time limitation — recorded, not waived

The historical universe must be described in every downstream artifact as:

> **point-in-time membership reconstructed from the vendor's currently restated historical SEP view** — not a pristine contemporaneous snapshot.

This is a **limitation, not a blocker**, and it is deliberately distinguished from the treatment rejected in the sector-classification ruling. Price and corporate-action restatement is **mechanical**; the reclassification leak that motivated Disposition 1 is **directional**, because re-sectoring follows the price and business behaviour a momentum signal measures. The two are not the same species of error, and this record exists so that a later reader does not have to reconstruct why one was accepted and the other refused.

## 5. Pre-ingestion fields — frozen before acquisition

Recorded before any data is pulled:

- vendor dataset / artifact identity and the retrieval time and data cutoff;
- the exact **current-`main` commit** used for ingestion — `origin/main` @ **`a992a9e`** unless superseded, recorded as the resolved SHA at acquisition;
- SEP acquisition parameters; TICKERS acquisition parameters;
- resulting schema;
- all source hashes/checksums obtainable from the provider or the acquisition process (bulk-export archive checksum at minimum).

**Ingest order:** SEP deep history first, then TICKERS **using current-`main` code**, so `permaticker`, `firstpricedate`, `lastpricedate` and the shipped fail-closed `permaticker_asof()` semantics are present in the **initial qualified artifact** — never added later as an annotation.

## 6. Host provenance

A **fresh** instance provisioned for this build. `mr002-phase3c-run-host` remains a fallback only; a new host keeps the chain free of residual state from a terminated program.

- Recorded **before acquisition**: instance identity, base image, runtime versions, empty-host state, and the ingestion commit.
- **Not** `ec2-paper`. That box carries a 10 GB free-space floor for the MDQ capture guard; a multi-GB pull and a store several times the size of the operating one would threaten it directly.
- **ADR 0051 applies:** the research plane holds **no broker capability** — no Alpaca trading SDK, no broker credentials, no `ROUTER_TOKEN`, and no import of `app.orders` / `app.risk` / `app.brokers`. The instance role is scoped to the research S3 prefixes; it is not an order-path principal.
- The existing CloudFormation stack is **not** touched. The 2026-07-27 incident — a full stack deploy for an IAM-only change replaced the live instance and destroyed its root volume — makes any stack-level operation for this build prohibited.

## 7. Qualification gates — all must pass before the store is used

1. Historical cross-sectional breadth exists back to the required period.
2. `permaticker` populated as expected.
3. `permaticker_asof()` behaves **fail-closed** — `None`, never a guess, outside the effective interval.
4. No silent ticker-reuse guess.
5. Sufficient data to reconstruct the PIT-200 on the **frozen weekly rebalance grid**.
6. Laptop reconciliation run under §3, with every difference classified and no unresolved `UNEXPLAINED_DIFFERENCE` in universe, identity or population.
7. Store hash and custody location sealed.

## 8. PIT-200 population pinning

Once the store qualifies, derive and seal as one artifact:

- governed-store version / hash;
- universe algorithm and version;
- rebalance grid;
- **per-date PIT-200 membership**;
- permanent IDs where resolved;
- the **full union** of names / identities to be served by the EDGAR crawl;
- a deterministic artifact hash.

**The classification crawl must record that exact union-artifact hash as an input.** A later SEP/TICKERS refresh then produces a **new universe version** — never a silent mutation of the population underlying an existing crawl.

## 9. Laptop corroboration custody

Preserved at the **weaker tier** — versioning + encryption + public-access blocking, **no seven-year COMPLIANCE lock** — because its evidentiary role is explicitly non-authoritative and irreversible retention would add little. Its **object key, version ID and SHA-256 are recorded in the reconciliation record**.

## 10. What this freeze does not do

It does not authorise the EDGAR crawl, modify frozen MR-002 machinery, or touch the coverage rule. **`5b26ffa209a6…` (0.95 / 0.95 / 20 years) remains unspent** — applied once, after the crawl, to an admissible measurement that does not yet exist. It reopens no frozen value: signal 252/21, K=3, the 10% cap, `N_min = 4`, the §10.1 gates and the §9.4 cost model are untouched. If the qualified rebuild cannot yield an admissible span meeting the 20-year floor, **SEC-001 V3 stops** — the freeze does not bend to the data.
