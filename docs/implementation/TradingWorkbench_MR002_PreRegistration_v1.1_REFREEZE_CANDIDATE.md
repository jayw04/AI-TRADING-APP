# MR-002 — Pre-Registration **v1.1** (RE-FREEZE CANDIDATE) · Portfolio-Construction Correction

**Date:** 2026-07-12 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** Running (v1.0
retired without a research verdict) · **Status:** 🟡 **RE-FREEZE CANDIDATE — awaiting the owner's
signature. No pipeline run has been made under v1.1.**

**Scope of this version: PORTFOLIO CONSTRUCTION ONLY.** Everything else is inherited **unchanged and
unread** from v1.0.

---

## 1. v1.0 disposition (governance record)

**MR-002 v1.0 — Research Design Invalidated · Implementation Infeasible Before Validation.**

This is **not** a strategy rejection, **not** evidence that residual mean reversion lacks an edge,
**not** a failed backtest, **not** a material implementation defect, and **not** grounds to open
validation or sealed OOS. **No economically valid MR-002 portfolio has yet been tested.**

### Supporting evidence (all archived)

| Evidence | Record |
|---|---|
| Zero-order structural result | Config B produced **0 orders on all 124 development sessions**; 8/8 registered constraint fixtures passed, proving the engine executed the registered rules faithfully (`MR002_DEV_FINDING_ConstraintInfeasibility_v1.0.md`) |
| Cause | The relative limits are **scale-invariant**: curing a breach by removing a candidate **shrinks G**, which **raises every remaining ratio** → the removal cascade is self-reinforcing and consumes the whole batch. Best day (25 candidates, 37.5% batch gross): a 1.5% position is 4.0% of gross; the 5% sector-net cap admits ~1.25 net positions/sector; all 25 were removed |
| Failed iterative-scaling prototype | Continuous per-sector down-scaling **does not converge** (200 iterations; residual sector-net 0.196 vs cap 0.05, beta 0.123 vs 0.10) — the same pathology in continuous form. **Permanently rejected** |
| LP feasibility demonstration | A **simultaneous** downward-only solve on the identical 2013-04-29 batch: **13 orders, 6.19% gross, every limit satisfied exactly** (sector-gross 0.2000, sector-net 0.0500, beta 0.0052, long gross = short gross, no weight above its registered start) |
| Two-position counterexample | Sequential existing-book repair **liquidates the book to zero** (a 2-sector book is 50%/50% of gross regardless of scale); the **joint** solve retains 1.667% NAV of existing exposure and places 10 new orders at a combined 16.67% gross, all limits satisfied |

### Why every in-place v1.0 alternative was rejected

| Option | Rejected because |
|---|---|
| Target-gross ramp-up denominator | Loosens the controls in exactly the states where they bind; introduces path dependency and a discretionary transition |
| Absolute NAV-denominated limits | At 15% gross a 5%-of-NAV sector-net allowance = 33% of actual gross — a different risk policy |
| Per-sector position counts | Counts do not control dollar weights, inverse-vol sizing, long/short imbalance, or beta |
| Broadened candidate batch | Changes percentile / z-threshold / signal distribution — a new research design, not a defect fix |
| 100%-of-NAV denominator (my original proposal) | Same objection as (2): materially looser when underinvested. **Withdrawn** |

---

## 2. Inherited UNCHANGED from v1.0 (immutable)

Hypothesis · signal construction (PIT-recursive orthogonalized sector factor; betas t−60…t−1;
mean-adjusted 5-day residual z with t−1 normalization; 60 complete observations; ddof=1; no
winsorization) · configurations **A 1.75 / B 2.00 (sole verdict config) / C 2.25** · entry rule (|z| ≥
z_entry **and** extreme decile of the side-eligible pool) · 5-session max hold · exit ladder · PIT
estimated earnings-risk blackout (70 calendar days + 2-session cooling, BMO/AMC semantics) · universe
(top-250 long / top-150 short, monthly PIT) · identity crosswalk + countersigned predecessor registry ·
PIT-SIC sector chain (no forward-fill) · four-series price policy · economic-gap filter · next-open
execution · costs (10 bps/side; borrow 50 bps/yr ÷ 360) · $10M NAV · 2% ADV participation cap
(clip, never delay) · **all pass gates and floors** · accepted exclusions · **§8a windows and hashes**.

