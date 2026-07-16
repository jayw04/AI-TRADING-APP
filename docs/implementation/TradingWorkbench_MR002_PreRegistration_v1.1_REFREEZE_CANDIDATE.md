# MR-002 — Pre-Registration **v1.1** (**rev 3 — FINAL, APPROVED FOR RE-FREEZE**)
## Portfolio-Construction Correction

**Date:** 2026-07-12 · **Owner:** Jay Wang · **Program ID:** MR-002 · **Registry:** Running (v1.0
retired without a research verdict)

**Status:** ✅ **APPROVED FOR RESEARCH-DESIGN RE-FREEZE** — *"No further conceptual review is
required."* Awaiting the owner's signature and hash. **No pipeline run has been made under v1.1.**

**Scope: PORTFOLIO CONSTRUCTION ONLY.** Everything else is inherited **unchanged and unread** from v1.0.

---

## 0. THE RECORDED ECONOMIC STATEMENT (owner-required, verbatim)

> **The 1.5%-of-NAV limit is a new-entry sizing cap inherited from v1.0. Existing positions are not
> automatically trimmed because mark-to-market exposure exceeds 1.5%; they may only decrease through
> registered exits or combined-book coupling-constraint reductions.**

This statement governs. Any text elsewhere in this document that conflicts with it is void.

---

## 1. Revision log

| Rev | Change |
|---|---|
| rev 1 | First v1.1 candidate — joint LP/QP construction |
| rev 2 | Four freeze blockers corrected (sealed-OOS wording · exact PIT-SIC rule · linearized system · `VALID_ZERO_ENTRY_OUTCOME`); solver appendix completed; two wording corrections; **D1–D4 raised for ruling** |
| **rev 3** | **D1–D4 ruled. D1 approved *with a broader correction*: the hard post-trade 1.5% invariant I proposed is REMOVED (see §2). D2 approved + materiality wording. D3 approved + `fixed_reason`, κ(H) rename, excluded-mass audit. D4 approved.** |

### rev 2 → rev 3 edits (all owner-directed)

| # | Edit |
|---|---|
| D1a | Bound reverts to `0 ≤ y_j ≤ c_j` — **the 1.5% cap no longer applies to existing positions** (§3, A.1, A.4) |
| D1b | The rev-2 "hard post-trade invariant" note is **deleted**; §0 replaces it |
| D1c | Changelog statement about the cap becoming an invariant **deleted** (§12) |
| D1d | `UNAVOIDABLE_FIXED_BREACH` **renamed** `EXISTING_POSITION_OVER_ENTRY_CAP` — it now applies to **tradable and non-tradable** holdings alike — with six recorded fields (§6) |
| D1e | Fixture 17 rewritten (§9) |
| D2a | Materiality wording corrected — there is **no positive discrete order quantum** under fractional shares (§4) |
| D2b | Fixture 18 must prove **both** halves: the below-floor tolerance warns *and stops*, **and** the accepted runtime verifies 1e-10 was honored (§9) |
| D3a | `fixed_reason ∈ {NO_EXECUTABLE_OPEN, BELOW_NUMERICAL_INCLUSION_FLOOR}` recorded on every fixed exposure (§6, B.7) |
| D3b | Hard exits are processed **before** inclusion-floor classification (§3, B.7) |
| D3c | `cond(G)` **renamed** `hessian_condition_number = κ(H)` — `G` is total gross and must not be overloaded (B.3, B.7) |
| D3d | Excluded-mass audit: four daily fields (B.7) |
| D4 | Frozen research store mounted **read-only where practicable** (B.6) |

---

## 2. **[D1 — RULED]** The position cap is a NEW-ENTRY SIZING CAP, not a trimming rule

The owner's ruling, adopted in full:

> *"v1.1 should not introduce a hard post-trade 1.5% invariant. That would be an additional economic
> change, add turnover and costs, and contradict the stated 'portfolio-construction correction only'
> scope."*

My rev-2 bound `y_j ≤ min(c_j, 0.015)` is **withdrawn**. It would have force-trimmed appreciated winners
at every executable open — turnover and cost that v1.0 never had. Flagging it was right; proposing it was
not. **v1.0's economic rule stands.**

