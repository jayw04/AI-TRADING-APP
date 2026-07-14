# MR-002 v1.1 — two-sided signed gap PASSES; exact-rational repair STOPS

**Date:** 2026-07-13
**Status:** 🛑 **STOPPED FOR ADJUDICATION** — `REPAIR_CERTIFICATE_UNAVAILABLE` on the predeclared
sizing sample (ruling §9, §16)
**Nothing was altered after the stop.** No solver profile, cascade order, tolerance, economic
coefficient, constraint, inclusion floor, absorber ordering, candidate selection, precision or
repair formulation was changed.

> **DIAGNOSTIC ONLY.** No performance computed, printed or persisted. Preflight and the
> development run remain **STOPPED**. Validation and sealed OOS remain **sealed and unread**.

---

## 1. The two-sided signed-gap correction WORKS

Recomputed on the immutable corpus (3,895 instances, hash `1d231930…`, **reproduced exactly**):

| | superseded nonnegative gate | **two-sided gate** |
|---|---|---|
| QUADPROG_SQRT nonqualifications | 2,054 | **5** |
| cascade `QUADPROG_SQRT → PIQP_P2` unresolved | 35 | **0** |
| determinism (corrected loop) | *defective field* | **PASS** — 5 checked, 0 differed |
| shuffle invariance (corrected loop) | *defective field* | **PASS** — 0 violations, worst \|Δ\| 1.78e-25 |
| worst interval width | 1.61e-100 | **1.61e-100** (limit 1e-30) |
| exact-identity violations | 0 | **0** |

The five primary nonqualifications are **exactly the registered five**, all the same mode
(`ValueError: constraints are inconsistent` — a false infeasibility), and PIQP_P2 certifies every
one of them. Their content hashes:

| index (label only) | content hash | fallback |
|---|---|---|
| 800 | `b04078d109861f62…` | QUALIFIES |
| 1328 | `0a5c00c75b61968e…` | QUALIFIES |
| 2140 | `c71a8803b643e680…` | QUALIFIES |
| 2296 | `a8c63b1eb866c635…` | QUALIFIES |
| 2765 | `d2eecc4032ee099c…` | QUALIFIES |

**Where the repair certificate was obtained, both agreement gates passed** — radius agreement 0
violations (worst `dz/bound` = 3.07e-09, worst `|z₁−z₂|` = 2.93e-16), objective agreement 0
violations (worst ratio 8.05e-04).

---

## 2. The repair certificate STOPS — and the constructor is not at fault

**4 of 50** predeclared overlaps obtained a repair. **46** returned
`REPAIR_CERTIFICATE_UNAVAILABLE / ONE_COORDINATE_EXACT_REPAIR_NOT_FOUND`.

Per §9 this is **not** a solver invalidation and **not** evidence that the feasible set is empty.
Diagnosis over 40 qualifying overlaps (`runtime/MR002_RepairFailure_Diagnosis.json`,
sha256 `8d01520c622cf0421457175d60fc9eded45b8cd3b503afe58db3d7fafa4ba41c`):

| | |
|---|---|
| overlaps whose **clipped proposal already violates an inequality row exactly**, before any absorber runs | **39 / 40** |
| worst such exact violation | **4.68e-17** |
| absorber candidates rejected on an inequality row | 271 |
| absorber candidates rejected on a bound | 163 |
| absorber candidates passing | 7 |

### Root cause

The proposal lands **on the boundary** of the feasible set: the rows that are active at the optimum
are tight, and many coordinates are pinned at `0` or `u`. That point is tolerance-feasible (≈1e-16)
but **not exactly feasible** — in rational arithmetic the active rows are violated by ~1e-17 roughly
half the time, purely by rounding.

The one-coordinate absorber then cannot recover:

* a violated row `r` with `A_ub[r, k] = 0` is **untouched** by any change to `w_k`;
* a coordinate already at a bound leaves the box under **any** nonzero correction.

