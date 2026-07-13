# MR-002 v1.1 — IMPLEMENTATION ERRATUM
## Execution Availability (Defect A) and ECI Semantics (Defect B)

**Date:** 2026-07-12 · **Status:** 🟡 **AWAITING SIGNATURE AND HASH.** No run has been executed under
this erratum.

| Bound artifact | SHA-256 |
|---|---|
| Pre-Registration v1.1 rev 3 (countersigned design) | `311e997b92858a7ede9f486ee7da11969703fc0304b2e6eb5c778ed8304f9dd5` |
| Structural-Executability Adjudication (accepted) | `ba980c4398b51d4ef4a0a3b77f687e62817b18beb5b3c281a7ab0fd1de3b947e` |
| Stage-3 Solver-Robustness Defect (escalation) | `41da8b0890b265ed5021c4afe83fe366a4ebdc3adc0fb72da193d161062053ed` |
| **Stage-3 Equivalent-Formulation Retry Erratum (countersigned)** | **`9ce8f53a4367c5817881cab55d9550db058a171e8ee504f57ad6a7060fe378fb`** |
| **Execution-Price / ECI Defect (escalation)** | **`9762b9eb775e3c72b427c9526a8fdb5aede2f0e7547cc266dd7e3baa5a7090f2`** |

All five hashes independently recomputed and confirmed.

**Classification: IMPLEMENTATION ERRATUM. No v1.2. No research-design re-freeze.**

**The Stage-3 cascade is NOT implicated and remains accepted unchanged.** Both defects are upstream of
the solver.

### Revision log

| Rev | Change |
|---|---|
| rev 1 | First draft (11,625 B, sha256 `3c72406a…`) — **SUPERSEDED, not countersigned.** |
| **rev 2** | **Resolves the price-availability vs numerical-floor contradiction.** rev 1 asserted *"valid registered open ⇔ position is executable"*, which would have flagged a **registered** v1.1 case as a Defect-A failure: a `BELOW_NUMERICAL_INCLUSION_FLOOR` position **has a valid open** yet is deliberately excluded from the `y` variables — **price-executable but not solver-reducible.** rev 2 registers the three distinct concepts (§1.1), the frozen classification sequence (§1.2), the corrected preflight equivalences and three new required-zero counters (§6), the per-ECI fixed-exposure breakdown by reason, and the corrected delayed-execution wording. |

---

## 1. Defect A — execution availability is not entry eligibility

### The frozen rule

> **For every held position, the next-open price is retrieved DIRECTLY from the frozen price store under
> the inherited four-series price policy, keyed by permanent identity and execution date.**
>
> **Held-position execution availability depends ONLY on whether the registered official execution-open
> bar exists.**

It must **not** depend on any of:

- monthly universe membership
- current z-score availability
- entry-side percentile eligibility
- current candidate status
- sector resolution used for **new-entry** eligibility

- A symbol leaving the top-250 / top-150 universe **does not prevent its exit.**
- A non-finite signal **does not prevent its exit.**
- A sector-resolution problem **must never fabricate a missing price** or block a registered hard exit
  when a valid open bar exists.

**No live fetch, no fallback vendor, no stale-price substitution is authorized. No entry-eligibility-induced
or discretionary delay is authorized. A hard exit may remain pending ONLY when the registered
execution-open bar is genuinely absent, under the inherited missing-open rule.**

> **Eligibility determines what may be ENTERED. Price availability determines what may be EXITED or
> REDUCED.**

### 1.1 THREE DISTINCT CONCEPTS (registered — they must never be conflated)

Price availability and numerical-floor classification are **different properties**. A below-floor position
is **price-executable but NOT solver-reducible**, and that is *registered v1.1 behavior*, not a defect.

| Concept | Determined by |
|---|---|
| **`execution_open_available`** | **ONLY** the frozen price store and the execution date. Nothing else. |
| **`hard_exit_executable`** | True **⇔** `execution_open_available` is true. |
| **`solver_reduction_eligible`** | True **only after hard exits**, when `execution_open_available` is true **AND** current exposure **> `ε_include`**. |

### 1.2 Frozen classification sequence

```
1. Retrieve the held position's registered open DIRECTLY from the price store.

2. If a hard exit is due:
       valid open    -> EXECUTE the exit
       missing open  -> keep the exit PENDING;
                        fixed_reason = NO_EXECUTABLE_OPEN

3. For a REMAINING position:
       no valid open
           -> fixed_reason = NO_EXECUTABLE_OPEN

       valid open AND exposure <= eps_include
           -> fixed_reason = BELOW_NUMERICAL_INCLUSION_FLOOR
              (price-executable, but deliberately excluded from the y variables —
               a REGISTERED numerical-floor case, NOT a Defect-A failure)

       valid open AND exposure > eps_include
           -> include as a TRADABLE y variable
```

> **No position with a valid bar may ever be classified `NO_EXECUTABLE_OPEN`.**

### What was wrong

