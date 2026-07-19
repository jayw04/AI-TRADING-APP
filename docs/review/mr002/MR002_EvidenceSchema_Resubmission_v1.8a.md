# MR-002 Delta v1.8a — Accepted-Block Closed Schema (narrow correction) — SUBMISSION FOR REVIEW

- **Date:** 2026-07-19 (laptop-side; no host restart — none was needed, per the verdict)
- **Scope:** EXACTLY the v1.8 review's blocking finding: the accepted block is now a
  closed schema. `stage3_cascade.py` is byte-UNCHANGED from the reviewed v1.8
  submission (sha still `1021cc287051a61a088c4a715604922f03ee4dfcff41a334681dab12cb3265ef`).
  Changes are confined to the runner's schema gate + tests.

## The correction (`mr002_stage3_population_runner.py`)

`_evidence_schema_defect` now additionally validates the accepted block, by
disposition:

- **Qualified records:** `_ACCEPTED_BLOCK_KEYS` is FROZEN to the registered producer
  contract — exactly `{solver, z_exact_hex, lam_exact_hex, z_sha256, lam_sha256,
  certificate}` (the six keys `numerical_evidence` emits; verified against the
  producer and asserted by test). Rules: a non-dict accepted →
  `EVIDENCE_ACCEPTED_NOT_A_DICT`; any unknown key beside the registered six (e.g. an
  `alternate_exact_hex`) OR any missing registered key →
  `EVIDENCE_ACCEPTED_KEYS_INVALID` (deterministic — never a generic
  `EVIDENCE_MALFORMED:*` exception); `z_exact_hex` / `lam_exact_hex` must be lists →
  `EVIDENCE_ACCEPTED_{Z,LAM}_EXACT_HEX_NOT_A_LIST`. A MISSING/empty block on a
  qualified record keeps its registered defect (`QUALIFIED_WITHOUT_ACCEPTED_BLOCK`,
  raised by the replay proper — existing disposition rule untouched).
- **Non-qualified records:** existing disposition rules retained exactly — a stop
  record is never required to carry the block, and the qualified-only closure is not
  applied to it (per the verdict). The record-wide recursive `*_exact_ratio` scan
  still applies to every record.
- **Certificate dict:** deliberately NOT narrowed — it keeps its own registered
  contract (`REQUIRED_CERT_FIELDS` presence + value replay in
  `_replay_certificate_defect`), as the verdict instructed.

**Record-level closure (explicit documentation, as requested):** the top-level
record is NOT closed to a fixed key set in v1.8a. Its non-encoding keys mirror the
registered `Outcome.summary()` contract (disposition/enums/flags) plus
`row_id`/`index`/`class`/hashes; they carry no schema-2 numerical encodings, are
covered by `record_sha256`, and are swept by the recursive ratio scan. Every
structure that DOES carry schema-2 encodings — the six input entries and the
accepted block — is now a closed set. If full top-level closure is wanted, it needs
the summary contract separately enumerated and tested; ruling is yours.

## File identities

| File | SHA-256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_population_runner.py` | `297901d7097008416e545c9b6f6f71b7a49ca255ebef6c6b282ab3f6eb624384` | 85,064 |
| `apps/backend/tests/research/test_mr002_stage3_population_runner.py` | `ba1951254b9164c6968186afd91ec1c2e8e58832a3e13c75c5467dcd10bbc376` | 78,375 |
| `apps/backend/app/research/mr002/stage3_cascade.py` | `1021cc287051a61a088c4a715604922f03ee4dfcff41a334681dab12cb3265ef` (unchanged) | 45,030 |
| `MR002_EvidenceSchema_Delta_v1.8a.patch` (cumulative git diff vs `5878c35`, supersedes the v1.8 patch) | `af6aef5a4d9b66cfd846366bfb079b154c896441dbaad8a9c788dc3ca63509ab` | 40,020 |

## Test evidence

| Log | Result | SHA-256 |
|---|---|---|
| `MR002_v18a_DevSuite_PopulationRunner.log` | **134 passed** (121 v1.8 + 13 new v1.8a cases; nothing removed or weakened) | `f8fa988f23466e1c4cc65f53325047a44b71a9f685657da5abd652562cef6a43` |
| Launcher tools (re-run, unchanged) | 98 passed, 1 host-only skip | (identical baseline) |
| `MR002_v18a_Ruff.log` | All checks passed — byte-identical content to the v1.8 ruff log, hence the same hash `82b3e6a6…` | `82b3e6a6c090a57601d22943bd23fca9218d1031dbe5a7b754092f9a156b4f18` |

Required-test mapping: unknown field beside `z_exact_hex`
(`test_v18a_unknown_field_beside_z_exact_hex_refuses` — the verdict's own
`alternate_exact_hex` example); beside `lam_exact_hex` (`…beside_lam…`); missing
`z_exact_hex` / `lam_exact_hex` / `z_sha256` / `lam_sha256` each refuse
deterministically (`test_v18a_missing_registered_accepted_key_refuses_deterministically`,
4 params, asserts NOT `EVIDENCE_MALFORMED:*`); non-dict accepted
(`test_v18a_non_dict_accepted_refuses`); non-list encodings (2 tests); the exact
registered key set passes (`test_v18a_exact_registered_accepted_key_set_passes` —
asserts producer output == frozen set); stop/non-qualified rules retained
(`test_v18a_stop_record_accepted_rules_unchanged` — one finding during authoring:
the aggregate surfaces `TERMINAL_NOT_COMPLETE` for a stopped run because the
terminal check precedes the class check in registered order; the test pins that
order); nested legacy `lam_exact_ratio` still refuses
(`test_v18a_nested_legacy_lam_exact_ratio_still_refuses`; the z case was already
covered in v1.8); aggregate STOP detail surfaces the new category + count
(`test_v18a_aggregate_detail_surfaces_accepted_schema_defect` →
`EVIDENCE_REPLAY_FAILED:EVIDENCE_ACCEPTED_KEYS_INVALID:first_row_id=0:failed_records=1`).

## Standing items (unchanged from v1.8)

Run-4 archived-record check: your ruling (authorized + required at host
qualification, read-only, corpus-source reconstruction, ≥1 failing + ≥1 clean
record + preferably every negative-zero placement pattern, NO checkpoint
conversion) is recorded and will be executed at the restart phase. mpmath: to be
resolved at host phase per your ruling (registered dependency set, full four
suites, version + fingerprint recorded, zero collection errors).

## Requested owner actions

1. Review + accept v1.8a (this doc + cumulative patch `af6aef5a…`).
2. On acceptance: commit authorization for the three code files + review artifacts
   (v1.8 + v1.8a docs/patches/logs; logs need `git add -f`).
3. Optional ruling: full top-level record closure (see the explicit documentation
   above) — in v1.8a scope only if you order it.
