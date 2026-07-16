# MR-002 full-population protocol — AMENDMENT v1.0 (COUNTERSIGNED)

**Amendment id:** `MR002_FullPopulation_Amendment_v1.0`
**Countersigned:** owner, 2026-07-16, after the row-2307 adjudication (disposition **A**) and the
completed population exact-feasibility census.
**Amends:** the frozen full-population protocol (owner ruling 2026-07-14 §7–§13) as implemented by
`scripts/mr002_full_population.py`.

**Basis:**
- `MR002_Row2307_Provenance_Note_v0.1.md` — Case 1 established.
- `MR002_Row2307_Adjudication_PREREG_v1.0.md` / `..._Report_v1.0.md` — disposition **A**, evidence
  sha256 `179d571d5c6b1db201fda235198c10aaff5623a348f3b31e263f711ad1a3cdef`.
- `MR002_Population_Feasibility_Census_PREREG_v1.0.md` / `..._Report_v1.0.md` — 3,838 feasible / 1
  infeasible / 0 unresolved, evidence sha256
  `2dd7a6c0f9dac24b2ae686a82550727091b6ce5c8ed8122b298992596f8ee1e3`.

---

## §1 The original STOP remains valid and visible

The frozen protocol **stopped correctly**. Certified exact infeasibility was not an anticipated
terminal category, so §12's *"unexpected Phase-I infeasibility"* fired exactly as specified. This
amendment does **not** retroactively remove, redefine, or excuse that STOP. It remains part of the
historical record, and row 2307's original checkpoint record is preserved **byte-identical**
(checkpoint md5 `9f261f5985c67f26de4f7148f2335370`, 2,269 records). Nothing is rewritten.

## §2 One new admissible terminal outcome, bound to row 2307 ALONE

Terminal outcomes become:

```
EXACT_REPAIR_OK
EXACTLY_INFEASIBLE_REGISTERED_MODEL      <- new, single-row scope
EXACT_PATH_STOP
```

> `EXACTLY_INFEASIBLE_REGISTERED_MODEL` is authorized **only** for the countersigned row-2307
> identity:
>
> ```
> index:        2307
> content_hash: cfdc115e46f16226fafbe59b73890adca2f0c2f27b6f42c3ebebdce4d18ea30f
> ```
>
> **Both** must match — index alone is not sufficient (it protects against index drift; the content
> hash protects against substitution).
>
> Any `EXACT_PHASE_I_POSITIVE` outcome for **any other registered row** is an **immediate STOP**,
> **regardless of whether a candidate certificate is produced**, because it contradicts the completed
> exact-feasibility census.

**Why the category is not generalised.** The census certified every other registered row
`FEASIBLE` with an algebraically verified **primal witness**. Given the proved and numerically
confirmed equivalence (*original feasible ⇔ full repair feasible*, since `rho` is unbounded above),
the resumed run must encounter **exactly zero** further Phase-I positives. A new one would not be
another instance of a known category — it would place a verified Farkas certificate and a verified
primal witness in contradiction for the same row, which is arithmetically impossible. That indicates
a broken verifier or constructor, not a model property. Recording it would launder a harness failure
into a model finding — precisely what this category exists to prevent. The certificate standard
cannot discriminate in that scenario, because the certificate machinery is itself the suspect.

Row 2307's registered disposition:

| Field | Value |
|---|---|
| `index` | 2307 |
| `status` | `EXACTLY_INFEASIBLE_REGISTERED_MODEL` |
| `repair_status` | `NOT_APPLICABLE` |
| `agreement_certificates` | `NOT_APPLICABLE` |
| `population_inclusion` | `INCLUDED` |
| `feasible_population_inclusion` | `EXCLUDED` |
| `reason` | verified exact Farkas certificate (`Mᵀy <= 0` on every column, `hᵀy > 0`) |

It is **not** a pass, **not** a repair failure, and **not** an implementation defect.

## §3 Exact-path provenance binding (closes a governance defect)

The original qualification manifest (`289a834c…`) binds the **selection and floating qualification
path** — `directed.py`, `certificate.py`, `joint_portfolio.py`, `coverage_signed_gap.py`,
`solver_intersection.py`, `mr002_directed_rounding_correction.py`, and its test. It does **not** bind
the exact repair authority or the runner. `build_manifest` records only
`repair_manifest()["method"] = "EXACT_MIN_LINF_REPAIR_LP"` — and **discards** the source hash that
`repair_manifest()` computes over `build_standard_form`, `canonical_order`, `lp_content_hash`,
`exact_repair`, `certify_repair`, `agreement`, `objective_agreement`.

