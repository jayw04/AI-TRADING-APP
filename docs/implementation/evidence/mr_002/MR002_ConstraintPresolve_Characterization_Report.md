# MR-002 v1.1 — EXACT CONSTRAINT-PRESOLVE CHARACTERIZATION

**Date:** 2026-07-12 · **VERDICT: 🔴 FAIL — stopping, per §8 of the adjudication.**

**No performance computed. Preflight and development run remain stopped. Validation and sealed OOS remain
sealed and unread.**

---

## 0. The result

**Exact constraint presolve removed 32.5% of all constraint rows and changed the failure count by
EXACTLY ZERO.**

| Formulation | Failures / 3,895 | With exact presolve |
|---|---|---|
| RAW | **70** | **70** — *identical* |
| SQRT | **5** | **5** — *identical* |

Not one failure was fixed. Not one was introduced. **The failures are not caused by constraint
redundancy.**

---

## 1. Corpus verification — PASSED on every criterion

Per your ruling, the original matrices-only corpus was **not modified**. The symbolic data was captured
into a **separate hashed sidecar**, keyed by the immutable matrix instance hash.

| Check | Result |
|---|---|
| Instance count | **3,895** ✅ (exactly as required) |
| Global matrix corpus hash | **`1d2319301a7b52df…`** ✅ **matches** |
| **Per-instance matrix hashes** | **all 3,895 match** ✅ |
| Matrix corpus modified? | **No** ✅ |
| Symbolic sidecar sha256 | `bbc73b03c16e06e3…` |

**A matching hash on every instance proves the symbolic capture was observational only and did not
perturb the numerical path.**

Artifacts: `MR002_Stage3_Corpus.npz` (unchanged) · `MR002_Stage3_Corpus_Symbolic.jsonl` (new) ·
`MR002_Stage3_Corpus_EnrichmentManifest.json`.

---

## 2. The presolve itself — correct, and substantial

| | |
|---|---|
| Constraint rows, total | **96,085** |
| **Rows removed** | **31,249 (32.5%)** |
| `SAME_DIRECTION_SECTOR_DOMINANCE` (certificate D) | **28,044** |
| `ZERO_ROW` (certificate C) | **3,164** |
| `SAME_LHS_WEAKER_BOUND` (certificate B) | 15 |
| `EXACT_DUPLICATE` (certificate A) | 26 |
| Rows removed by a numerical/rank/proximity threshold | **0** ✅ |

**Every removal carries a machine-verifiable certificate.** Certificate D's support includes fixed
exposures `f`, tradable `y` **and** new candidates `x`, as required, and is recorded with
`removed_row_id`, `dominating_row_id`, `sector_id`, `common_direction`, `fixed_support_ids`,
`variable_support_ids`, the coefficient hash and the IEEE-754 hex RHS.

**Correctness gates all PASS:**

| Gate | Result |
|---|---|
| Every original row (including removed) passes direct re-evaluation | ✅ **max violation 4.86e-16** |
| Primal agreement with raw-clean | ✅ **3.83e-14** |
| Objective agreement | ✅ **7.00e-14** |
| Zero rows removed by a numerical threshold | ✅ **0** |
| **sqrt + presolve solves all instances** | 🔴 **FAIL — 5 remain** |

The zero-multiplier reconstruction for removed rows is validated: every original row, removed ones
included, is re-evaluated directly and passes.

### A worthwhile discovery along the way

`build_joint` appends two **unlabelled** rows to `A_ub` after `_build` — the lexicographic bands. When
there are no new candidates (`n_x = 0`), **`row_Q` is an exact all-zero row**. A constraint with a
**zero-norm normal vector** is a textbook Goldfarb–Idnani failure mode, and certificate C removed **3,164**
of them. I expected this to be a large part of the fix.

**It was not. Removing them changed nothing.**

---

## 3. What this establishes

The failures are all `constraints are inconsistent, no solution` — a **feasibility-detection** failure on
regions HiGHS proves feasible. We have now removed, exactly and provably:

- the **Hessian** conditioning problem (√t equilibration ⇒ `cond(H) = 1`), and
- a third of the **constraint rows**, including every redundant sector row and every zero-norm row.

**Neither touches the failures.** The two structural explanations available within the registered solver
are exhausted, and the residual 5 (and the 2 that defeat every formulation) persist unchanged.

**Per §8 of your adjudication, quadprog is therefore to be treated as inadequately robust for the MR-002
Stage-3 problem class.**

I want to state the limit of this claim precisely, as you required for the previous report: this
demonstrates that **the tested formulations, cascades and presolve are incomplete**. It is not a proof
that no possible quadprog formulation can succeed.

---

## 4. What should be retained regardless of the solver decision

Both transformations are **exact, correct and independently valuable**, and I recommend registering them
whatever solver is chosen:

- **√t equilibration** — repairs the entire corrupted-dual failure class (8/8), drops worst stationarity
  from **17.5** to **1.89e-10**, and cuts bound-multiplier amplification from `1e8` to `1e4`.
- **Exact constraint presolve** — a 32.5% row reduction with every removal certificated and every original
  row still verified.
- **The t-scaled rescue should be retired** — 185 failures, *worse than raw*.

---

## 5. Requested ruling

Per §8, the next permissible step is **characterization of a different deterministic convex-QP solver
under a separate ruling**. I have not selected or introduced one, and I will not without that ruling.

Constraints I understand to remain in force: no `ε_include` change · no tolerance relaxation · no ridge,
jitter or regularization · no approximate row removal · no third attempt · no SLSQP or other optimizer
without a ruling.

**Nothing further runs until you rule.**

---

## 6. Process note (standing, from your ruling)

Every solver characterization from this point persists the **complete original model before the first
solver attempt** — successes and failures alike. The prospective corpus now satisfies this. The earlier
**historical corpus remains permanently unavailable**, and that remains a disclosed process deficiency,
not something the verified recapture repairs.
