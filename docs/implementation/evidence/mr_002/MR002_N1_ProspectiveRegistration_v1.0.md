# MR-002 Stage-3 v2 — Gate N1 Prospective Registration v1.0 (DRAFT)

**Program:** MR-002 / SPQ-1 · **Gate:** N1 (DEVELOPMENT PROTOTYPE) · **Date:** 2026-08-19
**Authority:** `docs/design/MR002/MR002_Stage3v2_AdjudicatedMemo_v1_2.md` §5 (Gate N1 grant)
**Status:** DRAFT, **owner-reviewed and amended 2026-08-19** — not yet frozen.
**No N1 result may be produced until this record is sealed.**

---

## 0. Why this record exists and what it is not

SA-4 requires that the **candidate set, the profiles, the corpus and the selection rule are frozen
before results**. This record is that freeze. It also carries the §2 certificate/equivalence
specification, the Reference-Solver-R method, and the preregistered N2 stress-generator
specification and seed, because each of them is a *rule* whose credibility depends on it existing
before the numbers do.

This record **produces no results**, scores no candidate, and reads nothing outside the development
domain. It authorizes nothing: authority is the memo §5 grant, and its scope is N1 only.

It is written by the developer. The owner adjudication points remain the N1 verdict and Cycle 2C.

**Prior-evidence disclosure (SA-4 honesty condition).** A v1 bakeoff already exists on the same
corpus — `MR002_Stage3FallbackCandidateUniverse_v1.0.json` (revision 1.1) and
`MR002_Stage3FallbackSelection_Audit_v1.0.json`. Its per-candidate counts are known to the author of
this record. Two things keep the freeze meaningful:

1. The N1 selection rule below is **not derived from that evidence**. It is the lexicographic
   ordering the owner wrote into memo SA-4, fixed before any N1 result exists.
2. The v1 counts were produced under the **v1 acceptance predicate**. N1 re-scores every candidate
   under the specification in §3–§4, so no v1 count transfers. They are prior context, not N1
   evidence, and §7 forbids citing them as N1 evidence.

### 0.1 Owner review amendments (2026-08-19, applied before seal)

The draft was reviewed before any candidate was scored — the only moment at which these decisions
are still scientifically clean. Four amendments were directed and are applied throughout:

| # | Amendment | Where |
|---|---|---|
| 1 | **Equivalence proof is mandatory for `N1_ADVANCE`, but is not part of candidate acceptance.** `BOUND_UNAVAILABLE` is an intermediate evidence state, never a post-results escape hatch. Unresolved equivalence at final N1 adjudication is incompatible with `N1_ADVANCE` — `N1_STOP`, not owner discretion after seeing the numbers. | §3.3, §4.3, **§4.4 (new)**, §6, §7 |
| 2 | **`HIGHS_QPASM` stays excluded for N1 v1.0**, with the narrative corrected: it is the *B-candidate universe* that fails to diversify away from the demonstrated fallback failure family — Solver A is active-set, not interior-point. | §5.2 |
| 3 | **Exception provenance tightened.** `GENERATOR_INTERNAL_ERROR` as a blanket "any other Exception" is withdrawn. Provenance must be assigned mechanically; ambiguity blocks advancement. | §2.5, §2.2, §2.3 |
| 4 | **N2 axis A2 generalized** from a PIQP-specific `max_iter` stress to iterative-solver convergence burden, so the stress population is not structurally tailored to one implementation. | §8 |

The frozen principle behind amendment 3, stated once:

> **Generator numerical failure may be non-fatal; provenance ambiguity is not.**

v1 treated ordinary numerics as an integrity defect. v2 must not commit the mirror-image error of
treating an actual software defect as ordinary numerics.

The frozen principle behind amendment 1:

> **Solver correctness and proof that N1 preserved the economic method are different claims.**
> A candidate may be accepted without the second. MR-002 may not *advance* without it.

---

## 1. The defect N1 exists to remove

The 2026-08-19 12:49Z validation execution consumed the sealed opening and stopped with

```
Stage3Stop: INVALID_RUN: fallback integrity defect:
UNREGISTERED_EXCEPTION:RuntimeError:status Status.PIQP_MAX_ITER_REACHED
```

Disposition: **INTEGRITY_FAILURE**. No A/B/C gate numbers exist.

The mechanism is `stage3_cascade.normalize`. The v1 method decides eligibility from an **exact
exception-class/message allowlist** (`NUMERICAL_ALLOWLIST`), which holds exactly one entry, scoped
to `QUADPROG_SQRT`. Any other raise — from either generator — maps to `INTEGRITY_DEFECT`, and an
`INTEGRITY_DEFECT` in the fallback is `INVALID_RUN`, a stop.