So the exact evidentiary authority's implementation was unidentified by the manifest, and so was the
runner this amendment modifies.

The resumed artifact MUST therefore carry an **`amendment_exact_path_binding`** block:

- runner commit SHA · `mr002_full_population.py` sha256
- `exact_repair.py` · `exact_simplex.py` · `certificate.py` sha256
- the previously discarded `repair_manifest()` source hash
- container image digest · Python version + ABI
- **callable provenance**: `certify_repair.__module__`, `agreement.__module__`,
  `objective_agreement.__module__`, and `exact_repair.solve_lp is exact_simplex.solve_lp` — guarding
  the *module-present vs function-actually-invoked* ambiguity.

**The original manifest is NOT revised.** It is preserved and hash-verified; the binding block is a
countersigned **companion**, additive only.

## §4 Two denominators — no collapsed success rate

The resumed report MUST report both populations and MUST NOT collapse them:

```
End-to-end floating-qualified population      : 3,839 rows
Exactly feasible repair population            : 3,838 rows
Exactly infeasible registered models          :     1 row
```

and separately:

```
exact repair success rate                     = successful exact repairs / 3,838
floating-predicate exact-feasibility admission rate      = 3,838 / 3,839
floating-predicate exact-infeasibility false-admission rate =     1 / 3,839
by distinct model                             =     1 / 3,819
```

**Row 2307 is excluded from every repair statistic**: distance-agreement pass rate, objective-
agreement pass rate, repair runtime distribution, repair pivot distribution, repaired-point
determinism, repaired-point shuffle invariance. It appears only in a separate exact-feasibility
section.

## §5 In-artifact amendment banner

A detached amendment document is insufficient. The primary JSON MUST carry a top-level block:

```json
{
  "protocol_status": "AMENDED_AFTER_AUTHORIZED_STOP",
  "amendment_id": "MR002_FullPopulation_Amendment_v1.0",
  "amendment_reason": "Certified exact infeasibility of registered row 2307",
  "denominator_change": {
    "original_expected_records": 3839,
    "exactly_feasible_repair_population": 3838,
    "exactly_infeasible_registered_models": 1
  }
}
```

and the human-readable banner MUST read **`FULL POPULATION — AMENDED PASS`**, never an unqualified
`FULL POPULATION: PASS`, stating that the original frozen run stopped correctly at row 2307, that the
PASS denominator is 3,838 exactly feasible rows, and that row 2307 is separately recorded and counted
as neither a repair success nor a repair failure.

## §6 All other stops unchanged

Resume still halts on: constructor defect · certificate-verification failure · determinism failure ·
shuffle-invariance failure · resource-ceiling breach · unexpected solver inconsistency ·
**any Phase-I positive outside the row-2307 identity** · unclassified result · manifest/corpus/record
hash mismatch. Ceilings are unchanged and, per the frozen note, *"may not be raised after observing a
stopped instance without a new adjudication"*.

## §7 Resume mechanics

Resume from the **verified untouched checkpoint**; do not restart the population and do not recompute
or overwrite the 2,268 completed repairs. Row 2307's record is **not** rewritten — the amendment
reclassifies it at aggregate time from the preserved record, so the checkpoint stays byte-identical.

Pre-resume verification (all must pass): checkpoint md5 · corpus hash · manifest hash (recomputed) ·
solver-path module hashes · last completed row · row-2307 adjudication artifact hash · census
artifact hash.

Final artifact provenance must show which records came from: the original run · the row-2307
adjudication · the feasibility census · the amended resumed run.

## §8 The predicate conclusion (registered wording)

> The registered floating-point qualification predicate is **not an exact-feasibility test**. It
> admitted one certified exactly infeasible binary64 model among 3,839 qualifying overlaps. The
> observed incidence is contained but nonzero. Exact feasibility must therefore be established by the
> exact evidentiary path, not inferred from floating KKT and signed-gap qualification.

The predicate is **not** described as generally invalid. It remains useful as a solver-overlap
selection rule. What is disproved is its **sufficiency as exact-feasibility evidence**.

## §9 Unchanged

Global tolerances · thresholds · rationalization semantics · corpus · model · ceilings — **all
unchanged**. No Phase-I epsilon. No rounding of any optimum. No arithmetic rearrangement. No upstream
model rebuild. Nothing is classified by the magnitude of any optimum.

## §10 Deferred

The row-2307 near-cancellation lineage analysis remains **diagnostic only** and does not block
resumption. Its result may motivate future pipeline hardening but **cannot alter row 2307's
registered disposition**.
