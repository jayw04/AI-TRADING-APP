# MR-002 P1 — Numerical Investigation Protocol v1.0

**Program:** MR-002 / SPQ-1 · **Phase:** P1 (roadmap label per Next-Phase Plan v1.0 §4)
**Date sealed:** 2026-08-21
**Status:** PROSPECTIVE PROTOCOL. Authorizes nothing. Freezes the investigation scope, the evidence
admissibility rules, and the disposition decision rule **before** the P1 analyses that have not yet
been run are run.
**Type:** governing record.

---

## 0. Authority binding

| Binding | Identity | Verification |
|---|---|---|
| Governing roadmap | `MR002_Next_Phase_Guidance_and_Implementation_Plan_v1.0.md` | `docs/design/MR002/`, read 2026-08-21 |
| Governing Stage-3 prior (F1) | `MR002_Stage3v2_AdjudicatedMemo_v1_2.md` | content SHA-256 **`3e1e491533a2aeb1a370610dc9854f5ea5a592d71fdff95dd0ec88e8e1536ee2`** — **recomputed from the tracked file and matched** |
| Operating authority | Gate N1 grant, Aug-19 memo §5 (GRANTED, scope N1 only) | quoted in §3 |
| Prospective requirements | `MR002_NextMethodVersion_ProspectiveRequirements_v1.0` / `0ec54ba3…` / commit `c715262` | R1 |
| Source commit at sealing | `c715262b7ae955d`, branch `research/mr002-preregistration` | `git log -1` |

This protocol does **not** broaden the Aug-19 authorization. Any P1 branch that would require
broadening stops and emits a `SUPERSESSION_REQUIRED` item (§6).

---

## 1. The question P1 must answer

> Determine, **without using consumed holdout data**, whether the frozen numerical pair's inability
> to complete reflects (a) an inadequate method, (b) a legitimately uncertifiable instance class,
> (c) an evaluation-protocol gap, or (d) insufficient evidence.

The observed incident is the Validation-2 terminal:

```
Stage3Stop: INVALID_RUN: fallback integrity defect:
UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED
```

raised inside `stage3_route._routed_solve_qp`, sealed as `TerminalOutcome v1.0`
`9c08bfc5cb18d683beeb347243fb657cc24d37d925ad06d5409b76979d5fa53b`, commit `7a6b6f7`.

**The incident text is the only Validation-2 information this protocol admits**, and it is admitted
under Aug-19 SA-5 as `INCIDENT_CLASS_KNOWLEDGE` (a production generator can terminate without a
candidate). Everything SA-5 prohibits as `CONSUMED_VALIDATION_INSTANCE_INFORMATION` — coefficients,
date, securities, target vector, constraint geometry, iteration trajectory — is out of scope, and is
**not available** in any case: the execution report was never written, and the Stage-3 invocation
census and the failing configuration are sealed as NOT AVAILABLE / NOT DETERMINED.

P1 may not infer, reconstruct, or narrow the failing configuration.

---

## 2. Prior-inspection disclosure (anti-peeking honesty)

`EVIDENCE_NOT_FEEDBACK` governs prospective evidence; P1 operates on **development** evidence, where
the corresponding discipline is that a disposition may not be reverse-engineered from results
already seen. The artifacts below were **read before this protocol was sealed**, and the disposition
rule in §5 is written in full knowledge of them. They are disclosed here so a reviewer can judge the
rule against what was already known rather than against a claim of blindness.

| Artifact | Read | What was seen |
|---|---|---|
| `.mr002out/n1/n1_census_c1c2.json` | yes — full | Per-candidate C1/C2 verdicts and termination-reason histograms over the 3,895-instance development corpus |
| `.mr002out/n1/n1_diff_v1.json` | yes — full | v1-seam vs v2-method accepted-point differential |
| Source of `stage3_cascade.py`, `stage3_route.py`, `n1/method.py`, `n1/seam.py`, `mr002_piqp.py`, `mr002_coverage_signed_gap.py`, `mr002_n1_census.py` | yes | The as-is numerical and disposition architecture |
| `.mr002out/n1/n1_census_rows.json` (per-instance rows) | **schema only — one row** | Field names. No aggregate over the rows was computed before sealing |
| Commit `7a6b6f7` message | yes | The sealed Validation-2 terminal record |