### Frozen consequences

- A held position **may exceed 1.5%** through appreciation, NAV movement or an execution constraint.
- **The solver may never increase an existing position** (`y_j ≤ c_j`).
- **No new order may exceed 1.5% of NAV** (`w_i ≤ 0.015`).
- **No pyramiding** — unchanged.
- An existing position is reduced **only** because of an exit, or because the **combined-book coupling
  constraints require it** — *never* solely because it appreciated beyond 1.5%.
- An over-entry-cap existing position is a **diagnostic**, not an LP constraint violation.
- It nevertheless **contributes fully** to gross, sector, net and beta exposure. If *that* produces an
  uncurable **coupling** breach, `EXECUTION_CONSTRAINED_INFEASIBLE` remains appropriate. **The individual
  cap itself never halts the day.**

---

## 3. Inherited UNCHANGED from v1.0 (immutable)

Hypothesis · signal construction (PIT-recursive orthogonalized sector factor; betas t−60…t−1;
mean-adjusted 5-day residual z with t−1 normalization; 60 complete observations; ddof=1; no
winsorization) · configurations **A 1.75 / B 2.00 (sole verdict config) / C 2.25** · entry rule (|z| ≥
z_entry **and** extreme decile of the side-eligible pool) · 5-session max hold · exit ladder · PIT
estimated earnings-risk blackout (70 calendar days + 2-session cooling; BMO/AMC semantics) · universe
(top-250 long / top-150 short, monthly PIT) · identity crosswalk + countersigned predecessor registry ·
four-series price policy · economic-gap filter · next-open execution · costs (10 bps/side; borrow 50
bps/yr ÷ 360) · $10M NAV · 2% ADV participation cap (**clip, never delay**) · **1.5%-of-NAV new-entry
sizing cap** · **all pass gates and floors** · accepted exclusions · **§8a windows and hashes**.

### 3.1 PIT-SIC classification chain (exact inherited rule)

> **PIT-SIC effective-dated chain:** a SIC becomes effective at its filing-acceptance timestamp and
> remains effective until the next accepted filing supplies a new valid SIC. **A missing SIC does not
> overwrite the last valid observation. No current-classification fallback is permitted.**

Two further inherited clauses, restated so the withdrawn rev-1 shorthand ("no forward-fill") cannot be
read as having relaxed them:

- **No pre-observation backfill.** A SIC is never effective *before* its first accepted observation.
  Sessions preceding a security's first accepted SIC filing have **no** classification.
- **Unresolved ⇒ ineligible.** A security whose sector cannot be resolved on session *t* through
  identity → PIT-SIC → sector-ETF is **ineligible on t**. Never defaulted, never assigned a fallback
  sector, never carried by a current classification.

**Authoritative source (takes precedence over any paraphrase here):**
`TradingWorkbench_MR002_PreRegistration_v1.0_FROZEN.md`, PIT-SIC section, as hashed in
`MR002_SealedManifest_v1.0.json`. Supporting immutable artifacts: `MR002_PITSIC_Gate_v2.0.json` (98.48%
overall; every year ≥ 95%) and `predecessor_override_registry_v1.0.csv` (21/21 countersigned).
**v1.1 changes no data rule.**

### 3.2 §8a windows

3,400 sessions, 2013-01-02 → 2026-07-10.

| Window | Range | Sessions | Status |
|---|---|---|---|
| Development | 2013-01-02 → 2019-10-02 | 1,700 | in use |
| Validation | 2019-10-03 → 2023-02-16 | 850 | **sealed and unread** |
| **Sealed OOS** | 2023-02-17 → 2026-07-10 | 850, **config B only** | **currently sealed and unread; designated for ONE future opening, after validation and all prerequisite gates** |

**Neither the validation window nor the sealed OOS window has ever been read.** Their untouched status is
exactly what permits v1.1 to reuse them without a fresh sample. Artifact hashes unchanged
(`MR002_SealedManifest_v1.0.json`, 16 artifacts).

