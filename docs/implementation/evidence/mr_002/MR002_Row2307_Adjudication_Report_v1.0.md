# MR-002 row 2307 — exact adjudication REPORT v1.0

**Protocol:** `MR002_Row2307_Adjudication_PREREG_v1.0` (frozen before execution).
**Evidence:** `MR002_Row2307_Adjudication.json`, sha256
`179d571d5c6b1db201fda235198c10aaff5623a348f3b31e263f711ad1a3cdef` (byte-identical on the c6a
instance and the laptop at `.mr002out/row2307_adjudication/`).
**Executed:** 2026-07-16, c6a.large (AVX2-only), image `mr002-research:v1.4`,
`OPENBLAS_CORETYPE=HASWELL`, code `5e5bde6`. Exit 0, **zero stops**.

---

## DISPOSITION: **A — `ORIGINAL_EXACTLY_INFEASIBLE`**

The registered original model for corpus row 2307, exactly rationalized from its binary64 values,
**has an empty feasible set**, established by an algebraically verified Farkas certificate.

Dispositions **B** and **C** are **excluded by evidence**, not by assumption.

---

## Front gates

| Gate | Result |
|---|---|
| Corpus reproduced | `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` = registered ✅ |
| Row addressed by content hash | `cfdc115e46f16226…` ✅ |
| Both solvers qualify | `QUADPROG_SQRT: QUALIFIES`, `PIQP_P2: QUALIFIES` ✅ |

## The exact quantity

```
Phase-I optimum = 8947896785247447 / 21778071482940060754961610164661284503552
                ≈ 4.108672704218469e-25          (rendering only — no evidentiary weight)
```

This is the value the ruling required. It is exact, positive, and reproduced identically by every
track below.

## Track results

| Track | Result |
|---|---|
| **1 — production replay w/ trace** | `EXACT_PHASE_I_POSITIVE` for **both** `z_s` (PRIMARY and FALLBACK), identical exact optimum. Production LP: 83 vars, 30 of 31 `m_ub` rows kept (one structurally empty, omitted). |
| **1b — permutation determinism** | Exact optimum **identical**; `M,h` hash **identical**; canonical order stable. ✅ |
| **2 — independent original, unreduced** | **INFEASIBLE.** 45 rows × 57 vars, 76 pivots. Farkas verified: `max(Mᵀy) = 0/1`, **0 violating columns**, `hᵀy > 0`. ✅ |
| **3 — independent full repair** | **INFEASIBLE** for both `z_s`, Farkas verified. ✅ |
| **4 — independent solve of production `M,h`** | **INFEASIBLE**, objective **identical** to production's. ✅ |

**Equivalence invariant held:** original infeasible ⇔ full repair infeasible — confirmed
numerically, not merely argued structurally.

## Why B and C are excluded

**C (exact simplex defect) is excluded.** An independently implemented exact simplex — dense tableau,
duals read from artificial reduced costs, no shared code with `exact_simplex.py` — solved the
**production-generated** `M, h` and returned the **identical exact objective**. The production
simplex is not wrong about its own LP.

**B (construction/reduction defect) is excluded.** A constructor that calls no production assembly,
performs **no row elimination**, keeps all 31 `m_ub` rows, uses a different variable layout and
count (57 vs 83), and preserves incoming order, reaches the **same exact optimum**:

```
independent-original objective == production full-repair Phase-I optimum
8947896785247447/21778071482940060754961610164661284503552
```

Two structurally different LPs agreeing to the last bit of an exact rational is not a coincidence of
implementation. It means the infeasibility is a property of the original equality / inequality /
bound system alone. The min-L∞ repair apparatus contributes nothing to it — as predicted, since `rho`
is unbounded above.

This also **empirically validates the one reduction in the path**: production omitted a
structurally-empty row; the independent constructor kept it and agreed exactly. That reduction was a
live candidate mechanism for B and is now excluded.

