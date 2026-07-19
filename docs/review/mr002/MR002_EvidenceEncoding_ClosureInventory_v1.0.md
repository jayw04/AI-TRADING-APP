# MR-002 Evidence-Encoding Closure Inventory v1.0 (delta v1.8)

Required by the run-4 evidence-replay verdict: the complete registered import and
evidence-production closure searched for `_exact_ratio_list`, `as_integer_ratio`,
`exact_ratio`, `n / d` replay, and ratio reconstruction, with EVERY producer and
consumer identified. Search scope: `apps/backend/{app,scripts,tests}` (the registered
closure is `scripts/mr002_stage3_population_runner.py` + its `app.research.mr002.*`
imports; the wider sweep is included so nothing hides outside it). Line numbers are
pre-delta (registered commit `d26bd9e` content).

## A. Durable-evidence encoding — the defective sites (ALL CHANGED by v1.8)

**Producers** (`app/research/mr002/stage3_cascade.py`):

| Site | Was | Now |
|---|---|---|
| `_exact_ratio_list` (:620) | `float.as_integer_ratio()` pairs — destroys the `-0.0` sign bit | REPLACED by `_exact_hex_list` — `float.hex()`, finite-only, non-finite raises `Stage3IntegrityError("EVIDENCE_NON_FINITE_VALUE")` |
| `numerical_evidence` input fields (:649) | `input.<k>.exact_ratio` | `input.<k>.exact_hex` + record-level `evidence_schema_version: "2.0"` |
| `numerical_evidence` accepted z (:663) | `z_exact_ratio` | `z_exact_hex` |
| `numerical_evidence` accepted lam (:664) | `lam_exact_ratio` | `lam_exact_hex` |

No other call site of `_exact_ratio_list` exists anywhere in the tree — no nested or
auxiliary numerical array used the encoder.

**Consumers** (`scripts/mr002_stage3_population_runner.py`,
`verify_numerical_evidence_record`):

| Site | Was | Now |
|---|---|---|
| input replay (:528) | `n / d` reconstruction | `_decode_exact_hex` (`float.fromhex`, finite-only, closed schema) |
| z replay (:540) | `n / d` | `_decode_exact_hex` |
| lam replay (:541) | `n / d` | `_decode_exact_hex` |

There is no other `n / d`-style ratio reconstruction of durable evidence anywhere in
the closure.

**Test references** (`tests/research/test_mr002_stage3_population_runner.py`): the
schema-touching assertions at (pre-delta) :134, :546, :643–:645 are updated to
schema 2.0. Two NEW tests deliberately inject v1 `exact_ratio` fields to prove the
mixed-schema refusal — those are the only remaining `exact_ratio` occurrences in
tests, and they exist to assert the field is refused.

## B. `as_integer_ratio` uses that are NOT durable-evidence encoding (RETAINED, justified)

These convert floats to exact `Fraction`s for **exact rational arithmetic**, where
`-0.0 → 0` is the *identical rational number*; no byte-identity or hash claim covers
them, so the sign of zero is mathematically irrelevant there:

- `app/research/mr002/certificate.py` :118, :136 (`to_fraction` for outward-rounded
  interval arithmetic; docstrings :55, :114)
- `app/research/mr002/directed.py` :90, :134 (directed-rounding checks)
- `scripts/mr002_directed_rounding_correction.py` :86, :87, :289 (Fraction bounds)
- `scripts/mr002_row2307_lineage.py` :54, :189 (post-hoc diagnostic lineage; already
  records IEEE-754 hex alongside each rational)
- `scripts/mr002_coverage_signed_gap.py` :381, :473 and
  `scripts/mr002_complementary_coverage.py` :460 (report text / printout only)
- `app/research/mr002/repair.py` :570 (`eta_exact_rational` — the registered constant
  η rendered as a rational; a strictly positive value, no zero possible)
- `tests/research/test_mr002_certificate.py`, `tests/research/test_mr002_directed_rounding.py`
  (tests of the above Fraction arithmetic)

None of these produce or consume the checkpoint evidence schema. Changing them is
neither required nor performed by v1.8.

## C. Conclusion

The defective encoding had exactly **4 producer sites (1 encoder + 3 fields)** and
**3 consumer sites** — all replaced by the schema-2.0 hex encoding in delta v1.8.
The remaining `as_integer_ratio` population is exact-arithmetic-only and retained
with the justification above.