**Gates explicitly NOT changed:** ≥500 trades · ≥100 long / ≥100 short · return and Sharpe gates ·
candidate thresholds · sector limits (20% / 5%) · beta limit (0.10) · net-drift band (5%).

---

## 4. v1.0 disposition (governance record)

**MR-002 v1.0 — Research Design Invalidated · Implementation Infeasible Before Validation.**

Not a strategy rejection, not evidence against residual mean reversion, not a failed backtest, not a
material implementation defect, and not grounds to open validation or sealed OOS. **No economically valid
MR-002 portfolio has yet been tested.**

| Evidence | Record |
|---|---|
| Zero-order structural result | Config B: **0 orders on all 124 development sessions**; 8/8 registered constraint fixtures passed, proving the engine executed the registered rules faithfully (`MR002_DEV_FINDING_ConstraintInfeasibility_v1.0.md`) |
| Cause | Relative limits are **scale-invariant**: curing a breach by removing a candidate **shrinks G**, which **raises every remaining ratio** → the removal cascade is self-reinforcing and consumes the batch. Best day (25 candidates, 37.5% batch gross): a 1.5% position is 4.0% of gross; the 5% sector-net cap admits ~1.25 net positions/sector; all 25 removed |
| Failed iterative-scaling prototype | Continuous per-sector down-scaling **does not converge** (200 iterations; residual sector-net 0.196 vs cap 0.05; beta 0.123 vs 0.10). **Permanently rejected** |
| LP feasibility demonstration | A **simultaneous** downward-only solve on the identical 2013-04-29 batch: **13 orders, 6.19% gross, every limit satisfied** (sector-gross 0.2000, sector-net 0.0500, beta 0.0052, long gross = short gross, no weight above its registered start) |
| Two-position counterexample | Sequential existing-book repair **liquidates the book to zero**; the **joint** solve retains 1.667% NAV of existing exposure and places 10 new orders at 16.67% combined gross, all limits satisfied |

**Rejected v1.0 in-place alternatives:** target-gross ramp denominator · absolute NAV-denominated sector
limits · per-sector position counts · broadened candidate batch · the 100%-of-NAV denominator I
originally proposed (**withdrawn**).

---

## 5. THE CHANGE — joint retention-and-entry optimization

**Hard exits are processed first**, at the execution open. **Inclusion-floor classification (B.7) happens
after exits**, so a tiny position with a valid mandatory exit is still exited.

| Symbol | Meaning |
|---|---|
| `f_j` | **fixed** exposure — cannot trade at this open. `fixed_reason ∈ {NO_EXECUTABLE_OPEN, BELOW_NUMERICAL_INCLUSION_FLOOR}` |
| `y_j` | retained exposure of a **tradable** existing position |
| `c_j` | its current exposure |
| `x_i` | new candidate exposure |
| `w_i` | its registered unconstrained inverse-residual-volatility weight, **with `w_i ≤ 0.015`** (the new-entry sizing cap) and the 2%-ADV clip already embedded |
| `d_p ∈ {−1,+1}` | the position's **fixed** direction |

**`f`, `y`, `c`, `x`, `w` are non-negative ABSOLUTE NAV weights. Direction is carried ONLY by `d`.**

### **[D1 — RULED]** Frozen bounds

```
0 ≤ y_j ≤ c_j              existing tradable positions — NO 1.5% cap
0 ≤ x_i ≤ w_i ,  w_i ≤ 0.015   new candidates — the 1.5% NEW-ENTRY sizing cap
```

No held symbol may also appear as a new-order variable (**no pyramiding, no same-open re-entry** —
unchanged). All constraints apply to the **complete post-trade book**; the full linearized system is
frozen in **Appendix A**.

New entries remain dollar-neutral: `Σ_{new long} x_i = Σ_{new short} x_i`.

The registered **net-drift band applies to the complete post-trade portfolio**. The solver may retain an
existing imbalance when diversifying new orders bring the resulting book inside the band.

### 5.1 Lexicographic stages (frozen)

