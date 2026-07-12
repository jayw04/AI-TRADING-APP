# MR-002 — Pre-Registration **v1.1** (RE-FREEZE CANDIDATE · **rev 2, corrected**)
## Portfolio-Construction Correction

**Date:** 2026-07-12 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** Running (v1.0
retired without a research verdict) · **Status:** 🟡 **RE-FREEZE CANDIDATE — awaiting signature. No
pipeline run has been made under v1.1.**

**Scope: PORTFOLIO CONSTRUCTION ONLY.** Everything else is inherited **unchanged and unread** from v1.0.

---

## 0. Revision log (rev 1 → rev 2)

Issued in response to the conditional-approval review. The four freeze blockers are corrected; the
solver appendix is completed; the two wording corrections are made.

| # | Item | Disposition |
|---|---|---|
| B1 | Sealed-OOS "opened once" contradiction | **Corrected** — §2.2 |
| B2 | PIT-SIC "no forward-fill" paraphrase | **Corrected** — §2.1, exact inherited rule + immutable hash reference |
| B3 | Linearized combined-book equations absent | **Added** — Appendix A |
| B4 | "Valid no-trade day" misnamed | **Corrected** — renamed `VALID_ZERO_ENTRY_OUTCOME`, §6 |
| S | Solver acceptance specification incomplete | **Completed** — Appendix B |
| W1 | Active-sector count vs the 1e-6 reporting threshold | **Corrected** — §8 |
| W2 | "post-rounding constraint breach" | **Corrected** — "post-target or post-execution constraint breach", §6 / B.4 |
| **D1–D4** | **Four proposed deviations from the review — forced by measured solver behavior, or by an over-broad consequence** | **§10 — flagged for the owner's ruling; NOT silently adopted** |

---

## 1. v1.0 disposition (governance record — unchanged from rev 1)

**MR-002 v1.0 — Research Design Invalidated · Implementation Infeasible Before Validation.**

Not a strategy rejection, not evidence against residual mean reversion, not a failed backtest, not a
material implementation defect, and not grounds to open validation or sealed OOS. **No economically
valid MR-002 portfolio has yet been tested.**

| Evidence | Record |
|---|---|
| Zero-order structural result | Config B: **0 orders on all 124 development sessions**; 8/8 registered constraint fixtures passed, proving the engine executed the registered rules faithfully (`MR002_DEV_FINDING_ConstraintInfeasibility_v1.0.md`) |
| Cause | Relative limits are **scale-invariant**: curing a breach by removing a candidate **shrinks G**, which **raises every remaining ratio** → the removal cascade is self-reinforcing and consumes the batch. Best day (25 candidates, 37.5% batch gross): a 1.5% position is 4.0% of gross; the 5% sector-net cap admits ~1.25 net positions/sector; all 25 removed |
| Failed iterative-scaling prototype | Continuous per-sector down-scaling **does not converge** (200 iterations; residual sector-net 0.196 vs cap 0.05; beta 0.123 vs 0.10). **Permanently rejected** |
| LP feasibility demonstration | A **simultaneous** downward-only solve on the identical 2013-04-29 batch: **13 orders, 6.19% gross, every limit satisfied** (sector-gross 0.2000, sector-net 0.0500, beta 0.0052, long gross = short gross, no weight above its registered start) |
| Two-position counterexample | Sequential existing-book repair **liquidates the book to zero**; the **joint** solve retains 1.667% NAV of existing exposure and places 10 new orders at 16.67% combined gross, all limits satisfied |

**Rejected v1.0 in-place alternatives:** target-gross ramp denominator (loosens the controls exactly
where they bind) · absolute NAV-denominated sector limits (a different risk policy: at 15% gross a
5%-of-NAV sector-net allowance is 33% of actual gross) · per-sector position counts (counts do not
control dollar weights, inverse-vol sizing, imbalance or beta) · broadened candidate batch (a new
research design, not a defect fix) · the 100%-of-NAV denominator I originally proposed (**withdrawn**).

---

## 2. Inherited UNCHANGED from v1.0 (immutable)

Hypothesis · signal construction (PIT-recursive orthogonalized sector factor; betas t−60…t−1;
mean-adjusted 5-day residual z with t−1 normalization; 60 complete observations; ddof=1; no
winsorization) · configurations **A 1.75 / B 2.00 (sole verdict config) / C 2.25** · entry rule (|z| ≥
z_entry **and** extreme decile of the side-eligible pool) · 5-session max hold · exit ladder · PIT
estimated earnings-risk blackout (70 calendar days + 2-session cooling; BMO/AMC semantics) · universe
(top-250 long / top-150 short, monthly PIT) · identity crosswalk + countersigned predecessor registry ·
four-series price policy · economic-gap filter · next-open execution · costs (10 bps/side; borrow 50
bps/yr ÷ 360) · $10M NAV · 2% ADV participation cap (**clip, never delay**) · **all pass gates and
floors** · accepted exclusions · **§8a windows and hashes**.

