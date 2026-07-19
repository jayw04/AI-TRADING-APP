# MR-002 Stage-3 — v5 Phase-B Execution-Binding Submission v1.0 (HOLD POINT)

- **Date:** 2026-07-19. Exactly one `execution_binding.json` candidate assembled and
  cross-validated. STOPPED before any one-run execution countersignature. The binding is NOT
  staged in `/inputs`; no `/out/cleanrun`; no launcher invocation; no Run 5.

## 1. Pre-Phase-B commit (prerequisite, completed first)

`db7dfb0f22897ab0d3b851a3116077061ade54d5` / tree `10ef68492084083e241771fb6ebb5fca6587f2dd`
/ parent `d99308fe5ef0a264b8532352641c65cd5727e1cb` (pushed; A × 2; tracked clean;
package/submission bytes unchanged — `42535d8e…` / `df6bf205…`).

## 2. Eight-file `/inputs` inventory (committed bytes, no-overwrite, 0444, 0 symlinks, dir 0555)

| File | realpath | SHA-256 | bytes |
|---|---|---|---|
| authorization.json | `/home/ec2-user/mr002/inputs/authorization.json` | `167b1b6e…f818c37` | 2,395 |
| expected_pins.json | `/home/ec2-user/mr002/inputs/expected_pins.json` | `59a23fc0…16a6e13` | 1,530 |
| source_manifest.json | `/home/ec2-user/mr002/inputs/source_manifest.json` | `9798302a…0bbf76f8` | 9,131 |
| execution_package.json | `/home/ec2-user/mr002/inputs/execution_package.json` | `846c6418…1d5c9ea24` | 5,313 |
| launch_attestation.json | `/home/ec2-user/mr002/inputs/launch_attestation.json` | `e82468c3…084d4fb2` | 4,096 |
| launch_verification_receipt.json | `/home/ec2-user/mr002/inputs/launch_verification_receipt.json` | `d69b95be…42baab56` | 694 |
| realism_pass.json | `/home/ec2-user/mr002/inputs/realism_pass.json` | `490e168a…d401512dd` | 12,131 |
| final_test_report.json | `/home/ec2-user/mr002/inputs/final_test_report.json` | `e51a4920…8550a0b093` | 61,982 |

Owner `ec2-user`; all mode `444`; directory mode `555`; **exactly 8 regular files, 0 symlinks.**
Each staged from the committed git blob and hash-verified at extraction, transfer, and after
placement — all equal the committed identities. The four closed-v4 inputs remain in
`~/mr002/inputs_v4_closed_quarantine/` (untouched).

**All eight artifact hashes match the committed bytes** (recomputed above; = the accepted
identities).

## 3. Execution-binding candidate (full JSON)

```json
{
 "authorization_sha256": "167b1b6e2b15fcce5f1e7f68a95a237184b94892f69867a8bec90c701f818c37",
 "bound_commit": "ecaa262480fb2b81fb0ba7d11b97721b617722bf",
 "bound_tree": "1cb95e254c0dc82bc231b355b8ab502f4e33f752",
 "countersigned_by": "Jay Wang (owner)",
 "countersigned_date": "2026-07-19",
 "decision": "EXECUTION_PACKAGE_COUNTERSIGNED",
 "execution_authorized": true,
 "execution_package_sha256": "846c6418c3b23b36c61da260fcf0953b5245a0967df8187355887d51d5c9ea24",
 "expected_pins_sha256": "59a23fc092b5e0ccdf4dfedc2873f584f722aaa71f62a3d3c19990da916a6e13",
 "final_test_report_sha256": "e51a49202076c2e8005e90ffc9a087f0f3b5a9c33d0a926a95f3cd8550a0b093",
 "image_digest": "sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea",
 "implementation_manifest_sha256": "9798302a868724ac92fab57274100bef928bb0ccdf29f393dcaf65850bbf76f8",
 "launch_attestation_sha256": "e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2",
 "launch_verification_receipt_sha256": "d69b95bef7e106db97a616a242ca071b8404bd0c029740b7d7f2b92e42baab56",
 "oci_config_digest": "sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea",
 "realism_pass_sha256": "490e168af94d443e2985025f4887e3c1939d3ab9f0068521e98d8b1d401512dd",
 "record_status": "IMMUTABLE",
 "record_type": "MR002_STAGE3_EXECUTION_BINDING",
 "repository": "jayw04/AI-TRADING-APP",
 "scope": "MR002_STAGE3_CLEAN_SUCCESSOR_ONLY",
 "version": "1.0"
}
```