PIQP reaching its frozen `max_iter = 1000` and raising is **a QP generator terminating without a
candidate**. It is not evidence that the model, the certifier, the mapping or the provenance is
defective. The v1 enum had no way to say that, so it said the strongest thing it could, and the
run died on a correct fail-closed reflex applied to a miscategorised event.

Memo SA-5 names the fix directly: `INCIDENT_CLASS_KNOWLEDGE` — *"a production QP generator can
terminate without a candidate"* — is **permitted knowledge**. The N1 architecture must be able to
express it.

⚠ **What N1 must not do about it.** `max_iter` is part of the frozen PIQP profile. Raising it, or
retuning any tolerance, after observing this failure is a **profile change** — prohibited by the
memo §5 prohibitions and by the cascade countersignature §5.1. If the incumbent Solver B cannot
meet the N1 criteria, the answer is a different candidate under §5.3, never a retuned one.

---

## 2. Candidate architecture — certificate-driven, two generators

### 2.1 The single principle

**A candidate is accepted because it carries a certificate, never because of how the generator
behaved.** The generator's exceptions, statuses, iteration counts and messages are *recorded* and
are never *routing inputs*. This inverts the v1 method, in which an exception string decided
eligibility.

### 2.2 Per-generator outcome enum (closed and total)

Applied independently to each generator on the identical canonicalized instance:

| Outcome | Meaning |
|---|---|
| `CERTIFIED` | The generator returned a contract-conforming `(z, lambda)` and the registered certifier's predicate is **true**. |
| `NO_CERTIFIED_CANDIDATE` | The generator did not produce a certified candidate, for a reason whose provenance is **mechanically assigned to the solver library** (§2.5): a registered terminal status; an exception raised inside the solver library; non-finite values in a correctly shaped return; or the certifier completed and the registered predicate is **false**. This is the SA-5 `INCIDENT_CLASS_KNOWLEDGE` class. |
| `SYSTEM_INTEGRITY_DEFECT` | A defect in the **system**, not in the generator's numerics: model-input contract violation; solver-identity / provenance failure; certifier fault or certifier-contract violation; the generator's return violating the *arity/shape/dtype* contract; **and any exception whose deepest owned frame is in our mapping, wrapper, certificate plumbing, or invariants** (§2.5). |

A `BaseException` that is not an `Exception` (`KeyboardInterrupt`, `SystemExit`, `GeneratorExit`)
propagates and is never normalized.

The v1 categories `NUMERICAL_STATUS_NONQUALIFICATION` and `CERTIFICATE_NONQUALIFICATION`, and the
*behavioural* half of v1 `INTEGRITY_DEFECT`, all collapse into `NO_CERTIFIED_CANDIDATE`. **The
exception allowlist is deleted, not extended.** There is no registered-message table to fall out of,
so there is no unregistered-exception class, so the 12:49Z failure mode cannot recur.

**The line between the two failure classes**, stated once so it is not re-litigated per case:
*shape is ours, values are the solver's.* A wrong-sized or non-numeric return means our mapping code
is wrong — a system defect. Non-finite entries of a correctly-shaped return are numerical behaviour
— no certified candidate.

### 2.3 The guard that collapsing the enum costs us, and how it is paid for

Collapsing the v1 categories removes a real alarm: under v1, a genuine wrapper bug that raised an
unexpected exception stopped the run. A naive collapse would turn it into `NO_CERTIFIED_CANDIDATE`,
covered silently by the other generator. **That is the mirror image of the v1 defect and is not
accepted here.**

Two mechanisms pay for it. The first is structural and acts at the instance; the second is a census
gate.

**Structural — provenance decides the class, not the message (§2.5).** An exception is assigned to
the solver library or to us by walking its traceback, not by reading its text. Only library-owned
exceptions are eligible for `NO_CERTIFIED_CANDIDATE`. Wrapper-owned exceptions remain
`SYSTEM_INTEGRITY_DEFECT` and still stop the run, exactly as they should.

**Census — ambiguity is counted and blocks advancement.**

- Every `NO_CERTIFIED_CANDIDATE` records a **reason code** drawn from the registered closed taxonomy
  (`REGISTERED_TERMINATION_REASONS`, §2.5).
- An exception whose provenance cannot be mechanically assigned, or a reason outside the taxonomy,
  is recorded verbatim as `UNREGISTERED_TERMINATION_REASON`. The instance still resolves — a
  fail-closed stop on an unfamiliar *message* is the defect N1 is removing — but the run-level census
  counts it.
- **N1_ADVANCE requires `UNREGISTERED_TERMINATION_REASON == 0` over the whole development corpus.**
  A non-zero count is an adjudication item, individually classified per SA-3, never an aggregate
  percentage.

