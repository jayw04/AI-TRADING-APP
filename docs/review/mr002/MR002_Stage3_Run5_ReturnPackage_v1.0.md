# MR-002 Stage-3 — Run 5 Return Package v1.0 — DISPOSITION: PASS

- **The single authorized v5 clean-successor registered run executed exactly once and reached a
  governed PASS.** No retry. No performance interpretation. Validation/OOS not accessed.
- Start `2026-07-19T21:36:06.461Z` → terminal (manifest write) `2026-07-19T21:43:19.7Z`
  (~7m13s). Authorization consumed at Docker start; it will not be reused for any outcome.

## 1. Countersignature commit (grouped step 1)

`a654d44520c857cb4da3e3ea9484c0e288212470` / tree `4f8a01390444d3e8f5a4b04e0d8029ef62298f5c`
/ parent `8a47d1b…` (pushed). Blobs: countersignature `52849f55…` (sha `7f6e3c82…`, byte-exact),
submission `dfd178c0…`. Tracked clean.

## 2. Final nine-file `/inputs` (pre- and post-run identical)

exactly 9 regular files, 0 symlinks, all `444`, dir `555`:
authorization `167b1b6e…`, expected_pins `59a23fc0…`, source_manifest `9798302a…`,
execution_package `846c6418…`, execution_binding `f4fb3c74…`, launch_attestation `e82468c3…`,
launch_verification_receipt `d69b95be…`, realism_pass `490e168a…`, final_test_report `e51a4920…`.
**Re-hashed after the run — all unchanged.**

## 3. Final pre-execution gate (all GREEN)

/work detached `ecaa262…`/tree `1cb95e25…`, porcelain 0, read-only, 0 symlinks; image/config
`sha256:81e8d7a7…` exact; `/out` empty; `docker ps -a` 0; archive unchanged; validation/OOS
sealed. Full in-image frozen-loader chain over the 9-file set: `load_authorization`,
`load_expected_pins` + `cross_validate_authorization`, `load_static_manifest`, `verify_source`
(zero defects), `evaluate` preflight `passed:true failed:[]`, `verify_execution_package`,
`load_final_test_report`, `load_realism_pass`, `load_launch_attestation` (sig), then
`load_verification_receipt` + `load_execution_binding` + `cross_validate_binding` — ALL ACCEPTED.

## 4. Output root at launch

`/home/ec2-user/mr002/out/cleanrun` — created as exactly one entry under `/out`, real directory,
non-symlink, empty; inode `66305:10179093`.

## 5. Exact invoked command + derived channel

Launcher: `python3.11 scripts/mr002_stage3_launch_attestation.py exec --attestation
/inputs/launch_attestation.json --receipt /inputs/launch_verification_receipt.json --binding
/inputs/execution_binding.json` (committed launcher `8d9874be…` at `b6e5d27`, from
`~/mr002/repo/apps/backend`, nohup). The launcher printed the fully-derived executed argv (in the
exec log) — the accepted v5 attestation template with **exactly one** injected field
`--env=MR002_EXECUTION_BINDING_SHA256=f4fb3c74ab7c1df4d0b6c7556d357f284bd83f350d832d1b42294b9026971167`,
`MR002_EXECUTION_COUNTERSIGN_SHA256=167b1b6e…`, image `sha256:81e8d7a7…`, `python
scripts/mr002_stage3_population_runner.py`. Launcher self-report: "attested, receipt-verified,
grammar-validated, inputs re-hashed, binding-derived".

## 6. Container / disposition

- Container `02e8584e…`, image `sha256:81e8d7a7…`, `--network=none`, auto-removed (`--rm`).
- **Runner stdout: `{"disposition": "PASS", "detail": "", "corpus_hash":
  "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b", "run_manifest":
  "/out/cleanrun/MR002_Stage3_CleanRun_Manifest.json"}`** — exit **0 = PASS**.
- Exec log (stdout+stderr) `MR002_Run5_exec_stdout_stderr.log` sha `48b5d4789024f87c…`; no errors,
  tracebacks, or refusals.

## 7. Output evidence

| Item | Value |
|---|---|
| Checkpoint | `MR002_Stage3_CleanRun_checkpoint.jsonl` — sha256 `511d11f52ce2751aacbbe78c2b96d7ce712b5dbf3161fa7b2ed0da5df5bb02ae`, **49,612,687 bytes, 3,896 lines** (3,895 records + 1 terminal) |
| Run manifest | `MR002_Stage3_CleanRun_Manifest.json` — sha256 `27fe7624a1a3b4e8328833f28f605eb2d636ea6d34513a75c1f396101431fa1f`, 130,845 bytes (laptop copy byte-verified identical) |
| Row-manifest sha256 (in manifest) | `699b17dffd222c06392842f58841f185e74132331e67f40df26817a94d7ac7eb` (identical to Run 4 — same registered corpus identity) |
| corpus_hash_derived_by_runner | `1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b` (== pins) |
| Terminal | `{"kind":"terminal","status":"COMPLETE","n_records":3895}` (final line) |
| Sidecars / emergency artifacts | **none** |

## 8. Run counters + solver split (manifest `run` block)

`n_expected 3895, n_processed 3895, n_qualified 3895, n_stopped 0, passed true, stopped false,
refused false, evidence_persisted true, resumable true, stop_reason "", refusal_reason "",
windows ["dev"]`. Solver split: **3,890 QUADPROG_SQRT (primary) + 5 PIQP_P2 (fallback)** —
identical to Run 4's split.

## 9. Final replay / schema-2 result (the Run-4 STOP is resolved)

- **`passed: true`** — the terminal `aggregate_verdict` semantic replay ACCEPTED all 3,895
  records (Run 4 STOPped here with 3,639 replay failures under the −0.0 defect).
- Every record carries `evidence_schema_version: "2.0"`: **3,895** schema-version markers,
  **23,370** `exact_hex` fields (3,895 × 6 input components), and **zero** legacy `exact_ratio`
  fields. The schema-2 hex encoding round-tripped the full population — negative zeros preserved.
- execution_provenance binds the full v5 chain: authorization/pins/manifest/package/attestation/
  receipt/binding/realism/report hashes + `bound_commit ecaa262…` / `bound_tree 1cb95e25…` /
  image+oci `81e8d7a7…` / preflight_report + semantic_summary.

## 10. Post-run confirmations

- `docker ps -a` **0** (container auto-removed).
- `/inputs` still exactly 9 files, hashes **unchanged**.
- Run-4 archive **unchanged** (checkpoint `b9b0a948…`, manifest `1132d3b8…`).
- Validation/OOS **SEALED AND UNREAD** — the frozen corpus source read the DEV window only
  (`windows: ["dev"]`); no validation/OOS path was touched.
- **No retry occurred** — one exec, one container, one checkpoint, one manifest.
- No output file was deleted, rewritten, normalized, truncated, repaired, or converted.

## Scope

A PASS authorizes ONLY submission of this complete execution evidence for adjudication. No
performance interpretation is made or authorized. The Run-5 checkpoint (49.6 MB) and manifest are
preserved on the box at `/home/ec2-user/mr002/out/cleanrun/` (owned by container root); the
manifest + exec log are pulled to `docs/review/mr002/run5_evidence/` (byte-verified). Await your
adjudication for checkpoint disposition (archive/transfer) and any next step. Instance remains
running (billing); termination remains forbidden until evidence review.