### 2.1 **[B2 — CORRECTED]** PIT-SIC classification chain (exact inherited rule)

> **PIT-SIC effective-dated chain:** a SIC becomes effective at its filing-acceptance timestamp and
> remains effective until the next accepted filing supplies a new valid SIC. **A missing SIC does not
> overwrite the last valid observation. No current-classification fallback is permitted.**

The rev-1 shorthand "no forward-fill" is **withdrawn** — it wrongly implied that a valid observation
does not carry forward. Two further inherited clauses are restated here so the shorthand cannot be read
as having relaxed them either:

- **No pre-observation backfill.** A SIC is never effective *before* its first accepted observation.
  Sessions preceding a security's first accepted SIC filing have **no** classification.
- **Unresolved ⇒ ineligible.** A security whose sector cannot be resolved on session *t* through
  identity → PIT-SIC → sector-ETF is **ineligible on t**. It is never defaulted, never assigned a
  fallback sector, and never carried by a current classification.

**Authoritative source (takes precedence over any paraphrase in this document):**
`TradingWorkbench_MR002_PreRegistration_v1.0_FROZEN.md`, PIT-SIC section, as hashed in
`MR002_SealedManifest_v1.0.json`. Supporting immutable artifacts: `MR002_PITSIC_Gate_v2.0.json`
(98.48% overall; every year ≥ 95%) and `predecessor_override_registry_v1.0.csv` (21/21 countersigned).
**v1.1 changes no data rule.**

### 2.2 **[B1 — CORRECTED]** §8a windows

3,400 sessions, 2013-01-02 → 2026-07-10.

| Window | Range | Sessions | Status |
|---|---|---|---|
| Development | 2013-01-02 → 2019-10-02 | 1,700 | in use |
| Validation | 2019-10-03 → 2023-02-16 | 850 | **sealed and unread** |
| **Sealed OOS** | 2023-02-17 → 2026-07-10 | 850, **config B only** | **currently sealed and unread; designated for ONE future opening, after validation and all prerequisite gates** |

The rev-1 phrase "opened once" is **withdrawn** — it wrongly implied the sealed sample had already been
consumed. **Neither the validation window nor the sealed OOS window has ever been read.** Their
untouched status is exactly what permits v1.1 to reuse them without a fresh sample.

Artifact hashes unchanged (`MR002_SealedManifest_v1.0.json`, 16 artifacts).

**Gates explicitly NOT changed:** ≥500 trades · ≥100 long / ≥100 short · return and Sharpe gates ·
candidate thresholds · sector limits (20% / 5%) · beta limit (0.10) · net-drift band (5%).

---

## 3. THE CHANGE — joint retention-and-entry optimization

After processing hard exits at the execution open:

| Symbol | Meaning |
|---|---|
| `f_j` | **fixed** existing exposure — no executable open at this session; **cannot trade** |
| `y_j` | retained exposure of a **tradable** existing position |
| `c_j` | its current exposure |
| `x_i` | new candidate exposure |
| `w_i` | its registered unconstrained inverse-residual-volatility weight (1.5%-NAV cap and 2%-ADV clip already embedded) |
| `d_p ∈ {−1,+1}` | the position's **fixed** direction |

**`f`, `y`, `c`, `x`, `w` are non-negative ABSOLUTE NAV weights. Direction is carried ONLY by `d`.**

Bounds:

```
0 ≤ y_j ≤ min(c_j, 0.015)          tradable existing positions
0 ≤ x_i ≤ min(w_i, 0.015) = w_i    new candidates (the cap is already embedded in w)
```

No held symbol may also appear as a new-order variable (**no pyramiding, no same-open re-entry** —
unchanged). All constraints apply to the **complete post-trade book**; the full linearized system is
frozen in **Appendix A**.

New entries remain dollar-neutral: `Σ_{new long} x_i = Σ_{new short} x_i`.

The registered **net-drift band applies to the complete post-trade portfolio**. The solver may retain an
existing imbalance when diversifying new orders bring the resulting book inside the band.