**Stage 1 — minimize forced liquidation.** `maximize R = Σ_j y_j`. **`x` participates in the feasibility
constraints during this stage** — intentionally: eligible new positions may supply the diversification
that permits existing positions to be retained.

**Stage 2 — maximize new deployment.** Subject to `R ≥ R* − ε_retention`: `maximize Q = Σ_i x_i`.

**Stage 3 — unique closest allocation.** Subject to `R ≥ R* − ε_retention` **and** `Q ≥ Q* − ε_new`:

```
minimize D = 1.0 · Σ_j (y_j − c_j)² / c_j  +  1.0 · Σ_i (x_i − w_i)² / w_i
```

Every included `c_j`, `w_i` is strictly positive (variables at or below `ε_include` are excluded before
matrix construction — B.7), so the Hessian `H` is diagonal and positive definite and the Stage-3 optimum
is **unique**.

**Block coefficients are registered as 1.0 / 1.0** — an economic rule, not a mathematical inevitability.
**They must never be tuned using development performance.**

Signal strength and identifier tie-breaks are **not** optimization objectives. Permanent identifiers are
the **canonical ordering** for variables, matrices, logs and serialization. **A materially different
second Stage-3 solution is a DEFECT, not an economic tie.**

The LP **optimal value** `R*` (and `Q*`) is unique even when the optimal **vertex** is not. A different
returned vertex is therefore *not* a defect; a different Stage-3 allocation is.

---

## 6. Frozen tolerances

| Symbol | Value | Unit | Rationale |
|---|---|---|---|
| `ε_retention` | **1e-8** | NAV weight | 100× the pinned solver feasibility tolerance (D2) |
| `ε_new` | **1e-8** | NAV weight | as above |
| `ε_include` | **1e-8** | NAV weight | Hessian-conditioning inclusion floor (D3) |
| `ε_active_sector` | **1e-6** | NAV weight | **reporting threshold only** (§9) — never a constraint input |

**[D2 — materiality wording, corrected].** Because the harness permits fractional shares there is **no
positive discrete executable order quantum**. The registered justification is therefore:

> At the registered $10M NAV, a weight of 1e-8 equals **$0.10**. It is **economically immaterial relative
> to the registered NAV and materially below any threshold used for portfolio decisions.**

---

## 7. Day-outcome classification (frozen)

| Outcome | Definition | Behavior |
|---|---|---|
| **`VALID_ZERO_ENTRY_OUTCOME`** | Stages 1 and 2 optimal **and** `Q* = 0` within tolerance | **No new entries submitted.** Existing positions are **retained or reduced** per the Stage-1/Stage-3 solution; previously scheduled exits remain effective. **A full-cash day only when no post-trade positions remain.** Recorded, not an error |
| **`EXECUTION_CONSTRAINED_INFEASIBLE`** | **Fixed** exposures (`f`) violate a **coupling** constraint (sector gross, sector net, beta, net drift, `G ≤ 1`) even with all `y = 0` and all `x = 0` | Submit **no new entries**; pending exits stay governed by the missing-open rule; **record the unavoidable breaches**; resume joint optimization at the next executable open. **Not** a solver failure and **not** a `VALID_ZERO_ENTRY_OUTCOME` |
| **`EXISTING_POSITION_OVER_ENTRY_CAP`** **[D1 — renamed]** | **Any** existing holding — **tradable or not** — whose current weight exceeds the 1.5% **new-entry** cap | **DIAGNOSTIC ONLY.** Not an LP constraint violation. **Never halts the day.** The position still contributes fully to gross, sector, net and beta; if *that* creates an uncurable coupling breach, `EXECUTION_CONSTRAINED_INFEASIBLE` applies — but the individual cap never does |
| **`INVALID_RUN` — FATAL** | Any fatal condition in Appendix B: non-optimal LP status · quadprog exception · time or iteration limit · residual failure · lexicographic-band violation · **any solver warning** · `κ(H) > 1e10` · **post-target or post-execution constraint breach** · non-deterministic canonical output | **STOPS the development run.** A solver failure is **never** converted into a no-trade day — that would introduce data-dependent missing orders |