`dataset.py` built `open_next` only for the day's PIT universe members, then skipped any member with a
non-finite `z` or an unresolved sector. Entry criteria were therefore deciding whether an **already-open
position could trade**.

| Measured (config A, 1,700 sessions) | |
|---|---|
| Held-position days | **3,048** |
| Marked `NO_EXECUTABLE_OPEN` | **1,389 (45.6%)** |
| …of which **a valid price bar EXISTS in the frozen store** | **948 — 68.3% SPURIOUS** |
| …genuinely missing bar (legitimate) | 441 |

It also blocked exits (`px` missing ⇒ *"exit stays PENDING"*), so positions that should have closed on the
5-session limit stayed open. And a single spuriously-fixed position destroys a whole session, because at
`y=0, x=0` the book **is** that position: `sector_gross / G = f / f = 1.00 > 0.20`.

---

## 2. Defect B — the `z = 0` probe is WITHDRAWN (registered-text correction)

### Why it was wrong

The `z = 0` probe tests only whether the **fixed book alone** is compliant **without using any available
retention or new-entry variable**. It does **not** test whether the complete joint feasible region is
empty. New entries **increase gross and diversify** a fixed exposure, and can satisfy the homogeneous
constraints.

*(This is the same scale-invariance that invalidated v1.0 — reappearing in the infeasibility **test**
rather than in the construction.)*

**Measured:** of the **1,371** sessions classified ECI in config A, HiGHS proves the LP **actually
feasible** on **261**.

### The replacement definition (FROZEN)

> **`EXECUTION_CONSTRAINED_INFEASIBLE` occurs when, after hard exits, fixed-exposure classification,
> candidate construction, and inclusion of every permitted `y` and `x` variable, the complete **Stage-1
> joint LP** returns HiGHS **status 2 — infeasible**. No combination of permitted retention and new
> entries can then satisfy the frozen coupling constraints.**

### Frozen classification logic

```
Stage-1 status 0
    -> continue the registered Stage-1 -> Stage-2 -> Stage-3 sequence

Stage-1 status 2  AND  at least one fixed exposure exists
    -> EXECUTION_CONSTRAINED_INFEASIBLE

Stage-1 status 2  AND  no fixed exposures
    -> INVALID_RUN                                      (FATAL)
```

The last case is **fatal** because with no fixed exposure, `y = 0, x = 0` **must** satisfy the homogeneous
constraints, the bounds and the neutrality equality. An infeasible result there indicates a **malformed
model or a numerical defect** — not an execution-constrained market state.

The old `y = 0, x = 0` calculation **may remain as a DIAGNOSTIC** showing whether the fixed book alone
breaches. **It must never determine the day classification.**

**This corrects a mathematical error in the registered text. It does not change the intended economic
rule.**

---

## 3. Disposition of the completed run

Recorded permanently as:

```
DISCARDED — INVALID IMPLEMENTATION PATH
HELD_EXECUTION_PRICE_FILTERED_BY_ENTRY_ELIGIBILITY
ECI_CLASSIFIED_BY_INVALID_ZERO-VARIABLE_PROBE
PERFORMANCE INSPECTED BUT VOID
NO MR-002 RESEARCH VERDICT
VALIDATION UNREAD
SEALED OOS UNREAD
```

**Do not resume it. Do not reuse its position state, ledgers, fills, candidate decisions or performance
summaries.**

The void figures remain **only** in the defect evidence, as a measure of distortion. **They are not an
MR-002 development result and must not influence any economic-design change.**

Seeing development performance **does not consume validation or sealed OOS.** The development window is
permitted for implementation discovery — **but the observed void figures may not motivate changes to
thresholds, limits, gates, signals or costs.**

---

## 4. Stage-3 cascade — implementation notes approved for the permanent record

**(a) Version pin.** The `quadprog` **module exposes no `__version__` attribute**; the frozen manifest's
`"0.1.13"` came from the pip report. The pin reads the installed **distribution metadata**:

```python
from importlib.metadata import version
assert version("quadprog") == "0.1.13"
```

**The installed Linux artifact hash must STILL match the frozen runtime manifest
(`cc1996a0e3de1d423f8662fe21368948afdc91d851910b77320caaf7c15357ff`). Version metadata alone is NOT
sufficient.**

**(b) Lower-bound multiplier fixture.** The strengthened fixture is approved. It must demonstrate that:

1. **Untransformed** scaled-space bound multipliers **FAIL** original-coordinate stationarity, and
2. applying **`μ_z,i = μ_u,i / t_i`** **restores** stationarity within the registered limit.

*(The original fixture proved nothing: the objective's optimum sits ON the upper bound, where the gradient
vanishes, so every bound multiplier was ≈ 0 and dividing by `t` changed nothing. It now drives a variable
onto its LOWER bound, where the multiplier is nonzero and the ~1e8 amplification is genuinely exercised.)*

**The existing suite count is therefore correctly 45.**

---

## 5. Required new fixtures — **10**, bringing the minimum suite to **55**