> **Note on the `y_j ≤ 0.015` bound.** In v1.0 the 1.5% cap was applied only at **entry sizing**; the
> registered drift rule is a **portfolio-net** band (|net| ≤ 5% of gross), not a per-position one, so a
> held position that appreciated past 1.5% of NAV was never trimmed. The bound above makes 1.5% a **hard
> post-trade invariant**, which will trim appreciated winners at their next executable open and therefore
> **adds turnover and cost** that v1.0 did not have. This is registered here explicitly and honestly: it
> is the **conservative** direction on risk, it is not adopted to improve expected performance, and the
> Stage-3 objective means the bound binds only when it must (`y_j = min(c_j, 0.015)` exactly). Flagged
> so it is a decision, not a side-effect.

### 3.1 Lexicographic stages (frozen)

**Stage 1 — minimize forced liquidation.** `maximize R = Σ_j y_j`. **`x` participates in the feasibility
constraints during this stage** — intentionally: eligible new positions may supply the diversification
that permits existing positions to be retained.

**Stage 2 — maximize new deployment.** Subject to `R ≥ R* − ε_retention`: `maximize Q = Σ_i x_i`.

**Stage 3 — unique closest allocation.** Subject to `R ≥ R* − ε_retention` **and** `Q ≥ Q* − ε_new`:

```
minimize D = 1.0 · Σ_j (y_j − c_j)² / c_j  +  1.0 · Σ_i (x_i − w_i)² / w_i
```

Every included `c_j`, `w_i` is strictly positive (variables at or below the inclusion floor are removed
before matrix construction — **D3**), so the Hessian is diagonal and positive definite and the Stage-3
optimum is **unique**.

**Block coefficients are registered as 1.0 / 1.0** — an economic rule, not a mathematical inevitability.
**They must never be tuned using development performance.**

Signal strength and identifier tie-breaks are **not** optimization objectives. Permanent identifiers are
the **canonical ordering** for variables, matrices, logs and serialization. **A materially different
second Stage-3 solution is a DEFECT, not an economic tie.**

The LP **optimal value** `R*` (and `Q*`) is unique even when the optimal **vertex** is not. A different
returned vertex is therefore *not* a defect; a different Stage-3 allocation is.

---

## 4. Frozen tolerances

| Symbol | Value | Unit | Rationale |
|---|---|---|---|
| `ε_retention` | **1e-8** | NAV weight | 100× the pinned solver feasibility tolerance (**D2**). $0.10 on a $10M book — economically zero, far below any executable quantum |
| `ε_new` | **1e-8** | NAV weight | as above |
| `ε_include` | **1e-8** | NAV weight | Hessian-conditioning inclusion floor (**D3**) |
| `ε_active_sector` | **1e-6** | NAV weight | **reporting threshold only** (§8) — never a constraint input |

---

## 5. Solver stack

| Stage | Method |
|---|---|
| Stages 1 & 2 (LP) | `scipy.optimize.linprog(method="highs-ds")` — **dual simplex pinned**; the generic `"highs"` may switch between dual simplex and interior point and is therefore **not** registered |
| Stage 3 (QP) | `quadprog.solve_qp` — Goldfarb–Idnani **dual active-set** method |

> **Wording (owner correction, retained):** quadprog is a **numerical** solver, not an *exact* one.
> Goldfarb–Idnani has finite active-set properties in exact arithmetic; the implementation is
> floating-point and does **not** produce exact KKT multipliers. **Acceptance depends on the registered
> primal / dual / stationarity / complementarity residual checks in Appendix B — never on a claim of
> exactness.**

The complete, binding solver contract — the options actually honored, accepted results, fatal
conditions, residual *definitions*, warning policy, determinism controls and the runtime manifest — is
**Appendix B**.

---

## 6. Day-outcome classification (frozen)

| Outcome | Definition | Behavior |
|---|---|---|
| **`VALID_ZERO_ENTRY_OUTCOME`** **[B4 — renamed]** | Stages 1 and 2 optimal **and** `Q* = 0` within tolerance | **No new entries submitted.** Existing positions are **retained or reduced** per the Stage-1/Stage-3 solution; previously scheduled exits remain effective. **It is a full-cash day only when no post-trade positions remain.** Recorded, not an error |
| **`EXECUTION_CONSTRAINED_INFEASIBLE`** | **Fixed, non-tradable** exposures (`f`) violate a **coupling** constraint (sector gross, sector net, beta, net drift, `G ≤ 1`) even with all `y = 0` and all `x = 0` | Submit **no new entries**; pending exits stay governed by the missing-open rule; **record the unavoidable breaches**; resume joint optimization at the next executable open. **Not** a solver failure and **not** a `VALID_ZERO_ENTRY_OUTCOME` |
| **`UNAVOIDABLE_FIXED_BREACH`** **[D1 — proposed]** | A **fixed** position's own exposure exceeds the 1.5% position cap | **Per-position** record, reported in the daily audit. Does **not** halt the day — see **D1** |
| **`INVALID_RUN` — FATAL** | Any fatal condition in Appendix B: non-optimal LP status · quadprog exception · time or iteration limit · residual failure · lexicographic-band violation · **any solver warning** · **post-target or post-execution constraint breach [W2]** · non-deterministic canonical output | **STOPS the development run.** A solver failure is **never** converted into a no-trade day — that would introduce data-dependent missing orders |

