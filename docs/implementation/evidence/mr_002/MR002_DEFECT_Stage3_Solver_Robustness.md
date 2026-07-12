# MR-002 v1.1 — IMPLEMENTATION DEFECT: Stage-3 solver robustness

**Date:** 2026-07-12 · **Status:** 🛑 **RUN STOPPED — `INVALID_RUN`. Separate adjudication required.**

Raised under the Full Development-Run Authorization (2026-07-12): *"The run must stop as INVALID_RUN for
any fatal solver … failure. No failed computation may be converted into a cash or zero-entry outcome."*
and *"Any later implementation defect must be documented and adjudicated separately."*

| Bound artifact | SHA-256 |
|---|---|
| Pre-Registration v1.1 rev 3 | `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Structural adjudication | `ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e` |

> **No development performance has been inspected.** The run stopped inside configuration A. No P&L,
> return, Sharpe, hit rate, drawdown or configuration comparison has been computed, printed or persisted.
> **Validation and sealed OOS remain sealed and unread.**

---

## 1. The defect

**The registered Stage-3 solver — `quadprog.solve_qp` (Goldfarb–Idnani dual active-set) — falsely
reports `"constraints are inconsistent, no solution"` on Stage-3 regions that are provably feasible.**

Per the frozen contract (Appendix B.3), this exception *must not occur at Stage 3*, because Stages 1 and
2 have already proved the region non-empty. It is therefore a **fatal implementation defect**, and the
run correctly stopped rather than converting it into cash.

### Independent proof that the failures are false

On **every** failing instance, HiGHS — the *already-registered* LP solver — finds a feasible point in the
**same** Stage-3 region with **zero** constraint violation.

| | Count |
|---|---|
| Stage-3 solves across A/B/C (1,700 sessions each) | **1,275** |
| Registered (raw) quadprog **failures** | **4** (~0.31%) |
| Failing instances HiGHS proves **feasible** | **52 / 52** |
| Failing instances HiGHS proves **infeasible** | **0** |

**The problems are solvable. The registered solver is not solving them.**

### Signature of the failing instances

All four share one: a decision variable whose target sits just above the registered inclusion floor.

| n vars | rows | `target_min` | `target_max / target_min` | scaled retry | HiGHS feasible |
|---|---|---|---|---|---|
| 26 | 34 | 1.014e-08 | 1.48e+06 | ✅ | ✅ |
| 29 | 28 | 1.009e-08 | 1.49e+06 | ✅ | ✅ |
| 21 | 31 | 1.348e-08 | 1.11e+06 | ✅ | ✅ |
| 35 | 34 | 1.020e-08 | 1.52e+06 | ✅ | ✅ |

A target of ~1.0e-8 produces a Hessian entry of `2 / 1.0e-8 ≈ 2.0e8` sitting beside entries of ~1e2.
Note that **`κ(H) ≈ 1.5e6` — comfortably inside the registered 1e10 limit.** *The registered
conditioning guard passes while the solver still breaks, so κ(H) is not a sufficient proxy for
solvability.* That is itself a finding.

---

## 2. Remedies tested — including one of mine that FAILED

I verified every candidate on the **full** 1,700-session × 3-config window rather than on the single
instance that first failed. That discipline mattered: **it killed my own first proposal.**

| # | Remedy | Result |
|---|---|---|
| 1 | **Always** solve scaled (`u = z/t`) | ❌ **REJECTED — 48 failures.** *12× worse than the registered path.* This was my initial proposal after it fixed the first failing instance. Verifying at full scale refuted it. |
| 2 | **Raw → scaled cascade** (raw first; scaled *only* on raw failure) | ✅ **0 failures in 1,275 solves.** All 4 raw failures rescued. Where both succeed they agree to **2.6e-15**. |
| 3 | Raise `ε_include` | ⚠️ **Not a root fix.** 0 failures at 1e-7 / 1e-6 / 1e-5 — **but 1 failure REAPPEARS at 1e-4.** |
| 4 | Independent SLSQP | ❌ 151 failures. Worse than quadprog. |

### Why remedy 3 must be rejected even though it "works"

Two independent reasons, either sufficient:

1. **It is not a root fix.** The failure returns at 1e-4. The floor merely moves the problem; it does not
   control the mechanism. A value that is quiet on *this* data offers no guarantee on validation or OOS.
2. **Choosing the floor by counting failures on development data is data-dependent tuning** — precisely
   what the authorization forbids: *"No signal, threshold, risk limit, gate, cost assumption, universe
   rule or construction rule may be changed in response to the development results."* Even a purely
   numerical knob, selected by its performance on the development sample, is a fit to that sample.

**I therefore do not propose raising `ε_include`.**

*(Counting note, for honesty: the floor sweep reports 5 raw failures at 1e-8 rather than 4. The sweep
continues past a failure using a HiGHS point so it can measure the whole window, which perturbs the
subsequent position path. The counts are not identical runs and should not be compared to the decimal.
The qualitative result — failures at 1e-8, none at 1e-7…1e-5, one at 1e-4 — is stable.)*

---

## 3. Recommendation — Remedy 2, and it needs your registration

**Deterministic two-formulation cascade, inside the same registered solver.**

```
Stage 3:
  1. attempt quadprog.solve_qp on the REGISTERED raw formulation
  2. ONLY if it raises, attempt quadprog.solve_qp on the exactly-rescaled formulation
        u = z / t        (T = diag(t), every t_i > 0)
        D = Σ (z_i − t_i)²/t_i  =  Σ t_i (u_i − 1)²
        H = diag(2t), a = 2t, constraints A·T·u ≤ b, bounds 0 ≤ u ≤ 1
     then map back z = T·u
  3. if BOTH fail -> INVALID_RUN (still fatal; never cash)
