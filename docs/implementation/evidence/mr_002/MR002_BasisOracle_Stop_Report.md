# MR-002 v1.1 — the HiGHS basis oracle cannot resolve ρ\*; capability characterization STOPS

**Date:** 2026-07-14
**Status:** 🛑 **STOPPED FOR ADJUDICATION** — the basis-oracle approach fails at every tolerance
**Classification:** **capability characterization, NOT Sample A evidence.** No oracle profile was
frozen; no evidence run was performed. Samples A and B were not started.

**Nothing was repaired, clipped or adjusted.** No negative exact variable was clipped. No `h` was
adjusted. The exact constructor, the repair LP, the two-sided signed-gap gate, the solver profiles,
the cascade order and the objective are untouched.

---

## 1. The finding

The exact reconstruction requires `M[:,S] · x_S = h` to hold **exactly**. It does not — and not
because the residual is merely small:

| candidate oracle profile | exactly consistent (`rank M[:,S] == rank[M[:,S] | h]`) | full column rank |
|---|---|---|
| default tol (1e-7), scaling on | **0 / 8** | 8 / 8 |
| tol 1e-10, scaling on | **0 / 8** | 8 / 8 |
| tol 1e-10, scaling **off** | **0 / 8** | 8 / 8 |
| tol 1e-12, scaling **off** | **0 / 8** | 8 / 8 |

`M[:,S]` has **full column rank**, but **`h` is not in its column space**. The basis therefore
corresponds to **no exactly feasible point at all**. Tightening the tolerance shrinks the residual
(1e-8 → 1e-18) without ever reaching zero, which is exactly the case the ruling names as a stop.

## 2. Root cause — and it is not a tuning problem

At every profile HiGHS reports:

```
kOptimal | rho = 0.000e+00 | rho_basic = False
```

**HiGHS returns the ρ = 0 basis.** It believes `z_s` is already feasible — because `z_s` violates
the original constraints by only **~1e-17**, and the tightest primal-feasibility tolerance HiGHS
accepts (~1e-12) is five orders of magnitude coarser.

But the ρ = 0 vertex **does not exist in exact arithmetic**: `z_s` is *not* exactly feasible, which
is the entire reason the repair exists. So the returned basis describes a vertex that isn't there,
`h` falls outside the column space, and no exact solution can be reconstructed from it.

**The exact quantity to be located (ρ\* ≈ 1e-17) lies below the oracle's resolution floor
(~1e-12).** This is the same wall that defeated R1, R2 and R2-C1, now in its LP form: a
floating-point solver is being asked to discriminate a structure that lives beneath its epsilon.

### What was ruled out along the way

* **Tolerance** — swept to the minimum HiGHS accepts. Residual shrinks, consistency never appears.
* **Model scaling** — disabled. No change.
* **`small_matrix_value`** — I suspected it was silently dropping matrix entries (it was copied
  from the validated QP profile). **Measured and exonerated:** the smallest nonzero coefficient in
  the corpus is **5e-2**, far above any threshold. Removed anyway, since it can only do harm here.
* **Negative reconstructed variables** — an artifact of the 1e-7 default; they vanish at 1e-10. Not
  the cause.

## 3. Separated measurements (as required)

| | default 1e-7 | tol 1e-10 |
|---|---|---|
| native status | kOptimal | kOptimal |
| native reported ρ | 0.000e+00 | 0.000e+00 |
| exact consistency of `M[:,S] x_S = h` | **never** | **never** |
| worst exact `\|basic-row activity − h\|` | 1.0e-08 | 3.7e-18 … 1.2e-17 |
| minimum reconstructed structural value | negative (up to 7 vars/instance) | **0** (none negative) |
| structural system rank / uniqueness | full column rank, unique | full column rank, unique |
| exact dual + reduced costs | not reached — primal fails first | not reached |

Determinism under a candidate profile was not characterized, because no candidate profile produces
an exactly reconstructable basis; characterizing the repeatability of an unusable basis would be
theatre.

## 4. Recommendation — not implemented

**Warm-start an exact rational simplex from the HiGHS basis.**

This keeps the authorized architecture intact — *HiGHS proposes, exact arithmetic certifies* — and
removes the failing dependency, which is the oracle's *resolution*, not its *direction*. HiGHS's
basis is combinatorially close; what it cannot do is take the last few pivots that only matter at
1e-17. Exact rational simplex has **no tolerance at all**, so those pivots are not merely accurate,
they are decidable.

* The LP is small: ≤ 321 columns and ≤ 251 rows, and the structure is mostly unit columns.
* Starting from a near-optimal basis, only a handful of exact pivots should be needed — this is the
  standard exact-LP pattern (float warm start, exact iterative pivoting), not novel machinery.
* Every certificate already specified survives unchanged: exact primal feasibility, exact
  nonnegativity, exact dual feasibility / reduced-cost signs (the load-bearing optimality proof),
  and the primal-dual objective identity as a consistency check.

**An alternative I considered and do not recommend:** rescaling the repair LP so ρ is O(1) (solving
for the displacement `d = w − z_s` and scaling it up). It fails for the same reason — the violation
is ~1e-15 *relative*, so no scaling makes it visible to a float LP; it merely moves the ill-scaling
into the bound rows. I flag it rather than quietly discarding it.

---

## Artifacts (capability characterization)

| script | what it establishes |
|---|---|
| `scripts/mr002_basis_convention_probe.py` | HiGHS's row-logical semantics, on a hand-checkable LP |
| `scripts/mr002_basis_feasibility_probe.py` | exact basic-row defect: 1e-8 at default tol, 1e-18 at 1e-10 |
| `scripts/mr002_basis_rank_probe.py` | **exact rank inconsistency at every profile; ρ = 0 basis** |

**Fixtures:** the 58 existing signed-gap and repair fixtures still pass; the exact-repair fixture
suite was not written, because writing 20 fixtures against a design that cannot repair the actual
geometry would have been the wrong order of work.

**Erratum:** remains **undrafted**. All predecessor artifacts preserved unmodified.
