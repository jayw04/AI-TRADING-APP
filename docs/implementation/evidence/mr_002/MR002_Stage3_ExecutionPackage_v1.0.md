# MR-002 Stage-3 — Execution Package (finalized cascade `QUADPROG_SQRT → PIQP_P2`)

**Version:** v1.0 — **SUBMITTED FOR THE EXECUTION COUNTERSIGNATURE.**
**Status:** implementation + fixtures + package prep, complete. **No Stage-3 instance has been run.**
**Companion manifest (machine-readable):** `MR002_Stage3_ExecutionPackage_v1.0.json`,
SHA-256 `53e7bbe06143a157b97096b0731ae482ba2177294059bb4e075743a865f9b2f0`, 17,245 B, LF.

---

## What this is, and what it is not

The owner **countersigned the successor Stage-3 design (DESIGN ONLY) on 2026-07-17**
(design commit `3548a2d`; countersign `MR002_Stage3ProspectiveAdjudication_Countersign_v1.0.json` at
commit `b8e95e1`). That countersignature authorized *implementation work* and explicitly **withheld
execution**: adjudication §10 requires a **separate execution countersignature** that binds the
finalized implementation, the eligibility fixtures, the source manifest, the image digest, the runtime
configuration, the regenerated-population protocol, and the clean-run stop gates **before any Stage-3
instance may be resolved.**

This package is that binding, assembled for the owner to grant or withhold the execution
countersignature. **It executes nothing.** It does not touch the registered corpus, the frozen
dataset, or any population-selection loop; it does not open validation or sealed OOS; it does not
compute performance; and it does **not** rehabilitate the suspended `MR002_Implementation_Erratum_v1.0`
or the quarantined `AMENDED PASS` — both of which remain, respectively, suspended and non-reusable.

The finalized cascade adds **exactly one thing** over the frozen diagnostic scripts: the §7 total
**eligibility decision table**. The numerics are the frozen implementations, **imported, not
re-derived** — the primary is `QUADPROG_SQRT` (`S^T H S = 2I` exactly), the fallback is the `PIQP_P2`
profile (`mr002_piqp.py` `BASE`, `preconditioner_scale_cost=true`), and acceptance is the single
registered certifier (registered KKT `LIMITS` + the two-sided signed Lagrangian gap). No new numerical
method is introduced.

---

## The finalized cascade (adjudication §7)

`app/research/mr002/stage3_cascade.py` runs the primary once, normalizes its raw behavior into the
closed enum, and — only on an eligible numerical nonqualification — invokes the one fixed fallback
**exactly once**:

```
closed enum:  QUALIFIED · NUMERICAL_STATUS_NONQUALIFICATION · CERTIFICATE_NONQUALIFICATION · INTEGRITY_DEFECT
              (default_for_unrecognized = INTEGRITY_DEFECT — never fallback-eligible, never by analogy)

primary QUALIFIED                         → PRIMARY_QUALIFIED        (accept primary; fallback NOT invoked)
primary NUMERICAL_STATUS_NONQUALIFICATION ┐
primary CERTIFICATE_NONQUALIFICATION      ┴→ invoke PIQP_P2 once
    fallback QUALIFIED                     → FALLBACK_QUALIFIED       (accept fallback)
    fallback NUMERICAL / CERTIFICATE       → UNRESOLVED_NUMERICAL_FAILURE  (STOP)
    fallback INTEGRITY_DEFECT              → INVALID_RUN              (STOP)
primary INTEGRITY_DEFECT                   → INVALID_RUN             (STOP; fallback NEVER invoked)
model-input defect (e.g. tᵢ ≤ 0)          → INVALID_RUN             (STOP; no solver constructed)
```

**Matching discipline (§7-B).** The numerical allowlist is keyed on the **exact exception class AND
the exact complete message**. The sole registered entry is
`(ValueError, "constraints are inconsistent, no solution") → QUADPROG_CONSTRAINTS_INCONSISTENT`.
No substring, regex, or partial match; a superstring, a wrong class, or a wrong message is
`INTEGRITY_DEFECT`, never a rescue.

**Injection seam.** `resolve_instance(rec)` binds the frozen production implementations (lazily, so the
decision-table logic imports without the solver stack). `resolve(rec, *, primary, fallback,
certify_fn)` exposes the same table for the fixtures. The production path has no test seam wired into
it — the stubs are only reachable through the explicit internal `resolve`.

---

## The seven bound items

| # | Item | Where |
|---|------|-------|
| 1 | Implemented-cascade source + tree identity (3 files, sha256 + git-blob + byte length; LF) | manifest `package_binds.1` |
| 2 | Complete §7 eligibility fixtures — every branch, incl. the fallback-not-invoked proof | manifest `package_binds.2` |
| 3 | Container image digest (`mr002-research:v1.4` `sha256:aa930021…`, OCI config `770553ae…`) | manifest `package_binds.3` |
| 4 | Runtime configuration (AVX2-only CPU + `OPENBLAS_CORETYPE=HASWELL` + single-thread BLAS + LIMITS/PIQP BASE) | manifest `package_binds.4` |
| 5 | Regenerated-population protocol (§10 clean rerun; corpus re-verified vs `1d231930…`) | manifest `package_binds.5` |
| 6 | Quarantine non-reuse checks (mechanical: no quarantined import/token/loop) | manifest `package_binds.6` |
| 7 | Stop behavior (§7-C / §7-D / §11) | manifest `package_binds.7` |