**§8a (unchanged):** 3,400 sessions 2013-01-02 → 2026-07-10 · development 2013-01-02 → 2019-10-02
(1,700) · validation 2019-10-03 → 2023-02-16 (850) · **sealed OOS 2023-02-17 → 2026-07-10 (850, config
B, opened once)**. Artifact hashes: `MR002_SealedManifest_v1.0.json` (unchanged).

**Gates explicitly NOT changed:** ≥500 trades · ≥100 long / ≥100 short · return and Sharpe gates ·
candidate thresholds · sector limits (20% / 5%) · beta limit (0.10).

---

## 3. THE CHANGE — joint retention-and-entry optimization (frozen)

After processing hard exits at the execution open:

| Symbol | Meaning |
|---|---|
| `f_j` | fixed existing exposure that **cannot trade** at this open (no official open) |
| `y_j` | retained exposure of a **tradable** existing position, `0 ≤ y_j ≤ c_j` |
| `c_j` | its current exposure |
| `x_i` | new candidate exposure, `0 ≤ x_i ≤ w_i` |
| `w_i` | its registered unconstrained inverse-residual-volatility weight (with the 1.5%-NAV cap and the 2%-ADV clip already embedded) |
| `s` | fixed direction ∈ {−1, +1} |

No held symbol may also be a new-order variable (**no pyramiding, no same-open re-entry** — unchanged).

**All constraints apply to the COMBINED post-trade book** (`post_trade = f + y + x`, `G = Σ|w_post|`):

```
sector_gross_k / G  ≤ 0.20
|sector_net_k| / G  ≤ 0.05
|portfolio_beta| / G ≤ 0.10
G ≤ 1.00 NAV
position weight ≤ 1.5% NAV
Σ_new_long x_i = Σ_new_short x_i          (new entries dollar-neutral)
```

The registered **net-drift band applies to the complete post-trade portfolio**; the solver may retain
an existing imbalance when diversifying new orders bring the resulting book inside the band.

### Lexicographic stages (frozen)

**Stage 1 — minimize forced liquidation.** `maximize R = Σ y_j`. **`x` participates in the feasibility
constraints during this stage** — intentionally: eligible new positions may supply the diversification
that permits existing positions to be retained.

**Stage 2 — maximize new deployment.** Subject to `R ≥ R* − ε_retention`: `maximize Q = Σ x_i`.

**Stage 3 — unique closest allocation.** Subject to `R ≥ R* − ε_retention` and `Q ≥ Q* − ε_new`:

```
minimize D = 1.0 · Σ_j (y_j − c_j)² / c_j  +  1.0 · Σ_i (x_i − w_i)² / w_i
```

Every included `c_j`, `w_i` > 0 (zero-bound variables are **removed before matrix construction**), so
the Hessian is positive definite and the Stage-3 optimum is **unique**.

**Block coefficients are registered as 1.0 / 1.0** — an economic rule, not a mathematical inevitability.
**They must never be tuned using development performance.**

Signal-strength and identifier tie-breaks are **not** optimization objectives. Permanent identifiers are
the **canonical ordering** for variables, matrices, logs and serialization. **A materially different
second Stage-3 solution is a DEFECT, not an economic tie.**

**Frozen tolerances (NAV-weight units, materially below any executable order quantum):**
`ε_retention = 1e-9` · `ε_new = 1e-9` · `ε_active_sector = 1e-6`.

---

## 4. Frozen solver stack

| Stage | Method |
|---|---|
| Stages 1 & 2 (LP) | `scipy.optimize.linprog(method="highs-ds")` — **dual simplex pinned**; the generic `"highs"` may switch between dual simplex and interior point and is therefore **not** registered |
| Stage 3 (QP) | `quadprog.solve_qp` — Goldfarb–Idnani **dual active-set** method |

