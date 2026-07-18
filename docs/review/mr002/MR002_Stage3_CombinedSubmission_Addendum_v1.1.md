# MR-002 Stage-3 — Combined Submission Addendum v1.1 (2026-07-18)

Responds to the combined-review disposition: masking-test correction, deterministic 1-ulp
regression, rerun evidence with explicit summaries/exit codes, and the lint log. **The
production code is untouched** — the delta remains exactly the reviewed `upper / s` expression
(patch `fa2fc883…`, fixed file `919f496c…`, blob `a6e2199`). Nothing is committed.

## 1. Masking-test correction (the only test-file change)

`test_masking_case_upper_equals_t_bounds_coincide_and_stay_qualified` →
**`test_masking_case_upper_equals_t_mathematically_equivalent_and_stays_qualified`**

- The corpus-general bitwise claim (`assert np.array_equal(upper / s, s)`) is REMOVED. The
  docstring now states the audit result explicitly: bitwise coincidence on only 156 of 3,895
  rows, 1-ulp difference on 3,739.
- Equivalence is asserted through reconstructed original-coordinate bounds at an explicit
  ulp-scale tolerance, per the review's prescription:
  `|s*s − upper| ≤ np.spacing(upper)` and `|s*(upper/s) − upper| ≤ np.spacing(upper)`,
  elementwise (spacing = 1 ulp of `upper` per coordinate).
- Solver + certifier behavior on the `upper == t` case remains asserted qualified, unchanged.

## 2. New deterministic 1-ulp regression (no RNG, pure numpy — runs everywhere)

**`test_masking_one_ulp_bitwise_nuance_fixed_example`** with fixed values
`t = upper = [0.001, 0.01, 0.021]`, chosen because `fl(t/√t) != fl(√t)` for each:

- asserts the corrected bound is bitwise DIFFERENT from `√t`;
- asserts the difference is at most `np.spacing(√t)` (1 ulp) per coordinate;
- asserts both forms map back to the same mathematical bound in original coordinates within
  1 ulp of `upper`.

## 3. Updated identities

| Item | Value |
|---|---|
| Test file (9 tests now) | blob `a3dfd15`, sha256 `0e2670e01a7a1c21c1240b5f8f329ff57a433218227f058e178ab4773f5913fe` |
| Production file (UNCHANGED from review) | blob `a6e2199`, sha256 `919f496c…` |

## 4. Rerun evidence — with exact command, summary line, and exit code in every log

| Log (this folder) | Result | sha256 |
|---|---|---|
| `MR002_SQRTFix_FocusedTests_v1.1.log` | collected 9 → **9 passed**, exit_code: 0 | `497f7cbe…` |
| `MR002_SQRTFix_PinnedSuite_v1.1.log` | **182 passed, 0 failed, 0 skipped**, exit_code: 0 | `46860f0f…` |
| `MR002_SQRTFix_DevSuite_v1.1.log` | 175 passed, 7 skipped, exit_code: 0 | `c2fb2b99…` |
| `MR002_SQRTFix_Ruff_v1.1.log` | exact command, both changed paths, “All checks passed!”, exit_code: 0 | `3df9191e…` |

Each log opens with the exact invocation and an environment line. As the review noted, the
pinned-stack runs are development evidence on the pinned-package Windows venv — **not** Linux
image qualification; the next qualification report will carry the image identity, final
collected count, per-outcome summary, exit code, and the production-binding record, per the
stated requirements.

## 5. Acknowledged dispositions

Hash gate ACCEPTED · MASKED_BY_IDENTITY ACCEPTED · trajectory conclusion ACCEPTED WITH 1-ULP
CAVEAT (now pinned by a deterministic regression) · wrapper correction ACCEPTED · scope
containment ACCEPTED · **implementation commit NOT YET AUTHORIZED — nothing committed** ·
Stage-3 numerical execution NOT AUTHORIZED · validation/OOS sealed and unread.
