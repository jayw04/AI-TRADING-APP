# MR-002 v1.1 — IMPLEMENTATION ERRATUM
## Stage-3 Equivalent-Formulation Retry

**Date:** 2026-07-12 · **Status:** 🟡 **AWAITING SIGNATURE AND HASH.** No run has been executed under
this erratum.

| Bound artifact | SHA-256 |
|---|---|
| Pre-Registration v1.1 rev 3 (countersigned design) | `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Structural-Executability Adjudication (accepted) | `ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e` |
| Stage-3 Solver-Robustness Defect (escalation) | `41da8b0890b265ed5021c4afe83fe366a4ebdc3adc0fb72da193d161062053ed` |

All three hashes independently recomputed and confirmed.

**Classification: IMPLEMENTATION ERRATUM. No v1.2. No research-design re-freeze.**

It changes none of: the feasible post-trade portfolios · the lexicographic objectives · the unique
Stage-3 minimizer · any signal, weight bound, risk limit, cost, gate or window · any treatment of solver
failure as cash.

---

## 1. What is superseded, and what is NOT

This erratum **supersedes Appendix B.3 in exactly one respect**: it permits **one** precisely-defined
retry, using **the same solver**, under an **algebraically equivalent coordinate transformation**.

**Everything else in the B.3 prohibition remains in force:**

- ❌ No alternate/different optimizer.
- ❌ No fallback solver.
- ❌ No regularization — no ridge, no jitter, no `H + λI`.
- ❌ No tolerance relaxation.
- ❌ No inclusion-floor change.
- ❌ No retry for any failure other than the exact registered trigger.
- ❌ No third attempt.

**Registered values that do NOT change:**

```
ε_include              = 1e-8      (NOT raised; raising it is neither a root fix nor permissible
                                    development-sample tuning)
HESSIAN_CONDITION_MAX  = 1e10
ε_retention = ε_new    = 1e-8
τ_primal               = 1e-9
ε_active_sector        = 1e-6
```

**Neither `ε_include` nor `HESSIAN_CONDITION_MAX` may ever be changed on the basis of development
failure counts.**

---

## 2. The defect (recorded)

The registered Stage-3 solver `quadprog.solve_qp` (Goldfarb–Idnani dual active-set) **falsely reports
`"constraints are inconsistent, no solution"` on Stage-3 regions that are provably feasible.**

| | |
|---|---|
| Stage-3 solves across A/B/C (1,700 sessions each) | **1,275** |
| Registered raw-path failures | **4** (~0.31%) |
| Failing instances proven **feasible** by HiGHS | **52 / 52** |
| Failing instances genuinely infeasible | **0** |

This is a **numerical solver defect** — not an infeasible portfolio, and not an economic-design failure.

---

## 3. The frozen cascade

```
1. Attempt the REGISTERED RAW quadprog Stage-3 formulation.

2. A scaled retry is permitted ONLY when raw quadprog raises EXACTLY:
       exception type    = ValueError
       exception message = "constraints are inconsistent, no solution"

3. Before retrying, run a ZERO-OBJECTIVE HiGHS feasibility probe on the ORIGINAL
   Stage-3 region:
       - same bounds
       - same coupling constraints
       - same neutrality equality
       - same R and Q lexicographic bands
       - warning policy remains FATAL

4. If HiGHS does not return optimal with original-coordinate primal feasibility <= 1e-9:
       INVALID_RUN

5. If the region is confirmed feasible, retry quadprog ONCE:

       t_i = registered upper bound of variable i
       T   = diag(t)          u = T^-1 z

       0 <= u_i <= 1

       H_scaled   = T H_raw T   = diag(2 t_i)
       a_scaled   = T a_raw     = 2 t
       A_scaled   = A_raw   T
       Aeq_scaled = Aeq_raw T

6. Map back:   z = T u

7. Recompute EVERY acceptance check in the ORIGINAL z coordinates.

8. If the scaled solve raises, warns, or fails any registered check:
       INVALID_RUN

9. No third attempt, alternate solver, regularization, jitter, tolerance relaxation
   or inclusion-floor change is permitted.
```

### 3.1 Transformation guards (§1 refinement — approved)

Before the scaled attempt, for **every** variable:

```
isfinite(t_i)
t_i > ε_include
t_i is BITWISE IDENTICAL to the registered upper_i     (IEEE-754 / array identity,
                                                        NOT approximate equality)
