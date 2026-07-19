# MR-002 Stage-3 — Exhaustive Environment-Read Inventory of the Registered Import Closure (v1.0)

- **Date:** 2026-07-19
- **Required by:** preflight-refusal review verdict (recorded static inventory across the
  entire registered import path before the next launcher delta is accepted).
- **Method:** `git grep -n "os\.environ\|os\.getenv" d26bd9e…` over
  `apps/backend/scripts/mr002_*` and `apps/backend/app/research/mr002/` — the REGISTERED
  bytes at the numerical commit, not the working tree — followed by per-site
  classification against the registered import closure of
  `python scripts/mr002_stage3_population_runner.py`:
  entry → `mr002_stage3_preflight` (entry-imported), `mr002_stage3_source_manifest`,
  `app.research.mr002.stage3_cascade` (+ `certificate`, solver wrappers `mr002_piqp`,
  `mr002_solver_intersection`, `mr002_coverage_signed_gap` via preflight fingerprints and
  the cascade), and the corpus path (`mr002_development_run.run_config`,
  `app.research.mr002.{joint_portfolio,dataset,runner}`).
- **Enforced by test:** `test_env_read_inventory_regression_guard` re-scans these modules
  on every suite run and FAILS on any env read absent from the approved map
  (`APPROVED_ENV_READS` in the launcher test file). The map requires review + disposition
  + (if attested) a grammar change to extend.

## In-closure inventory (every `os.environ` / `os.getenv` access)

| Key | Module:line (registered) | Function / consumer | Req? | Expected value | Grammar disposition |
|---|---|---|---|---|---|
| MR002_EXECUTION_COUNTERSIGN | population_runner:1324 | run_clean_successor → load_authorization | required | `/inputs/authorization.json` | ATTESTED (governed input, exact) |
| MR002_EXECUTION_COUNTERSIGN_SHA256 | population_runner:1325 | run_clean_successor (hash channel) | required | 64-hex == authorization bytes | ATTESTED (== observed auth hash at produce; == signed value at exec) |
| MR002_EXPECTED_PINS | population_runner:1332 | load_expected_pins | required | `/inputs/expected_pins.json` | ATTESTED (governed input, exact) |
| MR002_SOURCE_MANIFEST | population_runner:1334 | load_static_manifest | required | `/inputs/source_manifest.json` | ATTESTED (governed input, exact) |
| MR002_EXECUTION_PACKAGE | population_runner:1337 | verify_execution_package | required | `/inputs/execution_package.json` | ATTESTED (governed input, exact) |
| MR002_EXECUTION_BINDING | population_runner:1342 | load_execution_binding | required | `/inputs/execution_binding.json` | ATTESTED (fixed path + ro mount) |
| MR002_EXECUTION_BINDING_SHA256 | population_runner:1344, 1408 | binding hash channel + provenance | required | 64-hex == binding bytes | **LAUNCHER-DERIVED** (blocker-8 ruling: forbidden in template; injected once at exec) |
| MR002_LAUNCH_ATTESTATION | population_runner:1345 | load_launch_attestation | required | `/inputs/launch_attestation.json` | ATTESTED (fixed path + ro mount) |
| MR002_REALISM_PASS | population_runner:1350, 1372 | load_realism_pass + manifest hash | required | `/inputs/realism_pass.json` | ATTESTED (fixed path + ro mount) |
| MR002_FINAL_TEST_REPORT | population_runner:1351, 1373 | load_final_test_report + manifest hash | required | `/inputs/final_test_report.json` | ATTESTED (fixed path + ro mount) |
| MR002_LAUNCH_VERIFICATION_RECEIPT | population_runner:1353 | load_verification_receipt | required | `/inputs/launch_verification_receipt.json` | ATTESTED (fixed path + ro mount) |
| MR002_OUT | population_runner:1396 | output root | optional (default `/out/cleanrun`) | absent | DELIBERATELY ABSENT (grammar refuses the key; the default inside the governed rw `/out` governs) |
| **MR002_IMAGE_DIGEST** | preflight:340 | gather_env → image identity check | **required** | `sha256:81e8d7a7…` == attestation image_digest | **ATTESTED (THIS DELTA)** — in-grammar equality vs the attested image identity |
| **MR002_OCI_CONFIG_DIGEST** | preflight:341 | gather_env → OCI identity check | **required** | `sha256:81e8d7a7…` == attestation oci_config_digest | **ATTESTED (THIS DELTA)** — full-digest format in-grammar; equality vs the attestation at produce AND exec |
| OPENBLAS_NUM_THREADS / OMP_NUM_THREADS / MKL_NUM_THREADS | preflight:347 (observation); native BLAS (consumer) | thread_env check + BLAS runtime | required | `1` | ATTESTED (exact, pre-existing) |
| OPENBLAS_CORETYPE | preflight:347 (observation); OpenBLAS (consumer) | openblas_coretype check + kernel dispatch | required | `HASWELL` | ATTESTED (exact, pre-existing) |
| MR002_ROOT | preflight:362 | preflight `main()` CLI ONLY | n/a | — | NOT IN THE REGISTERED PATH (run_clean_successor calls gather_env(root=None)); grammar refuses |
| MR002_COMMIT_SHA / MR002_TREE_SHA | preflight:371-372 | preflight `main()` CLI ONLY (env-supplied expected pins) | n/a | — | NOT IN THE REGISTERED PATH (the runner builds Expected from the countersigned pins); grammar refuses |
| MR002_SOURCE_MANIFEST (2nd site) | preflight:363 | preflight `main()` CLI ONLY | n/a | — | CLI-only duplicate of the runner's attested key |
| MR002_SAMPLE | coverage_signed_gap:99 | corpus scope selector ("A"/"B"/"" = FULL) | optional | absent | DELIBERATELY ABSENT — **critical**: grammar refuses the key so the default `""` (FULL population) is structurally guaranteed |
| MR002_STORE | development_run:482 | corpus DB path in run_config | optional | absent | DELIBERATELY ABSENT — the default IS the registered DB path `/work/apps/backend/data/mr002_research.duckdb` (identical to the runner's own hardcoded `db_path`) |
| MR002_DEV_OUT | development_run:532 | development_run CLI `main()` ONLY | n/a | — | NOT reached by `run_config` in the capture path; grammar refuses |
| *(none)* | source_manifest.py, stage3_cascade.py, certificate.py, joint_portfolio.py, dataset.py, runner.py, mr002_piqp.py, mr002_solver_intersection.py | — | — | — | ZERO env reads (verified by the scan and re-verified by the regression guard on every run) |

## Out-of-closure sites (found by the scan, NOT imported by the registered command)

`mr002_build_*`, `mr002_dev_dataprep`, `mr002_characterize_*`, `mr002_directed_rounding_correction`,
`mr002_duplicate_census`, `mr002_full_population` (quarantined lineage), `mr002_hardened_smoke`,
`mr002_predecessor_discovery`, `mr002_preflight` (the OLD non-Stage-3 preflight),
`mr002_preliminary_universe`, `mr002_qp_capability_discovery`, `mr002_sample_*`,
`mr002_stage2_edgar_crawl`, `mr002_structural_slice`, `mr002_verify_v1_v4`,
`mr002_stage3_cascade_fixtures` (realism harness — its own env contract, not the run path).
None is imported by `mr002_stage3_population_runner` or its closure; listed for completeness.

## Native-library env consumers (no python read site)

`OPENBLAS_CORETYPE` / `*_NUM_THREADS` are additionally consumed by OpenBLAS/OpenMP inside
the numerical shared objects; the preflight observes them (row above) and the image bakes
matching defaults. Covered by the attested exact values.
