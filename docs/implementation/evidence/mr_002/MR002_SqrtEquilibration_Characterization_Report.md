# MR-002 v1.1 — SQUARE-ROOT EQUILIBRATION CHARACTERIZATION

**Date:** 2026-07-12 · **VERDICT: 🔴 FAIL — returning for adjudication as instructed.**

*"If the square-root formulation fails even one captured problem … stop and return for further
adjudication. Do not raise ε_include, add another formulation or introduce another optimizer without a
separate ruling."*

**No performance computed. Validation and sealed OOS remain sealed and unread.**

---

## 0. Headline

**The square-root formulation is a large improvement — and it is still not sufficient. More
importantly: NO combination of the three quadprog formulations solves every instance.**

| Formulation | Failures / 3,895 | |
|---|---|---|
| **RAW** | **70** | 62 false-inconsistency exceptions + 8 corrupted-dual returns |
| **T-SCALED** (`u = z/t`) — *the currently registered rescue* | **185** | **worse than raw** |
| **SQRT** (`v = z/√t`) — the candidate | **5** | 14× better than raw, 37× better than t-scaled |
| **raw → sqrt → t-scaled (all three)** | **2** | ← **the entire quadprog family fails on 2 instances** |

**That last row is the decisive finding.** Two instances defeat *every* formulation available under the
registered solver. No cascade built from quadprog alone can be complete.

---

## 1. Method (and one disclosure)

**Two corpora, per your ruling.**

**⚠️ DISCLOSURE — the historical corpus was NOT persisted.** My earlier census counted failures but never
serialized the matrices. I cannot preserve what I did not save, and you explicitly forbade passing off a
regenerated set as byte-equivalent. **The historical corpus is therefore unavailable**, and the evidence
below rests entirely on the **prospective corpus**. I record this as a process failure on my part: a
characterization that may need to be replayed must serialize its instances *at capture time*.

**Prospective corpus:** 3,895 Stage-3 instances, captured from session 1 on clean immutable state across
A/B/C. Each instance is serialized and hashed **before** any solver result affects the next portfolio
state. Corpus hash `1d2319301a7b52df…`; instances persisted to `MR002_Stage3_Corpus.npz` with per-instance
hashes.

**Capture-path caveat (disclosed).** The proposed **raw → sqrt** cascade **cannot complete the path** — sqrt
raises on at least one instance. Capture therefore used a **ladder** (raw → sqrt → t-scaled → HiGHS
feasible point) purely as a **device to reach the next session**. The ladder is **not** a proposed remedy.
All three formulations were then compared **offline, on immutable copies**; no offline result fed back into
the path.

---

## 2. Gate results

| Gate | Result |
|---|---|
| Zero solver exceptions on the corpus | 🔴 **FAIL** — 5 raise `constraints are inconsistent` |
| Every raw exception rescued | 🔴 **FAIL** — **59 / 62** |
| Every corrupted-dual result rescued | 🟢 **PASS** — **8 / 8** |
| Every double failure rescued | 🔴 **FAIL** — **1 / 3** |
| Primal agreement with raw-clean ≤ 1e-8 | 🟢 **PASS** — **3.83e-14** |
| Objective agreement ≤ 1e-8 | 🟢 **PASS** — **7.00e-14** |

---

## 3. What the square-root formulation DOES achieve

Where it works, it works **cleanly and exactly**:

- **Fixes the entire new defect class.** All **8/8** corrupted-dual instances are rescued with a valid
  original-coordinate certificate. Worst sqrt stationarity across the whole corpus: **1.89e-10** (limit
  1e-8) — versus **17.5** for raw.
- **Agrees with raw to 3.8e-14** on primal and **7.0e-14** on objective across 3,825 raw-clean instances.
  The transformation is exact, as designed.
- **Strictly dominates the currently-registered t-scaled rescue** (5 failures vs 185). The t-scaled
  formulation is in fact *worse than raw*, which is itself a finding: **the registered rescue is a poor
  one, and it survived only because the pre-Defect-A harness rarely exercised it.**

Bound-multiplier amplification falls from `1/t ≈ 1e8` to `1/√t ≈ 1e4`, which is exactly why the dual
certificates stop being corrupted.

---

## 4. Why it still fails — and why the family is exhausted

Every failure carries the same signature, unchanged from every prior investigation:

```
min target seen        = 1.0007e-08      (eps_include = 1e-8)
max Hessian entry seen = 1.9986e+08      (= 2/t)
```

The 5 sqrt failures are all `constraints are inconsistent, no solution` — a **feasibility-detection**
failure inside Goldfarb–Idnani, on regions HiGHS proves feasible. Equilibrating the Hessian to exactly
`2I` removes the *Hessian* conditioning problem entirely, but it **cannot** fix the conditioning of the
**constraint matrix**: `A·S` still has columns spanning `√t`, a range of ~1e3, and the active-set
factorization degenerates there.

**This is the ceiling of coordinate transformation.** Any positive-diagonal rescaling trades Hessian
conditioning against constraint conditioning; none of them makes both well-scaled, because the ill-scaling
is in the *problem data* (`t` spanning 1e-8 → 1.5e-2), not in the coordinates.

---

## 5. Options — I have selected none

1. **Register sqrt as the single rescue anyway.** A strict, large improvement (raw+sqrt → 5 residual
   failures vs the current raw+t-scaled → ~65). **Does not achieve zero.** Would still require a ruling on
   the residual 5.
2. **Register a different QP solver for the residual cases.** You have consistently resisted this, and I
   have no characterized candidate to offer. *(Recording only: HiGHS proves every failing region feasible,
   and an independent SLSQP solved the earlier double-failures — evidence the regions are solvable, not a
   proposal.)*
3. **Revisit `ε_include`.** You rejected my `2/H_MAX` derivation and you were right — I conflated an
   eigenvalue-*ratio* bound with an absolute *entry* bound. I am **not** re-proposing it. I note only the
   empirical fact, without a proposed action: **every failure across every investigation carries a variable
   at ≈ 1.0007 × `ε_include`.**
4. **Constraint-side conditioning** (not yet characterized): the failures are constraint-feasibility
   failures, and `A_ub` contains structurally near-dependent rows — for a sector holding a single position,
   `sector_gross ≡ |sector_net|`, making those rows linearly dependent. Removing provably-redundant rows is
   an exact transformation that does not change the feasible set. **This attacks the actual failure mode
   (constraint degeneracy) rather than the Hessian.** I have not characterized it and would not without a
   ruling.
5. **Accept 2–5 `INVALID_RUN` in 3,895.** You rejected this in principle.

---

## 6. My assessment

The square-root transformation was the right thing to try and it **did** fix the defect it was aimed at —
the corrupted duals — completely and exactly. But the residual failures are **not** a Hessian problem, so
no further Hessian-side transformation will close them. **Option 4 is the only remaining exact,
same-solver avenue**, because it targets the constraint degeneracy that is actually failing. If it does not
close the gap either, then the honest conclusion is that **quadprog is the wrong solver for this problem
class**, and the choice narrows to registering a different QP solver or changing the problem data.

**Nothing further runs until you rule.**

---

## 7. Artifacts

| File | |
|---|---|
| `runtime/MR002_SqrtEquilibration_Characterization.json` | full results, all gates |
| `runtime/MR002_Stage3_Corpus.npz` | 3,895 immutable Stage-3 instances |
| `runtime/MR002_Stage3_Corpus_Hashes.json` | corpus hash + per-instance hashes |
| `scripts/mr002_characterize_sqrt.py` | the characterization harness |

**Preflight and development run remain STOPPED. Defects A and B remain fixed (55/55 fixtures).**
