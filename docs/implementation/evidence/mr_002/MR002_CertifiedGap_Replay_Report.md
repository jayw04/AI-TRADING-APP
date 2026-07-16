# MR-002 v1.1 — Stage-3 certified-gap replay

**Date:** 2026-07-13
**Status:** 🛑 **STOPPED FOR ADJUDICATION** under the replay outcome rule (`comments.md` §6)
**Cascade under adjudication:** `QUADPROG_SQRT → PIQP_P2`
**Result:** unresolved = **35**, not 0.

Nothing was altered after the stop. No solver setting, tolerance, cascade order, objective
coefficient, constraint or registered floor was touched.

> **DIAGNOSTIC ONLY.** No performance computed, printed or persisted. Preflight and the
> development run remain **STOPPED**. Validation and sealed OOS remain **sealed and unread**.

## Artifacts

| artifact | sha256 | bytes |
|---|---|---|
| `runtime/MR002_ComplementaryCoverage_Certified.json` | `47215cd2aa65124ba0ffe4d2e41ae2539030a449fddd614b28e7f2078d00fda6` | 1,906,294 |
| `runtime/MR002_CertifiedGap_Diagnosis.json` | `4186951192e96521837cc6887ffb096820788a172bb609568f7c5b0c1bec7a0b` | 1,964 |
| `runtime/MR002_RuntimeManifest_Certified.json` | `68b116e02fb829c4849f0407b798acf3ebd48b3aeb95e147216cc988ce73218f` | 2,524 |

**Preserved, unmodified:** `runtime/MR002_ComplementaryCoverage.json` ·
`790002c05c45e685a5126b6a2a5707689460486ad16800c7ea3be960f9c7a1c7` — disposition unchanged:
*CASCADE COVERAGE PASSED / AGREEMENT GATE FAILED / SIGNED-GAP AGREEMENT SPECIFICATION INVALIDATED
/ NOT COUNTERSIGNED.*

**Image:** `mr002-research:v1.4`, linux/amd64, `sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`
**High-precision dependency:** `mpmath 1.3.0`; ABI `cpython-313-x86_64-linux-gnu`; Python 3.13.14.

## What passed

* **Corpus reproduced EXACTLY** — 3,895 instances, hash
  `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`.
* **Interval arithmetic**: worst width across all 27,265 certificates **1.61e-100** (limit 1e-30).
  Every IEEE-754 input entered through `as_integer_ratio()`, asserted zero-width.
* **Lagrangian-floor invariant** (`comments.md` §2): **zero violations**. No
  `CERTIFICATE_LAGRANGIAN_IDENTITY_VIOLATION`. The certificate module is not the defect.
* **Agreement gates** — the ones that FAILED under the invalidated signed-gap specification:
  * certified-radius agreement: **PASS**, 1,815 overlaps, **0 violations**, worst `dz/bound` = 0.249
  * objective agreement: **PASS**, **0 violations**, worst ratio 0.987
* **Determinism**: 2,019 qualifying instances rechecked, **0 differed**.
* **Shuffle invariance**: 2,015 rechecked, **0** exceeded 1e-8 (worst |Δ| = 6.39e-10).
* 26 certificates required a multiplier clip; all recorded with index and IEEE-754 hex.

> ⚠ The coverage artifact's own `same_image_determinism` and `shuffle_invariance` fields read
> `false`. **Those are a reporting artifact of that script, not a finding.** Both loops treat "the
> fallback NONQUALIFIES on this instance" as a failure, and the certified predicate produced 2,054
> primary nonqualifications instead of 5. Re-instrumented in the diagnosis run — both genuinely
> **PASS**. The artifact's fields are left as written rather than edited after the fact.

## Why the cascade did not close

**The certified gap is the signed complementarity residual.** When stationarity holds,
`h = q − Cλ̄ = −Hz`, and the construction collapses:

```
G = f − d = z'Hz + q'z − b'λ̄ = z'(Hz + q) − b'λ̄ = z'(Cλ̄) − b'λ̄ = λ̄'(C'z − b) = S_lag
```

Measured, not asserted:

| solver | max \|G − S_lag\| |
|---|---|
| QUADPROG_SQRT | 6.08e-25 |
| PIQP_P2 | 2.02e-22 |