> **Wording (owner correction):** quadprog is a **numerical** solver, not an *exact* one. Goldfarb–Idnani
> has finite active-set properties in exact arithmetic; the implementation is floating-point and does
> **not** produce exact KKT multipliers. **Acceptance depends on the registered primal / dual / KKT
> residual checks below — never on a claim of exactness.**

**Registered environment (this machine; the frozen container digest is recorded at Implementation
Freeze):**

| Item | Value |
|---|---|
| Python | 3.13.14 |
| NumPy | 2.2.6 |
| SciPy | 1.18.0 (HiGHS bundled) |
| quadprog | 0.1.13 · wheel `quadprog-0.1.13-cp313-cp313-win_amd64.whl` · sha256 `f8edf2b08aeee5d824ee4da4cfb2d3ac56e580c2b10ae132b7d1a45717c0bd92` |
| OS / arch | Windows-11-10.0.26200 / AMD64 |
| BLAS/LAPACK | scipy-openblas 0.3.29 |
| Container image digest | *(recorded at Implementation Freeze)* |

**Determinism controls (all pinned):** `OMP_NUM_THREADS=1` · `OPENBLAS_NUM_THREADS=1` ·
`MKL_NUM_THREADS=1` · `BLIS_NUM_THREADS=1` · `NUMEXPR_NUM_THREADS=1`; **LP/QP warm starts disabled**;
no adaptive behavior beyond the selected methods; canonical variable ordering by permanent identifier;
matrix + objective hashes recorded per solve.

**Byte-identical requirement (registered definition):** *byte-identical executable orders across
repeated runs in the same frozen container, dependency set, CPU architecture and input snapshot.*
Cross-platform runs must be **numerically equivalent within the frozen tolerances**, not byte-identical.
Final floating-point values are serialized **canonically as IEEE-754 hexadecimal**, never via
platform-dependent decimal formatting.

**Acceptance per solve:** LP status ∈ {optimal} · QP status accepted · primal feasibility ≤ 1e-9 ·
dual feasibility ≤ 1e-9 · KKT residual ≤ 1e-8 · post-solve constraint re-check on the realized orders.

---

## 5. Solver outcomes (frozen semantics)

| Outcome | Definition | Behavior |
|---|---|---|
| **Valid no-trade day** | LP status optimal **and** `Q* = 0` within tolerance | Legitimate cash outcome (economically infeasible candidate topology). Recorded, not an error |
| **EXECUTION_CONSTRAINED_INFEASIBLE** | **Fixed, non-tradable** exposures (`f_j`, no executable open) make the combined constraints infeasible **even with all `y = 0` and all `x = 0`** | Submit **no new entries**; pending exits stay governed by the missing-open rule; **record the unavoidable sector / beta / drift breaches**; resume joint optimization at the next executable open. **Not** a solver failure and **not** an ordinary `Q*=0` topology |
| **INVALID RUN — FATAL** | timeout · iteration limit · non-optimal status · inconsistent LP/QP gross · primal-feasibility failure · KKT failure · post-rounding constraint breach · non-deterministic canonical output | **STOPS the development run.** A solver failure is **never** converted into a no-trade day (that would introduce data-dependent missing orders) |

---

## 6. Shares and rounding (frozen)

**Fractional shares** (inherited from v1.0). **No integer rounding. No minimum-lot constraint.**
`shares = target notional ÷ execution price`. **Rounding-loss fields are zero by construction.** A live
implementation would require a separately governed integer/fractional-broker feasibility layer —
**out of research scope**. This prevents an unregistered rounding repair from reintroducing the
denominator cascade.

---

## 7. Low gross is an INTENDED consequence (registered)

> Sparse, sector-clustered residual signals combined with the frozen 5%-of-actual-gross sector-net
> limit may result in **low gross exposure, slow capital deployment and frequent cash holdings. This is
> an intended consequence of retaining the registered risk limits, not an implementation defect.**

