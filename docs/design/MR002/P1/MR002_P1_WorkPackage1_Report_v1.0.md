# MR-002 P1 — Work Package 1 report

**Reporting format:** MR-002 Next-Phase Guidance and Implementation Plan v1.0, §5.3.
**Date:** 2026-08-21 · **Phase:** P1 · **Tracks executed:** T1, T3, T4 (reanalysis tranche).
**Disposition emitted:** **none.** Protocol §5.1 admissibility condition A-2 is unmet.

---

## 1. Source commit / branch

| | |
|---|---|
| Branch | `research/mr002-preregistration` |
| HEAD at start and end of the work package | `c715262b7ae955d` — no commit was created |
| Working tree | dirty (pre-existing); the artifacts below are new and untracked |

Nothing was committed, pushed, branched or merged. GITHUB-OPS-001: no push was made, and no CI run
was triggered by this work package.

## 2. Exact artifacts added

| Path | Kind |
|---|---|
| `docs/design/MR002/P1/MR002_P1_NumericalInvestigation_Protocol_v1.0.md` | governing — prospective protocol |
| `docs/design/MR002/P1/MR002_P1_Stage3_AsIsManifest_v1.0.json` | governing — machine-readable as-is inventory (T1) |
| `docs/design/MR002/P1/MR002_P1_DevelopmentStatusCensus_v1.0.json` | evidence — reanalysis tranche (T3/T4) |
| `docs/design/MR002/P1/MR002_P1_WorkPackage1_Report_v1.0.md` | this report |
| `apps/backend/scripts/mr002_p1_asis_manifest.py` | generator for the manifest |
| `apps/backend/scripts/mr002_p1_dev_status_census.py` | generator for the census |

No existing file was modified.

**Document-location call (ADR 0050 / GITHUB-OPS-001).** All four documents sit under
`docs/design/**`, which `.gitignore` un-ignores, so they are Git-native with no `.gitignore` change.
That is the deliberate classification: the protocol and the manifest are *governing* (a reviewer must
read them beside the code), and the census, though generated, is the factual basis on which a P1
disposition will later be accepted — it is small, decision-bearing, and belongs in a PR diff. Bulk
per-instance derivatives stay in `.mr002out/`, which is ignored.

## 3. Content identities

SHA-256 over CRLF-normalised (LF) bytes — the portable identity. A Windows worktree's raw-byte hash
does not match an LF deployment, so `sha256_lf` is the value to compare.

| Artifact | `sha256_lf` |
|---|---|
| `MR002_P1_NumericalInvestigation_Protocol_v1.0.md` | `824530059245e33e11ad361067b2258d9ea488a21dd5dcf18fe2f57ae56915b5` |
| `MR002_P1_Stage3_AsIsManifest_v1.0.json` | `cd497273aceff6ab023855dbf2e3f8c87bf28b9e74bc0ef63bc11c69c3f35970` |
| `MR002_P1_DevelopmentStatusCensus_v1.0.json` | `245e77806283e8b9b60cc06e1c5b2e90543d009385deb0886d1befe0c4fb84f4` |
| `mr002_p1_asis_manifest.py` | `6383b1a74698cfabbd106782cd33760ac163e83c196b9b23a01ab2fbcea17fed` |
| `mr002_p1_dev_status_census.py` | `02338015943f91c336a2236d09e8777e5b878b684a8be5fd4c0f7b0ec964b6e4` |

Each JSON also carries `record_sha256_of_body_without_this_field`, reproducible by stripping that
one field and re-serialising: manifest `f5517316e88b6196…`, census `0b9824365bc23e5e…`.

**Bound prior, verified rather than quoted:** `MR002_Stage3v2_AdjudicatedMemo_v1_2.md` recomputes to
`3e1e491533a2aeb1a370610dc9854f5ea5a592d71fdff95dd0ec88e8e1536ee2`, matching plan issuance edit F1.
The file has no CRLF, so worktree and LF hashes coincide.

## 4. Tests and qualification results

