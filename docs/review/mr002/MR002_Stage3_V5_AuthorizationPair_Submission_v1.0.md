# MR-002 Stage-3 — v5 Authorization-Pair Submission v1.0 (STOPPED after production + validation)

- **Date:** 2026-07-19. Both artifacts are UNCOMMITTED and authorize nothing until your
  exact-byte review. No attestation, nonce, receipt, or binding exists.
- Record-only closeout completed first: `MR002_Stage3_V5_QualCommit_Record_v1.0.json` committed
  byte-unchanged (sha `5831f7dc…` staged-blob-verified) as commit
  `0565a7c5ad7513b1187927c0583417ea1c3ed0fb`, parent `ccca220…`, one non-executable JSON, no
  artifact bytes changed, tracked status clean, pushed.

## Artifact 1 — Expected-pins countersign record v2.0

- Proposed committed filename: `docs/review/mr002/MR002_Stage3_ExpectedPins_Countersign_v2.0.json`
- Proposed staging filename: not staged in `/inputs` (the runner consumes the PINS bytes +
  `MR002_EXPECTED_PINS(+_SHA256)` channel; the countersign record is a governance artifact —
  same treatment as the v1.0 countersign, committed only). Your ruling if staging is desired.
- **SHA-256 `4a1203cf4ad542dc4fe38e150d3d68591e4e246277392db7c55ad5611781437b`, 1,497 B.**
- Binds exactly (per your list): pins sha `59a23fc0…`, pins git blob `23e480e2…`, qualification
  commit `ccca220…`, implementation `ecaa262…`/tree `1cb95e25…`, image + OCI config
  `sha256:81e8d7a7…`, evidence schema `2.0` (plus corpus hash + python version in
  `binds_summary`, mirroring the v1.0 countersign shape). States it SUPERSEDES the v1.0 pins
  countersignature and does NOT authorize execution by itself.

```json
(full committed-candidate bytes — 24 keys, inventory below; the file in this submission IS the
exact byte candidate; see docs/review/mr002/MR002_Stage3_ExpectedPins_Countersign_v2.0.json)
```

Key inventory (closed, flat+nested): artifact_bytes, artifact_git_blob, artifact_path,
artifact_record_type, artifact_sha256, artifact_version, binds_summary{git_commit, git_tree,
corpus_hash, image_digest, oci_config_digest, python_version, evidence_schema_version},
bound_technical_values_unaltered, countersign_date, countersigned_by, decision, note,
qualification_commit, record_status, record_type, supersedes, version.

## Artifact 2 — Execution authorization v2.0

- Proposed committed filename: `docs/review/mr002/MR002_Stage3_ExecutionAuthorization_v2.0.json`
- Proposed staging filename: `/home/ec2-user/mr002/inputs/authorization.json` (the frozen
  channel `MR002_EXECUTION_COUNTERSIGN` + `MR002_EXECUTION_COUNTERSIGN_SHA256=167b1b6e…`),
  staged only at the later chain-staging step, after v4 inputs are quarantined per your ruling.
- **SHA-256 `167b1b6e2b15fcce5f1e7f68a95a237184b94892f69867a8bec90c701f818c37`, 2,395 B.**
- **Frozen-loader core (all 17 v1-schema fields, validated by `load_authorization`):**
  record_type/version 1.0/IMMUTABLE/authorized_date 2026-07-19/decision AUTHORIZED/
  execution_authorized true/countersigned_by "Jay Wang (owner)"/repository/bound_commit
  `ecaa262…`/bound_tree `1cb95e25…`/image+config `81e8d7a7…`/source_manifest `9798302a…`/
  expected_pins `59a23fc0…`/execution_package `846c6418…`/execution_package_version "1.9"/
  row_manifest_protocol `MR002_STAGE3_ROW_IDENTITY_V1`.
- **Extended bindings (your complete required set; the frozen loader validates its required
  fields exactly and tolerates additional binding fields — disclosed):** final_test_report
  `e51a4920…`, realism `490e168a…`, archive-qualification report `3a399021…` + publication
  `1a0eb4f9…`, qualification_commit `ccca220…`, corpus `1d231930…`, evidence_schema_version
  "2.0", scope `MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`, pins_countersign_sha256 `4a1203cf…` (the
  pair is mutually bound).
- **Statements (verbatim keys under `authorization_statements` + `supersedes_and_no_reuse`):**
  execution_authorized scope = "true only for preparation of the fresh v5 launch chain; no run
  executes until the separate one-run execution countersignature exists"; registered_run_count
  "one"; start_position "row zero"; resume_or_reuse "forbidden"; validation_oos "sealed and
  unread"; performance_interpretation "not authorized"; supersedes authorization `487c6ecb…`
  (v1–v4 chains consumed/closed); **contains NO nonce — the nonce belongs only to the later
  launch attestation** (proven structurally: no key in either artifact names a nonce).

## Validation output (frozen loaders, laptop backend venv against the exact local bytes)

```json
{
 "load_authorization": "ACCEPTED",
 "cross_validate_authorization_vs_pins": "PASS",
 "verify_execution_package_via_auth": "ACCEPTED version=1.9 revision=2.0",
 "load_final_test_report_via_auth_binding": "ACCEPTED",
 "load_realism_pass_via_auth_binding": "ACCEPTED",
 "committed_artifact_hash_crosscheck": "ALL EQUAL (manifest, archive report, archive publication)",
 "pair_binding": "countersign binds pins sha 59a23fc0...; authorization binds countersign sha 4a1203cf...",
 "no_nonce_key": "PROVEN structurally",
 "no_reuse": "authorization sha != 487c6ecb...; new countersign supersedes v1.0 by statement"
}
```

Every hash in both artifacts was cross-checked against the COMMITTED qualification artifacts at
`ccca220` (pins/manifest/package/report/realism) and the archive-qualification evidence at
`ed9ea51` (report/publication) — all equal.

## Exact frozen-loader verification commands (for your independent replay)

From `apps/backend` with the repo venv (or in-image with `/work` + PYTHONPATH):

```python
from scripts.mr002_stage3_population_runner import (
    load_authorization, load_expected_pins, cross_validate_authorization,
    verify_execution_package, load_final_test_report, load_realism_pass)
auth = load_authorization("docs/review/mr002/MR002_Stage3_ExecutionAuthorization_v2.0.json",
                          "167b1b6e2b15fcce5f1e7f68a95a237184b94892f69867a8bec90c701f818c37")
pins = load_expected_pins("docs/review/mr002/MR002_Stage3_ExpectedPins_v2.0.json",
                          auth["expected_pins_sha256"])
cross_validate_authorization(auth, pins)
verify_execution_package("docs/review/mr002/MR002_Stage3_ExecutionPackage_v2.0.json", auth)
load_final_test_report("docs/review/mr002/MR002_Stage3_FinalTestReport_v2.0.json",
                       auth["final_test_report_sha256"])
load_realism_pass("docs/review/mr002/MR002_Stage3_CascadeRealismHarness_v2.0.json",
                  auth["realism_pass_sha256"])
```

## Requested owner actions

1. Exact-byte review of both artifacts (`4a1203cf…` 1,497 B; `167b1b6e…` 2,395 B).
2. On acceptance: commit authorization for the pair + this submission; then the held sequence —
   v5 launch attestation with a NEW nonce → frozen-verifier receipt → v5 pre-Phase-B package →
   Phase-B binding → one-run execution countersignature → one empty `/out/cleanrun` → Run 5
   from row zero.
