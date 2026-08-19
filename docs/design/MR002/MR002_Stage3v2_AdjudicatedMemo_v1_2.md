# MR-002 Stage-3 v2 — Adjudicated Review Memo v1.2 (FINAL)

**Program:** MR-002 / SPQ-1 · **Date:** 2026-08-19
**Consolidates:** Review Memo v1.0 + Adjudicated Review Memo v1.1 · **Supersedes:** v1.1
**Type:** governance record — carries the owner-signable N1 authorization in §5; authorizes nothing else

---


## 0. v1.2 change summary

v1.2 makes three scope/rigor corrections without changing the Gate-N1 business decision:

1. **N1/N2 authority boundary:** Solver-B selection is completed in N1 using the frozen development corpus only. N2 is a qualification of that already-selected A/B pair on the preregistered synthetic stress population; N2 may PASS or STOP, but may not substitute a solver. Any substitution restarts N1.
2. **Cycle-2C sequencing:** all Validation-2 design decisions, including VA-1, sit behind **N3**, not merely N2.
3. **Administrative interim rigor:** bounded portfolio exposures do not by themselves create a rigorous upper bound on future cumulative returns. A Validation-2 interim may fast-fail only on a logically irreversible frozen-gate failure (for example, an integrity/numerical stop, or a completed-fold state from which Config-B's 3-of-5 gate is arithmetically impossible). Config-A/C cumulative-return gates receive no early-fail shortcut unless Cycle-2C separately derives and freezes a mathematically valid remaining-contribution bound.

No validation data, consumed validation artifacts, or OOS information is authorized or used by these corrections.

---

## 1. Adjudicated dispositions

| Item | Ruling | Final form |
|---|---|---|
| Part I closure rulings | ACCEPT | Unchanged from v1.0. "Method limitation, not economic evidence" quoted verbatim in future MR-002 decision records. |
| DR-1 reconcile precondition | ACCEPT + refined | Run-scoped: before any governed opening, reconcile all durable-evidence journals in the active program/run namespace; dangling read_intent, invalid hash chain, duplicate sequence, missing terminal disposition, or unresolved EVIDENCE_INCOMPLETE blocks the opening until adjudicated. Every journal row carries an immutable run_id. Platform infrastructure, reusable beyond MR-002. |
| SA-1 equivalence bound | MODIFY (v1.0 overclaimed) | See §2. Derived or prospectively calibrated; never residual-assumed, never hand-picked. Reference Solver R added (development/qualification only). |
| SA-2 disagreement disposition | ACCEPT | Both-certify-beyond-bound → CERTIFIED_SOLUTION_DISAGREEMENT → INTEGRITY_FAILURE (uniqueness contradiction impugns the certification system). No lower-objective pick, no voting, no re-run with new settings. |
| SA-3 frozen words | ACCEPT | N1: 100% of the registered development population ends in a preregistered admissible state; previously accepted v1 instances return equivalent certified allocations; residual unresolved instances individually classified — no aggregate percentage hiding a tail. Stress: 100% registered resolution or STOP. |
| SA-4 bakeoff mechanics | ACCEPT + strengthened / stage-split | **N1 selection uses development evidence only:** zero integrity defects → 100% dev-corpus certified resolution → agreement with R → deterministic reproducibility → then runtime → then dependency simplicity. Candidate set, profiles, corpus and selection rule are frozen before results. N1 selects exactly one Solver B alongside Solver A. **N2 then qualifies that fixed A/B pair on the preregistered stress population at 100% resolution or STOP; N2 may not substitute Solver B.** Any solver substitution restarts N1. Exactly two production generators, permanently. |
| SA-5 incident knowledge | ACCEPT + named | Permitted: INCIDENT_CLASS_KNOWLEDGE (a production QP generator can terminate without a candidate). Prohibited: CONSUMED_VALIDATION_INSTANCE_INFORMATION (coefficients, date, securities, target vector, constraint geometry, iteration trajectory). |
| SA-6 replay equivalence | ACCEPT + strengthened | Allocation equivalence is the primary Layer-5 gate; full A/B/C economic replay reconciles within a mechanically derived bound as a downstream invariant. Deviation in either direction — including improvement — fails the gate pending investigation. |
| VA-1 sample design | MODIFY substantially — DEFERRED | See §3. No α-spending; deferred to Cycle-2C adjudication **only after N3 passes**. |
| VA-2 paper-track merge | ACCEPT conditionally | See §4. Two-plane firewall + contamination rule. |
| VA-3 accrual infrastructure | ACCEPT (relevant post-N3) | GAPPER-hardened mechanisms wholesale, plus an autonomy dry-run before the accrual clock starts: a fixed run of consecutive eligible sessions (provisionally ~20; number frozen at Cycle 2C) with zero missing provenance, zero manual repair, zero interactive intervention, zero decision regeneration. |
| Gate N1 | GRANT | §5. |

---

## 2. SA-1 final form — candidate-equivalence bound

The v1.0 formulation assumed certified KKT residuals directly bound the objective gap; they do not. Final rule:

**The both-certified agreement threshold is never chosen by inspection. Before v2 freeze, either (a) rigorously derive the bound from the registered QP structure and certificate quantities, or (b) failing rigor, define it prospectively from development-only numerical qualification against Reference Solver R. No validation information may influence it.**

**Primary derivation route (for the N1 certificate-research task):** strengthen the certificate so each candidate carries a computable primal-dual (duality) gap — a primal-feasible point (exactly, or via a frozen restoration/projection step onto the linear constraints, or with feasibility-residual terms folded into the bound) plus a dual-feasible multiplier pair with computable dual objective q(λ). Then f(x) − f* ≤ g = f(x) − q(λ) rigorously, and strict convexity (μ = 2/max targetᵢ) gives ‖x_A − x_B‖ ≤ √(2g_A/μ) + √(2g_B/μ). The feasibility qualifier is where rigor is won or lost; if it cannot be closed cleanly, route (b) applies.

**Reference Solver R:** high-precision implementation establishing numerical truth on development and stress instances only. Never production, never a third voter, never consulted on any validation instance. N1's agreement question becomes: do A and B certified solutions agree with each other AND with R to the preregistered bound?

---

## 3. VA-1 final form — deferred, deterministic interim

The v1.0 "power analysis + α-spending" language was a category error: the frozen gates (Config B ≥3/5 positive folds; Config A and C cumulative > 0; integrity admissible) are deterministic decision rules, not hypothesis tests — there is no test statistic and no α to spend.

Final rule (Reviewer 2 Option A, adopted and tightened): defer the full Validation-2 sample design to a dedicated Cycle-2C adjudication held **only after N1, N2, and N3 pass**. At that adjudication, pre-register: full prospective N; exact folds; and at most **one administrative fast-fail interim that can only terminate for failure**. Never an early success declaration.

The interim may fire only on a **logically irreversible failure under the already-frozen gates**. Examples include: (a) a validation numerical/integrity stop whose frozen consequence is no advancement; or (b) a completed-fold state in which Config B can no longer reach 3 positive folds out of 5 even if every remaining fold is positive. **Do not infer a maximum future cumulative return merely from position caps, exposure bands, or loss controls.** Those controls bound portfolio construction/exposure, not necessarily upside price returns. Therefore the Config-A and Config-C cumulative-return gates receive no early-fail shortcut unless Cycle-2C separately derives, reviews, and freezes a mathematically valid remaining-contribution bound. If no such bound is established, A/C are adjudicated only at the full-sample endpoint.

Statistical redesign of Validation-2 (Option B) remains out of scope unless Cycle-2C explicitly chooses it.

Nothing about Validation-2 — length, folds, interim, accrual infrastructure — is frozen now, and no work on a new validation sample starts before N3 passes.

---

## 4. VA-2 final form — paper-track merge with firewall

Accepted: frozen-v2 prospective accrual doubles as MR-002's paper track record, converting accrual time into the platform deliverable. Conditions:

- **Decision plane:** frozen MR-002 v2 produces decisions without access to execution outcomes.
- **Observation plane:** paper execution records fills, slippage, rejects, borrow availability; stored and reported; can never alter frozen validation decisions or the solver.
- **Contamination rule (explicit):** any strategy change motivated by paper results during prospective validation terminates Validation-2 for that version; the modified strategy is a new version requiring a new prospective sample.

---

## 5. Authorization — MR-002 Stage-3 v2 / Gate N1 (DEVELOPMENT PROTOTYPE)

**Status: GRANTED (owner signature below). Scope: N1 only. Program status: CONDITIONAL RESEARCH RESTART — GATE N1 ONLY.**

**Objective:** determine whether a fixed certificate-driven two-generator Stage-3 method achieves 100% admissible resolution on the existing development population while preserving the frozen Stage-3 economic solution.

**Allowed:** existing development QPs; PIQP; candidate secondary solvers; development-only Reference Solver R; certificate research; equivalence-bound derivation (§2); and **design/pre-registration** of the deterministic synthetic stress generator and seed for N2. N1 may use only development-domain fixtures needed to test generator plumbing; it does not consume the N2 stress population as qualification evidence.

**Prohibited:** the consumed validation DuckDB (c4cabab2…) and any validation-derived QP; OOS; A/B/C parameter changes; cost changes; constraint changes; Stage 1/2 changes; using historical returns to select Solver B; per-instance solver-profile changes.

**Outputs (exhaustive):** candidate architecture; **N1-selected and frozen Solver A/B profiles**; Reference-Solver method; certificate specification; equivalence rule; full development census; difference-vs-v1 report; and the preregistered N2 stress-generator specification/seed (without using N2 results).

**Disposition:** N1_ADVANCE or N1_STOP. N1_STOP closes MR-002 without a further validation/governance cycle. N1_ADVANCE freezes the selected A/B pair but authorizes nothing beyond N1 — N2 requires its own grant. If later work proposes a different Solver A/B profile or substitutes Solver B, N1 must be rerun under a new prospective selection record.

**Sequencing:** N1 → (pass) N2 stress + reproducibility → (pass) N3 development behavioral/economic equivalence replay → (pass) Cycle-2C design adjudication (VA-1 sample design, VA-2 merge mechanics, VA-3 infrastructure, untouched-sample definition) → freeze → accrual. All Cycle-2C decisions sit behind numerical success. N1 is developer work and consumes no owner-queue capacity ahead of already-ordered items; owner adjudication points are the N1 verdict and Cycle 2C.

---

*Owner approval of §5 constitutes the N1 grant. All other items take effect per their stage as listed in §1.*
