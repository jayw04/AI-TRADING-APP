# MR-002 v1.1 — Stage-3 Cross-Family Solver Intersection

**Date:** 2026-07-13 · **Status:** Returned for adjudication (owner ruling `Docs/review/comments.md` answered)
**Corpus:** immutable 3,895 instances, hash `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` — **re-captured and verified exactly**
**Artifacts:**
`runtime/MR002_SolverIntersection.json` · sha256 `d1fbe8b9f523a294e945af295402f84275efc27ec150453c18d0c46299cef73d` · 67,988 B
`runtime/MR002_PIQP_on_SqrtFailures.json` · sha256 `3917e0d7cdad39f66bb3f604d1fdcbf72bc80c98eaeac44f4374c4ba50ed4709` · 990 B

> **DIAGNOSTIC ONLY.** No performance computed, printed or persisted. Preflight and the
> development run remain **STOPPED**. Validation and sealed OOS remain **sealed and unread**.

---

## 1. The question

Every prior characterization scored each solver **alone**. None reached the zero-failure gate,
and the escalation went to MOSEK (a licensed commercial solver, no licence available).

**Nobody had asked whether the failure SETS overlap.** If they are disjoint, a deterministic
cascade of *already-characterized* solvers reaches zero — no MOSEK, no licence, no redesign.

## 2. Method

All seven solve paths scored under **ONE canonical predicate** — the registered production
acceptance (`jp._acceptance` + `LIMITS`).

This mattered: the two prior characterizers used **different** predicates (the native-QP one adds
an external primal-dual gap gate; the quadprog one does not), so their headline counts were never
directly comparable and an intersection across them would have been meaningless.

Every solver path is **IMPORTED from its validated characterizer, never re-derived** (see §5).

## 3. Result — the union covers the corpus

| solver | failures / 3,895 | rate |
|---|---|---|
| QUADPROG_SQRT | **5** | 0.13% |
| QUADPROG_RAW | 70 | 1.80% |
| QUADPROG_TSCALED | 185 | 4.75% |
| CLARABEL | 9 | 0.23% |
| PIQP_P2 | 49 | 1.26% |
| PIQP_P1 | 57 | 1.46% |
| HIGHS_QPASM | 592 | 15.20% |
| **unsolved by EVERY family** | **0** | — |

Each solver **reproduced its registered count exactly**, which is the cross-check that makes the
intersection trustworthy.

### Two-solver cascades from the frozen square-root primary

```
SQRT -> PIQP_P2       unresolved: 0     fallback's own failure rate:  1.26%
SQRT -> PIQP_P1       unresolved: 0     fallback's own failure rate:  1.46%
SQRT -> HIGHS_QPASM   unresolved: 0     fallback's own failure rate: 15.20%
SQRT -> CLARABEL      unresolved: 1     (fails 2765)
```

### The five square-root failures — who certifies each

| instance | rescued by |
|---|---|
| 800 | quadprog-raw, Clarabel, HiGHS, **PIQP (P1+P2)** |
| 1328 | quadprog-raw, Clarabel, HiGHS, **PIQP (P1+P2)** |
| 2140 | Clarabel, HiGHS, **PIQP (P1+P2)** |
| 2296 | quadprog-t-scaled, Clarabel, HiGHS, **PIQP (P1+P2)** |
| **2765** | HiGHS, **PIQP (P1+P2)** |

**All five QUADPROG_SQRT failures share ONE mode:** `ValueError: constraints are inconsistent,
no solution` — a **false infeasibility**, not a real one (four other solvers certify them).

---

## 4. ⚠ Correction to the ruling: "2765 requires HiGHS" is FALSE

`Docs/review/comments.md` §2 and §10 bind the claim that instance 2765 *"is not certified by any
other characterized solver"*. **PIQP certifies it — both profiles.**

**PIQP was absent from the first intersection run.** That gap was mine, and the erratum would
have bound a false claim.

### Consequence: the fallback choice is open, and it matters

`SQRT → PIQP_P2` satisfies **every constraint of the ruling** — minimal, two solvers, zero
unresolved, no third attempt, no licence — with a fallback **12× more reliable** than HiGHS.

**And the algorithmic-family argument points the same way.** quadprog (Goldfarb–Idnani) and
HiGHS-qpasm are **both active-set**. The approved cascade has *no algorithmic diversity*, and the
mode that kills the square-root path is the characteristic active-set breakdown — which the
designated fallback exhibits too:

```
QUADPROG_SQRT   5 failures, ALL "constraints are inconsistent"   <- false infeasibility
HIGHS_QPASM   592 failures, of which 25 x kInfeasible            <- the SAME mode
```

**PIQP is a proximal INTERIOR-POINT method** — a different mechanism, hence a genuinely
complementary one.

---

## 5. ⚠ A false verdict this analysis nearly produced

The **first** intersection run reported `CLARABEL: 3,895 / 3,895 failures` and concluded:
*"structural — close v1.1 as Numerically Unimplementable."*

The registered report has Clarabel solving **3,886 / 3,895**. A solver does not go from 9 failures
to 3,895 — **the hand-rolled Clarabel path was wrong**: inverted dual sign convention *and* none of
the pinned regularization/refinement configuration (there is an owner-approved field-mapping
amendment on file for exactly this, and it was re-derived instead of read).

Only the sanity-check against the registered count caught it. Otherwise v1.1 would have been
closed and a v1.2 redesign opened **on the strength of a harness bug.**

> **This is the empirical case for `comments.md` §5.** Characterizers and runtime must *import*
> the canonical acceptance module, wrappers and dual mappings. **Never re-derive a validated
> numerical path.**

---

## 6. Statistical caveat on the zero

The zero is **empirical complementarity on one ladder-conditioned corpus — not proven structural
disjointness.**

Zero double-failures were observed across only **five** square-root failures. If HiGHS's 15.20%
failure rate were independent, `P(observe 0) = 0.848⁵ ≈ 44%`. **A coin flip is not evidence.**

`comments.md` §13 concedes the production corpus **will differ** (the current one was captured under
a raw→sqrt→t-scaled ladder; production will run sqrt→fallback). New square-root failures will
arise, each with a chance of also defeating the fallback:

| cascade | expected double-failures per fresh ~3,900 corpus |
|---|---|
| `SQRT → HIGHS_QPASM` | **≈ 0.76** — roughly even odds the clean preflight stops again |
| `SQRT → PIQP_P2` | **≈ 0.06** |

This **fails closed** (§8 → `INVALID_RUN`), so it is a *schedule* risk, not a correctness risk.
But the clean preflight is a real gate, not a formality.

---

## 7. Recommendations to the erratum

1. **Production fallback = `PIQP_P2`**, not `HIGHS_QPASM`. Freeze the P2 profile
   (`preconditioner_scale_cost = true`) and its dual mapping exactly as §7 does for HiGHS.
   HiGHS joins Clarabel as an **offline independent verifier**.
2. **Bind the five fixtures by instance CONTENT-HASH, not corpus index.** §13 says the corpus may
   differ — index 2765 in a new corpus is a *different problem*, and an indexed fixture suite would
   silently test the wrong instances.
3. **Record the zero as empirical, not structural** (§6), with the 44% figure, so the clean
   preflight is treated as a live gate.

Accepted without change: §4 (fallback eligibility — integrity failures are `INVALID_RUN`, never
fallback), §5 (one canonical imported predicate), §9 (agreement gate), §11–§13.

Withdrawn: the earlier three-solver defence-in-depth proposal. §2's reasoning is correct — a third
stage that removes no required dependency only adds surface.
