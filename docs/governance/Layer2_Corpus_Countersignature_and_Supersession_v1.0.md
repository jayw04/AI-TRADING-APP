# Layer 2 governed corpus — countersignature and supersession record v1.0

**Status: CONDITIONALLY COUNTERSIGNED — not deployed, not authorized for observation.**

| | |
|---|---|
| complete package | `72b98dbb40f8eadae16e91799062dd378f43b64738e814176a839aa3601817c5` |
| approved corpus manifest | `1e269fadedff74b04135dea5441f2f3338852464c3d06a74c81c98dfc43ca064` |
| supersedes | `a69ad50ffc3c6925b3c9b6c8fd1c2adc7143ef9d5c98e9378e1c3ea21ca75c49` |
| supersession reason | `HISTORICAL_RECONSTRUCTION_SINGLE_VINTAGE_AND_PERMANENT_LINEAGE` |
| construction kind | `layer2_governed_corpus` |
| schema version | `LAYER2_SINGLE_VINTAGE_PERMANENT_LINEAGE_v1.0` |
| approval type | conditional **data-construction** countersignature |
| countersigned by | Jay Wang (owner), 2026-07-30 |

## What was approved

The single-vintage historical reconstruction; permanent-lineage normalization; the 14,145 mapped-identity
universe and the 14,143 price-bearing universe; the OCCI/HYPG no-SEP-coverage dispositions; the SHOP/TLN
version-specific quarantine; the seam, lineage, adjustment, ranking and impact evidence; the narrow
session-scoped readiness contract; and the explicit supersession of the prior corpus **without mutating
it**.

The July 27 decision evidence is accepted: top five **AXTI, SNDK, BE, WDC, MU**, equal weights 19.6%,
gross 0.98, regime **ABOVE_BAND**.

> The unchanged portfolio does not diminish the materiality of the repair. The superseded corpus
> contained a physically impossible **+38.04%** cross-sectional seam return that materially distorted
> the cumulative regime path. The rebuilt margin above the moving average, `+12.3491%` rather than
> `+27.2576%`, is the valid one.

## What was NOT approved

This countersignature does **not** assert `full_action_semantics_proven = true`.

Eighteen acquired-side events remain economically unverifiable from the available vendor schema, which
supplies no per-share consideration, exchange ratio or successor conversion term. They are accepted only
as complete, digest-bound, **session-specific non-decision limitations**. The approved readiness claim is:

```
decision_validity_proven         = true
full_action_semantics_proven     = false
nondecision_limitations_present  = true
```

**Valid for session 2026-07-27 only.** It must not automatically carry into a later observation; the
attestation names one session and is refused for any other.

It also does not authorize deployment, window opening, or observation recording.

## Conditions precedent to deployment

All of the following must occur, in order:

1. Native support for the Layer 2 manifest kind and schema version is implemented.
2. The loader validates the Layer 2 manifest **without inventing** a base, a delta chain or a
   `base_coverage_through`.
3. Existing base-plus-delta loading remains unchanged.
4. The adjustment-verifier, narrow-readiness and runner receipt changes are included.
5. Focused and full local gates are green for the final PR diff.
6. One coherent PR is opened.
7. Linux CI passes at the exact reviewed head.
8. The PR is exact-head squash merged.
9. The host is fully redeployed from the resulting squash commit.
10. The countersigned corpus and exact manifests are installed.
11. Full readiness passes on the deployed construction.
12. The immediate Account 4 state check passes.
13. A final opening package is presented for authorization.

## Wording that must be preserved

**SHOP/TLN** must never be described as decision-irrelevant. They are:

- decision-relevant in the raw construction (SHOP ranks 119 and would enter the top five; TLN enters the
  proxy basket and contributors; both can affect the regime input);
- governed-quarantined due to unexplained vendor anomalies;
- and the post-quarantine decision remains valid with all gates passing.

**Headroom**: the scoring universe is *exactly filled* at 200/200 and the selection takes 5, leaving
**195 names of selection headroom**. "headroom 0" refers to universe **fill**, not selection fragility.

**Ordering**: AXTI and SNDK are tied at the winsorized z-score cap; the deterministic `(-z, ticker)` sort
places AXTI first. Economically immaterial under equal weighting, but the displayed order must **not** be
described as pure raw-momentum order.