The registered acceptance predicate already gates that quantity **in absolute value**
(`complementarity`). The certified-gap gate additionally requires it to be **non-negative** —
which is a demand that the submitted point be *exactly* primal-feasible on its active constraints.
No double-precision solver can meet that, and the effect is family-independent: it struck the
active-set primary and the interior-point fallback alike.

### The magnitudes

| | QUADPROG_SQRT | PIQP_P2 |
|---|---|---|
| certificates | 3,890 | 3,846 |
| pass every registered KKT gate | **3,890 (all)** | **3,846 (all)** |
| `\|G\| ≤ 1e-10` | **3,890 (all)** | 3,844 |
| `\|G\| > 1e-10` | **0** | 2 |
| `G < 0` | 2,049 | 12 |
| worst negative G | **−6.90e-14** | −1.45e-09 |

**Every one of the 6,324 negative gaps across all seven solvers had the negative gap as its SOLE
failure reason** — i.e. `CERTIFIED_GAP_NEGATIVE_APPROX_PRIMAL`, per your §2 classification, never
`CERTIFICATE_LAGRANGIAN_IDENTITY_VIOLATION`.

For the primary that means: on **every instance in the corpus** the square-root path is optimal to
within 1e-13 and passes every registered gate. It is disqualified 2,054 times purely by the *sign*
of a quantity at the 1e-14 level.

### The 35 unresolved

| count | reason |
|---|---|
| 35 | `QUADPROG_SQRT : CERTIFIED_GAP_NEGATIVE_APPROX_PRIMAL` |
| 27 | `PIQP_P2 : raised` (the pre-existing PIQP failures) |
| 8 | `PIQP_P2 : CERTIFIED_GAP_NEGATIVE_APPROX_PRIMAL` |

## Diagnostic counterfactual — recorded, NOT proposed

Holding every tolerance, solver setting, profile and the cascade order fixed, and changing *only*
the certified-gap gate from `0 ≤ G ≤ 1e-10` to the two-sided `|G| ≤ 1e-10`:

| | current | two-sided |
|---|---|---|
| QUADPROG_SQRT nonqualifications | 2,054 | **5** |
| PIQP_P2 nonqualifications | 61 | 51 |
| **cascade unresolved** | **35** | **0** |

The two-sided gate reproduces the **registered 5** square-root failures exactly — the same five
false-infeasibility instances characterized before any of this work.

## The mathematical question this puts to the owner

`G ≤ 1e-10` is the **suboptimality** claim, and it is sound on its own: `d_cert ≤ p*`, so
`G ≥ f(z) − p*`, and an upper bound on G bounds suboptimality regardless of sign. **`G ≥ 0` is not
a suboptimality condition at all — it is a primal-feasibility assertion**, and primal feasibility
is already owned by the registered `primal_residual` gate.

**But a two-sided gate is not a free substitution, and I am not proposing one unilaterally.** The
strong-convexity radius `r = sqrt(2G/m)` is undefined for `G < 0`. Taking `r = sqrt(2·max(G,0)/m)`
would collapse the radius to zero on ~2,000 newly-admitted overlaps — **which is precisely the
defect that invalidated the previous specification.** A sound two-sided gate therefore needs a
radius valid for a nearly-feasible point, and the honest statement of that is

```
(m/2)·||z − z*||²  ≤  (f(z) − f*) − ∇f(z*)'(z − z*)  ≤  G + λ*'(b − C'z)
```

which depends on the **true** optimal multipliers `λ*`, not on `λ̄`. Bounding that term rigorously
is a real derivation, not a substitution — and inventing one to fit the data is the exact error
that got the last agreement bound rejected. I am not doing it without a ruling.

## Recommendation

1. Rule on whether the certified-gap gate is **two-sided (`|G| ≤ 1e-10`)**, with `G ≥ 0` retired as
   a feasibility proxy that duplicates `primal_residual`.
2. If so, commission the **radius derivation for `G < 0`** as its own gated step, proved in a
   fixture before any corpus recomputation — not asserted.
3. The erratum stays undrafted until those gates pass. Per §6, nothing changes in the meantime.
