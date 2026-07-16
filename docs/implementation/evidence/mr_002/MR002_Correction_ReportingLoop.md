# MR-002 — CORRECTION ARTIFACT: determinism / shuffle-invariance reporting defect

**Date:** 2026-07-13 · **Status:** immutable correction · **Owner ruling §15**

This corrects a **reporting** defect. It does not correct, alter or reinterpret any numerical
result, and the affected artifact is **not modified**.

## Affected artifact

| | |
|---|---|
| artifact | `runtime/MR002_ComplementaryCoverage_Certified.json` |
| sha256 | `47215cd2aa65124ba0ffe4d2e41ae2539030a449fddd614b28e7f2078d00fda6` |
| defective fields | `same_image_determinism` (reported `false`), `shuffle_invariance.pass` (reported `false`) |
| producing script | `apps/backend/scripts/mr002_complementary_coverage.py` |

## The defective loop condition

Both checks iterate over the **primary's nonqualifying instances** and re-solve them with the
**fallback**, then mark the check failed unless the fallback both **qualifies** and reproduces
itself:

```python
a_ok, _, za, _, _ = try_solve(FALLBACK, rec)
b_ok, _, zb, _, _ = try_solve(FALLBACK, rec)
if not (a_ok and b_ok and np.array_equal(za, zb)):
    det_ok = False                      # <-- fires when the fallback merely NONQUALIFIES
```

`a_ok` is a **qualification** verdict, not a **repeatability** verdict. Conflating them means that
any instance where the fallback legitimately fails to qualify is counted as a determinism failure —
even though the fallback returned *the same answer both times*, which is all determinism asserts.

## Why it fired here and not before

Under the superseded nonnegative-gap gate the primary had **2,054** nonqualifications instead of
**5**. The loop therefore re-solved 2,054 instances with a fallback that itself nonqualifies on 61
of them. The conflation was always present; the change in gate merely made it certain to trigger.

**This is not a numerical finding, and it was not reported as one.**

## Re-instrumented result

`apps/backend/scripts/mr002_certified_gap_diagnosis.py` separates the two verdicts: instances where
the fallback nonqualifies are **skipped** (they say nothing about repeatability) rather than
counted as failures.

| check | population | result |
|---|---|---|
| same-image determinism | 2,019 qualifying instances, each solved twice | **0 differed** |
| canonical shuffle invariance | 2,015 qualifying instances, variables and rows permuted | **0** exceeded 1e-8 (worst \|Δ\| 6.39e-10) |

Both **PASS**.

## Hashes

| | sha256 |
|---|---|
| corrected script `mr002_certified_gap_diagnosis.py` | `4f663bd27bbdc7c92e23fabdc79d76164b0b4ab08fb6c368531a2391de9a90ff` |
| diagnosis artifact `MR002_CertifiedGap_Diagnosis.json` | `4186951192e96521837cc6887ffb096820788a172bb609568f7c5b0c1bec7a0b` |

## Disposition

The original coverage artifact is **retained unaltered**, defective fields included. Its recorded
disposition stands:

```
CERTIFICATE MODULE INTEGRITY PASSED
NONNEGATIVE SIGNED-GAP RULE INVALIDATED
CASCADE UNRESOLVED = 35 UNDER SUPERSEDED GATE
DETERMINISM/SHUFFLE FIELDS IN COVERAGE ARTIFACT DEFECTIVE
CORRECTED RE-INSTRUMENTATION: PASS
NOT COUNTERSIGNED
```

The successor coverage run corrects the loop at source: qualification and repeatability are
evaluated as separate predicates, and the count of skipped (nonqualifying) instances is reported
alongside the checked population, so a silently-empty check cannot pass by vacuity.