`Q* = 0` does **not** imply no trading: reductions (`y < c`) and hard exits may still execute. A
`VALID_ZERO_ENTRY_OUTCOME` day contributes to the breadth gates (≥500 trades, ≥100 long, ≥100 short) only
through the fills it actually generates.

### 7.1 `EXISTING_POSITION_OVER_ENTRY_CAP` — recorded fields

```
permaticker
current_weight
entry_weight
amount_above_1_5pct
tradable_at_open
reduction_due_to_other_constraints
```

---

## 8. Shares and rounding (frozen)

**Fractional shares** (inherited from v1.0). **No integer rounding. No minimum-lot constraint.**
`shares = target notional ÷ execution price`. **Rounding-loss fields are zero by construction.** A live
implementation would require a separately governed integer/fractional-broker feasibility layer — **out of
research scope**. This prevents an unregistered rounding repair from reintroducing the denominator
cascade.

---

## 9. Low gross is an INTENDED consequence · sector topology

> Sparse, sector-clustered residual signals combined with the frozen 5%-of-actual-gross sector-net limit
> may result in **low gross exposure, slow capital deployment and frequent cash holdings. This is an
> intended consequence of retaining the registered risk limits, not an implementation defect.**

**Sector-topology arithmetic (registered).** Sector gross sums to total gross and no sector may exceed
20% of gross ⇒ **any positive feasible portfolio requires at least FIVE sectors with strictly positive
gross exposure**; with exactly five, each must sit at exactly 20% of gross.

**Theory vs reporting.** The **theoretical** positive-sector count is **≥ 5**. The **reported
active-sector count** applies the frozen reporting threshold `sector_gross > ε_active_sector` (1e-6) and
**may differ from the theoretical count solely because of that reporting tolerance**. The threshold is a
reporting convention and **never** a constraint input.

**If MR-002 later fails the breadth or return gates because gross remains low, that is a legitimate
research result.** No gate, threshold or limit will be changed on that account.

---

## 10. Fixture suite — **27 tests**, all run inside the frozen Linux research image

**Inherited (8):** bootstrap-succeeds · single-sector rejection · batch-order invariance · denominator
recomputation · cascading breach · zero-gross · low-gross combined-gross · position cap + ADV clip.

**Joint-solve (16):**
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
11. **No new candidate exceeds its registered starting weight** (and none exceeds 1.5% of NAV).
12. New entries remain **exactly** side-matched.
13. Combined drift-band handling on the complete post-trade portfolio.
14. Fixed non-tradable position ⇒ **`EXECUTION_CONSTRAINED_INFEASIBLE`** (not solver failure, not `Q*=0`).
15. Solver failure **stops the run** (never becomes cash).
16. Primal, dual, stationarity and complementarity residuals pass; iterative-scaling non-convergence
    **permanently rejected** (regression-locked).

**rev 3 (3):**

17. **[D1 — rewritten]** An existing position above the entry cap **is fully included in accounting and
    coupling constraints, is never increased, is reported as `EXISTING_POSITION_OVER_ENTRY_CAP`, and does
    not by itself halt the optimization.**
18. **[D2 — two halves, both required]** (a) A below-floor tolerance (< 1e-10) **emits a warning and stops
    the run**; (b) the accepted runtime **verifies that 1e-10 was actually honored** — it does not merely
    request it.
19. **[D3]** An existing exposure at or below `ε_include` is carried as **fixed `f`** with
    `fixed_reason = BELOW_NUMERICAL_INCLUSION_FLOOR`, remains in NAV/gross/sector/net/beta accounting,
    **cannot increase**, and never enters the Hessian; a below-floor **candidate** is omitted and creates
    no order; **a below-floor position with a valid mandatory exit is still exited** (exits precede
    inclusion-floor classification).

---

## 11. Sequence after signature (no deviation)

1. **Sign and hash v1.1.**
2. Build the frozen Linux research image.
3. Emit the solver-runtime manifest.
4. Run all **27 fixtures**.
5. Run the **124-session structural slice** under the prohibited-inspection rules.
6. **Stop for structural-executability adjudication before viewing performance.**

