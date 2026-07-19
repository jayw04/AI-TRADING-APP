# MR-002 Stage-3 — v5 Pre-Attestation Qualification Submission v1.0 (HOLD POINT)

- **Date:** 2026-07-19. STOPPED before any v5 attestation or nonce, per the verdict. No launch
  artifact exists. Everything below is regenerated at, and cross-validated against, the frozen
  schema-2 implementation `ecaa262…`.

## 1. Archive-return-package commit (prerequisite step, completed first)

Commit `ed9ea5103dbac36f16128c847623a524d0cb1613` / tree `199ddd10…` / parent `ea77d49…`
(pushed). Committed blobs (staged-blob-verified byte-exact): return package `104eeaf9…` 5,256 B;
report `3a399021…` 2,854 B; **stderr `e3b0c442…` 0 B (a real zero-byte artifact)**; publication
record `1a0eb4f9…` 794 B; wrapper console `9ba76af0…` 441 B.

## 2. Regenerated qualification artifacts (all NEW, all cross-validated)

| Artifact | SHA-256 | Produced by |
|---|---|---|
| Implementation fingerprints (in `MR002_Stage3_EnvObservation_ecaa262.json`, `e6b196a1…`) | canonical_qualify `7a0ca6d2…`, certify `3fc60697…`, piqp_solve `ac68d715…`, primary_wrapper `b2b5c41e…`, resolve `c2cba44a…` | `gather_env("/work")` IN-IMAGE at `/work=ecaa262` |
| Expected pins v2.0 (DRAFT for countersign) | `59a23fc092b5e0ccdf4dfedc2873f584f722aaa71f62a3d3c19990da916a6e13` (1,530 B) | authored from the in-image observation; git ecaa262/1cb95e25; corpus/image/material/packages unchanged |
| Source manifest v2.0 | `9798302a868724ac92fab57274100bef928bb0ccdf29f393dcaf65850bbf76f8` | frozen `mr002_stage3_source_manifest.py --out` IN-IMAGE at ecaa262; zero files missing |
| Execution package v2.0 | `846c6418c3b23b36c61da260fcf0953b5245a0967df8187355887d51d5c9ea24` (5,313 B) | authored; binds schema 2.0, fingerprints, pins v2.0, manifest v2.0, corpus identity, image/config digest, dependency provenance incl. the non-PyPI pandas-ta transplant, and the archive-qualification PASS |
| Final in-image test report v2.0 | `e51a49202076c2e8005e90ffc9a087f0f3b5a9c33d0a926a95f3cd8550a0b093` | frozen `mr002_stage3_final_test_report.py` IN-IMAGE — **236 passed / 0 skipped / exit 0 / `admissible_as_final: true`**, bound ecaa262+1cb95e25 clean, binds pins/pkg/manifest v2.0 hashes |
| Realism harness (rerun) | `490e168af94d443e2985025f4887e3c1939d3ab9f0068521e98d8b1d401512dd` | frozen `mr002_stage3_cascade_fixtures.py` IN-IMAGE — **verdict PASS, 9/9 cases, full preflight gate PASSED against pins v2.0 + manifest v2.0** |

**Fingerprint finding (honest observation):** the regenerated fingerprints are IDENTICAL to the
prior pins — the fingerprinted set is the solver/certifier closure (`REQUIRED_FINGERPRINT_KEYS`),
which delta v1.8/v1.8a deliberately did not modify. The pins still change materially:
`git_commit`/`git_tree` now bind `ecaa262…`/`1cb95e25…`.

