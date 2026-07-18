# MR-002 Stage-3 — Execution Package v1.9 (review copy, repair cycle 9)

Responds to the cycle-5 review (18 findings). Byte-identical working-tree copies
(`research/mr002-preregistration`). **No Stage-3 instance run. Nothing committed.**

Start with **`MR002_Stage3_ExecutionPackage_v1.9.json`** — `corrections_from_review_v9` maps all 18
findings using the required closure taxonomy (CLOSED_IN_CODE / CLOSED_BY_DEVELOPMENT_TEST /
OPEN_IN_IMAGE / OPEN_AT_COMMIT / OPEN_AT_COUNTERSIGNATURE / OPEN_IN_LAUNCH_ATTESTATION).

## The five priority workstreams
1. **Two-phase binding** (2, 13, 14): Phase-A manifest carries `manifest_phase=PRE_EXECUTION_SOURCE`;
   the new Phase-B `MR002_STAGE3_EXECUTION_BINDING` artifact (validator: `load_execution_binding`)
   externally enumerates manifest/realism-PASS/test-report/package/pins/authorization/attestation
   hashes; the countersignature binds Phase B. Phase A is never regenerated in-container.
2. **Formal `_qp_matrices` contract** (4): `INPUT_CONTRACT` (11 clauses derived from
   `_qp_matrices`/SQRT/dual/PIQP/certifier) + `MR002_Stage3_QPMatrices_InputContract_v1.0.json` +
   `test_mr002_stage3_input_contract.py` — every clause has a boundary fixture, and a one-to-one
   test forbids contract/validator drift.
3. **Full replay schema** (7, 8, 9): `_replay_certificate_defect` (schema + value invariants),
   `validate_model_inputs` on the rebuilt record, `_replay_disposition_defect` (serialized
   `validate_outcome` equivalents) — all wired into `aggregate_verdict` and pinned by tamper tests.
4. **Corpus-day + DB hardening** (5, 6): `days = tuple(...)` materialized with day-sequence
   provenance; the DB must be a regular, hashable, non-symlink file BEFORE capture (refusal, not a
   note); dataset closed in `finally`.
5. **Launch attestation defined** (3): `ATTESTATION_REQUIRED_FIELDS` + `load_launch_attestation`
   enforce the full binding set (launcher identity, exact command, output mount, run nonce,
   signature). Producing + signing it remains the launcher's job — the acknowledged open channel.

Also: preflight-fail harness artifact now byte-bound + sidecar + distinct exit code (1, 17);
sequence-numbered atomic sidecars (10); `Exception` at every persistence boundary (11); byte-exact
governed JSON writes everywhere (12); ISO-8601 authorization dates (15).

## Verification (this session)
ruff clean · **147 passed, 1 skipped, exit 0** (cascade 48 · preflight 25 · runner 60 · contract 15)
· source manifest verifies (phase-aware, governance-checked) with zero defects.

## Still open
launch attestation (produce+sign) · final commit + regenerated Phase-A artifacts · in-image: full OCI
digest, realism PASS, production-binding test run · countersigned pins/authorization/Phase-B binding.
