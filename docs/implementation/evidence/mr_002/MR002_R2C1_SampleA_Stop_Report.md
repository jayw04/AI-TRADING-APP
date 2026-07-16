# MR-002 v1.1 — R2-C1 sample A STOPS: no η works with either authorized proposal solver

**Date:** 2026-07-13
**Status:** 🛑 **STOPPED FOR ADJUDICATION** — 40/50 `REPAIR_CERTIFICATE_UNAVAILABLE` (ruling §13)
**Sample B:** **NOT RUN** (§11 bars it until A passes).

**Nothing was changed after the stop.** η is unchanged at 1e-12. The tolerances are unchanged. No
alternate proposal solver was substituted into the frozen path. No multi-coordinate repair was
introduced. The exact constructor, the two-sided gate, the solver profiles, the cascade order and
the objective are untouched.

> **DIAGNOSTIC ONLY.** No performance computed, printed or persisted. Preflight and the development
> run remain **STOPPED**. Validation and sealed OOS remain **sealed and unread**.

---

## 1. Result

| | |
|---|---|
| repair certificates obtained | **10 / 50** (quadprog R2 obtained 0/50) |
| `REPAIR_CERTIFICATE_UNAVAILABLE` | 40 |
| Clarabel statuses on the failures | `AlmostSolved`, `InsufficientProgress`, `NumericalError`, `AlmostPrimalInfeasible` |

Everything else passed. Corpus hash reproduced exactly; two-sided cascade unresolved = 0; zero
identity violations; worst interval width 1.61e-100. **Where a repair was obtained, both agreement
gates passed** — radius 0 violations (worst `dz/bound` 7.68e-06), objective 0 violations (worst
ratio 1.46e-04), worst repair distance 6.16e-08, worst repaired gap 2.91e-08.

The mechanism works. It cannot be *fed*.

---

## 2. Root cause: η is squeezed between two walls, and there is no gap between them

Measured over 20 qualifying overlaps. `REPAIRED` is the only column that decides anything — the
**unmodified** exact constructor certifying membership in the **original untightened** set.

| η | Clarabel status | its own inequality residual | REPAIRED | LP oracle: is the tightened set feasible? |
|---|---|---|---|---|
| 1e-12 | Solved 20/20 | **2.87e-12 — larger than η** | 10/20 | feasible 20/20 |
| 1e-11 | Solved 18/20 | **1.45e-11 — larger than η** | 6/20 | feasible 20/20 |
| 1e-10 | **`PrimalInfeasible` / `AlmostPrimalInfeasible`** | — | 0/20 | **feasible 20/20** |
| 1e-9 | **`PrimalInfeasible` / `AlmostPrimalInfeasible`** | — | 0/20 | **feasible 20/20** |
| 1e-8 | **`PrimalInfeasible` / `AlmostPrimalInfeasible`** | — | 0/20 | **feasible 19/20** |
| 1e-7 | `PrimalInfeasible` | — | 0/20 | infeasible 0/20 |

**Below 1e-10:** Clarabel converges, but the point it returns violates the tightened constraints by
*more than η*. The original-set slack the tightening was supposed to buy is `η − r_ineq`, which is
**negative**. The tightening is annihilated by the solver's own attainable accuracy.

**At 1e-10 and above:** Clarabel emits a **false infeasibility certificate** on sets the LP proves
are feasible — the same failure quadprog produced, in a different guise.

So the usable η must simultaneously exceed the proposal solver's residual floor (~3e-12) and stay
below the η at which that solver starts hallucinating infeasibility (~1e-11). **Those two walls have
closed.** No η works, and tightening the tolerance does not help — it only stops convergence
(at tol 1e-14, Solved = 0/20 under every regularization variant tried).

### Why my "static regularization" hypothesis was wrong

I suspected the imported regularization values (`static_regularization_constant = 1e-8`, frozen
against the ill-conditioned Stage-3 Hessian `diag(2/t)`) were inappropriate for the identity-Hessian
projection. Tested at 1e-12, 1e-14, and disabled: **Solved = 0/20 in every case.** The hypothesis is
dead; the residual floor is not a regularization artifact.

---

## 3. What I am NOT claiming

