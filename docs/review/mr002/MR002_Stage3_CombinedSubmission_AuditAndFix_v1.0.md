# MR-002 Stage-3 — Combined Submission: Corpus Audit + SQRT-Wrapper Fix (v1.0, 2026-07-18)

Submitted under the 2026-07-18 amended Authorization A (frozen-device corpus reconstruction) and
the parallel fix-lane authorization. Both lanes ran operationally separated (frozen worktree vs
main tree). **Nothing is committed or pushed** — this package awaits the combined review.

## Headline results

1. **Phase A1 hash gate: PASS.** The registered corpus was reconstructed with the frozen
   defective capture device inside the pinned Linux image: **3,895 instances, aggregate hash
   `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` — exact match.**
2. **Every registered instance is MASKED_BY_IDENTITY.** All 3,895 rows have `upper == t` on
   every coordinate in exact float64; `upper/t` is identically 1.0 across the corpus
   (min = max = every quantile = 1.0). Zero rows MISMATCH_PRESENT; zero rows with any
   `upper < t` or `upper > t` coordinate.
3. Under the sufficient structural masking condition the ruling defined, the evidence supports:
   **the historical SQRT formulation was mathematically the intended model on every registered
   row, and the historical trajectory is clean with respect to this defect.** (The realism
   fixture that exposed the defect used `upper < t` — geometry that exists nowhere in the
   registered corpus.)
4. **Bitwise nuance the review must see:** the frozen bound `√t` and the corrected bound
   `upper/√t` coincide bitwise on only **156** rows; on **3,739** rows at least one coordinate
   differs by exactly **1 ulp** (max abs discrepancy 2.7755575615628914e-17; max rel
   2.2203836828715635e-16), because `fl(t/√t)` does not always round to `fl(√t)`. The two
   formulations are mathematically identical on the corpus but not bit-identical; under the
   fixed wrapper, corpus-row primary solves may differ in the last ulp from historical
   characterization results. Historical-result reuse is already prohibited; forward behavior is
   gated per-row by the unchanged certifier.
5. **Fix lane:** the one-expression production fix + 8 focused tests all pass; **pinned-stack
   suite 181 passed / 0 failed / 0 skipped**; only the `primary_wrapper` fingerprint changed.

## 1–4. Audit artifact, sidecar, command + environment record, hash-gate proof

| Item | File (review copy in this folder) | sha256 |
|---|---|---|
| Immutable audit artifact (per-row records ×3,895 + aggregate + statements) | `MR002_CorpusStructuralAudit_v1.0.json` | `519375fb1aeca8eb92515585cb02d83f525971959f243d01ecada19166a85dc6` |
| External audit hash sidecar | `MR002_CorpusAudit_Sidecar_v1.0.json` | `f36069186bd413bdb673fb239c8f3c145957d6e027aa8031f8e55ba134ecbe84` |
| Reconstruction manifest (ordered 3,895 instance hashes + environment) | `MR002_CorpusReconstruction_Manifest_v1.0.json` | in sidecar |
| Audit driver (external, read-only mounted; replicates frozen `main()` Phase-1 statements) | `mr002_corpus_audit_driver.py` | `38d488feadd000e6d2a972e9e514dcfbb9497cbe4a2b5ddd5366f8293706254d` |
| In-image run log (env record + gate output) | `audit_run_inimage.log` | in sidecar |

Reconstruction environment: image `mr002-research:v1.4` (Id `sha256:aa930021c072…` — the
registered known-good base), `--network=none`, `OPENBLAS_CORETYPE=HASWELL`, all thread envs =1;
frozen worktree of `3a37545` mounted read-only with **all 935 backend Python files verified
byte-identical to the committed blobs** (a fresh Windows checkout smudges CRLF; files were
rewritten from blobs and re-verified — the eight named device files match their committed
sha256 exactly, including `mr002_solver_intersection.py` = `ee1aacf3…`). Dataset
`mr002_research.duckdb` sha256 `24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a`,
mounted read-only. Solvers were invoked **only** inside the frozen capture device to advance the
trajectory; no outcome was adjudicated or recorded; no solver comparison; no validation/OOS.

**Disclosed failed first attempt (preserved):** an initial reconstruction on Windows
(byte-identical source, identical dataset, same pinned package versions) produced the correct
count (3,895) and an identical row 0 but a different aggregate hash — 3,690 rows diverged
beginning at row 1 (Windows scipy-openblas vs the image's manylinux OpenBLAS; path-dependent
trajectory). Preserved as `MR002_CorpusReconstruction_FailedWindowsAttempt_Manifest.json`
(sha256 `996025e637c0d206ffbff1e9a61f7fb6d731e8117079656ce8b869888fe586b9`), diagnosis confined
to instance-hash comparison. No statistics were computed from that reconstruction. This
independently demonstrates the trajectory's environment-sensitivity and why execution is
image-pinned.

## 5. Full structural statistics

