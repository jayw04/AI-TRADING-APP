# MR-002 — Recovery Adjudication and Program Termination v1.0

**Date:** 2026-08-21 · **Authority:** owner ruling, 2026-08-21 · **Status:** TERMINAL

> ## MR-002 TERMINATED — NO ECONOMIC VERDICT
>
> Classification: **`TERMINATED_WITHOUT_ECONOMIC_VERDICT — VALIDATION_INTEGRITY_FAILURE`**
>
> **This is not a rejection.** MR-002 has *not* demonstrated that its economics are bad. It has
> demonstrated that this research program can no longer produce a clean confirmatory answer under
> its existing experimental lineage. Anyone reading this record later must preserve that
> distinction: `TERMINATED_WITHOUT_ECONOMIC_VERDICT` ≠ `REJECTED`.

The designated validation opportunity was consumed in a non-conforming execution and is retained
solely as **integrity evidence**. The validation gate was **never satisfied**. OOS remains
**unconsumed and under permanent DENY** for this research program.

---

## 1. The cumulative basis

The ruling rests on the accumulation, not on any single defect:

| # | Established | Record |
|---|---|---|
| 1 | **P1 closed at `INSUFFICIENT_DEVELOPMENT_EVIDENCE`** — the frozen numerical-environment requirement could not be satisfied | `MR002_P1_Closeout_v1.0`, `edca117` |
| 2 | **Validation-2 consumed non-conformantly**, zero economic-validation credit | `TerminalOutcome v1.0` `9c08bfc5…`, `7a6b6f7` |
| 3 | **Material execution-package binding gap** — registered v2, executed v1 | `MR002_QB_LineageVerdict_v1.0`, `440afe0` |
| 4 | **OOS cannot be repurposed** as replacement validation, ethically or scientifically | `MR002_QB_OwnerAdjudication_v1.0`, `8dbad97` |

A valid recovery would therefore require an entirely new prospective experiment on genuinely new
untouched data. That is technically possible, but it is **a new research program, not recovery of
this one**.

This also follows the program's own governing direction: MR-002 was explicitly bounded to a
"get to validation" workstream, with a warning against open-ended development whose marginal value
falls while competing with getting other strategies into meaningful testing. Its decision contract
already said an integrity failure means **stop** — no OOS consumption.

## 2. Terminal program state

| Item | Terminal state |
|---|---|
| **Program** | **TERMINATED — NO ECONOMIC VERDICT** |
| Classification | `TERMINATED_WITHOUT_ECONOMIC_VERDICT — VALIDATION_INTEGRITY_FAILURE` |
| P1 | CLOSED — `INSUFFICIENT_DEVELOPMENT_EVIDENCE` |
| Question B | CLOSED — `EXECUTION_PACKAGE_BINDING_GAP` CONFIRMED |
| Validation-1 | CONSUMED / CLOSED |
| Validation-2 | CONSUMED — INTEGRITY FAILURE / NOT EVALUATED; integrity evidence only |
| Validation gate | **NOT SATISFIED** |
| Economic verdict | **UNKNOWN / NONE** — no economic statistic was ever produced |
| OOS partition | **UNCONSUMED — PERMANENT DENY for this program** |
| Same-partition rerun | PROHIBITED |
| Paper / production | NOT AUTHORIZED, and not reachable from this state |

## 3. What is NOT authorized

Repair-and-replay in any form · replacement validation using the existing OOS partition · further
numerical investigation · evaluator start · AWS research execution · validation or OOS access ·
P2A · paper strategy · product integration · promotion of any MR-002 result to a product surface.

## 4. What remains authorized — closeout and archival only

- this record;
- preserving the OOS partition **untouched** — neither deleted nor inspected;
- preserving both research branches and the runtime/evidence custody already established;
- updating status indexes to show the terminal state **without rewriting historical records**.

### 4.1 On "marking" the OOS partition

The OOS partition is marked **here, in governance**, and deliberately **not** by writing anything
into the `oos/` prefix. Writing a marker object into the holdout prefix would be a mutation of the
partition's contents by the very program forbidden to touch it, and "preserve it, don't inspect it"
is best served by not reaching for it at all. The existing resource-side controls already stand:
`DenyValidation2ReadsToEveryPrincipalButGovernedValidationReader` scopes `oos/*`, and
`DenyPermanentDeletionOfSealedObjectVersions` covers `oos/*` object versions.

**No OOS object was read, listed for content, written, tagged or deleted at any point in this
program's closeout.**

## 5. Preserved artifacts

| Branch | Head | Contents |
|---|---|---|
| `research/mr002-preregistration` | `edca117` — **frozen** | full MR-002 research history through the P1 evidence chain |
| `research/mr002-validation2-lineage` | `8dbad97` | Question B protocol → verdict → owner adjudication |

Neither is merged. PR #422 is marked `[LEGACY UMBRELLA DRAFT — NOT MERGE-READY]`. Repository
integration remains a **separate workstream**, and MR-002 governance artifacts bind commit
identities — **do not rebase or squash this history**.

The bound Stage-3 runtime is under evidence-store custody at
`s3://workbench-mr002-sealed-219024422756/runtime-custody/mr002-research-v1.4/config-770553aeae6c/image.oci.tar`,
config identity `sha256:770553aeae6c…`, with the permanent-deletion Deny proven behaviourally.

## 6. The control lesson worth carrying to other programs

> **Hash-binding proves an artifact is present. It never proves the artifact was executed.**

The Validation-2 registration bound `frozen_method` to three v2 files marked `enforced: true`. All
three were deployed on the host and byte-correct at execution time. The run still routed v1 —
because enforcement verified **presence**, not **use**. This gap applies to every `enforced: true`
binding of this shape, not only to a launcher.

Its corollary, from the earlier N3 defect in which the solver handle was captured *before* entering
the routing context: a conformance gate must be **observational, not pre-flight**. It must read
emitted evidence — the census disposition vocabulary after the first invocation — rather than any
declaration of intent made before the run.

## 7. If MR-002 ever returns

It returns as a **new charter**, never as "MR-002 Validation-3". That future program requires:

1. a fresh prospective preregistration;
2. genuinely new untouched observations, unavailable to today's investigation;
3. a newly frozen execution package;
4. the **observational conformance gate** above — proving the registered layer actually executed,
   not merely that its files existed — built and passing **before any data access**.

## 8. Final direction

Redirect research capacity elsewhere. MR-002's contribution to the platform is now an
**evidence-engineering** contribution rather than an economic one: it is a fully documented case in
which the governance system detected, refused to paper over, and correctly terminated a program
whose experimental integrity could not be re-established.
