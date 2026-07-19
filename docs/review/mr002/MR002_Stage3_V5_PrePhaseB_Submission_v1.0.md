# MR-002 Stage-3 — v5 Pre-Phase-B Submission v1.0 (HOLD POINT)

- **Date:** 2026-07-19. STOPPED after assembling + cross-validating the complete pre-Phase-B
  chain binding. **No `execution_binding.json`, no one-run countersignature, no `/out/cleanrun`,
  no launcher invocation, no Run 5.** Nothing staged into `/inputs`.

## 1. Attestation + receipt commit (prerequisite, completed first)

Commit `d99308fe5ef0a264b8532352641c65cd5727e1cb` / tree `6330c2158d3ce6d5d0d87a2dfaac997a1e7cf21e`
/ parent `e4ca2a6…` (pushed). Name-status **A × 5** (all under `docs/review/mr002/`).
Staged-blob-verified byte-exact:

| Artifact | SHA-256 | bytes |
|---|---|---|
| MR002_Stage3_LaunchAttestation_v5.0.json | `e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2` | 4,096 |
| MR002_Stage3_LaunchVerificationReceipt_v5.0.json | `d69b95bef7e106db97a616a242ca071b8404bd0c029740b7d7f2b92e42baab56` | 694 |
| MR002_Stage3_LaunchAttestation_v5_argv.json | `c820a677d8364651404d3f2e36d2d87623bfa1ca99d13f51d7920b0810cc89d5` | 2,441 |
| MR002_Stage3_V5_Attestation_Submission_v1.0.md | `6aba4dd070b23cdc18f1df0f787071fdf6916a2fb99176561560b1a59abc9e4e` | 7,903 |
| MR002_Stage3_V5_Receipt_Submission_v1.0.md | `25902fa37c19b3f050b296e3b243063c4fba6be2a9a8f771d9a954239dd5f36b` | 5,689 |

Binary-safe diff `git diff e4ca2a6..d99308f --binary` sha256
`a5b83faa17316944279908a7aac990064623acd264f3f5ffffba565d2ece3e32`, 22,550 B. Tracked status
clean. No bytes regenerated or normalized.

## 2. Pre-Phase-B package

`docs/review/mr002/MR002_Stage3_V5_PrePhaseB_Package_v1.0.json` — sha256
`42535d8ee752c1e52c2ee008a5d98a84524206dbb0de33e1a452fda69d9370d1` (uncommitted; this
submission's subject). It binds the full chain:

| Component | SHA-256 |
|---|---|
| authorization | `167b1b6e2b15fcce5f1e7f68a95a237184b94892f69867a8bec90c701f818c37` |
| expected pins | `59a23fc092b5e0ccdf4dfedc2873f584f722aaa71f62a3d3c19990da916a6e13` |
| pins countersign | `4a1203cf4ad542dc4fe38e150d3d68591e4e246277392db7c55ad5611781437b` |
| source manifest | `9798302a868724ac92fab57274100bef928bb0ccdf29f393dcaf65850bbf76f8` |
| execution package | `846c6418c3b23b36c61da260fcf0953b5245a0967df8187355887d51d5c9ea24` |
| final report | `e51a49202076c2e8005e90ffc9a087f0f3b5a9c33d0a926a95f3cd8550a0b093` |
| realism | `490e168af94d443e2985025f4887e3c1939d3ab9f0068521e98d8b1d401512dd` |
| launch attestation | `e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2` |
| verification receipt | `d69b95bef7e106db97a616a242ca071b8404bd0c029740b7d7f2b92e42baab56` |
| archive-qual report | `3a399021451a054301db7c2f87695652d52c2f38c6c78ba7f075d04f2320f072` |
| archive-qual publication | `1a0eb4f9373d33b09a59b4fe12af4284cbcc970a043319b4d6dd70f34a5188ee` |

Chain identities: nonce `f3e0edf7…`, implementation `ecaa262…`/tree `1cb95e25…`, qualification
commit `ccca220…`, authorization-pair commit `e4ca2a6…`, attestation/receipt commit `d99308f…`,
image + OCI config `sha256:81e8d7a7…`, corpus `1d231930…`, evidence schema `2.0`, scope
`MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`; canonical payload `2704c606…`, signing key
`ed25519:86c48f8f…`, verification tool `33d08fe3…`.

## 3. Cross-validation (all committed bytes)

- **All 11 committed artifact file hashes recomputed == the bound identities** (exact).
- **Full frozen-loader chain ACCEPTS end-to-end** (repo venv against committed copies):
  `load_authorization` → `load_expected_pins` + `cross_validate_authorization` →
  `verify_execution_package` → `load_final_test_report` → `load_realism_pass` →
  `load_launch_attestation` (Ed25519 signature verified) → `load_verification_receipt`
  (cross-checked against the attestation). Identity coherence proven: the attestation binds
  `authorization_sha256 = 167b1b6e…`, which itself binds pins/package/manifest/report/realism/
  archive-qual; the receipt binds the attestation hash `e82468c3…` and the reserved nonce
  `f3e0edf7…`; every equality holds.

## 4. Confirmations

- No `execution_binding.json` exists; no one-run countersignature; no `/out/cleanrun`; no
  launcher invocation; no Run 5.
- Attestation + receipt NOT staged in `/inputs` (host `/inputs` still holds exactly the four
  governed inputs; v4 quarantine preserved).
- `/out` EMPTY; `docker ps -a` zero; validation/OOS SEALED AND UNREAD.

## Requested owner actions

1. Review the pre-Phase-B package (`42535d8e…`).
2. On acceptance: the held sequence — attestation + receipt `/inputs` staging, the Phase-B
   `execution_binding.json` (assembled AFTER attestation + receipt, binding all nine chain
   identities including attestation `e82468c3…` and receipt `d69b95be…`), its one-run execution
   countersignature, one empty `/out/cleanrun`, and Run 5 from row zero — each on your explicit
   authorization.