The rev-1 term "valid no-trade day" is withdrawn: `Q* = 0` does **not** imply no trading. Reductions
(`y < c`) and hard exits may still execute on such a day. This distinction is required for fill counts,
breadth reporting and the daily audit classification. A `VALID_ZERO_ENTRY_OUTCOME` day contributes to
the breadth gates (≥500 trades, ≥100 long, ≥100 short) only through the fills it actually generates.

---

## 7. Shares and rounding (frozen)

**Fractional shares** (inherited from v1.0). **No integer rounding. No minimum-lot constraint.**
`shares = target notional ÷ execution price`. **Rounding-loss fields are zero by construction.** A live
implementation would require a separately governed integer/fractional-broker feasibility layer — **out
of research scope**. This prevents an unregistered rounding repair from reintroducing the denominator
cascade.

---

## 8. Low gross is an INTENDED consequence · sector topology

> Sparse, sector-clustered residual signals combined with the frozen 5%-of-actual-gross sector-net limit
> may result in **low gross exposure, slow capital deployment and frequent cash holdings. This is an
> intended consequence of retaining the registered risk limits, not an implementation defect.**

**Sector-topology arithmetic (registered).** Sector gross sums to total gross and no sector may exceed
20% of gross ⇒ **any positive feasible portfolio requires at least FIVE sectors with strictly positive
gross exposure**; with exactly five, each must sit at exactly 20% of gross.

**[W1 — CORRECTED] Theory vs reporting.** The **theoretical** positive-sector count is **≥ 5**. The
**reported active-sector count** applies the frozen reporting threshold `sector_gross > ε_active_sector`
(1e-6 NAV weight) and **may differ from the theoretical count solely because of that reporting
tolerance** — a mathematically positive sector below 1e-6 is not counted as active. The threshold is a
reporting convention and **never** a constraint input.

**If MR-002 later fails the breadth or return gates because gross remains low, that is a legitimate
research result.** No gate, threshold or limit will be changed on that account.

---

## 9. Fixture suite (all must pass BEFORE the structural rerun)

**Inherited (8):** bootstrap-succeeds · single-sector rejection · batch-order invariance · denominator
recomputation · cascading breach · zero-gross · low-gross combined-gross · position cap + ADV clip.

**New joint-solve (16):**
1. Two-position counterexample — sequential repair liquidates; **joint solve retains and diversifies**.
2. Full retention when new candidates make the combined book feasible.
3. **Minimum** forced liquidation when full retention is impossible.
4. Empty existing book reduces exactly to the approved new-order LP/QP.
5. No eligible new candidates ⇒ only **necessary** existing reductions.
6. Genuine joint `R* = 0, Q* = 0` accepted without error.
7. Stage-1 and Stage-2 **degenerate** LP optima produce the **same unique** Stage-3 allocation.
8. Stage-3 output **independent of the vertex** HiGHS returns.
9. Candidate **and existing-position** shuffle ⇒ byte-identical orders.
10. **No existing position increases.**
11. **No new candidate exceeds its registered starting weight.**
12. New entries remain **exactly** side-matched.
13. Combined drift-band handling on the complete post-trade portfolio.
14. Fixed non-tradable position ⇒ **`EXECUTION_CONSTRAINED_INFEASIBLE`** (not solver failure, not `Q*=0`).
15. Solver failure **stops the run** (never becomes cash).
16. Primal, dual, stationarity and complementarity residuals pass; iterative-scaling non-convergence
    **permanently rejected** (regression-locked).

**Added by rev 2 (3 — conditional on the §10 rulings):**

17. A fixed position above the 1.5% cap is recorded as `UNAVOIDABLE_FIXED_BREACH` and does **not** halt
    the day, while a fixed **coupling** breach **does** (**D1**).
18. A silently-rejected solver option raises `INVALID_RUN` instead of reverting to a default (**D2**).
19. An existing exposure decayed below `ε_include` is carried as **fixed `f`** — never dropped from the
    accounting — and never enters the Hessian (**D3**).

**Total: 27 fixtures**, all run inside the frozen Linux research image (**D4**).

---

## 10. **Proposed deviations from the review — owner ruling required**

Not silently adopted. Three are forced by **measured** behavior of the registered stack; one is a
judgment call about an over-broad consequence. **None is an economic-performance change.**