**Test-count note:** 182 → **236** (the registered five-file selection is unchanged; the
population-runner file grew by the accepted v1.8/v1.8a battery). Selection (from the v1.0
report's collected ids, byte-for-byte the same five files): sqrt_upper_transform,
stage3_cascade_dispA, stage3_input_contract, stage3_population_runner, stage3_preflight —
run with `--noconftest -p no:cacheprovider`.

**Loader-version constraint (disclosed):** the FROZEN runner at ecaa262 pins
`SUPPORTED_EXECUTION_PACKAGE_VERSION = "1.9"` and `PINS_VERSION = "1.0"`; the regenerated records
therefore keep those record versions (`version: "1.9"`, `revision: "2.0"` on the package) —
changing the constants would need a new code delta.

## 3. Generator / verifier commands (all `docker run --rm --network=none`, `/work`=numrepo ro, image `81e8d7a7…`)

1. Env observation: `python /regen/observe_env.py` (gather_env + JSON dump; identity env channels set).
2. Source manifest: `python scripts/mr002_stage3_source_manifest.py --out /regen/MR002_Stage3_SourceManifest_v2.0.json`.
3. Realism: `python scripts/mr002_stage3_cascade_fixtures.py` with `MR002_EXPECTED_PINS(+_SHA256)` + `MR002_SOURCE_MANIFEST(+_SHA256)` env channels, `/out` → fresh dir.
4. Final report: `python scripts/mr002_stage3_final_test_report.py --out … -- --noconftest -p no:cacheprovider <the 5 registered files>` with manifest/pins/package env channels.
5. Loader cross-validation: a driver invoking every frozen loader (below).

## 4. Loader / cross-validation outcomes (in-image, one run)

`load_expected_pins` ACCEPTED · `load_static_manifest` ACCEPTED · `verify_source` → **zero
defects** · `verify_execution_package` ACCEPTED (version 1.9, revision 2.0) ·
**`evaluate(gather_env, pins_v2, verify_source)` → `passed: true, failed: []` (the FULL 17-check
preflight)** · `load_final_test_report` ACCEPTED · `load_realism_pass` ACCEPTED. The realism
harness independently ran the same full preflight gate before its 9 numerical cases — twice-proven.

## 5. Identities and rechecks

- Image / OCI config: `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea`
  (unchanged — regeneration proved no new image is required; code stays supplied via `/work`).
- /work: detached `ecaa262…`, porcelain 0, read-only, DB intact — rechecked after regeneration.
- Host: instance `i-0f3ceafdd4294c572`, vol `vol-0ce8c0056244d14f5`, `docker ps -a` **0**.
- **/out: EMPTY** (still no `cleanrun`; created only when the run-5 chain is authorized).
- Archive: checkpoint `b9b0a948…` + manifest `1132d3b8…` re-verified unchanged.
- Validation/OOS: **SEALED AND UNREAD** (realism uses tiny hand-built problems; the report suite
  and manifest generator read only the checkout; nothing touched validation/OOS data).
- Dependency/provenance record: execution package §dependency_provenance (in-image pinned set +
  host qualenv pip-report hashes `dcd5892d…`/`bda05912…` + pandas-ta transplant archive
  `e402c0f1…` with the NOT-reproducible-solely-from-PyPI ruling).

## 6. Files in this submission (uncommitted, for review)

`MR002_Stage3_ExpectedPins_DRAFT_v2.0.json` (`59a23fc0…`) ·
`MR002_Stage3_SourceManifest_v2.0.json` (`9798302a…`) ·
`MR002_Stage3_ExecutionPackage_v2.0.json` (`846c6418…`) ·
`MR002_Stage3_FinalTestReport_v2.0.json` (`e51a4920…`) ·
`MR002_Stage3_CascadeRealismHarness_v2.0.json` (`490e168a…`) ·
`MR002_Stage3_EnvObservation_ecaa262.json` (`e6b196a1…`) · this submission.
Box-side originals live under `~/mr002/regen/` (hash-identical; pulled copies verified).

## Requested owner actions (v5 pre-attestation review)

1. Review the regenerated artifacts; countersign the pins v2.0 (as with the v1 pins-countersign)
   and rule on the execution package v2.0.
2. Rule on the loader-version constraint disclosure (record versions frozen by the ecaa262 code).
3. On acceptance: commit authorization for the regenerated artifacts + this submission, then the
   v5 attestation/receipt/binding/countersign chain (currently HELD) and staging of
   `/inputs` + one empty `/out/cleanrun` for Run 5.