1. Held position **leaves the ranking universe** but has a valid open ⇒ **hard exit executes**.
2. Held position has a **non-finite z** but a valid open ⇒ **reduction executes**.
3. Held position is **not entry-sector-resolved** but has a valid open ⇒ **a scheduled exit is not blocked**.
4. **Genuine missing open** ⇒ `NO_EXECUTABLE_OPEN`, and the exit **stays pending**.
5. **Every** held-position day with a valid registered bar is classified **executable**.
6. Fixed-only `z = 0` book **breaches**, but Stage 1 finds a **feasible diversifying** solution ⇒ the day
   is **NOT** ECI.
7. Stage-1 **status 2 with fixed exposures** ⇒ **ECI**.
8. Stage-1 **status 0 can NEVER** be labelled ECI.
9. Stage-1 **status 2 with NO fixed exposure** ⇒ **`INVALID_RUN`**.
10. The **five-session mandatory exit remains enforceable** after a symbol leaves the entry universe.

---

## 6. Structural-gate ruling

**Do NOT merely replace 124 sessions with an arbitrary longer calendar slice.** The weakness was
**behavioral coverage**, not length.

- **Keep the 124-session slice** as the **bootstrap gate**.
- **Add a second held-position lifecycle gate** covering **mature-book** paths.

### Full-window execution-state PREFLIGHT (A/B/C, performance aggregation DISABLED)

Before calculating or inspecting **any** replacement development performance, the preflight must prove:

```
for every held-position day:
        valid registered open exists    <=>   execution_open_available

NO_EXECUTABLE_OPEN
        <=>   NO valid registered open exists in the frozen store

valid open AND exposure > eps_include, after hard exits
        =>    solver_reduction_eligible

BELOW_NUMERICAL_INCLUSION_FLOOR
        =>    a valid open MAY exist, but the exposure is fixed for the separately
              registered NUMERICAL-FLOOR reason  (this is NOT a Defect-A failure)

every ECI:
        Stage-1 status == 2   AND   at least one fixed exposure exists

no Stage-1 status 0:
        is classified ECI

every pending hard exit:
        is explained by a genuinely absent execution open

every session:
        has a reconciled outcome and a canonical decision hash
```

> **Note.** The equivalence is on **`execution_open_available`**, *not* on "executable". A below-floor
> position is **price-executable but not solver-reducible** — a registered v1.1 case. Asserting
> `valid open ⇔ position is executable` would have wrongly flagged it as a Defect-A failure.

### Required preflight report

```
held_position_days
held_days_with_valid_open
held_days_without_valid_open
NO_EXECUTABLE_OPEN count
false_missing_open count                = REQUIRED 0
hard_exits_due
hard_exits_executed
hard_exits_pending_for_missing_open
Stage-1 feasible sessions
Stage-1 infeasible sessions
ECI sessions
ECI_without_status_2                    = REQUIRED 0
status_2_without_fixed_exposure         = REQUIRED 0

NO_EXECUTABLE_OPEN_with_valid_bar       = REQUIRED 0
solver_eligible_without_valid_bar       = REQUIRED 0
below_floor_misclassified_as_no_open    = REQUIRED 0
```

### Per-ECI-session fixed-exposure breakdown BY REASON

```
fixed_no_open_count
fixed_no_open_weight
fixed_below_floor_count
fixed_below_floor_weight
```

**Once the preflight passes, its immutable decision and execution ledgers may be used for performance
aggregation. The logic must NOT differ between the structural preflight and the performance
calculation.**

---

## 7. Repository hygiene

**Do NOT rewrite the pushed history** solely to remove the accidentally-committed `.pyc` and `.parquet`
files. The corrective deletion-and-ignore commit **preserves the audit trail**. *(Done: commit
`14e1207`.)*

Before rebuilding:

1. Confirm they are **absent from the current tree**.
2. Add them to **both `.gitignore` and the research-image `.dockerignore`**.
3. Confirm **none enters the container build context**.
4. **Regenerate the image digest and runtime manifest.**
5. Confirm **none appears in the frozen evidence or input manifests**.

---

## 8. Registered sequence (after signature and hash)

1. Rebuild and hash the frozen Linux/amd64 research image (with `.dockerignore`).
2. Update and hash the solver-runtime manifest and dependency records.
3. Run the expanded fixture suite (**≥ 55**).
4. Rerun the **124-session bootstrap slice**; confirm decision-hash behavior.
5. Run the **held-position lifecycle gate**.
6. Run the **full-window execution-state preflight** over A/B/C with performance aggregation **disabled**;
   every required-zero counter must be **0**.
7. Restart the complete A/B/C **1,700-session development run from session 1** on clean immutable state,
   using the **same** logic as the preflight.
8. Produce the **byte-identical** same-image rerun.
9. **Stop for Implementation Freeze review.**

**Performance inspection remains PROHIBITED until the preflight passes and the clean development run
completes. Validation and sealed OOS remain SEALED AND UNREAD.**

---

*Awaiting signature and hash. Nothing has been run under this erratum.*