### D1 — Do **not** let a fixed over-cap position halt the whole day  *(judgment call — please rule)*

The review states: *"A fixed position above the position cap can create EXECUTION_CONSTRAINED_INFEASIBLE."*

That is true **only if** the 1.5% cap is modeled as a constraint over all post-trade positions
*including* `f`. Modeled that way, a single non-tradable position that has appreciated to, say, 1.6% of
NAV renders the LP infeasible and **shuts down the entire book for that session** — no entries, no
retention optimization — even though the rest of the book is perfectly feasible and the breach is
uncurable by any `y` or `x`.

The position cap is naturally a **bound on decision variables**, not a coupling constraint: a fixed
position has **no decision variable**, so no `y` and no `x` can ever cure it, and no feasible point
exists at any `G`. Declaring the day infeasible therefore punishes the whole book for a condition that
is (a) uncurable and (b) already fully recorded.

**Recommendation:** apply the cap as a **bound on `y` and `x` only**; record a fixed over-cap position as
`UNAVOIDABLE_FIXED_BREACH` (per-position, auditable, reported in the daily record); and **reserve
`EXECUTION_CONSTRAINED_INFEASIBLE` for the coupling constraints** (sector gross, sector net, beta, net
drift, `G ≤ 1`), which genuinely admit no feasible point.

This is conservative on risk either way — the breach is uncurable and recorded under both readings —
while preserving the strategy's ability to trade, which is the property v1.1 exists to restore.
**If you prefer the strict reading, say so and I will register the halt instead. Both are implementable;
fixture 17 pins whichever you choose.**

### D2 — `ε` must be **1e-8**, tolerances pinned at **1e-10**, and **warnings must be FATAL**  *(measured)*

Measured on the registered stack (SciPy 1.18.0 / bundled HiGHS):

- HiGHS's feasibility-tolerance **floor is 1e-10**. Any tighter value is **silently rejected**.
- On rejection SciPy emits only an `OptimizeWarning` (*"Invalid option value"*), **falls back to the
  HiGHS default of 1e-7, and still returns `success=True`, `status=0`.**

Two consequences:

1. **rev 1's `ε_retention = ε_new = 1e-9` is only 10× the tightest achievable feasibility tolerance** —
   the Stage-2/Stage-3 band `R ≥ R* − ε` would sit within one order of magnitude of solver noise.
   **Proposed: `ε = 1e-8` with `primal/dual_feasibility_tolerance = 1e-10`** → a 100× margin. In NAV
   weight 1e-8 is **$0.10 on a $10M book** — economically zero.
2. **Every solver warning is FATAL** (`warnings.simplefilter("error")` around each solve). This is the
   answer to *"treatment of warnings"*, and it is not a formality: the silent path is precisely the one
   that reverts a registered tolerance to a default **while still reporting success**. A run could
   otherwise pass every check without having executed the registered contract.

### D3 — Hessian-conditioning inclusion floor `ε_include = 1e-8`  *(measured)*

The Stage-3 Hessian is diagonal with entries `2/c_j`, `2/w_i`. An exposure decayed toward zero drives
`2/c_j → ∞`. Measured condition numbers: `c_min = 1e-4 → 150`; `1e-6 → 1.5e4`; `1e-8 → 1.5e6`; below
that it degrades without bound and quadprog's positive-definiteness check becomes unreliable
(`ValueError: matrix G is not positive definite`).

**Proposed:** variables with `c_j` or `w_i` **≤ `ε_include` = 1e-8** are excluded from the matrices.
Crucially, an excluded **existing** position is **carried as fixed `f`** — *not* dropped — so its
(negligible) exposure still enters `G`, the sector sums and beta: **no exposure ever vanishes from the
accounting.** An excluded candidate simply generates no order. `cond(G)` is logged per solve;
`cond(G) > 1e10` is **FATAL**.

### D4 — The frozen runtime is **Linux/amd64**; **no** structural evidence will be produced on Windows  *(agreed, and extended)*

I agree with the review and go further: **I will not run the structural slice on Windows at all**, not
even as a preview. The Windows/AMD64 `quadprog` wheel hash registered in rev 1 is **WITHDRAWN**.

The frozen runtime is a dedicated **Linux/amd64 `mr002-research` container** — a standalone research
image, **not** the workbench Docker Compose stack (which the repository conventions forbid starting on
this machine). It is fully offline: it mounts only the frozen research store `mr002_research.duckdb` and
touches no live database, no broker connection and no market-data websocket.

