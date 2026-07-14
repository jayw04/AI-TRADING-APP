# MR-002 v1.1 — R2 sample A STOPS: the proposal solver reports a FALSE infeasibility

**Date:** 2026-07-13
**Status:** 🛑 **STOPPED FOR ADJUDICATION** — `REPAIR_CERTIFICATE_UNAVAILABLE` on 50/50 of
regression sample A (ruling §7, §10, §16)
**Sample B:** **NOT RUN.** A failed, so §13 forbids proceeding. The B container was stopped
mid-scoring and produced no artifact.

**Nothing was changed after the stop.** η was not modified. No alternate proposal solver was
substituted. No multi-coordinate repair was introduced. The exact constructor, the two-sided gate,
the solver profiles, the cascade order, the tolerances and the objective are all untouched.

> **DIAGNOSTIC ONLY.** No performance computed, printed or persisted. Preflight and the development
> run remain **STOPPED**. Validation and sealed OOS remain **sealed and unread**.

---

## 1. Result

| | |
|---|---|
| repair certificates obtained | **0 / 50** |
| reason code, all 50 | `TIGHTENED_PROPOSAL_NOT_OBTAINED` |
| underlying error, all 50 | `quadprog ValueError: constraints are inconsistent, no solution` |
| exact constructor invocations | **0** — it never ran |

Everything upstream of the repair still passed: corpus hash reproduced exactly, two-sided cascade
unresolved = 0, zero identity violations, worst interval width 1.61e-100.

**The failure moved.** Under R1 the constructor ran and correctly rejected candidates. Under R2 the
constructor is never reached, because the *proposal* solver refuses the tightened problem.

---

## 2. Root cause: the tightened set is NOT empty — quadprog is wrong

An independent LP feasibility test (HiGHS, used **only** to answer "is the set empty", never as a
proposal) on the R2 tightened constraints:

| | |
|---|---|
| tightened set **feasible** per independent LP | **12 / 12** |
| original set feasible per LP | 12 / 12 |
| quadprog on the **same** tightened problems | `constraints are inconsistent` — **6 / 6** |

**η is not too large. The tightened formulation is not infeasible. The proposal solver is
reporting a FALSE INFEASIBILITY** — the identical Goldfarb–Idnani mode that defeats
`QUADPROG_SQRT` on its five registered instances, now striking the proposal path.

### Why it strikes here and not on the untightened problem

The accepted Stage-3 point sits on a **highly degenerate vertex**: typically **16 of 18** nonzero
inequality rows carry slack below η, with the minimum slack *negative* at ~−1e-17 (the same
tolerance-feasibility that killed R1). Tightening every one of those near-active rows by η pushes
the active-set method straight into a rank-deficient working set, and Goldfarb–Idnani answers
"inconsistent" rather than "degenerate".

So the two failures share one origin: **the solution lives on the boundary, against many
simultaneously-active constraints.** R1 died because the exact constructor had no slack to absorb
into. R2 dies because the active-set proposal solver cannot navigate the tightened boundary.

---

## 3. What this does NOT mean (ruling §10)

* It is **not** a Stage-3 solver invalidation. The primary and fallback qualify normally.
* It is **not** evidence of economic infeasibility — the LP finds the tightened set feasible.
* It is **not** permission to revert to the R1 proposal, to change η, or to introduce a
  multi-coordinate repair.

---

## 4. What I am asking for

**Authorize a different proposal solver for R2.** §7 binds the proposal path to one frozen
deterministic solver and forbids trying another after a failure, so I have not.

The proposal is **non-evidentiary**: exact rational verification against the original untightened
constraints remains the sole feasibility authority, and it is unchanged. Substituting the proposal
solver therefore changes nothing that constitutes evidence — it only determines whether the
constructor is handed an interior point at all.

Candidates, all already pinned in the frozen image (no new dependency, no image rebuild):

| solver | family | note |
|---|---|---|
| **HiGHS** (`scipy.optimize`) | simplex / IPM | already demonstrated to solve the tightened set on 12/12 |
| Clarabel | interior-point | already a registered offline verifier |
| PIQP | proximal interior-point | already the adjudicated Stage-3 fallback |

**Recommendation: an interior-point method, not another active-set one.** The failure mode is
specific to active-set navigation of a degenerate boundary, and the tightened problem is *designed*
to have an interior — which is exactly what an interior-point method is built to find. Choosing
another active-set solver would reproduce the defect.

If you authorize this, the replacement must be frozen and hashed before execution exactly as R2 was
(solver, settings, thread configuration, status rules, package hashes), and sample A must be rerun
from the beginning.

---

## 5. Sample B record — the fields you asked for

Sample B did not run, so no record is claimed. When it does, its immutable record will bind, before
execution:

* **selection algorithm and sort convention**, stated unambiguously: *the qualifying overlaps not
  in sample A, ordered by **ascending lowercase SHA-256 hexadecimal** of the instance content hash,
  first 100 taken.* (Your point is well taken — "content-hash order" alone would let a different
  implementation select a different sample while claiming the same rule.)
* eligible-overlap **population hash**
* sample-A **exclusion list**
* the selected **content hashes**
* **sample size**
* two-sided **qualification-module hash**
* **R2 repair-module hash**
* **proposal-solver / configuration hash**
* **η** as exact rational, submitted IEEE-754 float, and hex
* **image digest**

---

## 6. Interpretation rules acknowledged

* A repaired result may differ from R1 — expected, and not a defect.
* The underlying **Stage-3 solver outputs are unchanged**: the primary's five nonqualifications and
  the zero-unresolved cascade are identical across the R1 and R2 runs.
* Every R2 repair must pass **exact original-set membership** — not merely show that tightening
  removed the prior ~1e-17 violations. The fixture
  `test_exact_verification_uses_the_ORIGINAL_constraints_not_the_tightened_ones` pins this: a point
  lying exactly *on* an original bound is accepted, so the certificate covers the full original
  feasible set rather than the narrower tightened one.

---

## Artifacts

| artifact | sha256 |
|---|---|
| `runtime/MR002_R2_RegressionSampleA.json` | `4806a0f55bc15e058a227f3ac147f78c109217c61adc88b13fc1541133f15793` |
| `runtime/MR002_R2_Infeasibility_Diagnosis.json` | `d13d7a1c868a4d1e1007c57d34262cff73daae3175e62da73d751a80965fc561` |
| `app/research/mr002/certificate.py` (two-sided gate, unchanged) | `8d25740ee8318af26167805898762d4e48b029f93283eff57db7b6b922b76b76` |
| `app/research/mr002/repair.py` (R2) | `79e446ebd5cb54b0f1cc9dd7552913def809d294c3e3998df558c25b4386e6b7` |

**Fixtures:** 44/44 pass (the 32 retained + the twelve §12 amendments).
**Image:** `mr002-research:v1.4`, `sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`.
**Erratum:** remains **undrafted**. All prior artifacts preserved unmodified.
