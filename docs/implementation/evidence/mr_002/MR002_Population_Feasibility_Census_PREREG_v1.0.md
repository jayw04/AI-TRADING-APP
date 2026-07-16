# MR-002 — POPULATION EXACT-FEASIBILITY CENSUS — pre-registration v1.0 (FROZEN)

**Frozen before execution.** Authorised by the owner on 2026-07-16 following disposition **A** on row
2307 (`MR002_Row2307_Adjudication_Report_v1.0.md`).

## The question

**How many of the 3,839 qualifying overlaps sit on an exactly infeasible registered model?**

Row 2307 established that the registered qualification predicate admitted at least one model whose
exact binary64-rationalized feasible set is empty. The population run never tested that precondition:
"no Phase-I positive" was only ever observed for rows that *reached* a repair, and 2,268 clean
repairs prove those 2,268 models feasible — but say nothing about the 1,570 rows never reached.

## What this is NOT

**This is not a population resume.** It repairs nothing, produces no `rho*`, writes no repair
evidence, and does not advance the halted full-population run. The row-2307 STOP remains in force.
This is a **read-only measurement of a precondition**, on a question the owner authorised separately.

No tolerance change. No epsilon. No alternate rationalization. No corpus regeneration. No arithmetic
rearrangement. No model rebuilding. Nothing is classified by the magnitude of any optimum.

## Method

For every index in the registered population, construct the **original registered model only**:

```
A_eq w        = b_eq
A_ub w + s    = b_ub
w + v         = upper
w, s, v >= 0
```

- Independent constructor (`indep_original`): **no** `build_standard_form`, **no** `empty_rows_of`,
  **no** production canonical ordering, **no** repair assembly, **no** row elimination, **no** `rho`
  / `p` / `q` / submitted point. Incoming order preserved. Structurally-empty rows KEPT, so every
  certificate is checked against the **unreduced** system.
- Registered rationalization semantics only: `to_fraction(x) = Fraction(*float(x).as_integer_ratio())`.
- Independent exact Phase-I simplex (`indep_phase1`), dense tableau + Bland, no shared code with
  `app.research.mr002.exact_simplex`.
- **Every verdict carries an algebraically verified certificate** — Farkas (`Mᵀy <= 0`, `hᵀy > 0`) for
  infeasible, primal witness (`Mx = h`, `x >= 0`) for feasible — in exact `Fraction` arithmetic. No
  solver is an authority.

The independent implementation and both verifiers were fixed by known-answer tests before use,
including a row-2307-shaped case (infeasible by `2⁻⁸⁰`) and negative controls proving the verifier
**rejects** bogus certificates.

## Binding

| Field | Value |
|---|---|
| Registered corpus hash | `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` |
| Population manifest | `289a834ca328ac734c0a036d9ab22479b901f73ae12d58e7e4f1132b89de9c46` |
| Population | the manifest's 3,839 `population_indices` — **not** re-derived |
| Duplicates | the 20 duplicate equivalence classes are KEPT, never deduplicated; results reported raw AND by distinct model |
| Code | `5e5bde6`; census harness reuses the row-2307 validated independent implementation verbatim |
| Environment | c6a.large (AVX2-only), `mr002-research:v1.4`, `OPENBLAS_CORETYPE=HASWELL` |
| Ceilings | 4000 pivots / 600 s per row (registered values, inherited unchanged) |

The manifest hash is **recomputed and verified**, never trusted from its own field: pop
`manifest_sha256`, re-dump with `sort_keys=True, separators=(",",":"), default=str`, sha256, compare.

## Recorded categories

- `FEASIBLE` — primal witness verified.
- `EXACTLY_INFEASIBLE` — Farkas certificate verified.
- `UNRESOLVED_WITHIN_CEILING` — a row exceeded 4000 pivots or 600 s. **Recorded and reported, not a
  stop**: a census that halts on one hard row answers nothing, and silently dropping it would
  overstate coverage. The count is reported in the headline.

## STOP conditions

Corpus hash mismatch · manifest hash mismatch · **certificate verification failure** (a produced
certificate that does not verify means the harness is broken, not the model) · any non-rational or
non-finite quantity · a row not classifiable into the categories above.

## Checkpoint

Append-only JSONL, one line per completed row, each binding the manifest hash and a per-record hash,
flushed and fsynced. Resume continues from the first uncompleted index in frozen order; it never
reruns only favourable rows and never merges incompatible manifests.

## Permitted output

One JSON artifact + a written report giving: rows censused, `FEASIBLE` / `EXACTLY_INFEASIBLE` /
`UNRESOLVED` counts (raw and by distinct model), the full list of infeasible indices with their exact
Phase-I optima as rationals and certificate verification status, and whether row 2307 reproduces.

**No disposition, no verdict, no resume decision** follows from this census. It measures exposure and
hands the governance question back to the owner.
