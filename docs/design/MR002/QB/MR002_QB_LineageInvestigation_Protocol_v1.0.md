# MR-002 Question B — Execution-Lineage Investigation Protocol v1.0

**Date sealed:** 2026-08-21 · **Branch:** `research/mr002-validation2-lineage`, cut from `edca117`
**Status:** PROSPECTIVE PROTOCOL. Authorizes nothing. Bounds the scope, the prohibitions and the
disposition set **before** lineage evidence is inspected.

---

## 0. The question

> Why did the 2026-08-21 Validation-2 execution bind the **v1** `stage3_route._routed_solve_qp`
> execution layer, when the **v2** certificate-driven implementation had landed on 2026-08-19?

This is material because it concerns the provenance of an **already-consumed validation execution**.
It is not a numerical question and it is not a second attempt at P1.

## 1. Standing on P1

P1 is **CLOSED**. Terminal disposition `INSUFFICIENT_DEVELOPMENT_EVIDENCE`, delivery state
**COMPLETE — DURABLE ON REMOTE, NOT INTEGRATED TO MAIN**, head `edca117`. Question B does not
reopen it, does not revisit A-2, F1 or F2, and cannot change the P1 disposition.

Two P1 findings are **inputs** here and are not to be re-litigated:

- **P1-F5** — the v2 layer would **not** have produced a Validation-2 economic verdict. The same
  event yields `UNRESOLVED_INSTANCE` → `Stage3StopV2`. Demonstrating that v2 also stops does not
  explain why v1 ran, and Question B must not drift into arguing the counterfactual.
- The Aug-19 differential — v1 and v2 agree on **3,895 / 3,895** accepted points with zero
  disposition differences on development. The layer choice is an evidence-semantics choice, not an
  economic one.

## 2. Authorized scope — lineage and configuration ONLY

- deployment identities and the deployed-tree aggregate;
- entrypoint selection: which runner script the execution actually invoked;
- container / image / run-spec binding;
- commit and deploy chronology across 2026-08-19 → 2026-08-21;
- execution terminal provenance — what the sealed terminal record names, and what that frame
  uniquely identifies;
- the execution package, countersignature and closure records, and what seam each binds;
- whether any record states a deliberate choice of layer.

## 3. Prohibited

- **Any numerical run.** No solver, no corpus, no fixture execution, no reproduction host.
- **Any reopening of P1** — A-2, F1, F2, T2, T5, T6, or the disposition.
- **Any consumed-holdout inspection**: Validation-1 and Validation-2 materializations, their
  archived custody copies, any validation-derived QP, any economic value, and the failing
  configuration — which remains NOT DETERMINED and may not be inferred.
- **Any attempt to show v2 would have produced a better economic result.** P1-F5 settles it.
- Any change to a frozen numerical parameter, tolerance, profile or acceptance predicate.
- Any Validation-2 reopening, retry, substitution or repair.
- Opportunistically solving the repository-integration problem (#422). That is a separate
  workstream and must not be folded in here.
- Rebasing or squashing MR-002 history. Governance artifacts bind commit identities; a rewrite
  would break valid historical SHA references.

## 4. Evidence sources

All local and offline. No AWS call is required, and none that reads sealed or holdout content is
permitted.

| Source | What it settles |
|---|---|
| `git log` / `git show` over 2026-08-19 → 2026-08-21 | when v2 landed, what shipped after it, deploy chronology |
| Sealed terminal record `TerminalOutcome v1.0` `9c08bfc5…`, commit `7a6b6f7` | which frame raised, and therefore which layer executed |
| `MR002_Phase3C_ValidationExecutionPackage_v2.x`, `..._ExecutionCountersignature_v*`, `MR002_Validation2_ExecutionPackage_v1.0` | which seam the execution package binds |
| `MR002_Validation2_ReadinessQualification_v4.0` / `v5.0` | the deployed-tree aggregate and bound invocation |
| Runner sources: `mr002_phase3c_validation_run.py`, `mr002_v2_harness.py`, `mr002_v2_evaluator_requal.py` | which runner imports which seam |
| `stage3_route.py` vs `n1/seam.py` | frame-name discrimination (`_routed_solve_qp` vs `_routed`) |

## 5. Disposition set — FROZEN, closed, neutral in naming

Exactly one, and no label presupposes fault:

```
DELIBERATE_LAYER_SELECTION_RECORDED       a record states the v1 layer was chosen on purpose
EXECUTION_PACKAGE_BINDING_GAP             v2 landed but was never bound into the execution package
DEPLOYED_ARTIFACT_PREDATES_V2             the deployed tree/artifact did not carry the v2 seam wiring
AMBIGUOUS_BINDING_NOT_DETERMINED_BY_CONFIG  both layers present; selection was implicit, not configured
INSUFFICIENT_LINEAGE_EVIDENCE             the record cannot settle it
```

`INSUFFICIENT_LINEAGE_EVIDENCE` is the default. A disposition may be selected only if every claim
supporting it names an artifact identity or a commit SHA.

## 6. Explicit non-goal

Question B is **not** an attempt to establish that the Validation-2 result should be set aside. The
terminal disposition — `INTEGRITY FAILURE / NOT EVALUATED`, sealed as `9c08bfc5…` — stands
regardless of the answer. Validation-2 is CONSUMED and there is no further opening. Whatever the
lineage shows, it does not retroactively convert an integrity stop into an economic verdict, and it
does not authorize a re-run.

## 7. Stop conditions

- Any consumed-holdout access, by any path.
- Any drift into numerical or economic argument.
- Any finding that would require a numerical run to confirm — record it as a limit, do not run it.
- Any pressure to reach a disposition that the artifact record does not support.

## 8. What this protocol does not authorize

P1 reopening · P2A · P3 · any freeze · any registration · any holdout opening · paper or production
activation · any numerical execution · any repository-integration work · any merge.