In the artifact (`aggregate` + 3,895 `rows`): per-row `upper<t / ==t / >t` coordinate counts,
transformed-bound mismatch coordinate counts, max abs/rel bound discrepancy, per-row
classification, and the aggregate table (all 3,895 MASKED_BY_IDENTITY; `upper/t` quantiles all
1.0; 156 rows bitwise-zero discrepancy).

## 6. Trajectory-effect limitation (stated verbatim in the artifact)

“A mismatched transformed bound proves the historical SQRT formulation differed from the
intended model. Structural input audit alone cannot establish whether that difference altered a
solver-selected point or the path-dependent downstream trajectory.” — With zero mismatched rows,
this limitation is not exercised: every row satisfies the exact-identity masking condition, and
no TRAJECTORY_EFFECT_UNDETERMINED labels were assigned.

## 7–11. The exact fix delta, tests, and outputs

- **Patch:** `MR002_SQRTWrapperFix_20260718.patch` (sha256 `fa2fc883c673779e157418c33d55d2e2b212aa311ba0772fd95818f327e0f974`).
  One expression at the production SQRT site: `jp._qp_matrices(A_ub @ S, b_ub, A_eq @ S, b_eq,
  upper / s, n)` replaces `…, s, n)` plus a two-line constraint comment. File blob
  `409b6c8` → `a6e2199` (`apps/backend/scripts/mr002_coverage_signed_gap.py`, post-fix sha256
  `919f496c…`; review copy in this folder).
- **New test file:** `apps/backend/tests/research/test_mr002_sqrt_upper_transform.py`
  (blob `2354e16`, sha256 `8b8cc4d1…`; review copy in this folder) — 8 tests covering the seven
  required groups:
  1-D active upper bound (z = 0.01, active, qualifies); masking case `upper == t` (bitwise
  bound coincidence asserted + still qualified); inactive bound `upper > t` (z ≈ t);
  heterogeneous bounds with `<, ==, >` coordinates (recorded `_qp_matrices` call proves the
  transformed bound elementwise-bitwise equals `upper/√t`; all bounds respected); transformation
  identity `0≤z≤upper ⇔ 0≤v≤upper/√t` (exact-dyadic + margin vectors, no RNG); dual
  reconstruction (μ_upper = 1.0 recovered analytically → `/= s` unscaling undisturbed); realism
  regression (unchanged fixture input, rec hash re-asserted `4bbaa6d1…`, now
  **PRIMARY_QUALIFIED**, `accepted_by = QUADPROG_SQRT`, no fallback).
- **Focused-test output:** 8/8 passed in the pinned stack (1.59 s).
- **Full development suite:** pinned stack **181 passed, 0 failed, 0 skipped, exit 0**
  (`MR002_SQRTFix_PinnedSuite_181pass.log`, sha256 `76a7adb4…`) — includes the production-binding
  test. Dev venv (no piqp/mpmath): 174 passed + 7 skipped, exit 0 (`MR002_SQRTFix_DevSuite.log`,
  sha256 `a8e052da…`) — skips are the solver-stack-gated tests, the established pattern.
- **Lint:** `ruff check` clean on both changed files.

## 12. Executable-delta and fingerprint-delta table

| File | Before | After |
|---|---|---|
| `apps/backend/scripts/mr002_coverage_signed_gap.py` | blob `409b6c8` | blob `a6e2199` (one expression + comment) |
| `apps/backend/tests/research/test_mr002_sqrt_upper_transform.py` | — (new) | blob `2354e16` |

| Fingerprint | Before | After | Status |
|---|---|---|---|
| `primary_wrapper` | `5212a77e5f879705…` | `b2b5c41e19b66a32…` | **CHANGED (anticipated)** |
| `piqp_solve` | `ac68d71505360448…` | same | unchanged |
| `canonical_qualify` | `7a0ca6d28353dd3a…` | same | unchanged |
| `certify` | `3fc606978c420162…` | same | unchanged |
| `resolve` | `c2cba44acf8fce65…` | same | unchanged |

## 13. The three disclosed analogous sites — byte-unchanged

`git diff HEAD` reports **zero modification** to `mr002_solver_intersection.py`,
`mr002_piqp.py`, and `mr002_characterize_native_qp.py`. The T-scaled occurrences
(`coverage_signed_gap.py` T-path passing `ones(n)`; `solver_intersection.py::solve_sqrt`
passing `s`; `solver_intersection.py::solve_tscaled` passing `ones(n)`) remain **known analogous
defects outside the registered Stage-3 production path — deferred, not waived**, per the ruling.

## Awaiting

Combined review of this package. On approval, per the standing sequence: new implementation
commit → Linux Phase-A regen → new pinned image (fingerprint pins v1.2 with the new
`primary_wrapper`) → verify_source zero defects → in-image suite zero skips → realism harness →
persisted realism PASS before any Phase B. Registered Stage-3 successor execution remains NOT
authorized; validation/OOS sealed and unread.