Before any v1.1 structural rerun: build that image; regenerate and hash the dependency lockfile; emit the
**solver-runtime manifest** (B.6); and **run the complete 27-fixture suite inside it**. The structural
slice and the determinism rerun use that same image. At Implementation Freeze the final
application-image digest is recorded and the byte-identical determinism check is re-run there.

---

## 11. Sequence after re-freeze (no deviation)

1. Owner signs the corrected v1.1 **and rules on D1–D4**.
2. Build the Linux research image; lock and hash dependencies; emit the solver-runtime manifest.
3. Implement the joint solver; run the **full 27-fixture suite inside that image**.
4. Rerun the **124-session structural slice**.
5. **Permitted inspection:** retention and deployment gross · nonzero-feasible days ·
   `VALID_ZERO_ENTRY_OUTCOME` days · `EXECUTION_CONSTRAINED_INFEASIBLE` days · order counts · sector
   topology · binding constraints · solver statuses and residuals · determinism hashes.
   **Prohibited until structural executability is accepted:** P&L · returns · Sharpe · hit rate ·
   drawdown · configuration comparisons.
6. **Declared in advance:** *no further economic-design change will be made merely because gross,
   feasible-day count or order count is lower than hoped. Only an implementation or mathematical defect
   may reopen v1.1.*
7. Then the full A/B/C development run → Implementation Freeze review.

**Validation and sealed OOS remain sealed and UNREAD.**

---

## 12. Changelog (narrow — portfolio construction only)

v1.0 → v1.1: the whole-candidate removal cascade is **replaced** by a **joint, downward-only,
three-stage lexicographic optimization** over existing retention `y` and new orders `x`, evaluated on the
complete post-trade portfolio against **actual gross**. The solver stack, tolerances, determinism
controls, day-outcome semantics, the fractional-share rule, the sector-topology arithmetic and the
expanded fixture suite are registered. The 1.5% position cap becomes a hard post-trade invariant (§3
note). **No signal, universe, identity, temporal, cost, window, gate or exclusion change.**

**Trial/design ledger:** MR-002 v1.0 (invalidated, no verdict) and MR-002 v1.1 (this document) are both
permanent entries in the research history.

---
---

# Appendix A — **[B3]** Frozen linearized combined-book system

**`f`, `y`, `c`, `x`, `w` are non-negative ABSOLUTE NAV weights. Direction is carried ONLY by
`d_p ∈ {−1, +1}`, which is fixed and never a decision variable.**

Index sets: `F` = fixed (non-tradable) existing positions · `E` = tradable existing positions ·
`N` = new candidates. `F_k`, `E_k`, `N_k` are their restrictions to sector `k`.

## A.1 Decision variables and bounds

```
0 ≤ y_j ≤ min(c_j, 0.015)          j ∈ E
0 ≤ x_i ≤ min(w_i, 0.015) = w_i    i ∈ N     (the 1.5% cap and the 2% ADV clip
                                              are already embedded in w_i)
```

`f_j` (j ∈ F) is a **constant**, not a variable.

## A.2 Linear forms

```
G               = Σ_{j∈F} f_j        +  Σ_{j∈E} y_j        +  Σ_{i∈N} x_i

sector_gross_k  = Σ_{j∈F_k} f_j      +  Σ_{j∈E_k} y_j      +  Σ_{i∈N_k} x_i

sector_net_k    = Σ_{j∈F_k} d_j f_j  +  Σ_{j∈E_k} d_j y_j  +  Σ_{i∈N_k} d_i x_i

portfolio_beta  = Σ_{j∈F} d_j β_j f_j + Σ_{j∈E} d_j β_j y_j + Σ_{i∈N} d_i β_i x_i

portfolio_net   = Σ_{j∈F} d_j f_j    +  Σ_{j∈E} d_j y_j    +  Σ_{i∈N} d_i x_i
```

Because every weight is absolute and non-negative, **`G` is a linear form** — no absolute value, no
disjunction, no binary variable. That is what makes the system an LP.

## A.3 Frozen inequalities (homogeneous in `G` — **no division anywhere**)

```
 sector_gross_k − 0.20 · G  ≤ 0        for every sector k
  sector_net_k  − 0.05 · G  ≤ 0        for every sector k
 −sector_net_k  − 0.05 · G  ≤ 0        for every sector k
 portfolio_beta − 0.10 · G  ≤ 0
−portfolio_beta − 0.10 · G  ≤ 0
  portfolio_net − 0.05 · G  ≤ 0        net-drift band, complete post-trade book
 −portfolio_net − 0.05 · G  ≤ 0
              G             ≤ 1.00
```

Equality (new entries dollar-neutral):

```
Σ_{i ∈ N, d_i = +1} x_i  −  Σ_{i ∈ N, d_i = −1} x_i  =  0
```