So an unfamiliar *library* termination cannot kill a run mid-flight; an unfamiliar *wrapper* fault
still does; and anything the machine cannot attribute cannot pass unnoticed.

### 2.4 Run-level disposition (closed and total)

| Disposition | Condition | Consequence |
|---|---|---|
| `PRIMARY_CERTIFIED` | A is `CERTIFIED` | accept A's point; B not invoked (production mode) |
| `SECONDARY_CERTIFIED` | A is `NO_CERTIFIED_CANDIDATE`, B is `CERTIFIED` | accept B's point |
| `UNRESOLVED_INSTANCE` | neither generator is `CERTIFIED` | **STOP.** Classified individually (SA-3). |
| `INVALID_RUN` | any `SYSTEM_INTEGRITY_DEFECT` in either generator or in the model inputs | **STOP.** |
| `CERTIFIED_SOLUTION_DISAGREEMENT` | both `CERTIFIED` **and** `norm(z_A - z_B)` exceeds the §4 bound | **INTEGRITY_FAILURE** (SA-2) |

`CERTIFIED_SOLUTION_DISAGREEMENT` is per SA-2 and is **terminal**: no lower-objective pick, no
voting, no re-run with new settings. Two certificates asserting different minimizers of a strictly
convex program contradict uniqueness, which impugns the certification system itself.

In production the cascade invokes B only on A's `NO_CERTIFIED_CANDIDATE`, so both-certified cannot
arise there. It arises in N1 development qualification, where **both generators and R run on every
instance**. The disposition is registered for both modes so the rule is not invented later.

Exactly **two** production generators, permanently (SA-4). No third attempt, no jitter, no
per-instance routing, no eligibility by analogy.

### 2.5 Termination reasons and the mechanical provenance rule

#### 2.5.1 Terminal statuses are returned, never raised

Each generator wrapper translates its library's **terminal statuses** into an explicit
`GeneratorTermination(reason)` **return value**. It does not raise for them. This is the change that
makes provenance decidable: a status is data, and after this rule an exception escaping a wrapper is
an *unplanned* event by construction.

Registered reasons reachable this way (`REGISTERED_TERMINATION_REASONS`):

```
ITERATION_LIMIT_REACHED           library reports its frozen iteration budget exhausted
CONSTRAINTS_REPORTED_INCONSISTENT library reports the feasible region empty
NUMERICAL_BREAKDOWN               library reports a factorization / linear-algebra failure
NON_FINITE_CANDIDATE              correctly-shaped return containing inf / nan
CERTIFICATE_PREDICATE_FALSE       certifier completed; registered predicate false
LIBRARY_RAISED                    an exception whose deepest owned frame is inside the solver library
```

`CERTIFICATE_PREDICATE_FALSE` carries the failing predicate terms verbatim (e.g.
`stationarity_residual+kkt_residual`), so a certificate failure is never flattened to a single word.
`LIBRARY_RAISED` carries the exception class and the owning module.

There is **no** blanket `GENERATOR_INTERNAL_ERROR`. "Catch every `Exception` and downgrade it" is
withdrawn.

#### 2.5.2 Provenance is assigned by traceback ownership, never by message

For an exception that nonetheless escapes a wrapper, walk the traceback **from the deepest frame
outward** and take the first frame belonging to a **registered ownership domain**:

| Owning domain | Membership test | Class |
|---|---|---|
| **Solver library** | the frame's module resolves under a registered solver-library root: `piqp`, `clarabel`, `quadprog`, `highspy` (including their extension modules) | `NO_CERTIFIED_CANDIDATE`, reason `LIBRARY_RAISED` |
| **Ours** | the frame's module resolves under `app.research.mr002.*` or a registered wrapper/certifier module | `SYSTEM_INTEGRITY_DEFECT`, reason `WRAPPER_ORIGIN` |
| **Neither** | no frame in the traceback belongs to any registered domain, or the traceback is absent / unresolvable | `UNREGISTERED_TERMINATION_REASON` |

Three properties this buys, each deliberate:

- **Shared numeric libraries are transparent.** `numpy` and `scipy` are not ownership domains, so a
  `numpy` raise inside PIQP's Python layer resolves outward to `piqp` and is correctly the library's;
  a `numpy` raise inside our mapping resolves outward to us and is correctly ours.
- **The message is never read.** The v1 defect was routing on text. Provenance is structural.
- **Ambiguity is not silently resolved in anyone's favour.** An unattributable exception resolves
  the *instance* (so an unfamiliar event cannot kill a run mid-flight) but sets
  `UNREGISTERED_TERMINATION_REASON`, and §7 makes that incompatible with `N1_ADVANCE`.

A registered solver-library root list is part of the frozen configuration; adding to it after
observing a failure is a profile-class change and is prohibited on the same footing as §1.