**A is affirmed by certificate, not by elimination.** The Farkas certificate `y` satisfies
`Mᵀy <= 0` on **every** column (0 violations) and `hᵀy > 0`, checked in exact `Fraction` arithmetic
against the **unreduced** system. No solver was treated as an authority at any point.

### Verifier trustworthiness

The independent simplex and both verifiers were fixed by known-answer tests before use, including a
deliberately **row-2307-shaped** case (infeasible by `2⁻⁸⁰ ≈ 8.27e-25`, Farkas verified, exact
optimum equal to the contradiction) and **negative controls** confirming the verifier *rejects* a
bogus Farkas vector on a feasible system and *rejects* witnesses with negative entries or nonzero
residuals. A verifier that cannot fail proves nothing.

---

## THE FINDING

> **The registered qualification predicate admitted an exactly infeasible binary64 model.**

Both floating solvers — `QUADPROG_SQRT` and `PIQP_P2` — passed the registered KKT acceptance limits
**and** the two-sided signed Lagrangian gap predicate, on a model whose exact feasible set is
**empty**. Their reported signed gaps were `[-8.674e-17, -8.674e-17]` and `[+4.107e-17, +4.107e-17]`
respectively: comfortably qualifying, on a problem with no feasible point at all.

This is a substantive MR-002 result about the **qualification predicate**, not a defect in the exact
path. The exact path did exactly what it was built to do: it detected, and refused to launder, a
condition that both floating solvers reported as success. The 2,268 preceding rows repaired cleanly;
this one is different in kind, and the harness said so and stopped.

---

## Consequences — for the owner, not for me

Per the ruling, disposition A triggers a **governance question I am not answering**:

**1. Does the frozen population protocol permit this as a recorded category, or require the STOP?**

The frozen §12 text lists *"unexpected Phase-I infeasibility"* among the STOP conditions, and the
code implements it (`mr002_full_population.py:283-289`: `"PHASE_I_POSITIVE" in reason` → *"unexpected
on a qualifying overlap → §12 stop"*). The specification provides **no recorded category** for a
*genuine, certified* exact infeasibility. On a literal reading the STOP was correct and **remains in
force**; admitting row 2307 as a recorded category would be an **amendment to a frozen protocol** and
needs a countersign. I have not treated the adjudication as authorising a resume.

**2. Row 2307 is NOT recorded as a repair failure.** Per the ruling, it is recorded as
**`EXACTLY_INFEASIBLE_REGISTERED_MODEL`**. The repair did not fail — no repair exists, because the
target set is empty. Calling it a repair failure would misattribute a property of the model to the
method.

**3. Deferred governance question (ruling §"If disposition A holds"):** are pipeline-generated
binary64 models permitted to be exactly infeasible, or must model construction guarantee feasibility
before solver comparison? This bears directly on the qualification predicate's meaning across the
whole corpus and is out of scope here.

**4. Population exposure is unassessed and unassessable from this row alone.** 2,268 rows repaired
cleanly, but "no Phase-I positive" is not the same as "original model feasible" — a feasible original
model is a *precondition* the population run never tested independently. How many other qualifying
overlaps sit on exactly infeasible models is **unknown**, and answering it is a separate authorised
question. I make no claim either way.

## Authorised but not run

The near-cancellation lineage analysis of `joint_portfolio`'s expressions for row 2307 (upstream
operands, binary64 hex, operation sequence, resulting coefficient, exact rational, cancellation
diagnostic) is authorised as **diagnostic only**. It may explain *how* an exactly infeasible derived
model arose. It cannot override the exact result, and per the ruling it must not become an arithmetic
rearrangement offered as a replacement model.

## Still not authorised

No population resume. No tolerance or threshold change. No Phase-I epsilon. No rounding of the
optimum. No alternate rationalization. No corpus regeneration. **D remains NOT APPLICABLE under the
currently registered corpus semantics, and retained in the taxonomy.**

---

**State:** c6a instance `i-04b2248581d5f77ef` still up and halted at row 2307/3839; checkpoint
(2,268 `EXACT_REPAIR_OK` + 1 stop) preserved and backed up byte-identically. Nothing resumed.