```

Any failure ⇒ **`INVALID_RUN`**.

These confirm that **`T` is invertible** and that **`0 ≤ z_i ≤ t_i ⇔ 0 ≤ u_i ≤ 1`**, and they prevent a
future bound change from silently invalidating the transformation.

### 3.2 Trigger pin (§2 refinement — approved)

Required at process start:

```
quadprog.__version__ == "0.1.13"
installed Linux artifact == the one recorded in the frozen runtime manifest
    (sha256 cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff)
```

**The trigger is exact and FAIL-CLOSED.** A changed message, a different exception type, package-version
drift, or an artifact mismatch is **immediately fatal — never eligible for rescue**. In particular
`"matrix G is not positive definite"` **must not** trigger the cascade.

### 3.3 Warning behavior (§3 refinement — approved)

**A warning from the raw solve is NEVER a cascade trigger.**

Because every solve executes under:

```python
with warnings.catch_warnings():
    warnings.simplefilter("error")
    result = solve(...)
```

a warning becomes an exception **distinct from** the exact registered `ValueError`. It therefore produces
**immediate `INVALID_RUN`**. Stated here explicitly rather than left to fall out of the machinery.

---

## 4. Original-coordinate acceptance rule (FROZEN, without qualification)

- Scaled-coordinate residuals **may be recorded diagnostically.**
- **They are NOT sufficient for acceptance.**
- Every rescued result **must be mapped back to `z`.**
- **All** final residuals, objective values, lexicographic bands, bounds, coupling constraints and KKT
  conditions are evaluated in the **original** formulation.

**Multiplier transformation.** General inequality and equality multipliers **retain their row
association** under the coordinate transformation. **Bound** multipliers transform:

```
μ_z,i = μ_u,i / t_i
```

*Derivation (independently confirmed).* With `H_s = T H T`, `a_s = T a`, `u = T⁻¹z`, and the bound rows
unscaled, stationarity in scaled coordinates `H_s u − a_s − C_s λ = 0` gives
`T(Hz − a) = T(Aeqᵀλ_eq − Aᵀλ_ineq) + (λ_lo − λ_hi)`. Dividing by `T`:

```
Hz − a = Aeq^T λ_eq − A^T λ_ineq + T^-1 (λ_lo − λ_hi)
```

— i.e. **row multipliers unchanged; bound multipliers divided by `t_i`.**

### 4.1 Measured evidence that the rule is operationally satisfiable

The division by `t_i` **amplifies bound multipliers by up to ~1e8**. Whether the amplified
floating-point error would breach the registered thresholds was the single most important open question;
it was measured on the real rescued instances:

| | Observed (worst rescue) | Registered limit | Margin |
|---|---|---|---|
| Amplification `1 / t_min` | **9.91e+07** | — | — |
| **Original-coordinate stationarity** | **8.31e-12** | 1e-8 | **~1,200×** |
| Original-coordinate primal | 4.5e-18 | 1e-9 | — |
| Original-coordinate complementarity | 3.0e-16 | 1e-8 | — |
| Original-coordinate KKT | 8.31e-12 | 1e-8 | ~1,200× |
| *(reference)* scaled-coordinate stationarity | ~2e-16 | — | — |
| Raw (non-rescued) path, worst KKT | 1.46e-11 | 1e-8 | ~700× |

**Every rescue passes every check in original coordinates.** The amplification is harmless because the
bound multipliers of the sub-floor variables are themselves ≈ 0.

> **The cascade is therefore not merely mathematically equivalent — it is operationally compatible with
> the frozen acceptance contract.**

---

## 5. Recorded fields (per Stage-3 solve)

```
stage3_formulation        = RAW | SCALED_RESCUE
raw_exception_class
raw_exception_message
feasibility_probe_status
scaled_solver_status
raw_coordinate_objective
primal_residual
dual_residual
stationarity_residual
complementarity_residual
KKT_residual
max_homogeneous_violation
```

---

## 6. The κ(H) lesson (permanent record)

> **Every observed raw quadprog false-infeasibility occurred with κ(H) ≈ 1.5×10⁶ — roughly four orders
> of magnitude below the registered 10¹⁰ fatal threshold. The condition-number guard was not close to
> binding and did not predict these failures. It remains a useful diagnostic and an extreme-conditioning
> guard, but it is NOT a solvability certificate for the Goldfarb–Idnani implementation.**

`HESSIAN_CONDITION_MAX = 1e10` is retained unchanged.

---

## 7. Remedies rejected (recorded, with evidence)

| Remedy | Disposition |
|---|---|
| **Always**-scaled formulation | **REJECTED — 48 failures**, 12× worse than the registered path. It was the author's own first proposal after it fixed the single instance that first failed; verifying at full scale refuted it. It may appear **only** as the registered rescue formulation, after the narrow raw-failure trigger. |
| Raise `ε_include` | **REJECTED.** Not a root correction — a failure **reappears at 1e-4**. And selecting it by failure count on the development sample is impermissible development-sample tuning. **Keep `ε_include = 1e-8`.** |
| Different QP solver | **NOT AUTHORIZED.** No sufficiently characterized replacement exists, and one is unnecessary given the equivalent-formulation remedy. |
| Accept intermittent `INVALID_RUN` | **REJECTED.** A valid research result cannot depend on whether the numerical solver happens to reject a feasible instance. |

---

## 8. Fixture suite — **43 tests**

| | Count |
|---|---|
| Existing suite | **28** *(27 registered + the D1 converse, kept separate for audit clarity)* |
| Cascade-specific | **15** |
| **Total** | **43** |

*Do not consolidate tests merely to preserve the earlier provisional count of 42.*

**The 15 cascade fixtures:**

1. Raw Stage 3 succeeds; the scaled path is **never invoked**.
2. The exact false-inconsistency exception triggers the HiGHS feasibility probe.
3. A feasible raw region is **rescued** by the scaled formulation.
4. Raw and scaled solutions **agree within tolerance** when both are deliberately evaluated.
5. The mapped-back scaled solution passes **all** checks in **original** coordinates.
6. Original-coordinate **bound multipliers and stationarity** are transformed correctly (`μ_z = μ_u / t`).
7. `"matrix G is not positive definite"` remains **immediately fatal** (no cascade).
8. An exception with **any other message** remains immediately fatal.
9. HiGHS probe **infeasible or non-optimal** remains fatal.
10. Scaled quadprog **failure** remains fatal.
11. Scaled **residual or KKT failure** remains fatal.
12. Repeated rescue produces **byte-identical** executable decisions.
13. Candidate **and existing-position shuffles** produce the same rescued result.
14. No retry changes `R*`, `Q*`, the economic objective, or any registered bound.
15. **No third attempt or alternate solver is reachable.**

---

## 9. Structural-comparison basis

Comparison against the previously-committed 124-session structural slice uses the **canonical session
executable-decision hashes**, **not** whole-report bytes — this erratum adds `stage3_formulation`,
`raw_exception_message`, `feasibility_probe_status` and the rescue diagnostics, so byte equality against
the pre-erratum report is **neither expected nor meaningful**.

**Required checks:**

1. All **124** historical session decision hashes remain **identical**.
2. Order, exit, reduction, outcome and position decisions remain **identical**.
3. The newly-generated post-erratum report is **byte-identical across two runs** in the same rebuilt image.
4. Per-solve records may differ **only** through the added audit fields.

---

## 10. Cross-platform standard

On another architecture the **raw** formulation may succeed where Linux/amd64 required `SCALED_RESCUE`.
This does **not** violate the numerical-equivalence standard, provided the mapped-back allocations agree
within the registered tolerances. *(Measured: where both formulations succeed they agree to **2.6e-15**.)*

- **Same frozen image:** same formulation path, byte-identical decisions and reports.
- **Different platform:** economically and numerically equivalent original-coordinate solution;
  **formulation-path identity is not required.**

---

## 11. Disposition of the aborted run

The stopped development attempt is **permanently recorded** as:

```
ABORTED — INVALID_RUN
STAGE3_RAW_QUADPROG_FALSE_INFEASIBILITY
NO PERFORMANCE INSPECTED
VALIDATION UNREAD
SEALED OOS UNREAD
```

**The stopped run is DISCARDED.** It will **not** be resumed from the failure point, and **no altered
state from the diagnostic sweeps will be reused.** The full development run **restarts from session 1 on
clean immutable state.**

*(Verified: no diagnostic mutated the committed source. `mr002_test_inclusion_floor.py` altered
`jp.EPS_INCLUDE` only in-process; the registered source retains `EPS_INCLUDE = 1e-8`.)*

---

## 12. Registered restart sequence (after signature and hash)

1. Rebuild and hash the Linux research image.
2. Update the dependency/runtime manifest if any artifact changed.
3. Run the expanded **43-fixture** suite.
4. Rerun the 124-session structural slice and confirm via **decision-hash comparison** that the raw path
   is unchanged except where a rescue is deliberately exercised.
5. Restart the **complete A/B/C 1,700-session development run from session 1** on clean immutable state.
6. Produce a **byte-identical** same-image rerun.
7. **Stop for Implementation Freeze review.**

**Performance inspection remains PROHIBITED until that clean development run completes. Validation and
sealed OOS remain SEALED AND UNREAD.**

---

*Awaiting signature and hash. Nothing has been run under this erratum.*