**Permitted inspection:** retention and deployment gross · nonzero-feasible days ·
`VALID_ZERO_ENTRY_OUTCOME` days · `EXECUTION_CONSTRAINED_INFEASIBLE` days ·
`EXISTING_POSITION_OVER_ENTRY_CAP` diagnostics · excluded-mass audit · order counts · sector topology ·
binding constraints · solver statuses and residuals · determinism hashes.

**Prohibited until structural executability is accepted:** P&L · returns · Sharpe · hit rate · drawdown ·
configuration comparisons.

**Declared in advance:** *no further economic-design change will be made merely because gross,
feasible-day count or order count is lower than hoped. Only an implementation or mathematical defect may
reopen v1.1.*

**Validation and sealed OOS remain sealed, unread and reusable.**

---

## 12. Changelog (narrow — portfolio construction only)

v1.0 → v1.1: the whole-candidate removal cascade is **replaced** by a **joint, downward-only, three-stage
lexicographic optimization** over existing retention `y` and new orders `x`, evaluated on the complete
post-trade portfolio against **actual gross**. The solver stack, tolerances, determinism controls,
day-outcome semantics, the fractional-share rule, the sector-topology arithmetic and the 27-fixture suite
are registered.

**The 1.5%-of-NAV limit remains exactly what it was in v1.0: a new-entry sizing cap. It is NOT a
post-trade invariant and NOT a mark-to-market trimming rule.** (The rev-2 proposal to make it one is
withdrawn — see §2.)

**No signal, universe, identity, temporal, cost, window, gate or exclusion change.**

**Trial/design ledger:** MR-002 v1.0 (invalidated, no verdict) and MR-002 v1.1 (this document) are both
permanent entries in the research history.

---
---

# Appendix A — Frozen linearized combined-book system

**`f`, `y`, `c`, `x`, `w` are non-negative ABSOLUTE NAV weights. Direction is carried ONLY by
`d_p ∈ {−1, +1}`, which is fixed and never a decision variable.**

Index sets: `F` = fixed exposures (either `NO_EXECUTABLE_OPEN` or `BELOW_NUMERICAL_INCLUSION_FLOOR`) ·
`E` = tradable existing positions · `N` = new candidates. `F_k`, `E_k`, `N_k` are their restrictions to
sector `k`.

## A.1 **[D1 — RULED]** Decision variables and bounds