---

## 3. Certificate specification

### 3.1 The acceptance predicate is unchanged

The acceptance authority stays the **single registered certifier** already in force —
`joint_portfolio._acceptance` KKT LIMITS plus the two-sided signed Lagrangian gap
(`app.research.mr002.certificate`, `SIGNED_GAP_MAX = 1e-10`, interval containment at
`IV_DPS = 100`, `MAX_INTERVAL_WIDTH = 1e-30`):

```
primal_residual          <= 1e-9
dual_residual            <= 1e-9
stationarity_residual    <= 1e-8
complementarity_residual <= 1e-8
kkt_residual             <= 1e-8
signed Lagrangian gap    whole interval within [-1e-10, +1e-10]
```

This is deliberate and load-bearing. The memo's objective is 100% admissible resolution **while
preserving the frozen Stage-3 economic solution**. The accepted point *is* the economic solution.
Changing the acceptance predicate would change which point is accepted, and the preservation claim
would have to be re-earned rather than held by construction. N1 changes the **disposition of
failures**, which is what broke; it does not change what "certified" means.

### 3.2 What is *added*: the equivalence certificate

Memo §2 asks that each candidate carry a **computable primal-dual gap** so the agreement threshold
is derived rather than inspected. Route (a) — the rigorous route — is already implemented in this
program and is adopted as-is:

- `certificate.py` supplies the rigorous **dual lower bound** `d(lambda_bar)`, valid for any
  `lambda_bar` with `lambda_bar[meq:] >= 0` by weak duality, independent of stationarity, in
  outward-rounded interval arithmetic over exact binary rationals.
- `repair.py` (profile R2) supplies the **feasibility qualifier**, which is where §2 says rigor is
  won or lost: an **exactly feasible rational point** `zhat_s`, proved by exact absorber enumeration
  and exact verification against the **original, untightened** constraints.
- Hence `Ghat_s = f(zhat_s) - d(lambda_bar_s) >= 0` rigorously (weak duality at an exactly feasible
  point), and strong convexity with `mu = 2 / max_i t_i` gives

```
norm(zhat_s - z*)  <= sqrt(2 * Ghat_s / mu)
norm(z_s   - z*)   <= delta_s + sqrt(2 * Ghat_s / mu) =: R_s
                      delta_s = norm(z_s - zhat_s), outward-rounded
```

This is memo §2's inequality with its feasibility qualifier discharged by exact arithmetic rather
than assumed. `mu` matches the memo's `2/max target_i` exactly (`repair.certify_repair`, `m_iv`).

### 3.3 The equivalence certificate is required evidence, not an acceptance gate

An accepted candidate must carry its equivalence certificate **where one is obtainable**. Where the
exact repair cannot be constructed, `repair.py` returns `REPAIR_CERTIFICATE_UNAVAILABLE` — the
equality correction can exceed the available absorber slack, and the module correctly refuses to
retry quietly.

Registered rule (owner amendment 1):

- `REPAIR_CERTIFICATE_UNAVAILABLE` is **not** an acceptance failure and **not** an integrity
  defect. The instance resolves on the §3.1 predicate. A candidate can be `CERTIFIED` without it.
- It **is** recorded per instance, and the count and the full per-instance list appear in the N1
  census. SA-3 forbids an aggregate percentage that hides the tail.
- It **is** decisive wherever an agreement question is actually asked: if a pair needs the bound and
  either side lacks its certificate, the pair is `BOUND_UNAVAILABLE` (§4.3), never "assumed to
  agree".
- It is **never** a route to `N1_ADVANCE` without equivalence evidence. The preservation claim is
  gated separately and unconditionally by **§4.4**.

**The distinction being preserved.** *Solver correctness* and *proof that N1 preserved the economic
method* are different claims with different evidence. Folding the second into the acceptance
predicate would push resolution below 100% for reasons unrelated to generator correctness, working
against the N1 objective. Dropping it entirely would let `BOUND_UNAVAILABLE` become a post-results
escape hatch. §4.4 is the middle rule: acceptance stays clean, advancement does not.

---

## 4. Equivalence rule (SA-1 final form)

### 4.1 The bound

For two certified points `z_1`, `z_2` on the same instance, with repair certificates `r_1`, `r_2`:

```
norm(z_1 - z_2) <= R_1 + R_2 + AGREEMENT_SLACK,     AGREEMENT_SLACK = 1e-10
```

with the left-hand side itself evaluated at an **upper** endpoint from exact rationals
(`repair.agreement`). The companion objective test
`|f(z_1) - f(z_2)| <= U_1 + U_2 + OBJECTIVE_SLACK` (`repair.objective_agreement`) is recorded
alongside.

### 4.2 Provenance of every constant