### 2 — the eligibility fixtures, and how they are validated

`tests/research/test_mr002_stage3_cascade_dispA.py` drives **all nine required branches** plus the
completeness invariants. It validates the **decision table** in isolation from the numerical stack by
injecting stub solvers / a stub certifier — which makes each branch deterministic and lets the fixtures
run without quadprog / piqp / mpmath. The nine branches:

1. valid solver exception eligible for rescue → `FALLBACK_QUALIFIED`
2. finite candidate failing one KKT gate → primary `CERTIFICATE_NONQUALIFICATION` → fallback
3. finite candidate failing **only** the signed-gap gate → primary `CERTIFICATE_NONQUALIFICATION`
4. non-finite candidate → `INVALID_RUN`, fallback not invoked
5. wrong-sized candidate → `INVALID_RUN`, fallback not invoked
6. unknown status → `INTEGRITY_DEFECT` → `INVALID_RUN` (with wrong-class, wrong-message, and
   superstring cases proving exact-match, no substring/analogy)
7. certifier exception → `INVALID_RUN`, fallback not invoked
8. both solvers numerically nonqualify → `UNRESOLVED_NUMERICAL_FAILURE` (STOP)
9. **primary integrity failure — proof the fallback was not called** (`fallback_invoked == False`
   *and* the fallback callable is never constructed: a recording spy asserts `calls == 0`)

**Run in this session:** `python -m pytest tests/research/test_mr002_stage3_cascade_dispA.py` →
**24 passed** (backend `.venv`, numpy 2.2.6; no solver stack required).

The numerical **producibility** of each enum against the **real** frozen solvers + real certifier on
tiny hand-solvable problems is exercised by the in-image realism harness
`scripts/mr002_stage3_cascade_fixtures.py` (`PRIMARY_QUALIFIED` end-to-end with the real
`QUADPROG_SQRT` + certifier; `FALLBACK_QUALIFIED` with the real `PIQP_P2` + certifier on the rescue
path). That harness needs the pinned image (quadprog/piqp/mpmath) and is therefore **not run here**; it
runs as part of the clean rerun once execution is countersigned. That the registered `ValueError` is a
real `QUADPROG_SQRT` behavior is already established, admissibly, by the immutable characterization
corpus (§6: the five `F_Q` rows).

### 6 — quarantine non-reuse (mechanical, not merely asserted)

- The finalized module imports **none** of `mr002_full_population`, `FrozenDataset`, the runner
  `CONFIGS`, the corpus, or the frozen duckdb — only the frozen primary/fallback/certifier. (Verified
  by source scan.)
- No quarantined token — content-hash, row index `2307`, population count `3839`, corpus hash,
  checkpoint, or `AMENDED`-`PASS` marker — appears anywhere in the finalized source, the fixtures, or
  the realism harness. (Verified by grep — clean.)
- The fixtures and the realism harness operate only on tiny hand-built problems; they never open the
  corpus, the dataset, or a population-selection loop.

Crucially, the finalized cascade **does not reproduce the population-constitution defect** that caused
the quarantine: the quarantined run resolved *both* solvers on every row and took the set intersection,
so population membership depended on the prohibited fallback. The finalized cascade resolves the
**primary first** and reaches the fallback only on an eligible primary nonqualification — the fallback
never constitutes the population.

---

## What the execution countersignature would authorize (and its preconditions)

On a **separate** execution countersignature binding the seven items above, the clean successor rerun
(§10) may run: fresh checkout at the countersigned implementation commit; fresh container/runtime
binding; the complete corpus and all overlap/coverage manifests **regenerated anew** and re-verified
against `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b`; no quarantined artifact,
row disposition, or checkpoint reused; validation and sealed OOS **inaccessible**. The future
unresolved set is **unknown until executed** — it is not asserted to be zero, and
`UNRESOLVED_NUMERICAL_FAILURE → STOP` remains a live outcome.

**Until that countersignature exists, nothing here runs.** `MR002_Implementation_Erratum_v1.0` remains
**suspended**; the quarantined `AMENDED PASS` remains **non-reusable**; preflight **closed**;
performance **not computed**; validation and sealed OOS **sealed and unread**.

---

## The judgment requested of the owner

Not whether the quarantined cascade passed. It is whether **this finalized implementation** faithfully
realizes the countersigned design — the §7 decision table exactly, the frozen numerics imported not
re-derived, every branch exercised (including the fallback-not-invoked guarantee), the runtime pinned,
the quarantine mechanically severed — and whether execution of the clean rerun should be authorized by
a separate execution countersignature.

*— Package ends. Awaiting the execution countersignature. No Stage-3 instance may run until it is given.*