| Check | Result |
|---|---|
| `ruff check` on both new scripts | **All checks passed** |
| Manifest generator | exit 0 · 15 files inventoried · 0 missing · 25 frozen constants extracted |
| Census generator | exit 0 · 3,895 instances × 3 candidates reanalysed · input corpus hash matched the registered `1d231930…` |
| `check_research_plane_order_path_isolation.sh` | **reports a violation — pre-existing, not from this work package.** See §7 |
| `check_research_plane_no_broker_capability.sh` | OK |

No numerical test was run: the solver stack is absent here (§6).

## 5. Data scope actually touched

Development domain only.

- Read: repository source at HEAD; `.mr002out/n1/n1_census_rows.json`;
  `.mr002out/n1/n1_census_c1c2.json`; `.mr002out/n1/n1_diff_v1.json`; the commit message of `7a6b6f7`.
- **Not** opened: any corpus `.npz`, any dataset, any sealed reader, any validation store, any OOS
  data, and both archived consumed materializations. Neither generator imports a research module or
  a solver; the manifest generator parses source with `ast` and never executes it.
- The only Validation-2 information used is the sealed terminal string, admissible under Aug-19 SA-5
  as `INCIDENT_CLASS_KNOWLEDGE`.

## 6. Findings

Six findings are recorded in the census record. The three that matter most:

**P1-F1 — the fallback path's development qualification rests on five invocations.**
Gate N1 passed `PIQP_P2` on gate C2, "100 % certified resolution over 3,895 instances". But in
production shape the fallback is invoked *only* where the primary produced no certified candidate,
and the primary certified 3,890 of 3,895. The fallback path was therefore exercised **5 times**. All
five certified, so the observed failure rate is 0 — but the exact one-sided 95 % Clopper-Pearson
upper bound from 0 failures in 5 trials is **0.451**. C2 as measured cannot distinguish a fallback
that never fails from one that fails on nearly half its invocations.

**P1-F2 — the Validation-2 failure mode has zero development observations.**
The joint event *primary produces no certified candidate **and** the fallback terminates without one*
occurs **0 times** on the development corpus. No development result attests that the frozen pair
resolves that class, because the class was never observed.

**P1-F3 / P1-F6 — the fallback generator's termination rate was measured, and is not small.**
Independently of invocation, `PIQP_P2` terminated with the registered reason
`ITERATION_LIMIT_REACHED` on **49 of 3,895** development instances (1.258 %). Stratified by problem
size the rate is ~28× higher on mid-sized instances than the smallest: 0.17 % at *n* < 10, 0.68 % at
*n* ∈ [10,19], **4.80 %** at *n* ∈ [20,29], 4.23 % at [30,39], 3.23 % at [40,49]. It is not monotone
— it peaks at [20,29] and declines while staying well above the small-*n* level. The corpus is
dominated by small instances (1,740 of 3,895 have *n* < 10), so the corpus-wide figure understates
exposure for any population with a larger size mix. *This says nothing about any holdout population's
size distribution and must not be used to infer one.*

Taken together: the behaviour that ended Validation-2 was **measured and visible in the sealed Aug-19
development census**. It did not fail C2 because C2 charges only the instances where the fallback is
actually invoked, and there were five of them.

**P1-F4 / P1-F5 — the taxonomy question, stated without overclaiming.**
Two disposition layers exist in the tree. The v1 cascade (`stage3_cascade`) keys acceptance on an
exact `(solver, exception class object, complete message)` allowlist that contains **one** entry,
scoped to `QUADPROG_SQRT`. `PIQP_P2` has none, so *any* raise from the fallback is
`INTEGRITY_DEFECT → INVALID_RUN`; the terminal `UNRESOLVED_NUMERICAL_FAILURE` is reachable from the
fallback only when it *returns* a point the certifier rejects, never when it terminates. The v2
method (`n1/method.py`) classifies the same event structurally as
`NO_CERTIFIED_CANDIDATE / ITERATION_LIMIT_REACHED`.