Nothing in §4.1 is chosen by inspection, which is SA-1's whole point:

| Quantity | Origin |
|---|---|
| `R_s = delta_s + sqrt(2*Ghat_s/mu)` | **derived** — weak duality + strong convexity + exact feasibility |
| `mu = 2 / max_i t_i` | **structural** — `lambda_min(H)` for `H = diag(2/t)` |
| `AGREEMENT_SLACK = 1e-10` | **inherited**, already frozen in `repair.py` before N1; recorded as pre-existing, not newly picked |
| `OBJECTIVE_SLACK` | **inherited**, same provenance |

No validation information enters any of them. Route (b) — prospective calibration against R — is
**not** used for the bound itself, because route (a) closes. Route (b) survives only as §4.3's
per-instance handling.

### 4.3 When the bound cannot be formed

If either side lacks a repair certificate, the pair is `BOUND_UNAVAILABLE`. It is **never** silently
treated as agreement and **never** replaced by a hand-picked threshold. Such pairs are listed
individually in the census.

`BOUND_UNAVAILABLE` is an **intermediate evidence state only**. It is not a terminal disposition, and
it is not deferred to discretion at the verdict. Every instance in it must be resolved by §4.4
before N1 can advance.

### 4.4 The equivalence gate — mandatory for `N1_ADVANCE`

**Required population.** Every instance in the registered 3,895-instance corpus for which **the v1
method produced an accepted point** (disposition `PRIMARY_QUALIFIED` or `FALLBACK_QUALIFIED`). The
census establishes the exact set; under the recorded governed development qualification it is the
whole corpus.

**Provenance of the v1 points.** `z_v1` is regenerated by executing the **v1 method** on the same
frozen corpus in the same pinned image. The regeneration must reproduce the recorded v1 dispositions
exactly; a mismatch is a `SYSTEM_INTEGRITY_DEFECT` and stops N1. Equivalence is never asserted
against a remembered number.

**This comparison is not the SA-2 comparison.** §2.4's `CERTIFIED_SOLUTION_DISAGREEMENT` compares
**A against B** on one instance. §4.4 compares **v2-accepted against v1-accepted**. Two different
questions, two different pairs, both required.

**Establishment routes, applied in order.** The first that succeeds settles the instance:

| Route | Condition | Result |
|---|---|---|
| **E0 — identity** | `z_v2` is byte-identical to `z_v1` | `EQUIVALENCE_TRIVIAL` |
| **E1 — derived bound** | both points carry repair certificates and `norm(z_v1 - z_v2) <= R_v1 + R_v2 + AGREEMENT_SLACK` | `EQUIVALENCE_PROVEN_BOUND` |
| **E2 — exact reference** | `R_EXACT` is available; `rho_s` substitutes the exact `d_s = norm(z_s - z*)` for any side lacking a repair certificate, and `norm(z_v1 - z_v2) <= rho_v1 + rho_v2 + AGREEMENT_SLACK` | `EQUIVALENCE_PROVEN_R` |
| **E3 — neither** | no route establishes it | **`EQUIVALENCE_UNPROVEN`** |

E2 is rigorous, not a weaker substitute: because the program is strictly convex, `z*` is **unique**,
and `R_EXACT` supplies each side's error exactly. An exact distance is a *tighter* radius than the
derived `R_s`, not a looser one. E2 is exactly the memo's instruction to *"use exact Reference Solver
R if available to establish the equivalent unique solution."*

**The gate.**

> **Any `EQUIVALENCE_UNPROVEN` instance in the required population means `N1_STOP`.**

Not owner discretion after seeing the numbers. Not a deferred adjudication item. Not an exception
granted because the count is small. This is registered now, before any number exists, precisely so it
cannot be renegotiated later.

**No ceiling relief.** If E2 fails because R hit a frozen resource ceiling, the ceiling is **not**
raised for that instance. §6's ceilings are operational stop limits, and raising one after observing
the instance it stopped on is the same class of act as retuning a solver profile after observing a
failure (§1).

---

## 5. Solver A / Solver B selection

### 5.1 Fixed inputs

- **Solver A (primary), fixed, not under selection:** `QUADPROG_SQRT`.
- **Corpus:** the immutable 3,895-instance Stage-3 development corpus,
  `corpus_hash = 1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`, regenerated
  deterministically by replaying configs A, B, C over the development window
  **2013-01-02 … 2019-10-02** from `apps/backend/data/mr002_research.duckdb`. The hash is
  re-verified at N1 execution start; a mismatch **aborts N1** before any candidate is scored.