Three facts were therefore known at sealing time. They are stated plainly here rather than presented
later as discoveries:

- **D-1.** The Validation-2 terminal was produced by `stage3_route` → `stage3_cascade` — the **v1
  allowlist cascade** — not by the certificate-driven **v2** method in `app/research/mr002/n1/`,
  whose stack frame is named `_routed`, not `_routed_solve_qp`.
- **D-2.** The Aug-19 development census recorded `PIQP_P2` terminating with
  `ITERATION_LIMIT_REACHED` on 49 of 3,895 development instances while reporting
  `C2_full_resolution: true` — because Solver A certified 3,890 of 3,895, and the production-shape
  cascade never invokes the fallback where A certifies.
- **D-3.** Over the development corpus with B = `PIQP_P2`, the v1 seam and the v2 method produced
  **3,895 / 3,895 identical accepted points and zero disposition differences**.

No aggregate, cross-tabulation, or joint-event count over the per-instance census rows had been
computed at sealing time. Those are P1 analyses, governed by §5.

---

## 3. Data scope

### 3.1 Admissible (development domain only)

- The registered 3,895-instance Stage-3 development corpus, `.mr002out/n1/corpus.npz`, corpus hash
  `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
- The Aug-19 Gate-N1 development artifacts under `.mr002out/n1/`.
- Repository source at the sealed commit, and its Git history.
- Development-domain deterministic fixtures generated for plumbing.
- Reference Solver R (`app/research/mr002/n1/reference.py`) — development / qualification only.
- A deterministic synthetic / adversarial stress generator: **design and pre-registration only**
  (Aug-19 §5 — N1 may pre-register the N2 generator and seed; it may not consume stress results as
  qualification evidence).

### 3.2 Prohibited

- The consumed Validation-1 and Validation-2 materializations and any validation-derived QP,
  **including the archived custody copies**. They are evidence, not research corpora.
- Any OOS or holdout information.
- A/B/C economic parameter changes, cost changes, Stage-1 / Stage-2 changes, constraint changes.
- Historical-return-based Solver-B selection.
- Per-instance solver-profile changes and adaptive tolerance profiles.
- Any change to the acceptance predicate (`canonical_qualify`) or its registered limits made in
  response to an observed failure.

### 3.3 Named prohibition carried forward from the Validation-2 seal

Widening `NUMERICAL_ALLOWLIST` to swallow `PIQP_MAX_ITER_REACHED` **as a repair** is prohibited:
against the consumed population that is post-freeze accommodation. P1 may **analyse** the
classification consequence of the allowlist — that is precisely the evaluation-protocol question it
exists to answer — and may **recommend** a prospective disposition architecture for a future method
version. It may not present allowlist widening as a fix to Validation-2, and no P1 output re-opens
Validation-2.

---

## 4. Investigation tracks

| ID | Question | Method | Environment |
|---|---|---|---|
| **T1** | What exactly is the as-is Stage-3 architecture? | Static inventory of source, taxonomies, profiles, tolerances, exception→enum→disposition mappings, seams, and content identities. **No solver import.** | Any |
| **T2** | Is the numerical environment reproducible? | Reproduce `corpus.npz`, confirm the registered corpus hash, confirm `FROZEN_THREAD_ENV` (threads = 1, `OPENBLAS_CORETYPE=HASWELL`), confirm pinned image and dependency identity. | **Pinned research image required** |
| **T3** | How do the two disposition taxonomies classify the same development evidence? | Reclassify the already-collected Aug-19 per-instance census rows under (i) the v2 method rule as run and (ii) the v1 cascade rule as it would have applied. Report the joint event *A does not certify **and** B terminates*. Reanalysis of existing data; **no solver**. | Any |
| **T4** | What are the frequency, structure and correlates of generator termination on development? | Cross-tabulate termination reason against problem size `n` and against A's outcome. Report distributions, not aggregates. | Any for recorded fields; **image** for new fields |
| **T5** | Can the SA-1 candidate-equivalence bound be **derived** rather than calibrated? | Attempt the Aug-19 §2 duality-gap derivation: primal-feasible point plus dual-feasible multipliers give `f(x) − f* ≤ g = f(x) − q(λ)`; strict convexity `μ = 2/max tᵢ` gives `‖x_A − x_B‖ ≤ √(2g_A/μ) + √(2g_B/μ)`. Close or explicitly fail the feasibility qualifier. | Analysis: any. Numerical confirmation: **image** |
| **T6** | Which neutral response classes survive the evidence? | Enumerate: unchanged method plus a hard-stop policy; stronger certificates / equivalence proof; pre-solve conditioning or scaling; an alternative Solver B inside the two-generator architecture; a materially different architecture (requires supersession). Score under the lexicographic rule below wherever Solver-B selection is in scope. | **Image** |

**Lexicographic selection rule (Aug-19 SA-4)** — applied in this order and no other: zero integrity
defects → 100 % development certified resolution → agreement with Reference Solver R to the
preregistered or derived bound → deterministic reproducibility → runtime → dependency simplicity.

**Certificate primacy (Aug-19, unconditional):** the frozen acceptance certificate adjudicates; raw
solver status never does. A nominal solver success that fails the certificate is not a resolution.

---

## 5. Disposition decision rule — FROZEN

P1 emits **exactly one** label from this closed set (plan F6; a new label requires explicit owner
acceptance):

```
METHOD_UNCHANGED_PROTOCOL_CLARIFICATION_REQUIRED
METHOD_NUMERICAL_REVISION_REQUIRED
SOLVER_CASCADE_REVISION_REQUIRED
INSTANCE_CLASS_DECLARED_UNCERTIFIABLE
INSUFFICIENT_DEVELOPMENT_EVIDENCE
```

### 5.1 Admissibility precondition

A label other than `INSUFFICIENT_DEVELOPMENT_EVIDENCE` may be selected **only if all** of:

- **A-1** T1 complete, and the as-is manifest bound by content identity.
- **A-2** T2 complete: the development corpus reproduces to the registered hash under a confirmed
  deterministic environment. *A development conclusion drawn in an unreproduced environment is not
  evidence.*
- **A-3** T3 complete over the full 3,895-instance development record.
- **A-4** Every claim in the disposition record traceable to a named artifact identity.

If any of A-1…A-4 fails, the disposition is `INSUFFICIENT_DEVELOPMENT_EVIDENCE`, however suggestive
the partial evidence is.

### 5.2 Ordered predicates

Evaluated **in this order**; the first satisfied predicate is the disposition. Evidence may not be
re-run in order to reach a later label.

**P-1 → `INSTANCE_CLASS_DECLARED_UNCERTIFIABLE`** — satisfied only if **all** hold:

1. a class of instances is characterized by a **prospectively statable membership predicate over
   registered problem data alone** (no reference to any solver's behaviour on the instance);
2. on development members of that class, **neither** registered generator produces a certified
   candidate;
3. Reference Solver R, at development precision, **also** fails to produce a point satisfying the
   frozen acceptance predicate — the failure is a property of the instance and the frozen
   tolerances, not of the two production generators;
4. the class is non-empty on development.

*Why this is the strictest predicate: declaring an instance class uncertifiable asserts that the
frozen method is correct and the problem is not solvable to the frozen standard. Without (3) the
claim is indistinguishable from "our two generators are not good enough", which is P-2 or P-3.*

**P-2 → `METHOD_NUMERICAL_REVISION_REQUIRED`** — satisfied if the evidence identifies a defect in the
**registered problem's numerical presentation** (conditioning, scaling, presolve, or the SQRT
transformation) that is (i) uniform across instances, (ii) correctable without per-instance routing,
adaptive tolerances, or any change to the acceptance predicate, and (iii) demonstrably responsible
for generator termination on development.

**P-3 → `SOLVER_CASCADE_REVISION_REQUIRED`** — satisfied if the evidence shows the frozen A/B pair
fails to resolve a development instance that an admissible alternative generator resolves **under
the unchanged acceptance predicate and unchanged tolerances**, scored under the §4 lexicographic
rule. Selecting this label **restarts N1** under a new prospective selection record (Aug-19 §5) and
must say so.

**P-4 → `METHOD_UNCHANGED_PROTOCOL_CLARIFICATION_REQUIRED`** — satisfied if the evidence shows each
generator behaved **within its registered numerical contract**, and the failure to complete is
attributable to the **disposition / protocol layer**: how a legitimate generator termination is
classified, and what a governed run is required to do when an instance is legitimately unresolvable.
The P1 record must then state the specific protocol question left open, without proposing a change
to any numerical parameter.

**P-5 → `INSUFFICIENT_DEVELOPMENT_EVIDENCE`** — the default. Selected when no predicate above is
satisfied, or when §5.1 fails.

### 5.3 Anti-steering constraints

- No predicate may be satisfied by evidence generated **after** the analyst has seen that a
  different predicate failed, unless that evidence was already scheduled in §4.
- **P-4 may not be used as a residual "nothing else fit" answer.** It carries a positive
  requirement — a demonstration that the numerics stayed inside contract. Absent that
  demonstration the answer is P-5, not P-4.
- A disposition that would be materially different had a scheduled track been executed must say so
  in a `NOT_EXECUTED` section naming the track and its effect.
- The disposition record names the exact artifact identity of every input.

---

## 6. Supersession tripwires

Any of the following requires a named `SUPERSESSION_REQUIRED` item against the Aug-19 record
(`3e1e4915…`) and **stops that branch** pending an owner ruling. None may be implemented under this
protocol.

| Tripwire | Frozen prior violated |
|---|---|
| A third production generator | Aug-19 SA-4 — exactly two production generators, permanently |
| Any per-instance solver profile or adaptive tolerance | Aug-19 §5 prohibited list |
| Reference Solver R used as a production voter | Aug-19 §2 |
| A hand-picked or residual-assumed equivalence bound | Aug-19 §2 / SA-1 |
| Raw solver status used as an acceptance authority | Aug-19 certificate primacy |
| Substituting Solver B without restarting N1 | Aug-19 §0.1, §5 |
| Accepting "PIQP with more iterations" because the observed incident was `PIQP_MAX_ITER_REACHED` | Plan v1.0 §3.2, final bullet |

The last row is a standing tripwire, not a caution. Raising `max_iter` is a profile change; it is
motivated by an observation on the consumed population; and it would be adopted without any evidence
that the instance is solvable at the frozen tolerances at all. If P1 concludes that iteration budget
is the operative constraint, it must record that as a **finding requiring a prospective,
development-qualified profile decision under a restarted N1** — never as a repair.

---

## 7. Deliverables and their state

| Deliverable | State at protocol sealing |
|---|---|
| `MR002_P1_NumericalInvestigation_Protocol_v1.0` | **this document** |
| `MR002_P1_Stage3_AsIsManifest_v1.0` | T1 — produced in this work package |
| `MR002_P1_DevelopmentStatusCensus_v1.0` | T3 / T4 — reanalysis tranche produced in this work package; solver-dependent tranche pending environment |
| `MR002_P1_CertificateAndEquivalenceAnalysis_v1.0` | T5 — not started |
| `MR002_P1_CandidatePolicyComparison_v1.0` | T6 — not started |
| `MR002_P1_MethodDisposition_v1.0` | **blocked on A-2** (see §8) |
| `MR002_P1_Aug19_SupersessionRequest_v1.0` | emitted only if §6 fires |

---

## 8. Known environment blocker

`quadprog`, `piqp`, `clarabel` and `mpmath` are **not installed** in the working environment, and the
MR-002 evaluator host is **STOPPED**. Tracks T2, the numerical half of T5, and T6 therefore cannot
execute here, and admissibility condition **A-2 is unmet**.

Consequently **no P1 disposition may be selected until the pinned research environment is
available.** Any disposition asserted before A-2 is met would be `INSUFFICIENT_DEVELOPMENT_EVIDENCE`
by construction. This is the P1 critical path, recorded rather than worked around.

---

## 9. Stop conditions

- Accidental consumed-holdout access, by any path.
- Inability to reproduce the numerical environment (→ `INSUFFICIENT_DEVELOPMENT_EVIDENCE`).
- Unregistered adaptive tuning appearing anywhere in a proposed implementation.
- A proposed implementation contradicting a frozen prior without an explicit supersession ruling.
- Any P1 output being read as authorization for P2A, P3, a freeze, a registration, or an opening.

---

## 10. What this protocol does not authorize

P2A implementation; P3 economic work; any freeze; any registration; any holdout opening; any paper
or production activation; any change to a frozen numerical parameter; any Validation-2 re-opening.
No phase auto-authorizes the next.