```
0 ≤ y_j ≤ c_j                    j ∈ E     NO 1.5% cap on existing positions
0 ≤ x_i ≤ w_i ,  w_i ≤ 0.015     i ∈ N     the 1.5% NEW-ENTRY sizing cap
                                           (the 2% ADV clip is embedded in w_i)
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

## A.3 Frozen coupling inequalities (homogeneous in `G` — **no division anywhere**)

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

**When `G = 0` every linearized constraint is satisfied trivially — no division, therefore no
zero-denominator case.** This is precisely the pathology that destroyed v1.0: the ratio form
`sector_gross_k / G ≤ 0.20` is undefined at `G = 0` and scale-invariant above it. The homogeneous form is
mathematically equivalent for `G > 0` **and** well-defined at `G = 0`.

**These eight are the ONLY coupling constraints. `EXECUTION_CONSTRAINED_INFEASIBLE` is defined
exclusively against them.**

## A.4 **[D1 — RULED]** The 1.5% cap is NOT a constraint of this system

The 1.5% limit appears **only** as the bound `w_i ≤ 0.015` on **new** candidates in A.1. It is **not** an
inequality in A.3, it is **not** applied to `y`, and it is **never** applied to `f`. An existing holding
above 1.5% is a **diagnostic** (`EXISTING_POSITION_OVER_ENTRY_CAP`, §7.1), fully present in every A.2
linear form and therefore in every A.3 constraint, but incapable — by itself — of rendering the system
infeasible.

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

`scipy.optimize.linprog(method="highs-ds")`. **Every option below is verified as actually honored on the
registered stack**; options SciPy does not honor are in B.2 and are **not** registered.

| Option | Frozen value | Note |
|---|---|---|
| `method` | `"highs-ds"` | dual simplex pinned; removes HiGHS's simplex/IPM auto-choice |
| `presolve` | `True` | pinned explicitly. Presolve can change *which* optimal vertex is returned; it cannot change the optimal **value** `R*`/`Q*`, and Stage 3 makes the final allocation unique regardless (fixture 8) |
| `primal_feasibility_tolerance` | `1e-10` | **the HiGHS floor** (D2) |
| `dual_feasibility_tolerance` | `1e-10` | **the HiGHS floor** (D2) |
| `simplex_dual_edge_weight_strategy` | `"devex"` | pinned; removes the default `"choose"` automatic selection |
| `time_limit` | `60.0` s | exceeded ⇒ **FATAL** |
| `maxiter` | `100000` | exceeded ⇒ **FATAL** |
| `disp` | `False` | |

**Accepted result — and nothing else:** `res.success is True` **and** `res.status == 0`. Every other
status: **status 2 (infeasible) at the Stage-1 probe with `y = 0, x = 0`** is the
`EXECUTION_CONSTRAINED_INFEASIBLE` test of §7; **every other non-zero status — 1 (iteration/time limit),
3 (unbounded), 4 (numerical difficulties) — is FATAL.**

## B.2 Options SciPy does **not** honor (recorded so they are never mistakenly "frozen")

Verified rejected or ignored with only a warning: `simplex_strategy` · `simplex_iteration_limit` ·
`random_seed` · `threads` · `parallel` · `run_crossover`. **Not registered.** Determinism of the
underlying simplex is secured instead by **pinning the SciPy build** (which vendors a specific HiGHS
version) together with the single-thread environment pins of B.5.

## B.3 QP stage (3)

`quadprog.solve_qp(H, a, C, b, meq)` — Goldfarb–Idnani dual active-set.

> **[D3c — naming]** The Hessian is denoted **`H`**, never `G`. **`G` is reserved for total gross
> exposure** throughout this program. The recorded metric is `hessian_condition_number = κ(H)`.

- **Successful normal return:** a 6-tuple `(x, f, xu, iterations, lagrangian, iact)`. **Returning without
  raising *is* the success signal** — quadprog has no status code.
- **Fatal exceptions** (both `ValueError`, distinguished by message):
  - `"matrix G is not positive definite"` *(quadprog's own message text; it refers to the Hessian `H`)* —
    a conditioning/inclusion defect (D3). **FATAL.**
  - `"constraints are inconsistent, no solution"` — at Stage 3 this **must not occur**, because Stages 1
    and 2 already proved the region non-empty. If it occurs it is a **FATAL implementation defect**,
    never a no-trade day.
- **No automatic retry with another solver. No fallback solver. No matrix regularization** (no ridge, no
  jitter, no `H + λI`) unless separately registered by ADR. **No external timeout or watchdog** — the QP
  is small, dense and finite; if it does not return, that is a fatal defect to diagnose, not to mask.
- **`κ(H) > 1e10` ⇒ `INVALID_RUN`.**

## B.4 Residual **definitions** (not merely thresholds)

**Sign convention:** constraints in the standard form of A.3 — `A z ≤ 0` for the homogeneous
inequalities, `A_eq z = 0` for the neutrality equality, `l ≤ z ≤ u` for the bounds — where `z = (y, x)`
in canonical permanent-identifier order. Multipliers `λ ≥ 0` for inequalities and bounds; `ν` free for
the equality.

**All residuals are ABSOLUTE, in NAV-weight units** (the same units as `y`, `x`, `G`) — **not**
normalized. Deliberate: a normalized residual shrinks toward zero exactly when `G` is small, which is the
state MR-002 is expected to spend most of its time in.

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

**Post-target / post-execution re-check:** after the Stage-3 allocation is converted to executable orders,
**every** A.3 inequality is re-evaluated directly on the realized post-trade book. Any breach ⇒ **FATAL**.
Rounding loss is zero by construction (§8), so this check cannot fail for rounding reasons — it exists to
catch an implementation error between the solver and the ledger.

## B.5 Determinism controls

`OMP_NUM_THREADS=1` · `OPENBLAS_NUM_THREADS=1` · `MKL_NUM_THREADS=1` · `BLIS_NUM_THREADS=1` ·
`NUMEXPR_NUM_THREADS=1` — **asserted at process start, not merely set.** LP and QP **warm starts
disabled**. No adaptive behavior beyond the pinned methods. **Canonical variable ordering by permanent
identifier** throughout. Per-solve canonical hashes of the constraint matrix, bounds, objective and
solution.

**[D2 — warning policy]** Every solve is wrapped:

```python
with warnings.catch_warnings():
    warnings.simplefilter("error")
    result = solve(...)
