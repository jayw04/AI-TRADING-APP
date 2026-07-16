# MR-002 v1.1 — IMPLEMENTATION ERRATA & SESSION-FUNNEL RECONCILIATION

**Date:** 2026-07-12 · **Status:** ✅ **Reconciliation complete — the 1,700-session A/B/C development
run is unblocked.**

| Bound artifact | SHA-256 |
|---|---|
| Pre-Registration v1.1 rev 3 (countersigned design) | `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Structural-Executability Adjudication (owner-accepted) | `ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e` |

Both hashes independently recomputed and confirmed. **No new design version and no re-freeze:** these
are implementation errata recorded against the artifacts above, per the owner's ruling of 2026-07-12.

---

## Part 1 — Errata (both approved as non-economic)

### E1 · Lexicographic-band audit inherits the primal feasibility tolerance

The Stage-3 retention and deployment bands are **rows of the primal system** and therefore inherit its
registered feasibility tolerance. The frozen audit is now:

```
R* − ε_retention − τ_primal  ≤  realized_R  ≤  R* + ε_retention + τ_primal
Q* − ε_new       − τ_primal  ≤  realized_Q  ≤  Q* + ε_new       + τ_primal

τ_primal = 1e-9   (= PRIMAL_RESIDUAL_MAX)
```

Registered in code as `TAU_PRIMAL`. **Changes no optimizer objective and no economically material
exposure.** It aligns the independent audit with the already-frozen primal-residual contract.

### E2 · Division-by-dust in reporting

The **authoritative compliance measure is the division-free homogeneous violation.** Gross-normalized
ratio fields are **reporting-only** and are emitted **only when `G > ε_active_sector = 1e-6`.** This
correction changes no order, position or constraint.

> **Permanent implementation-record lesson.** *A division-free solver formulation does not automatically
> protect downstream reporting.* The homogeneous constraint form (`expr − k·G ≤ 0`) was adopted precisely
> because the ratio form (`expr / G ≤ k`) is undefined at `G = 0` — the state that invalidated v1.0. The
> reporting layer re-introduced that division and manufactured ratios of 16.0 and 22.2 out of solver dust
> (~1e-17 NAV weight), while the constraints themselves were satisfied to 1.3e-16. **The pathology can
> re-enter anywhere a ratio is displayed.**

---

## Part 2 — Session funnel: **124 reconciles to 124, with no residual bucket**

| Registered session state | Sessions |
|---|---|
| `TERMINAL_SESSION_NO_EXECUTION_OPEN` | **1** |
| `FEASIBLE` (positive-entry sessions) | **17** |
| `VALID_ZERO_ENTRY_OUTCOME` | **103** |
| `EXECUTION_CONSTRAINED_INFEASIBLE` | **3** |
| `INVALID_RUN` | **0** |
| **Unclassified** | **0** |
| **Sum of states** | **124** |
| **Total scheduled sessions** | **124** |

The reconciliation is now **enforced in code**: the slice asserts `sum_of_states == total_sessions`, that
`FEASIBLE` sessions are exactly the sessions with new orders, and that every zero-entry session carries
exactly one registered reason. A funnel that fails to reconcile **stops the run**.

### The previously-missing session

**2013-06-28** — the slice's **last** session. There is no t+1 open *inside the window*, so **no execution
decision is made**. It is a **window-boundary artifact, not a market condition**. It was previously
emitted under an unregistered `"NO_EXECUTION_SESSION"` label that the summary silently dropped; it is now
the named state `TERMINAL_SESSION_NO_EXECUTION_OPEN`. In the 1,700-session run exactly one such session
occurs (the window's final one).

### `VALID_ZERO_ENTRY_OUTCOME` sub-reasons (103 = 98 + 5)

| Reason | Sessions | Meaning |
|---|---|---|
| `SOLVED_ZERO_DEPLOYMENT` | **98** | The LP ran and returned `Q* = 0`. A genuine solver outcome. |
| `NO_MATCHED_INCREMENT` | **5** | 2013-01-16, 01-17, 04-12, 06-12, 06-18. Candidates existed (2, 2, 1, 5, 3 after the gap filter) but were **one-sided**, so the frozen dollar-neutrality equality `Σ_new_long x = Σ_new_short x` admits no positive new increment. There are then **no decision variables**. This is the **inherited v1.0 sizing rule**, not a solver outcome. |

> **A mislabel caught during this reconciliation and corrected before shipping.** The slice filters
> zero-weight candidates *before* calling the solver, so `build_joint` could not distinguish "no candidates
> existed" from "candidates existed but received no matched increment", and initially reported these five
> as `NO_TRADABLE_HOLDINGS_NO_CANDIDATES` — which is **false**: candidates did exist. Only the caller has
> that information, so the label is now assigned by the caller. **No unclassified execution decision was
> found**; this was a reporting-fidelity defect, and it is exactly the kind of thing the funnel exists to
> surface.

---

## Part 3 — Determinism-hash coverage: **124 / 124**

A **canonical session-level determinism hash is now emitted for EVERY session**, including terminal,
zero-variable and execution-constrained ones, as the owner requested. It is a SHA-256 over the session
date, the registered outcome and zero-entry reason, the retained (`y`) and new (`x`) weights in canonical
permanent-identifier order serialized as **IEEE-754 hexadecimal**, and the exit/reduction/order counts —
i.e. **the session's entire executable decision**, not merely the solver's output.

| Measure | Coverage |
|---|---|
| **Session-level determinism hashes** | **124 / 124** |
| Per-solve hashes | 123 / 124 |

**The nine previously-missing hashes.** The old per-solve hash was emitted only on the solver's main
return path, so it was absent on every early return: **3** `EXECUTION_CONSTRAINED_INFEASIBLE` + **5**
`NO_MATCHED_INCREMENT` (zero decision variables) + **1** terminal session = **9**. All nine now carry a
session-level hash.

The two counts are reported **separately rather than conflated**. Per-solve coverage is 123, not 124,
because the terminal session **performs no solve** — there is nothing to hash at the solver level, and
manufacturing a hash there would assert a computation that never happened. Session-level coverage is
complete, which is what the audit requires.

**No reproducibility failure was found.** The corrected report is byte-identical across repeated runs in
the frozen image: `5bdafade980abee18fe2fed4fd3e7ed8a8a28faa39d84722632f1eb8f904436f`.

---

## Part 4 — Structural results are unchanged

The reconciliation changed **no order, no position, no constraint and no solver result**. Re-verified in
the frozen Linux/amd64 image (`sha256:1b0939e5…`):

- **27/27 fixtures pass.**
- 138 new orders across **17** sessions · 126 reductions · 105 exits · **0** `INVALID_RUN`.
- `max_homogeneous_violation` **1.34e-16** (limit 1e-9) · max KKT residual **1.14e-12** (limit 1e-8) ·
  max κ(H) **40,679** (limit 1e10) · LP statuses `{0}` only.
- Material gross on 18 sessions: median **4.52%**, max **7.08%** of NAV. Active sectors **6–9**.

---

## Status

**The session-count and hash-coverage reconciliation is complete and committed. No unclassified execution
decision and no determinism failure were found**, so no further owner review is required.

Per the adjudication, the structural-inspection prohibition is lifted and **the full A/B/C run over the
frozen 1,700-session development window (2013-01-02 → 2019-10-02) is authorized.** Performance may be
inspected **only within the development window**.

**Validation (850 sessions) and sealed OOS (850 sessions, config B, one opening) remain SEALED AND
UNREAD.**