The sealed Validation-2 terminal names the frame `stage3_route._routed_solve_qp` and the code
`UNREGISTERED_EXCEPTION`, both unique to the **v1** layer; the v2 seam's frame is `n1.seam._routed`.
So the v1 layer was the bound Stage-3 path.

**This is deliberately not stated as "the v2 method would have saved Validation-2."** It would not.
Under v2 the same event yields `UNRESOLVED_INSTANCE`, which raises `Stage3StopV2` and ends the run.
The layers differ in what the stop *means* — an impugned evaluation system versus an unresolved
instance — not in whether an economic verdict is produced. Neither produces one. Independently, the
Aug-19 differential shows v1 and v2 agree on **3,895 / 3,895** accepted points with zero disposition
differences on development, so the choice of layer is an evidence-semantics choice, not an economic
one.

## 7. Unresolved items

**No `SUPERSESSION_REQUIRED` item was generated.** Nothing in this work package proposes a change to
a frozen prior.

Open items, in priority order:

1. **`NEEDS_RULING` — environment.** `quadprog`, `piqp`, `clarabel`, `mpmath` are not installed here
   and the evaluator host is STOPPED. Protocol admissibility condition **A-2 is unmet**, so tracks
   T2, the numerical half of T5, and T6 cannot run, and **no P1 disposition may be selected.** This
   is the P1 critical path. An owner decision is required on how the pinned research environment is
   made available.
2. **Open P1 question — why the v1 layer was the bound path.** The v2 method landed 2026-08-19
   (`770a109`); Validation-2 ran 2026-08-21 through the v1 seam. Whether that was a deliberate
   freeze decision or an execution-package binding gap is **NOT DETERMINED** by this work package.
   It is an execution-package question, not a numerical one, and it belongs in the P1 record.
3. **Unrelated pre-existing defect, flagged not fixed.**
   `apps/backend/app/research/disc001/snapshot.py` is **untracked** in this working tree and its
   local copy spells `"ROUTER_TOKEN"` literally, which trips
   `check_research_plane_order_path_isolation.sh`. `origin/main` deliberately writes it as
   `"ROUTER" + "_TOKEN"` so the isolation grep does not treat the file as a token holder. The local
   untracked copy has lost that workaround. It is outside MR-002 scope and was not touched — but it
   would fail CI if committed as-is.

## 8. Next gate status

| Gate | Status |
|---|---|
| P1 disposition | **BLOCKED** on A-2 (numerical environment) |
| P1 tracks T1, T3, T4-reanalysis | complete |
| P1 tracks T2, T5, T6 | not started — environment-blocked |
| Aug-19 Gate N1 authority | in force, scope N1 only, unchanged |
| P2A | not authorized — see §9 |

## 9. What is explicitly NOT authorized next

Per plan v1.0 §5.1–5.2 and protocol §10, this work package authorizes **nothing** further:

- **P2A may not begin.** Plan §5.1: "P2A may begin only when the owner/developer handoff explicitly
  includes it or a prior authority already covers the work. Do not infer authorization from roadmap
  order." No such handoff exists.
- No P3 economic work, no rubric, no freeze, no registration, no holdout opening, no paper or
  production activation.
- No change to any frozen numerical parameter, tolerance, profile or acceptance predicate. In
  particular, raising PIQP's `max_iter` remains a standing supersession tripwire (protocol §6) — it
  is a profile change motivated by an observation on the consumed population, and no evidence yet
  exists that the failing instance class is solvable at the frozen tolerances at all.
- No Validation-2 re-opening, retry, solver substitution, or repair against the consumed population.
- No allowlist widening presented as a fix.

Findings P1-F1 through P1-F6 are **characterization**, not a disposition. The five-label closed set
remains open, and P-5 `INSUFFICIENT_DEVELOPMENT_EVIDENCE` is the standing answer until A-2 is met.

---

## 10. Owner corrections to the program record (2026-08-21)