- **Runtime:** the pinned research image `mr002-research:v1.4`, `--network=none`, under the
  registered `FROZEN_THREAD_ENV` (`OMP/OPENBLAS/MKL/NUMEXPR_NUM_THREADS=1`,
  `OPENBLAS_CORETYPE=HASWELL`). An unset thread variable is not frozen; a green small-fixture suite
  is not evidence the environment is right.
- **Boundary:** development domain only. The consumed validation DuckDB (`c4cabab2…`), any
  validation-derived QP, and OOS are out of scope and unread. Historical returns may not influence
  selection.

### 5.2 Frozen candidate set

Bounded by the pinned image, so that no candidate can force a new dependency or a new image:

| Profile | Family | Admissible as B? | Basis |
|---|---|---|---|
| `PIQP_P1` | interior-point (proximal) | **yes** | distinct from active-set A |
| `PIQP_P2` | interior-point (proximal) | **yes** | distinct from active-set A |
| `CLARABEL` (QP-form) | interior-point (conic, QP-form) | **yes** | distinct; valid primal+dual under the common certifier |
| `QUADPROG_RAW` | active-set (quadprog) | no | not algorithmically distinct from A |
| `QUADPROG_TSCALED` | active-set (quadprog) | no | not algorithmically distinct from A |
| `HIGHS_QPASM` | active-set | no | not algorithmically distinct from A |

Admissibility gate C0 (all conditions, inherited from the v1 admissibility ruling): algorithmically
distinct from A · exactly one globally fixed configuration · valid primal **and** dual mapping under
the common certifier · deterministic · canonically shuffle-invariant · no per-instance adjustment ·
present in the pinned image.

Two declarations, so neither is a silent choice:

- The retired **exact-conic Clarabel experiment** (commit `18c55f5`, invalid dual transformation) is
  not a candidate and is not evidence about the admissible QP-form profile.
- **`HIGHS_QPASM` remains excluded for N1 v1.0** (owner amendment 2). The precise statement, because
  the earlier draft's wording invited a false inference:

  > The observed validation failure occurred in the v1 **interior-point fallback**, PIQP. All
  > currently admissible Solver-B candidates are also interior-point or conic-interior-point
  > implementations, so the **B-candidate universe** does not diversify away from the demonstrated
  > fallback failure family. `HIGHS_QPASM` would add an independently implemented active-set
  > candidate, but admitting it would change the inherited C0 requirement that B be algorithmically
  > distinct from the **active-set** Solver A. That admissibility rule is **not reopened in N1
  > v1.0**.

  ⚠ **Solver A is active-set, not interior-point.** A and B do not share the demonstrated failure
  family; it is the *set of available B candidates* that is undiversified. Any future reader taking
  the earlier phrasing to mean `QUADPROG_SQRT` is an interior-point method would be wrong.

  **Why it is not reopened now.** Broadening the candidate universe in response to the specific
  observed failure family would be using the consumed validation incident to reshape N1's frozen
  inputs. SA-5 permits incident-class knowledge for *hardening* — so that knowledge goes into the N2
  stress design (§8), not into widening N1's candidate set. Three pre-existing B candidates plus an
  active-set A are enough to answer N1's first question cheaply.

  **And if none passes C1–C4: `N1_STOP`.** Not "then add HiGHS". §5.3 already forbids widening after
  results, and this is the case it was written for. If active-set implementation diversity is later
  judged an architectural hypothesis worth testing on its own merits, that is a **new prospective N1
  registration**, not an amendment made after seeing this N1's scores.

### 5.3 The selection rule (SA-4, lexicographic)

Each admissible candidate `B` is evaluated as the pair `(A = QUADPROG_SQRT, B)` over the full
corpus. Criteria are applied **in order**; a later criterion is consulted only among candidates tied
on every earlier one.

| # | Criterion | Pass condition |
|---|---|---|
| C1 | **zero integrity defects** | `SYSTEM_INTEGRITY_DEFECT == 0` over the corpus, both as the paired cascade and standalone |
| C2 | **100% dev-corpus certified resolution** | 3,895 / 3,895 instances end `PRIMARY_CERTIFIED` or `SECONDARY_CERTIFIED`; zero `UNRESOLVED_INSTANCE`, zero `INVALID_RUN` |
| C3 | **agreement with R** | zero agreement violations against Reference Solver R on the R-available subset, and zero `CERTIFIED_SOLUTION_DISAGREEMENT` between A and B |
| C4 | **deterministic reproducibility** | two independent runs in the pinned image produce byte-identical accepted `z` and identical dispositions; canonical shuffle-invariance holds |
| C5 | **runtime** | lower total corpus wall-clock wins |
| C6 | **dependency simplicity** | fewer / lighter dependencies wins |

C1–C4 are **hard gates**: a candidate failing any of them is eliminated, not ranked. C5 and C6 are
orderings among survivors.

