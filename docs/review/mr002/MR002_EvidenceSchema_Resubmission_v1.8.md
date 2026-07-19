# MR-002 Delta v1.8 — Evidence Schema 2.0 (exact hex) — SUBMISSION FOR REVIEW

- **Date:** 2026-07-19 (laptop-side, per the run-4 closeout verdict: "Delta v1.8
  laptop implementation AUTHORIZED; host-side qualification DEFERRED UNTIL RESTART")
- **Scope:** the registered numerical evidence schema + replay logic ONLY. The
  launcher (`b6e5d27`) is untouched. Nothing is committed; nothing ran on the launch
  host (still stopped, as ordered).

## What changed (3 files)

| File | SHA-256 (working tree, LF) | Bytes |
|---|---|---|
| `apps/backend/app/research/mr002/stage3_cascade.py` | `1021cc287051a61a088c4a715604922f03ee4dfcff41a334681dab12cb3265ef` | 45,030 |
| `apps/backend/scripts/mr002_stage3_population_runner.py` | `edf2a7f1d27b78e173a7e663547cd974f42df7ce07ee735e733c701fea85ea21` | 83,447 |
| `apps/backend/tests/research/test_mr002_stage3_population_runner.py` | `139663b89c94c9f37dd30fde7f59ffd891f3e11e48325164f600672f6e39e62c` | 73,367 |

Patch: `MR002_EvidenceSchema_Delta_v1.8.patch` — sha256
`72c221604905ac236b89e1b6dbde40a50e4dae6f876d1f064987dbd1fe0569be`, 33,273 B
(git diff vs the committed tree at `5878c35`, whose numerical files equal the
registered `d26bd9e` content).

### 1. Versioned lossless encoding (producer — `stage3_cascade.py`)

- `EVIDENCE_SCHEMA_VERSION = "2.0"` — explicit and closed; every record now carries
  `evidence_schema_version: "2.0"` (covered by `record_sha256`).
- `_exact_ratio_list` is REPLACED by `_exact_hex_list`: encoder `float.hex()`,
  finite binary64 only; NaN/±inf raise `Stage3IntegrityError("EVIDENCE_NON_FINITE_VALUE")`
  at publication (fail-closed: inside the row loop this becomes a governed
  `RESOLVER_ERROR` stop, never a durable record).
- Field names: `input.<component>.exact_hex`, `z_exact_hex`, `lam_exact_hex`. Hex is
  NEVER stored under a ratio-named field; no field named `exact_ratio` is produced.
- `rec_content_hash` is UNCHANGED — the content hash remains the raw registered
  float64-byte hash (shape + bytes), as required.

### 2. Closed-schema replay (consumer — `mr002_stage3_population_runner.py`)

`verify_numerical_evidence_record` now, in order:
1. `_evidence_schema_defect`: version missing → `EVIDENCE_SCHEMA_VERSION_MISSING`;
   version ≠ "2.0" → `EVIDENCE_SCHEMA_VERSION_UNKNOWN`; any `exact_ratio` /
   `*_exact_ratio` field anywhere in the record tree → `EVIDENCE_MIXED_SCHEMA_FIELDS`;
   input keys must be exactly the 6 components and each entry exactly
   `{shape, exact_hex}` → unknown fields refuse.
2. `_decode_exact_hex`: decoder `float.fromhex`; non-string → refuse; malformed →
   `EVIDENCE_MALFORMED_HEX`; non-finite reconstruction (fromhex accepts "inf"/"nan"
   spellings) → `EVIDENCE_NON_FINITE_VALUE`; result dtype float64.
3. The rebuilt arrays are **byte-verified against the recorded content hash BEFORE
   any semantic use** (`INPUT_EXACT_HEX_DOES_NOT_MATCH_CONTENT_HASH` on mismatch);
   shape is reproduced from the recorded shape and covered by the hash, so any
   shape/ordering/dtype drift fails the hash check. z/lam hash conditions renamed
   `Z_EXACT_HEX_DOES_NOT_MATCH_HASH` / `LAM_EXACT_HEX_DOES_NOT_MATCH_HASH`.
   All downstream checks (model-input validation, certificate replay, disposition
   replay, length checks) are unchanged.

### 3. Deterministic STOP detail

- New `aggregate_verdict_defect(state, row_manifest) -> str | None` — same conditions
  as the boolean gate (which is now a façade over it), but a failure returns e.g.
  `EVIDENCE_REPLAY_FAILED:INPUT_EXACT_HEX_DOES_NOT_MATCH_CONTENT_HASH:first_row_id=1:failed_records=2`
  — first failure chosen deterministically by registered row order, total count
  included, category included, no giant lists (per-row detail stays in the durable
  evidence). Structural failures name their condition
  (`…:CHECKPOINT_CORRUPTION`, `…:TERMINAL_NOT_COMPLETE`, etc.).
- `run_population` now sets `stop_reason` to that defect whenever `passed=false`
  because of replay failure → the manifest `stop_reason` and the printed
  `detail` are NONEMPTY (run 4's `{"disposition":"STOP","detail":""}` is impossible).

### 4. Closure inventory

`MR002_EvidenceEncoding_ClosureInventory_v1.0.md` — the full sweep for
`_exact_ratio_list` / `as_integer_ratio` / `exact_ratio` / `n / d` replay across
`app`, `scripts`, `tests`: exactly 4 producer + 3 consumer sites, all replaced;
every remaining `as_integer_ratio` use is exact-`Fraction` arithmetic with no
byte-identity claim (justifications per site in the inventory).

## Test evidence (dev machine; host suite DEFERRED to requalification)

| Log | Result | SHA-256 |
|---|---|---|
| `MR002_v18_DevSuite_PopulationRunner.log` | **121 passed** (41 collected v1.8 cases incl. parametrizations; 0 skips) | `b82d5ca55e8826df78c0ad2a1a81169296520effe50a8d632df321cb28f376e0` |
| `MR002_v18_DevSuite_LauncherTools.log` | **98 passed, 1 skipped** (the known host-only real-CLI test — identical to the accepted v1.7 dev baseline) | `07019b60b9e24dab5f7b1e8695139c5222646796d66aecf570cb3a770b495700` |
| `MR002_v18_Ruff.log` | All checks passed (3 changed files) | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |

Required-test coverage (verdict list → test):
±0.0 bit-exact (`test_v18_negative_zero_roundtrips_bit_exact`, incl. the v1
counter-demonstration; `…positive_zero…`); ±subnormals / min-normal / max-finite /
representative values (`test_v18_finite_values_roundtrip_bit_exact`, 17 cases);
mixed ±0.0 input reproduces the content hash through the REAL run loop
(`test_v18_run4_replica_mixed_zero_input_passes` — the run-4 failing-record
REPLICA); clean analogue still passes (`test_v18_clean_record_remains_successful`);
z / lam with −0.0 (`test_v18_accepted_z…`, `test_v18_accepted_lam…`); NaN/±inf
refuse at publication (`test_v18_non_finite_refuses_at_publication`) and at decode
(`test_v18_non_finite_hex_refuses_at_decode`); malformed hex
(`test_v18_malformed_hex_refuses`, `…non_string_hex…`); missing / unknown / mixed
schema version (`test_v18_missing…`, `…unknown…`, `…mixed_v1_input…`,
`…mixed_v1_accepted…`); unknown evidence fields (`test_v18_unknown_input_entry_field_refuses`);
shape change with valid scalars (`test_v18_shape_change_refuses…`); ordering/dtype
fail the content hash (`test_v18_ordering_and_dtype_changes_fail_content_hash`);
one-bit mutation (`test_v18_one_bit_mutation_still_fails_replay`); record hashes +
structural checks remain enforced and PASS only when every replay succeeds
(`test_v18_aggregate_defect_reports_first_row_and_count`, `…none_when_all_replay`,
updated cycle-4/5 tamper tests); STOP-detail end-to-end through RunResult, run
manifest, and orchestration result (`test_v18_stop_detail_nonempty_end_to_end`);
deterministic uint64 bit-pattern property sweep, 5,012 patterns incl. corners, LCG
(no randomness — resume-safe), non-finite patterns assert encoder refusal
(`test_v18_property_uint64_bit_patterns_roundtrip`).

## Disclosures

1. **Run-4 record fixture is a REPLICA, not the archived bytes.** The archived
   checkpoint is immutable evidence on the STOPPED launch host, and restarting the
   instance for local work is forbidden by the closeout verdict. The replica
   reproduces the exact defect signature (mixed +0.0/−0.0 in `b_ub`, the component
   carrying the negative zeros in every sampled run-4 failing record) and fails
   under v1 semantics / passes under v2. **Proposed host-phase check (owner
   decision):** at requalification, replay an archived run-4 record's decoded
   numerical content re-encoded under schema 2.0 and confirm byte-identity to its
   recorded `input_content_hash`.
2. Four PRE-EXISTING collection errors in `tests/research/` (certificate /
   directed-rounding / correction-regression / exact-repair suites) — missing
   `mpmath` in the dev venv, unrelated to and untouched by this delta; those suites
   import a module this delta does not modify.
3. Dev machine is Windows; the registered environment is the pinned Linux image.
   Nothing here executes solvers (stub resolvers only), and `float.hex()`/`fromhex`
   are platform-independent binary64 text, but the registered 182-test in-image
   final report and the fingerprint pins must be REGENERATED at host qualification
   (changed callables ⇒ changed fingerprints ⇒ new pins / source manifest /
   execution package / report, per the verdict's consequence list).

## Requested owner actions

1. Review + accept (or amend) delta v1.8 (patch + inventory + this submission).
2. On acceptance: authorize commit of the three code files (+ these review artifacts;
   logs need `git add -f`).
3. Rule on the proposed host-phase archived-record replay check (disclosure 1).
4. Subsequent chain work (host requalification → new source manifest / pins /
   package / in-image report / realism as required → v5 attestation/receipt/binding/
   countersign → fresh `/out/cleanrun` → Run 5 from row zero) awaits your explicit
   order per the standing sequence.