I probed HiGHS QP as a possible proposal solver. It reported `kOptimal` 20/20, **but with residuals
proportional to η itself** (`r_eq` = 1.00e-12 / 1.00e-11 / 1.00e-10 as η varied; `r_ineq` = 3.7η).
A residual that scales exactly with the tightening is the signature of the tightening not reaching
the solver — **a defect in my probe wrapper, not a verdict on HiGHS.** I am recording it as
**inconclusive** and drawing no inference from it. The artifact is retained so the claim can be
checked, not relied upon.

---

## 4. The structural conclusion

Every proposal solver available in the frozen image has an attainable accuracy on this geometry
that is **comparable to or worse than the tightening the exact constructor needs**, and two of them
manufacture false infeasibility certificates on it. That is not a tuning problem. The accepted
Stage-3 point sits on a degenerate vertex against many simultaneously-active rows, and asking a
floating-point solver for a point that is *provably interior by less than 1e-11* is asking for
something below its noise floor.

**The one-coordinate exact repair fed by a numerically-solved interior proposal is, on the present
evidence, not reachable with the authorized solvers.**

---

## 5. What I recommend — not implemented, and not to be inferred as done

**Authorize the multi-coordinate exact repair**, deferred in an earlier ruling as disproportionate.
It is now the proportionate option, because it removes the dependency that is failing: it needs no
numerically-interior proposal at all.

The violations the constructor must absorb are **~1e-17 to 1e-12** — the exact-arithmetic residue
of a boundary-sitting solver point. A multi-coordinate absorber corrects the equality *and* the few
violated inequality rows together, by solving a small exact rational system over the coordinates
appearing in those rows. The repair distance stays at the scale of the violation (~1e-12), which
keeps the agreement radius tight and the gate meaningful.

Its cost is the specification surface the earlier ruling correctly named — exact active-set
selection, rational linear solving, rank/degeneracy handling, basis selection and tie-breaking,
shuffle-invariance, more failure classes. That is real, and it is why it was deferred. But the
alternative on the table is an approach that the evidence now shows cannot be fed.

**An interior-anchor blend** (`ŵ = (1−θ)·w + θ·c`, with `c` an exactly-feasible strictly-interior
rational point and θ exact) would also work and is far simpler — but with the measured interior
thickness (~1e-8) it forces θ ≈ 1e-4 and a repair distance ~1e-5, inflating the agreement radius to
~1e-3 against actual solver disagreement of ~1e-10. The gate would still be rigorous, but it would
be **seven orders looser than the quantity it is testing** — a bound that passes without proving
much. I do not recommend buying simplicity at that price, and I flag it rather than quietly
choosing it.

---

## Artifacts

| artifact | sha256 |
|---|---|
| `runtime/MR002_R2_RegressionSampleA.json` (C1) | *(regenerated — supersedes the quadprog A artifact, which is retained)* |
| `runtime/MR002_C1_Convergence_Diagnosis.json` | tolerance × regularization grid |
| `runtime/MR002_EtaSweep_Diagnosis.json` | η × tolerance × REPAIRED, with statuses |
| `runtime/MR002_InteriorWidth_Diagnosis.json` | LP feasibility oracle by η |
| `runtime/MR002_HiGHS_Projection_Probe.json` | **INCONCLUSIVE — probe wrapper suspect** |

**Fixtures:** 58/58 pass, including the fifteen §9 Clarabel fixtures.
**Erratum:** remains **undrafted**. All earlier artifacts preserved unmodified.

### Two implementation findings worth recording

* **Clarabel is not bitwise permutation-equivariant.** Equilibration and the KKT factorization
  depend on presentation order, so the same problem under two layouts returns primals differing in
  the last bits — and the exact repair, being derived from the proposal, inherited it. The wrapper
  now submits in a **model-defined canonical order** and maps back, so shuffle-invariance holds by
  construction. (`z_s` is in the ordering key: the proposal objective is `−z_s`, so two variables
  identical in the model but with different `z_s` are not interchangeable.)
* **A rigor bug in the certificate module, caught by a fixture.** Interval endpoints were converted
  to doubles with `float()`, which rounds to *nearest* — so a rigorous upper bound could round
  **down** below the true value and silently stop being a bound. All reported bounds now use
  directed rounding (`nextafter`).