```

**Any warning emitted during a solve is FATAL** — including an invalid-option warning that would
otherwise permit SciPy to revert to a default **while still returning `success=True`**.

**Byte-identical requirement (registered definition):** *byte-identical executable orders across repeated
runs in the **same frozen container image, dependency set, CPU architecture and input snapshot***. Runs on
a different platform must be **numerically equivalent within the frozen tolerances**, not byte-identical.
Final floating-point values are serialized **canonically as IEEE-754 hexadecimal**, never via
platform-dependent decimal formatting.

## B.6 Solver-runtime manifest and the frozen runtime

**The solver-runtime manifest — not the developer workstation — is the authoritative execution record.**
Emitted and hashed **before** the fixtures and the structural slice.

Runtime boundary (**D4, approved**): a dedicated **Linux/amd64 standalone `mr002-research` image** — not
the workbench Compose stack. **No live database. No broker connection. No market-data websocket.** The
frozen research store is mounted **read-only where practicable**. **No structural or determinism evidence
is generated on Windows.**

| Field | Status |
|---|---|
| OS, distribution, kernel, CPU architecture | Linux / amd64 — recorded from the frozen image |
| Research-image digest | recorded **before** fixtures or structural execution |
| Application-image digest | recorded at Implementation Freeze |
| Python / NumPy / SciPy versions | recorded in-image |
| HiGHS version (as vendored by SciPy) | recorded in-image |
| quadprog version **+ Linux artifact hash** | recorded in-image — **the rev-1 Windows AMD64 wheel hash `f8edf2b0…` is WITHDRAWN** |
| BLAS/LAPACK vendor and version | recorded in-image |
| Dependency lockfile + its hash | **generated and hashed inside the image** |
| Solver tolerances, accepted status codes, iteration/time limits | as B.1–B.4 |
| Thread settings (asserted, not merely set) | as B.5 |
| Canonical ordering | permanent identifier |

The **same image** is used for all 27 fixtures, the structural slice and the determinism rerun.
Development-machine values (Windows) are provenance only and are **NOT** the frozen runtime.

## B.7 **[D3]** Inclusion floor, fixed-exposure reasons, and the excluded-mass audit

**Ordering (mandatory):** hard exits are processed **first**; inclusion-floor classification happens
**after** them. A tiny position with a valid mandatory exit **is still exited**.

**Classification:**

- An **existing** exposure at or below `ε_include` (1e-8) becomes a **fixed constant exposure** with
  `fixed_reason = BELOW_NUMERICAL_INCLUSION_FLOOR`. It is **never deleted from NAV, gross, sector, net or
  beta accounting**, and it **cannot increase**.
- A **new candidate** at or below the floor is **omitted and creates no order**.
- A tradable position with no executable open is fixed with `fixed_reason = NO_EXECUTABLE_OPEN`.

**Only `NO_EXECUTABLE_OPEN` represents an execution impediment.** The two reasons are never conflated.

**Daily excluded-mass audit** (proves the numerical floor never silently removes meaningful exposure):

```
below_floor_existing_count
below_floor_existing_total_weight
below_floor_candidate_count
below_floor_candidate_total_weight
```

**Recorded per solve:** `hessian_condition_number = κ(H)` — `κ(H) > 1e10` ⇒ **`INVALID_RUN`**.

---

*Approved for Research-Design Re-Freeze. Awaiting the owner's signature and hash. Nothing has been run
under v1.1. Validation and sealed OOS remain sealed, unread and reusable.*