- **SHA-256 `f4fb3c74ab7c1df4d0b6c7556d357f284bd83f350d832d1b42294b9026971167`, 1,436 bytes.**
- Local file (uncommitted): `docs/review/mr002/MR002_Stage3_ExecutionBinding_v5.0.json`.

### Schema / key inventory (21 keys — the frozen closed Phase-B set)

12 required binding hashes: `implementation_manifest_sha256, realism_pass_sha256,
final_test_report_sha256, execution_package_sha256, expected_pins_sha256, authorization_sha256,
launch_attestation_sha256, launch_verification_receipt_sha256, bound_commit, bound_tree,
image_digest, oci_config_digest`; plus the closed optional set: `record_type, version (1.0),
record_status (IMMUTABLE), countersigned_by ("Jay Wang (owner)"), countersigned_date, repository,
decision (EXECUTION_PACKAGE_COUNTERSIGNED), execution_authorized (true), scope
(MR002_STAGE3_CLEAN_SUCCESSOR_ONLY)`.

**Closed-schema disclosure (per your instruction not to add unsupported fields):** the frozen
`load_execution_binding` REJECTS any key outside the set above (`BINDING_UNEXPECTED_KEYS`).
Therefore `run_nonce`, `output_mount`, and `evidence_schema_version` are NOT binding fields — they
bind TRANSITIVELY through `launch_attestation_sha256 = e82468c3…`: the bound attestation carries
`run_nonce = f3e0edf7…`, `output_mount_identity = /home/ec2-user/mr002/out:/out:rw`, and the exact
argv; evidence schema 2.0 binds via the authorization/package the binding also names. The receipt
(`d69b95be…`) independently carries the same nonce.

## 4. Producer + frozen-loader / cross-validation output

- **Producer:** the binding has no separate CLI producer — it is assembled JSON validated by the
  frozen loaders (same as v1–v4). Validation ran with the repo backend venv against the committed
  artifact bytes.
- `load_execution_binding(path, f4fb3c74…)` → **ACCEPTED** (closed schema; decision, exec flag,
  scope, countersigner, ISO date, and all hex64 formats pass; zero unexpected keys).
- `cross_validate_binding(...)` → **PASS**: every bound artifact hash equals the committed bytes
  AND `bound_commit`/`bound_tree`/`image_digest`/`oci_config_digest` equal the authorization's
  identities.

## 5. Nonce coherence

The binding schema has no nonce field; nonce agreement is proven transitively and directly:
`launch_attestation_sha256` and `launch_verification_receipt_sha256` in the binding equal the
committed attestation/receipt, and BOTH of those carry `run_nonce =
f3e0edf795a6998eb99fb1eca45ea9f9501ca1c9e9389e6a711db4be392594fc` (the single reserved v5 nonce).

## 6. Proposed filenames

- Committed: `docs/review/mr002/MR002_Stage3_ExecutionBinding_v5.0.json`.
- Host staging (LATER, on your authorization): `/home/ec2-user/mr002/inputs/execution_binding.json`
  (becomes the ninth `/inputs` file only after acceptance).

## 7. Confirmations

- `execution_binding.json` is NOT staged in `/inputs` (none present; `/inputs` still exactly 8).
- No one-run execution countersignature exists.
- `/out` EMPTY; `docker ps -a` zero; validation/OOS SEALED AND UNREAD.
- No v1–v4 attestation, receipt, binding, nonce, or countersignature reused; the closed v4
  set stays quarantined.

## Requested owner actions

1. Exact-byte review of the binding candidate (`f4fb3c74…`, 1,436 B).
2. On acceptance: commit the binding, then — each on explicit authorization — the one-run
   execution countersignature, staging `execution_binding.json` into `/inputs` (→ 9 files),
   `mkdir` exactly one empty `/out/cleanrun`, and `exec` = Run 5 from row zero.