```

**Why this is defensible under the frozen contract:**

- **It is not a different solver.** Same `quadprog.solve_qp`, same Goldfarb–Idnani dual active-set.
- **It is not regularization.** No ridge, no jitter, no `H + λI`. `T` is a positive diagonal bijection,
  so the feasible set and the unique minimizer are **mathematically identical**. (In the scaled space the
  box is exactly `[0,1]ⁿ`, because `upper_i == t_i` for both the `y` and `x` blocks by construction.)
- **It cannot silently move existing results.** It engages only where the registered path *raises*. On
  the 99.7% of solves that already succeed, nothing changes — and where both formulations succeed they
  agree to **2.6e-15**, far below every registered tolerance.
- **It stays fully audited.** Every rescued solve still passes the complete registered battery: primal,
  dual, stationarity, complementarity, KKT, the two-sided lexicographic band audit, and the division-free
  post-target constraint re-check. A bad rescue would still be caught and would still be fatal.
- **It is deterministic and order-independent** — raw always first, scaled only on failure.
- **It introduces no economic change and no data-dependent tuning.**

**But the frozen Appendix B.3 says: _"No automatic retry with another solver. No fallback solver."_** A
retry on an exactly-equivalent reformulation of the *same* solver is arguably neither — but it is close
enough to the prohibition's intent that **I will not adopt it without your explicit registration.**

### Alternatives, if you prefer

- **A. Register the cascade** (recommended). Erratum against the v1.1 hash; no re-freeze; no economic change.
- **B. Register a different Stage-3 QP solver.** You previously rejected OSQP (ADMM + a guessing polish
  step) on sound grounds. I have no better-evidenced candidate to offer, and I would want to characterize
  any replacement across all 1,275 solves before recommending it.
- **C. Accept ~0.3% of sessions as `INVALID_RUN`.** I do **not** recommend this: it makes the development
  result depend on solver luck, and it is not what `INVALID_RUN` was registered to mean.

---

## 4. What I am NOT doing

- Not adopting any remedy unilaterally.
- Not raising `ε_include` (data-dependent tuning).
- Not converting the failure into a cash or zero-entry outcome.
- Not inspecting development performance.
- Not touching validation or sealed OOS.

**Awaiting your adjudication. Nothing further runs until you rule.**

---

## Appendix — reproduction

All inside the frozen `mr002-research:v1.1` image (`sha256:1b0939e5…`):

| Script | Purpose |
|---|---|
| `scripts/mr002_development_run.py` | the authorized A/B/C run — stops with `INVALID_RUN` |
| `scripts/mr002_diagnose_qp.py` | captures the first failing instance; proves HiGHS finds it feasible |
| `scripts/mr002_diagnose_qp2.py` | isolates the cause (band rows and tiny targets are **not** it; scaling is) |
| `scripts/mr002_characterize_qp_defect.py` | all 1,275 solves: per-method success, cross-method agreement |
| `scripts/mr002_qp_cascade_check.py` | proves all raw failures are rescued by the scaled retry |
| `scripts/mr002_test_inclusion_floor.py` | the `ε_include` sweep that refutes remedy 3 |