**A tie surviving C6 is an owner adjudication item.** There is no seventh tiebreak, no coin flip and
no undocumented preference. Registering this now is what stops a rule from being invented after the
numbers are visible.

If **no** admissible candidate passes C1–C4, the disposition is **N1_STOP**. It is not an
invitation to retune a profile (§1) or to widen the candidate set after seeing results.

### 5.4 Authority boundary

N1 selects **exactly one** Solver B and freezes the A/B pair using development evidence only. N2
qualifies that fixed pair on the preregistered synthetic stress population and may PASS or STOP;
**N2 may not substitute a solver.** Any substitution restarts N1 under a new prospective selection
record.

---

## 6. Reference Solver R

**Role.** R establishes numerical truth on development and stress instances. R is **never** a
production generator, **never** a third voter in the cascade, and **never** consulted on any
validation instance. The prohibition is enforced in code by a module-level guard, not by convention.

**Method.** R is an **exact-rational primal active-set QP solver** on the registered canonical form

```
minimise    f(z) = 1/2 z'Hz + q'z + c        H = diag(2/t), q = -2*1, c = sum(t)
subject to  C'z >= b                          first meq rows equalities, remainder lambda >= 0
```

All arithmetic in `fractions.Fraction`; every comparison, ratio test and pivot exactly decidable, so
there is no tolerance anywhere in R. R reuses the canonical machinery already proven in this program
— `exact_simplex.py` (Bland's rule over canonical identities, deterministic, no float in the proof
path) for the feasibility / active-set work, and the `certificate.py` / `repair.py` convention of
ingesting every frozen IEEE-754 input through its exact binary rational (`as_integer_ratio`, never
`str()`).

**R returns exactly one of:**

- `R_EXACT` — the exact minimizer `z*` as a rational vector, with an exact KKT certificate:
  stationarity exactly zero, exact primal feasibility, exact `lambda >= 0`, exact complementarity.
- `R_UNAVAILABLE` — a frozen resource ceiling was reached. Ceilings mirror `exact_simplex.py` and are
  **operational stop limits, not mathematical tolerances**; they may not be raised after observing a
  stopped instance without a new adjudication.

**Handling `R_UNAVAILABLE` (SA-3).** The **C3 selection criterion** is evaluated on the R-available
subset. The unavailable subset is reported with its **full per-instance list**, individually
classified — never as an aggregate percentage. A large unavailable subset is itself an N1
adjudication item, because a weak reference weakens C3.

⚠ **`R_UNAVAILABLE` cannot weaken the preservation gate** (owner amendment 1). R may be unavailable
*operationally*; equivalence may not be unavailable *logically* if N1 wants to advance. The two
cases compose exactly as §4.4 states:

- repair bound unavailable, R exact → E2 proves equivalence → fine;
- R unavailable, repair bound available → E1 proves equivalence → fine;
- **both unavailable → `EQUIVALENCE_UNPROVEN` → `N1_STOP`.**

No ceiling is raised after seeing the instance that stopped on it.

**What agreement with R means.** Because `z*` is exact, `norm(z_s - z*) <= R_s` is a rigorous,
one-sided statement per certified point. C3 tests exactly that, using the §4 radius — the same
derived quantity, not a second threshold.

---

## 7. N1 outputs and disposition

Exhaustive, per memo §5:

1. candidate architecture — §2
2. N1-selected and frozen Solver A/B profiles — produced by §5.3
3. Reference-Solver method — §6
4. certificate specification — §3
5. equivalence rule — §4
6. full development census — 3,895 rows, every instance carrying its per-generator outcome, reason
   code and provenance domain, disposition, certificate fields, repair-certificate availability,
   R comparison, and its §4.4 equivalence route and status
7. difference-vs-v1 report — every instance where the v2 method's accepted point or disposition
   differs from the v1 method's, with the economic consequence stated
8. preregistered N2 stress-generator specification and seed — §8 (specification only; **N2 results
   are not consumed by N1**)

**Disposition:** `N1_ADVANCE` or `N1_STOP`.

`N1_ADVANCE` requires **all** of:

1. a candidate passing C1–C4;
2. `UNREGISTERED_TERMINATION_REASON == 0` over the whole development corpus (§2.3, §2.5);
3. zero `CERTIFIED_SOLUTION_DISAGREEMENT` (§2.4);
4. **`EQUIVALENCE_UNPROVEN == 0` over the §4.4 required population, and zero instances left in
   `BOUND_UNAVAILABLE`** — the preservation gate, not subject to discretion;
5. the corpus hash re-verified;
6. SA-3's frozen words satisfiable — *100% of the registered development population ends in a
   preregistered admissible state; previously accepted v1 instances return equivalent certified
   allocations; residual unresolved instances individually classified.*