## Store identities

| identity | value |
|---|---|
| `store_file_sha256` | `5960a0f7c0ae5dfd5955a15e910abc109376ff511cc3d33a849a712a6eee2a09` |
| `store_identity_sha256` (registered, 273-session window) | `fa8fc9a89a3ac83269cb144fd787fce70213ba8a42e1b1f11744b23f6be8f3a7` |

Superseded, for comparison: registered `57234b02322bcf13368caf9c23461ecdda7d7eb015bca4b1ffa778c858cf86ee`.

⚠ **The extended `store_value_identity_sha256` is RETRACTED** — see Amendment 1. It was never part of
the registered runtime contract and was not well-defined (its ordering was not total over a table with
identical duplicate rows). No replacement is defined. The registered `store_identity()` is unaffected.

## Where the evidence lives — a deliberate trust boundary

This is a trust-boundary choice, **not a missing file**.

**Repository** — runtime loader, validators, evidence consumers and portable verification tools
(`apps/backend/scripts/forward_validation/`, 16 tools), plus this record, ADR 0048 and the small
governed manifest `manifests/layer2/corpus_manifest_v2.json`.

**Governed artifact storage** — the sealed source vintage, the exact corpus artifacts, the quarantine
evidence, and **the preserved post-build reconstruction implementation**
(`build_normalized_corpus.py`).

⚠ The reconstruction builder is deliberately **not** in a repository production tree. Invariant A4
(`test_only_the_store_finalizer_writes_dataset_coverage`) permits exactly one authoritative completion
path — `FactorDataStore.finalize_dataset_ingest`. The builder writes Layer 2 load and coverage records
during reconstruction, which is honest for an offline producer but would create a second mechanism if it
lived under `app/` or `scripts/`. It is therefore a **governed offline construction artifact, not
deployed application code**. Neither the invariant nor the finalizer API was changed to admit it.

Repository tooling may validate the built store, recompute identities, inspect coverage, verify
manifests and generate deployment evidence. It must **not** recreate or backfill source-authority rows —
verified by scanning the staged diff for `dataset_coverage` and `ingest_runs` writes.

### ⚠ Producer provenance — a recorded gap

| | |
|---|---|
| original producer bytes | **NOT PRESERVED** |
| original builder digest | **NOT CAPTURED** at build time |
| preserved builder | `ed212e787ea6edd0b3acac48d6656582f8237ff68689952566c512b754e3eae2` |
| builder relationship | `POST_BUILD_REVISION_NOT_PROVEN_IDENTICAL_TO_ORIGINAL_PRODUCER` |
| equivalent-producer status | **INDEPENDENTLY PROVEN VALUE-EQUIVALENT** (Amendment 1) |
| platform limitation | **WINDOWS-PATH DEPENDENT** |

The corpus store was written 2026-07-29 **19:44:54** and its evidence at **19:44:56**; the builder file
was last modified at **20:23:12** — **38 minutes after the build**. The build evidence records no builder
identity, and no backup of the pre-edit bytes exists.

The recorded change was removal of dead constants (`PRICE_IDENTITY_COUNT`, `RETRACTED_IDENTITIES`,
`RETRACTED`, `CONTROL_TICKER`, `_api_sep_rows`) and documentation/unused-helper cleanup; a reference scan
finds no remaining runtime dependency on any of them, and identity names and counts are read from
`layer2_price_adjudication.json` as data rather than from constants. **Semantic equivalence has not been
independently rebuilt.** The corpus output identities remain independently verified.

This is the preserved post-build reconstruction implementation. The exact producer identity was not
recorded, **and equivalence has since been demonstrated by an independent rebuild from identical sealed
inputs** — verdict `VALUE_IDENTICAL_WITH_EXPLAINED_PHYSICAL_DIFFERENCE`, with zero differing governed
rows in either direction across all three tables. See **Amendment 1**
(`Layer2_Countersignature_Amendment_1.md`, sha256
`7a18d3c07dfcb3894dda2ca55f644152a4ac257d828f09c5164d2440b495d273`).

See ADR 0048, amendment 2026-07-30.

See ADR 0048, amendment 2026-07-30.