Two corrections were ruled by the owner at the close of this work package. Both are recorded here
because each changes what a later reader may rely on.

### 10.1 The v1.3 / v1.3.1 development plan is NOT the current authorization record

`docs/design/MR002/MR002_Development_Plan_Next_Phases_v1.3.md` is dated **2026-08-09** and still
records:

| Line | Claim | Actual state at 2026-08-21 |
|---|---|---|
| 64 | `validation_authorization` = **false**, `_rev 0` | superseded — the opening was authorized and executed |
| 65, 419–420 | Validation partition **CLOSED**; single opening **UNCONSUMED**; OOS under DENY | superseded — **Validation-2 is CONSUMED**, terminal `INTEGRITY FAILURE / NOT EVALUATED` (`TerminalOutcome v1.0` `9c08bfc5…`, commit `7a6b6f7`) |

**Ruling:** v1.3/v1.3.1 remains useful for **custody and runtime principles** — immutable-digest
resolution, fail-closed behaviour, the numeric-runtime identity bindings — and is cited in this
program for those principles only. It **must not be treated as the authorization record** for this
P1 investigation. The governing authorities for P1 are the Aug-19 adjudicated memo (`3e1e4915…`),
the Next-Phase Plan v1.0, and this P1 protocol.

**Concrete consequence for the next work package:** v1.3.1 §"WP-B" names evaluator index digest
`sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9`. That value is dated
**2026-08-09** and **may not be reused on trust.** The authoritative image/runtime binding must be
re-derived from the post-Aug-19/21 authority artifacts before any solver executes. v1.3.1's own
principle governs the method: resolve strictly by immutable digest, fail closed on miss, mismatch or
registry unavailability — **no tag, no local Docker daemon, no rebuild fallback.**

### 10.2 Question A and Question B are separate and must stay separate

| | Question | State |
|---|---|---|
| **A** | *Why did Validation-2 stop?* | Evidence exists: the v1 route was the bound execution layer, and the fallback generator terminated with `ITERATION_LIMIT_REACHED`, which that layer classifies `INTEGRITY_DEFECT → INVALID_RUN`. |
| **B** | *Why was v1 the bound execution layer on 2026-08-21 rather than the 2026-08-19 v2 certificate-driven method?* | **NOT DETERMINED.** |

Finding P1-F5 — that v2 would also have stopped — answers neither question B nor question A's
"why this layer". **Demonstrating that v2 would also stop does not explain why v1 executed**, and
the two layers' stop *semantics* differ (v1 route termination → `INVALID_RUN`; v2 →
`UNRESOLVED_INSTANCE` → `Stage3StopV2`). Collapsing them would let an architectural convenience
substitute for a lineage fact.

**Ruling:** question B is a **binding/lineage investigation in its own right**, to be conducted
**after** the numerical work (T2/T5/T6), and it may **not** be used to force or shortcut a P1
disposition. The general principle it protects is the one v1.3.1 states plainly: execution identity
and structural bindings are not changed or reinterpreted in order to reach a result.

### 10.3 Authorized next action

Owner decision, 2026-08-21: **temporarily start the existing evaluator host** and use the
already-pinned research environment there, to satisfy A-2 and execute **T2 → T5 → T6** under the
sealed P1 protocol. Recreating the environment by installing `quadprog`/`piqp`/`clarabel`/`mpmath`
on the workstation is **explicitly not authorized** — a local install answers "what happens with
today's packages on this laptop", not "what happened under the governed numerical environment", and
a different solver build, BLAS implementation, CPU dispatch path or tolerance implementation could
move observations between disposition categories.

Scope of that authorization, stated as the owner stated it: **restoration of the environment
necessary to execute the already-defined P1 protocol — and nothing else.** It is not authorization
for P2A, a validation rerun, OOS access, any strategy change, or a disposition. The frozen decision
rule is applied only after T2/T5/T6 complete; if A-2 cannot be reproduced, the result stays
`INSUFFICIENT_DEVELOPMENT_EVIDENCE` rather than an inferred disposition.