Condition 4 is what makes condition 6's middle clause *provable* rather than asserted.

`N1_STOP` closes MR-002 without a further validation/governance cycle.

`N1_ADVANCE` freezes the A/B pair and **authorizes nothing beyond N1.** N2 requires its own grant.

**Citation discipline.** No N1 output may cite the v1 bakeoff counts as N1 evidence (§0).

---

## 8. N2 synthetic stress generator — preregistered specification

Designed and frozen in N1; **run in N2, under N2's own grant.** N1 uses development-domain fixtures
only to test generator plumbing and does not consume the stress population as qualification
evidence.

**Determinism.** `numpy.random.Generator(numpy.random.PCG64(seed))`, one generator instance,
instances emitted in index order, no reliance on dict/set iteration order, no wall-clock or hostname
input. Regenerating from the seed must reproduce the population **byte-identically**; the population
hash is recorded at generation and re-verified before use.

**Registered seed:** `20260819` — a fixed constant, frozen by this record.

**Structural contract.** Every emitted instance conforms to the registered Stage-3 input contract:
`t > 0` elementwise · `meq == 1` (the structural precondition `repair.assert_structure` enforces) ·
box `0 <= z <= u` · finite `A_ub`, `b_ub`, `A_eq`, `b_eq`, `upper` · `kappa(H) <=
HESSIAN_CONDITION_MAX = 1e10`. An instance violating the contract is a generator bug, not a stress
case, and is rejected at generation.

**Stress axes and strata** — each axis targets a mechanism that has actually failed or is
structurally fragile in this program, not a generic "hard QP":

| Axis | Mechanism stressed | Stratum |
|---|---|---|
| A1 Hessian conditioning | `kappa(H) = max t / min t` swept toward the 1e10 ceiling | log-spaced decades 1e2 … 1e10 |
| A2 iterative-solver burden | **convergence stress**, implementation-agnostic: high dimension, dense constraints, many near-active rows. Designed using permitted SA-5 `INCIDENT_CLASS_KNOWLEDGE`; **no parameter is taken from the consumed validation instance.** | wide `n`, dense `A_ub`, high near-active fraction |
| A3 constraint tightness | near-degenerate rows, slack approaching `ETA = 1e-12` | slack decades 1e-6 … 1e-13 |
| A4 equality-slack scarcity | the **repair absorber** — the known `REPAIR_CERTIFICATE_UNAVAILABLE` mechanism | equality coefficients spanning many magnitudes against tight box slack |
| A5 active-set size | active-set enumeration cost in A and in R | fraction of rows active swept 0 … 1 |
| A6 structurally empty rows | the all-zero-coefficient `A_ub` row path (retained in exact verification, omitted from the numerical proposal) | present / absent |
| A7 boundary optima | optimum pinned at box bounds, where R1-style projection provably failed | coordinates at 0 and at `u` |
| A8 problem size | wide-`n` scaling | `n` across the development range and above it |

**Axis A2 is deliberately not tailored to one implementation** (owner amendment 4). It stresses
*convergence burden*, which every iterative method has, rather than PIQP's particular `max_iter`
knob — the A/B pair N1 freezes might select CLARABEL, and a stress population shaped around one
vendor's iteration counter would qualify it dishonestly. **Each candidate profile retains its own
frozen registered limits under stress:** the PIQP profiles keep `max_iter = 1000`, and every other
profile keeps whatever its registered configuration specifies. Stress changes the *instances*, never
the *profiles*.

Population size, per-axis instance counts, and the exact parameter ranges are frozen in the
companion JSON record (`n2_stress_generator.strata`), so the population is fully determined by
(seed, record).

**N2 rule.** N2 qualifies the **N1-frozen** A/B pair at **100% registered resolution or STOP**
(SA-3 frozen words for stress). N2 may **not** substitute Solver B. N2 additionally reports
reproducibility: an independent regeneration and re-run producing identical dispositions.

---

## 9. What this record does not touch

- No A/B/C parameter, cost, constraint, or Stage-1 / Stage-2 change.
- No Validation-2 design decision. VA-1 sample design, VA-2 merge mechanics, VA-3 accrual
  infrastructure and the untouched-sample definition all sit behind **N3**, at Cycle 2C.
- No sealed or reference byte is read. The consumed opening stays consumed; no replacement opening
  is requested, implied, or needed by N1.
- No OOS. OOS remains NOT AUTHORIZED.

---

## 10. Sealing

This record is DRAFT. Sealing requires: owner acceptance, commit, **push**, and re-derivation of the
record identity from **pushed Git blobs** (per the governance-hash rule — identities derived from a
Windows working tree carry CRLF and fail-close against an LF deploy).

**No N1 candidate may be scored before this record is sealed.**