**When `G = 0` every linearized constraint is satisfied trivially — there is no division and therefore no
zero-denominator case.** This is precisely the pathology that destroyed v1.0: the ratio form
`sector_gross_k / G ≤ 0.20` is undefined at `G = 0` and scale-invariant above it. The homogeneous form
above is mathematically equivalent for `G > 0` **and** well-defined at `G = 0`.

## A.4 Position cap

The 1.5% cap enters as the **variable bound** in A.1. A **fixed** position with `f_j > 0.015` cannot be
cured by any `y` or `x`; its disposition is **D1** (owner's ruling pending).

## A.5 Objectives

```
Stage 1:   maximize   R = Σ_{j∈E} y_j
Stage 2:   maximize   Q = Σ_{i∈N} x_i        s.t.  R ≥ R* − ε_retention
Stage 3:   minimize   D = 1.0 · Σ_{j∈E} (y_j − c_j)²/c_j
                        + 1.0 · Σ_{i∈N} (x_i − w_i)²/w_i
                                             s.t.  R ≥ R* − ε_retention
                                                   Q ≥ Q* − ε_new
```

**All A.3 constraints and all A.1 bounds apply at every stage.**

---
---

# Appendix B — Binding solver contract

## B.1 LP stages (1 and 2)

`scipy.optimize.linprog(method="highs-ds")` with the options below. **Every option listed is verified as
actually honored on the registered stack**; options SciPy does not honor are in B.2 and are **not**
registered.

| Option | Frozen value | Note |
|---|---|---|
| `method` | `"highs-ds"` | dual simplex pinned; removes HiGHS's simplex/IPM auto-choice |
| `presolve` | `True` | pinned explicitly. Presolve can change *which* optimal vertex is returned; it cannot change the optimal **value** `R*`/`Q*`, and Stage 3 makes the final allocation unique regardless (fixture 8) |
| `primal_feasibility_tolerance` | `1e-10` | **the HiGHS floor** — D2 |
| `dual_feasibility_tolerance` | `1e-10` | **the HiGHS floor** — D2 |
| `simplex_dual_edge_weight_strategy` | `"devex"` | pinned; removes the default `"choose"` automatic selection |
| `time_limit` | `60.0` s | exceeded ⇒ **FATAL** |
| `maxiter` | `100000` | exceeded ⇒ **FATAL** |
| `disp` | `False` | |

**Accepted result — and nothing else:** `res.success is True` **and** `res.status == 0`
("Optimization terminated successfully"). Every other status is handled thus: **status 2 (infeasible) at
the Stage-1 probe with `y = 0, x = 0`** is the `EXECUTION_CONSTRAINED_INFEASIBLE` test of §6; **every
other non-zero status — 1 (iteration/time limit), 3 (unbounded), 4 (numerical difficulties) — is
FATAL.**

## B.2 Options SciPy does **not** honor (recorded so they are never mistakenly "frozen")

Verified rejected or ignored with only a warning: `simplex_strategy` · `simplex_iteration_limit` ·
`random_seed` · `threads` · `parallel` · `run_crossover`. **These are not registered.** Determinism of
the underlying simplex is instead secured by **pinning the SciPy build** (which vendors a specific HiGHS
version) together with the single-thread environment pins of B.5.

## B.3 QP stage (3)

`quadprog.solve_qp(G, a, C, b, meq)` — Goldfarb–Idnani dual active-set.

- **Successful normal return:** a 6-tuple `(x, f, xu, iterations, lagrangian, iact)`. `x` is the primal
  solution, `iterations` a length-2 integer array, `lagrangian` the multipliers, `iact` the active set.
  **Returning without raising *is* the success signal** — quadprog has no status code.
- **Fatal exceptions** (both `ValueError`, distinguished by message):
  - `"matrix G is not positive definite"` — a conditioning/inclusion defect (**D3**). **FATAL.**
  - `"constraints are inconsistent, no solution"` — at Stage 3 this **must not occur**, because Stages 1
    and 2 have already proved the region non-empty. If it occurs it is a **FATAL implementation defect**,
    never a no-trade day.
- **No automatic retry with another solver. No fallback solver. No matrix regularization** (no ridge, no
  jitter, no `G + λI`) unless separately registered by ADR. **No external timeout or watchdog** — the QP
  is small, dense and finite; if it does not return, that is a fatal defect to diagnose, not to mask.

## B.4 Residual **definitions** (not merely thresholds)

**Sign convention:** constraints in the standard form of A.3 — `A z ≤ 0` for the homogeneous
inequalities, `A_eq z = 0` for the neutrality equality, `l ≤ z ≤ u` for the bounds — where
`z = (y, x)` in canonical permanent-identifier order. Multipliers `λ ≥ 0` for inequalities and bounds;
`ν` free for the equality.

**All residuals are ABSOLUTE, in NAV-weight units** (the same units as `y`, `x`, `G`) — they are **not**
normalized. This is deliberate: a normalized residual shrinks toward zero exactly when `G` is small,
which is the state MR-002 is expected to spend most of its time in.

```
primal_residual          = max( max_r (A z)_r ,                        inequality violation
                                max_r |(A_eq z)_r| ,                   equality violation
                                max_p max(l_p − z_p, z_p − u_p, 0) )   bound violation

dual_residual            = max_r max(−λ_r, 0)                          multiplier-sign violation

stationarity_residual    = ‖ ∇_z L ‖_∞ ,   L = D(z) + λᵀ A z + νᵀ A_eq z
                                           (LP stages: D ≡ the linear objective)

complementarity_residual = max_r | λ_r · slack_r | ,   slack_r = −(A z)_r ≥ 0

KKT_residual = max( primal_residual, dual_residual,
                    stationarity_residual, complementarity_residual )
```

**Acceptance per solve:** `primal_residual ≤ 1e-9` · `dual_residual ≤ 1e-9` ·
`stationarity_residual ≤ 1e-8` · `complementarity_residual ≤ 1e-8` · `KKT_residual ≤ 1e-8`.
**Any breach ⇒ FATAL.**

**Lexicographic band audit — both sides:**

```
R* − ε_retention  ≤  realized_R  ≤  R* + ε_retention
Q* − ε_new        ≤  realized_Q  ≤  Q* + ε_new
```

**Any breach ⇒ FATAL.**

**Post-target / post-execution re-check [W2]:** after the Stage-3 allocation is converted to executable
orders, **every** A.3 inequality is re-evaluated directly on the realized post-trade book. Any breach ⇒
**FATAL**. Rounding loss is zero by construction (§7), so this check cannot fail for rounding reasons —
it exists to catch an implementation error between the solver and the ledger.

## B.5 Determinism controls

`OMP_NUM_THREADS=1` · `OPENBLAS_NUM_THREADS=1` · `MKL_NUM_THREADS=1` · `BLIS_NUM_THREADS=1` ·
`NUMEXPR_NUM_THREADS=1` — **asserted at process start, not merely set.** LP and QP **warm starts
disabled**. No adaptive behavior beyond the pinned methods. **Canonical variable ordering by permanent
identifier** throughout (variables, matrices, logs, serialization). Per-solve canonical hashes of the
constraint matrix, bounds, objective and solution.

**Warning policy [D2]:** `warnings.simplefilter("error")` around every solve. **Any warning — including
`OptimizeWarning: Invalid option value` — is FATAL.**

**Byte-identical requirement (registered definition):** *byte-identical executable orders across repeated
runs in the **same frozen container image, dependency set, CPU architecture and input snapshot***. Runs
on a different platform must be **numerically equivalent within the frozen tolerances**, not
byte-identical. Final floating-point values are serialized **canonically as IEEE-754 hexadecimal**, never
via platform-dependent decimal formatting.

## B.6 Solver-runtime manifest

Emitted and hashed **before** the structural rerun. **It — not this document — is the authoritative
record of what actually executed.**

| Field | Status |
|---|---|
| OS, distribution, kernel, CPU architecture | **Linux / amd64 — recorded from the frozen image** (D4) |
| Research-image digest | recorded at image build, before the structural rerun |
| Application-image digest | recorded at Implementation Freeze |
| Python version | recorded in-image |
| NumPy / SciPy versions | recorded in-image |
| HiGHS version (as vendored by SciPy) | recorded in-image |
| quadprog version **+ Linux wheel/sdist hash** | recorded in-image — **the rev-1 Windows AMD64 wheel hash `f8edf2b0…` is WITHDRAWN** (D4) |
| BLAS/LAPACK vendor and version | recorded in-image |
| Full dependency lockfile + its hash | regenerated and hashed in-image |
| Solver tolerances, accepted status codes, iteration/time limits | as B.1–B.4 |
| Thread settings (asserted, not merely set) | as B.5 |
| Canonical ordering | permanent identifier |

**Development-machine values (Windows: Python 3.13.14, NumPy 2.2.6, SciPy 1.18.0, quadprog 0.1.13,
scipy-openblas 0.3.29) are recorded for provenance only and are NOT the frozen runtime. No structural,
determinism or fixture evidence produced on Windows will be used to establish v1.1 behavior.**

---

*Awaiting the owner's signature and a ruling on D1–D4. Nothing has been run under v1.1.*
