# MR-002 Stage-3 — Preflight-Smoke Qualification Delta Resubmission (v1.7)

- **Date:** 2026-07-19
- **In response to:** v1.6 review verdict (delta/checkout/inventory/97-suite ACCEPTED;
  corrected launcher commit HELD pending smoke-test Option 1 implementation + pass).
- **Headline:** **the smoke PASSED — the FULL registered preflight (all 17 checks) passes
  inside the pinned container against the real numerical checkout, exit 0.**

## The smoke tool (Option 1, exactly as scoped)

`apps/backend/scripts/mr002_stage3_preflight_smoke.py` — sha256
`c59e1a10c84ef6ef073d87bac90afe74eddfebab95a8da17eccba13b11d43139` · **2,291 B** (additive
qualification tooling, comparable to the final-test-report generator). It: loads the
countersigned authorization through the frozen `load_authorization`
(`MR002_EXECUTION_COUNTERSIGN` + `_SHA256`); loads the REAL countersigned pins through the
frozen `load_expected_pins` hash-bound via the authorization (no operator-supplied
expected value exists anywhere); parses the registered source manifest exactly as the
runner does; calls the registered `run_preflight(pins, manifest)`; prints the complete
summary; exits 0 only when every check passes. It does not invoke population resolution,
open or iterate the corpus DB, call the cascade, create output, change any registered
module, or accept free-form expected values — and it is NOT a production command.

**Composition pinned by test** `test_smoke_tool_composition_static`: required elements
present; forbidden names (`run_clean_successor`, `orchestrate`, `resolve_instance`,
`production_corpus_source`, `run_population`, `FrozenDataset`, `seal_implementations`,
`stage3_cascade`, `duckdb`, the DB filename, `checkpoint`, `/out`,
`MR002_COMMIT_SHA`/`MR002_TREE_SHA`, and any `ExpectedPins(` construction) appear nowhere
in the code body; the import set is EXACTLY `{__future__, json, os, sys,
scripts.mr002_stage3_population_runner, scripts.mr002_stage3_preflight}`; no write-mode
`open`. And `test_smoke_tool_not_in_registered_command_grammar` proves the launcher
grammar still refuses it as a container command — production remains exactly
`python scripts/mr002_stage3_population_runner.py`.

## Smoke execution — REQUIRED EVIDENCE (all captured in `MR002_PreflightSmoke_Execution_v1.0.log`)

- **Configuration:** exact pinned image `sha256:81e8d7a7…`; `numrepo → /work` read-only;
  the countersigned authorization + pins + source manifest mounted read-only from the
  governed inputs; the four numerical thread variables; BOTH new digest channels;
  `--network=none`; NO `/out` mount (the frozen functions never demanded one); no
  population runner; no validation/OOS inputs; the smoke tool mounted read-only at
  `/tools/` (the final-test-report precedent).
- **Exact argv:** recorded in full in the log.
- **Container:** `ef0a38bac1b1e03883f0af13896f0b1dba3b68018cdc0f573de7cbc415529256`
  (via `--cidfile`); image `sha256:81e8d7a7…`.
- **Timestamps:** start `2026-07-19T01:38:27.068Z` → end `01:38:28.453Z` (~1.4 s).
- **Exit code: 0.** Complete stdout captured — **`"passed": true`, `"failed": []`,
  all 17 checks PASS**, including every item on the required list: `git_commit`
  (observed == `d26bd9e…`), `git_tree` (== `c0e52d8e…`), `working_tree_clean`,
  `image_digest`, `oci_config_digest`, `python_version` 3.13.14, `python_abi`,
  `package_versions`, `cpu_avx2_present` + `cpu_avx512_absent`, `thread_env` +
  `openblas_coretype`, `source_manifest`, `solver_certifier_fingerprints`,
  `corpus_hash_constant` (== `1d231930…`), `material_config`, `cascade_import_hygiene`.
- **`docker ps -a` before `[]` / after `[]`**; `/out` entries 0 before / 0 after (the
  host `/out` was never mounted and remains empty).
- **No corpus iteration:** structural — `run_preflight` touches manifest files + git +
  module imports only; corpus access would require `production_corpus_source`, which the
  composition-pinned tool provably does not import; the 1.4 s container lifetime is
  consistent with preflight-only work.

This is the proof the v1.6 verdict demanded: the next chain's in-container preflight has
now been exercised for real, end to end, and passes completely.

## Suite and lint

- **Qualified host (controlling):** `MR002_LauncherTools_HostSuite99_v1.7.log`
  (`52308b34…`) — **collected 99, 99 passed, ZERO skips, exit 0** (real CLI enabled;
  records the exact producer/tests/smoke hashes).
- Dev venv: `MR002_LauncherTools_DevSuite_v1.7.log` (`aab8aec9…`) — 98 passed + the one
  intentional host-only skip, exit 0.
- Ruff (now five paths incl. the smoke tool): `MR002_LauncherTools_Ruff_v1.7.log`
  (`967a4769…`) — `All checks passed!`, exit 0.
- No existing test replaced or weakened: 97 → **99** (the two additions above).

## Patch

`MR002_LauncherTools_Delta_v1.7.patch` (`fd9db930…`, 5,701 B) — incremental vs the v1.6
submitted bytes: the tests delta (+2 tests) and the ADDITIVE smoke script; the producer is
byte-unchanged since v1.6 (`8d9874be…`), the frozen verifier and report generator remain
at their committed accepted identities.

## Hash table (working tree; review copies byte-identical)

| File | sha256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_preflight_smoke.py` (NEW) | `c59e1a10c84ef6ef073d87bac90afe74eddfebab95a8da17eccba13b11d43139` | 2,291 |
| `apps/backend/scripts/mr002_stage3_launch_attestation.py` (unchanged since v1.6) | `8d9874beaef1732abba3f8d513df7016c301fcfeccc490f38c478edb646a1931` | 44,389 |
| `apps/backend/tests/research/test_mr002_stage3_launcher_tools.py` (97→99) | `bca74ec24e5854d15cf9395c6bebf9034d24c614d1433ff5483221839ccb71dd` | 63,893 |
| `MR002_PreflightSmoke_Execution_v1.0.log` | `ab85010320addc7fb39591e721f29a24af7b9d26085337202296c81ec9b4974c` | 4,523 |

## Held state

Corrected launcher commit still HELD (awaiting this acceptance). v2 chain remains
revoked/consumed; authorization `487c6ecb…`, pins countersignature, keys, QUAL3, host and
numrepo qualifications retained. On acceptance: commit (producer + tests + smoke tool +
governance records) → host-verify → full recheck → NEW attestation (new nonce; `/work` ←
numrepo; both digest channels) → NEW receipt → NEW binding → NEW execution
countersignature → one new clean registered execution. Performance NOT authorized;
validation/OOS SEALED AND UNREAD.
