# MR-002 P1 — Closeout

**Date:** 2026-08-21 · **Phase:** P1 · **Branch:** `research/mr002-preregistration`
**Terminal disposition:** **`INSUFFICIENT_DEVELOPMENT_EVIDENCE`**

This record states the terminal P1 state in one place. It contains **no new analysis and no new
claim** — every fact below is already established in the records it cites. It exists because the
only narrative document at the branch head, the WP1 report, was written before T2 ran and still
tells a reader that "T2, T5, T6 — not started". That is stale, and a reader landing on this branch
should not have to reconstruct the outcome from six commits.

The WP1 report is **not** rewritten. Correcting a committed evidence record in place would destroy
the chronology that makes the sequence worth having.

---

## Terminal state

| Item | State |
|---|---|
| **P1 disposition** | **`INSUFFICIENT_DEVELOPMENT_EVIDENCE`** |
| A-2 (admissibility) | **FAILED**, on two independent grounds |
| T2 — numerical environment | **NOT COMPLETE** |
| T1 · T3 · T4 (reanalysis tranche) | complete |
| T5 · T6 | **BLOCKED — never executed** |
| F1 — bound dependency-aggregate identity | **unresolved / unreproducible** |
| F4 — runtime custody defect | **REMEDIATED** (the historical defect stands) |
| Evaluator host `i-00c1034f7026db45e` | STOPPED |
| Latch | 8 / CLOSED, canonical `44f5549a…`, unchanged throughout |
| Consumed-holdout access | **none, at any point** |
| P2A | **not authorized** |

## Why P1 terminated where it did

Protocol §5.1 is unconditional: if any of A-1…A-4 fails, the disposition is
`INSUFFICIENT_DEVELOPMENT_EVIDENCE` "however suggestive the partial evidence is." A-2 requires T2
complete, and T2 as frozen requires confirming "pinned image **and dependency identity**". Two
independent failures followed:

- **F1** — the bound dependency-bundle identity `26e23049…` could not be reproduced by any of
  nineteen canonicalisations. The file count matches exactly (2954) and the mount demonstrably
  happened, so this is a *lost algorithm*, not drift. Status label, to be quoted whole:
  `BOUND_AGGREGATE_ALGORITHM_NOT_REPRODUCIBLE; NO_OBSERVED_NUMERICAL_COMPONENT_DRIFT`.
- **F2** — the development corpus could not be regenerated on the evaluator host, which is
  provisioned as a *validation* host with no development dataset. Its runtime-artifact component
  was subsequently resolved; its reproduction component was not.

The frozen rule decided its own consequence. No judgement call was available, and the protocol was
not amended to fit the evidence.

## The two legitimate exits, neither taken

1. Satisfy T2 in full — reproduce the corpus **and** establish a dependency identity that can
   actually be confirmed.
2. An explicit, prospectively recorded owner amendment to the protocol — a governance act,
   versioned and dated, never a reading.

Inventing a twentieth canonicalisation until one hash-matches is **not** an exit; it fits the
algorithm to the answer.

## Substantive findings that survive P1

These are characterization, not a disposition, and they carry forward:

- **P1-F1 / P1-F2** — Gate N1's C2 gate ("100 % certified resolution over 3,895 instances") tested
  the *fallback* path on **five invocations**. The exact one-sided 95 % bound from 0/5 is **0.451**.
  The joint event that ended Validation-2 — primary uncertified **and** fallback terminates — has
  **zero** development observations.
- **P1-F3 / P1-F6** — `PIQP_P2` terminated with `ITERATION_LIMIT_REACHED` on **49 of 3,895**
  development instances (1.258 %), and ~4.80 % at *n* ∈ [20,29] against 0.17 % at *n* < 10. The
  behaviour that consumed the holdout was already measured and visible in the sealed Aug-19 census;
  it did not fail C2 because C2 charges only invoked instances.
- **P1-F5** — the v2 certificate-driven method would **not** have produced a Validation-2 economic
  verdict. The same event yields `UNRESOLVED_INSTANCE` → `Stage3StopV2`. The layers differ in what
  the stop *means*, not in whether it stops.

## Evidence chain

| Commit | Record |
|---|---|
| `7c51066` | Protocol (frozen decision rule) · As-Is Manifest · Development Census · WP1 Report |
| `2418164` | `MR002_P1_T2_EnvironmentIdentity_v1.0` — environment CONFIRMED, A-2 FAILED |
| `7c77f73` | `MR002_P1_T2b_ReproductionFeasibility_v1.0` — F4 discovered |
| `da0d29b` | `MR002_P1_RuntimePreservation_v1.0` — runtime exported, re-identified off-host |
| `cffa999` | `MR002_P1_RuntimeCustodyTransfer_v1.0` — custody placed, deletion gap left open |
| `8e50621` | `MR002_P1_RuntimeCustodyAmendment_v1.0` — Amendment-R applied, deny proven behaviourally |

The order is evidentiary. The discoveries and their remediations happened in this sequence, and the
sequence is part of the evidence — it shows the uncustodied-runtime finding provably predating the
preservation that fixed it.

## Standing operational note

`s3://workbench-mr002-sealed-219024422756/runtime-custody/_control-probe/deletion-deny-proof.txt`
is a **deliberate control-evidence object**, permanently undeletable by design. Its undeletability
*is* the behavioural proof that the permanent-deletion Deny covers `runtime-custody/*`. Its own
body text says so. **It is not orphaned debris and must not be cleaned up** — removing it would
require weakening the control it demonstrates.

## Next work item — not P1

**Question B:** why did the 2026-08-21 Validation-2 execution bind the v1
`stage3_route._routed_solve_qp` layer rather than the 2026-08-19 v2 certificate-driven layer?

Scope is **lineage and configuration only**: deployment identities, entrypoint selection,
container/image/run-spec binding, commit and deploy chronology, execution terminal provenance.

It must **not** reopen numerical P1, rerun validation, inspect consumed holdout values, or attempt
to show that v2 would have produced a better economic result. P1-F5 already establishes that it
would not, and demonstrating that v2 also stops does not explain why v1 executed.

## Not authorized by this record

P2A · P3 · any freeze · any registration · any holdout opening · paper or production activation ·
T5/T6 or any numerical run · a reproduction host · any further policy change · any Validation-2
reopening, retry, substitution or repair. No phase auto-authorizes the next.
