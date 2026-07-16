# MR-002 — POPULATION EXACT-FEASIBILITY CENSUS — REPORT v1.0

**Protocol:** `MR002_Population_Feasibility_Census_PREREG_v1.0` (frozen before execution).
**Evidence:** `MR002_PopulationFeasibilityCensus.json`, sha256
`2dd7a6c0f9dac24b2ae686a82550727091b6ce5c8ed8122b298992596f8ee1e3`; checkpoint
`MR002_FeasibilityCensus_checkpoint.jsonl` (3,839 records). Both backed up to
`.mr002out/row2307_adjudication/`.
**Executed:** 2026-07-16, c6a.large (AVX2-only), `mr002-research:v1.4`, `OPENBLAS_CORETYPE=HASWELL`,
code `5e5bde6`. Exit 0, **zero stops**, ~19 minutes.

---

## HEADLINE

> **Population exposure is exactly ONE row. Row 2307 is the only exactly infeasible model in the
> registered population of 3,839 qualifying overlaps.**

| Measure | Result |
|---|---|
| Rows censused | **3,839 / 3,839** (100%) |
| `FEASIBLE` | **3,838** |
| `EXACTLY_INFEASIBLE` | **1** — index **2307** |
| `UNRESOLVED_WITHIN_CEILING` | **0** |
| By distinct model | 3,818 feasible / 1 infeasible over **3,819 distinct models** |
| All certificates verified | **True** |
| Row 2307 reproduces | **`EXACTLY_INFEASIBLE`** |

Every one of the 3,839 verdicts carries an **algebraically verified certificate** — a primal witness
(`Mx = h`, `x >= 0`) for each of the 3,838 feasible rows, a Farkas certificate (`Mᵀy <= 0`,
`hᵀy > 0`) for row 2307 — all checked in exact `Fraction` arithmetic against the **unreduced**
system. No solver was treated as an authority.

## Bindings

| Field | Value |
|---|---|
| Corpus | `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` — reproduced EXACTLY |
| Manifest | `289a834ca328ac734c0a036d9ab22479b901f73ae12d58e7e4f1132b89de9c46` — **verified by recompute**, not trusted from its own field |
| Population | the manifest's 3,839 `population_indices`, not re-derived |
| Duplicates | 20 equivalence classes KEPT; results reported raw AND by distinct model |
| Full-population checkpoint | **untouched** — md5 `9f261f5985c67f26de4f7148f2335370`, still 2,269 rows |

## The positive control

The census reproduced row 2307 **independently of the adjudication run**: same status, same exact
optimum `8947896785247447/21778071482940060754961610164661284503552`, same 76 pivots, Farkas
verified.

This matters more than the count. A census that reports "1 infeasible" is only meaningful if it can
*detect* infeasibility at all. The harness was fixed beforehand by known-answer tests — including a
deliberately row-2307-shaped case (infeasible by `2⁻⁸⁰ ≈ 8.27e-25`) and **negative controls** proving
the verifier rejects bogus certificates — and it then found the one real instance in the population
without being told where it was. **The low count is absence, not blindness.**

## What this closes

The population run had proved 2,268 models feasible *by repairing them*. It said nothing about the
**1,570 rows it never reached**. That gap is now closed: all 1,570 are feasible, with verified
witnesses.

Row 2307 is not the leading edge of a systemic problem. It is a **singleton**.

## What this does NOT establish

**This is not a resume, and it changes no verdict.** It measured a *precondition*, not a repair. It
produced no `rho*`, no repair evidence, and no agreement certificate. Feasibility of the original
model is necessary for a repair to exist — it is not sufficient for a row to PASS. The 1,570
unreached rows remain **unrepaired and uncertified**; their exact repairs have not been computed, and
nothing here predicts their outcome.

The row-2307 STOP **remains in force**. The frozen §12 text lists *"unexpected Phase-I infeasibility"*
as a STOP condition and provides no recorded category for a genuine certified infeasibility. Whether
to admit row 2307 as a recorded category and resume remains an **amendment to a frozen protocol**
requiring an owner countersign. This census informs that decision; it does not make it.

## Bearing on the qualification-predicate finding

The adjudication established that the registered qualification predicate admitted an exactly
infeasible model. The census now bounds that failure's **incidence within this population at 1 in
3,839** (1 in 3,819 distinct models).

Two honest cautions on reading that rate:

1. **It bounds incidence, not severity.** One admitted infeasible model is still a demonstrated
   defect in the predicate's discriminating power. Both floating solvers reported comfortably
   qualifying signed gaps (`-8.674e-17` and `+4.107e-17`) on a problem with no feasible point. Rarity
   does not make the predicate sound; it makes the consequence contained.
2. **It is scoped to the qualifying overlap, not the corpus.** The census covers the 3,839 rows where
   BOTH solvers qualified. The other 56 corpus rows (3,895 − 3,839) were not censused, because they
   are not in the registered population. Whether non-qualifying rows sit on infeasible models is a
   different question and was not asked.

## Deferred (unchanged)

The near-cancellation lineage analysis for row 2307 remains authorised as **diagnostic only** and is
not run here. The governance question — whether pipeline-generated binary64 models are permitted to
be exactly infeasible, or whether construction must guarantee feasibility before solver comparison —
is unaffected by the count and remains open.

---

**State:** c6a `i-04b2248581d5f77ef` up; full-population run still halted at 2307/3839; nothing
resumed; no tolerance, threshold, rationalization, corpus, or model changed.