So the enumeration correctly rejects almost every candidate. **The exact certificate is doing its
job.** The defect is in the numerical **proposal** — which the ruling itself designates as "not
evidence of anything" (§4).

This is the same class of error as the one that killed the nonnegative-gap rule: a construction
that implicitly assumed exact primal feasibility from a floating-point point.

---

## 3. Proposed amendment — NOT implemented

§4 forbids trying an alternate proposal after observing a failed repair, and §9 forbids silently
switching to a multi-coordinate adjustment or another projection method. So this is a proposal,
not a change.

**Make the proposal STRICTLY INTERIOR, so the exact correction cannot leave the feasible set.**
Solve the projection against tightened constraints:

```
min ½‖w − z_s‖²   s.t.   A_ub w ≤ b_ub − η,    η ≤ w ≤ u − η
```

with a single frozen `η` (proposed: `1e-12`). Every row then carries slack ≈ `η`, which dominates
the ~1e-17 absorber correction by five orders of magnitude, so exact verification passes by
construction.

**This changes only the PROPOSAL. The certificate is untouched** — feasibility is still proved in
exact rational arithmetic, the absorber is still enumerated and verified exactly, and the selection
is still exact-minimum-distance. Nothing that constitutes evidence changes.

Cost, and why it is negligible:

* repair distance grows by `δ ≈ η·√n ≈ 1.4e-11` (n ≤ ~200), entering `R_s` additively;
* the repaired gap grows by roughly `|∇f|·η ≈ 1e-12`, so `sqrt(2·Ĝ/m) ≈ 1.4e-7` — the same order as
  the radii already observed (~1e-6). No blow-up.

**Corner case that must be classified, not hidden:** if the feasible set has empty interior (the
budget exactly consuming the caps), the tightened projection is infeasible. That must return
`REPAIR_CERTIFICATE_UNAVAILABLE` and stop — not fall back to the untightened problem.

**Alternative, if you prefer:** authorize a multi-coordinate exact repair. I think the tightened
proposal is the better artifact — it keeps the one-coordinate constructor, whose exactness and
shuffle-invariance are already proved by 32 fixtures — but it is your call, and I have not assumed
it.

---

## 4. Timing (§16, operational planning only)

The repair is **cheap**: ~3 ms per overlap (two repairs each), so the full ~3,800-overlap pass is
on the order of **12 seconds**, not hours. Cost is not a constraint on this design. The proposal
source split was `quadprog_projection` 4 / `clip_fallback` 4 across the 4 successful overlaps.

---

## Artifacts

| artifact | sha256 |
|---|---|
| `runtime/MR002_RepairSizingSample.json` | `aa0f4cf145805af796653fa08e1c80ad134ecf59914f8d37af751a07d633a0d8` |
| `runtime/MR002_RepairFailure_Diagnosis.json` | `8d01520c622cf0421457175d60fc9eded45b8cd3b503afe58db3d7fafa4ba41c` |
| `app/research/mr002/certificate.py` (signed-gap module) | `8d25740ee8318af26167805898762d4e48b029f93283eff57db7b6b922b76b76` |
| `app/research/mr002/repair.py` (repair module) | `5488d986d12b56accd357b2adf8ea29980e396a0085dd1763c19ffeef03c15c6` |
| `scripts/mr002_coverage_signed_gap.py` | `196d468a4837b54daae9636a60b6554e42736c404fb38be4d4c9705e516ce780` |

**Preserved unaltered:** `MR002_ComplementaryCoverage.json` (`790002c0…`) and
`MR002_ComplementaryCoverage_Certified.json` (`47215cd2…`), each retaining its recorded disposition.
The reporting-loop defect is issued separately as `MR002_Correction_ReportingLoop.md` (§15) rather
than by editing the artifact that contains it.

**Fixtures:** 32/32 pass in `mr002-research:v1.4`
(`sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a`), covering every item in
§14 including the previously-owed generic native-wrapper fixture with a genuinely nonzero optimal
lower-bound multiplier outside the MR-002 objective family.

**Erratum:** remains **undrafted**.