**Sector-topology arithmetic (registered):** sector gross sums to total gross and no sector may exceed
20% of gross ⇒ **any positive feasible portfolio requires at least FIVE sectors with positive
exposure**; with exactly five active sectors each must sit at exactly 20% of gross. An **active
sector** is `sector_gross > ε_active_sector` (= 1e-6).

**If MR-002 later fails the breadth or return gates because gross remains low, that is a legitimate
research result.** No gate, threshold or limit will be changed on that account.

---

## 8. Per-day audit record (frozen)

Candidate sectors · active post-trade sectors · long/short presence by sector · max sector-gross ratio ·
max sector-net ratio · binding constraints · retained existing gross · new gross · total gross ·
`R*`, `Q*`, realized `R`, `Q`, optimality gaps · max constraint violation · primal / dual / KKT
residuals · LP and QP statuses · canonical matrix + objective hashes · determinism hash of the executable
orders · continuous target weights vs executed notionals (rounding loss = 0 by construction).

---

## 9. Fixture suite (all must pass BEFORE the structural rerun)

**Inherited (8):** bootstrap-succeeds · single-sector rejection · batch-order invariance · denominator
recomputation · cascading breach · zero-gross · low-gross combined-gross · position cap + ADV clip.

**New (16, per the final review):**
1. Two-position counterexample — sequential repair liquidates; **joint solve retains and diversifies**.
2. Full retention when new candidates make the combined book feasible.
3. **Minimum** forced liquidation when full retention is impossible.
4. Empty existing book reduces exactly to the approved new-order LP/QP.
5. No eligible new candidates ⇒ only **necessary** existing reductions.
6. Genuine joint `R* = 0, Q* = 0` result accepted without error.
7. Stage-1 and Stage-2 **degenerate** LP optima produce the **same unique** Stage-3 allocation.
8. Stage-3 output **independent of the vertex** HiGHS returns.
9. Candidate **and existing-position** shuffle ⇒ byte-identical orders.
10. **No existing position increases.**
11. **No new candidate exceeds its registered starting weight.**
12. New entries remain **exactly** side-matched.
13. Combined drift-band handling.
14. Fixed non-tradable position ⇒ **EXECUTION_CONSTRAINED_INFEASIBLE** (not solver failure, not `Q*=0`).
15. Solver failure **stops the run** (never becomes cash).
16. Primal, dual and KKT residuals pass; iterative-scaling non-convergence **permanently rejected**
    (regression-locked).

---

## 10. Sequence after re-freeze (no deviation)

1. Owner signs v1.1 → implement the joint solver.
2. Run the full fixture suite (24 tests).
3. Rerun the **124-session structural slice**.
4. **Permitted inspection:** retention & deployment gross · nonzero-feasible days · valid zero-order
   days · execution-constrained-infeasible days · order counts · sector topology · binding constraints ·
   solver statuses & residuals · determinism hashes.
   **Prohibited until structural executability is accepted:** P&L · returns · Sharpe · hit rate ·
   drawdown · configuration comparisons.
5. **Declared in advance:** *no further economic-design change will be made merely because gross,
   feasible-day count or order count is lower than hoped. Only an implementation or mathematical defect
   may reopen v1.1.*
6. Then the full A/B/C development run → Implementation Freeze review.

**Validation and sealed OOS remain unchanged and UNREAD.**

---

## 11. Changelog (narrow, portfolio-construction only)

v1.0 → v1.1: whole-candidate removal cascade **replaced** by a **joint, downward-only, three-stage
lexicographic optimization** over existing retention `y` and new orders `x`, evaluated on the complete
post-trade portfolio against **actual gross**; solver stack, tolerances, determinism controls,
outcome semantics, fractional-share rule, sector-topology arithmetic and the expanded fixture suite
registered. **No signal, universe, identity, temporal, cost, window, gate or exclusion change.**

**Trial/design ledger:** MR-002 v1.0 (invalidated, no verdict) and MR-002 v1.1 (this document) are both
permanent entries in the research history.

---

*Awaiting the owner's re-freeze signature. Nothing has been run under v1.1.*
