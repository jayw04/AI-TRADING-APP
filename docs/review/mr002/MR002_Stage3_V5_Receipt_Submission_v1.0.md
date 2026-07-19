# MR-002 Stage-3 — v5 Verification-Receipt Submission v1.0

- **Date:** 2026-07-19. The frozen verifier was invoked EXACTLY ONCE against the accepted
  attestation; the receipt was written to a vacant no-overwrite path OUTSIDE `/inputs`. STOPPED
  after receipt production. Nothing committed or staged; no Phase-B binding, no `/out/cleanrun`,
  no Run 5.

## 1. Exact verifier command (real frozen CLI — read from the committed tool, not inferred)

```
cd /home/ec2-user/mr002/repo/apps/backend
PYTHONPATH=/home/ec2-user/mr002/repo/apps/backend python3.11 \
  scripts/mr002_stage3_attestation_verify.py \
  --attestation /home/ec2-user/mr002/v5_stage_tmp/launch_attestation_v5.json \
  --trusted-public-key /home/ec2-user/keys/mr002_launcher_ed25519.pub.pem \
  --receipt-out /home/ec2-user/mr002/v5_stage_tmp/launch_verification_receipt_v5.json
```

The committed tool's CLI is a flat parser with exactly `--attestation`, `--trusted-public-key`,
`--receipt-out` (no subcommand). My earlier provisional command named `verify`/`--public-key`/
`--out` — corrected here from the committed source, per your instruction.

## 2. Verification-tool identity

- File: `scripts/mr002_stage3_attestation_verify.py`
- **Content SHA-256 `33d08fe345b3b88f49cc85ee50cf6a53233d3523164bb7f927eb7333c4464e94`** — equals
  the attestation's `verification_tool_sha256`, and the tool self-checks this (`own_sha` vs
  `verification_tool_sha256`, exit 4 on mismatch) before signing the receipt.
- Git blob (b6e5d27): `687588513d5ea5089d6022788209a50bbe1fcafb`. Host copy at
  `~/mr002/repo/apps/backend/…` hashes identically.

## 3. Attestation pre-verification hash

`e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2` (the accepted candidate) —
**unchanged after verification** (re-hashed post-run: identical).

## 4. Public key

- Path: `/home/ec2-user/keys/mr002_launcher_ed25519.pub.pem`
- File SHA-256: `1fd0af4efb6c7608684378d90f734c40cb57a59612982180c2331b5b0d1e225f` (the trusted
  launcher public key; host copy == committed blob).
- Derived key id: `ed25519:86c48f8f19affc3a81b8b263f0244c03379e9a03593a86ae1bcd4c851cb35a87`
  (matches the attestation's `signing_key_id`).

## 5. Verifier exit code + complete output

- **Exit 0.**
- stdout (only line): `{"verified": true, "receipt_path": ".../launch_verification_receipt_v5.json",
  "receipt_sha256": "d69b95bef7e106db97a616a242ca071b8404bd0c029740b7d7f2b92e42baab56",
  "attestation_sha256": "e82468c3…4d4fb2", "run_nonce": "f3e0edf7…392594fc"}`
- stderr: empty. (The tool verifies canonical payload → tool-identity binding → trusted-key
  identity/type → Ed25519 signature over the canonical payload, then emits the receipt.)

## 6. Full receipt JSON

```json
{
 "attestation_sha256": "e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2",
 "canonical_signed_payload_sha256": "2704c6062ac66ddde5f18e62ffc708bf18ef45b2f92ecb1547e91c944b27fa87",
 "record_status": "IMMUTABLE",
 "record_type": "MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT",
 "run_nonce": "f3e0edf795a6998eb99fb1eca45ea9f9501ca1c9e9389e6a711db4be392594fc",
 "signature_algorithm": "ed25519",
 "signing_key_id": "ed25519:86c48f8f19affc3a81b8b263f0244c03379e9a03593a86ae1bcd4c851cb35a87",
 "verification_exit_status": 0,
 "verification_tool_sha256": "33d08fe345b3b88f49cc85ee50cf6a53233d3523164bb7f927eb7333c4464e94",
 "verified_at": "2026-07-19T21:00:43+00:00",
 "version": "1.0"
}
```

- **Receipt SHA-256 `d69b95bef7e106db97a616a242ca071b8404bd0c029740b7d7f2b92e42baab56`, 694 bytes.**
- Local review copy (uncommitted): `docs/review/mr002/MR002_Stage3_LaunchVerificationReceipt_v5.0.json`
  (byte-identical, same sha256).

## 7. Receipt schema / key inventory (closed 11-key set)

`attestation_sha256, canonical_signed_payload_sha256, record_status, record_type, run_nonce,
signature_algorithm, signing_key_id, verification_exit_status, verification_tool_sha256,
verified_at, version`. record_type `MR002_STAGE3_LAUNCH_VERIFICATION_RECEIPT`, version 1.0,
record_status IMMUTABLE, verification_exit_status 0.

## 8. Receipt ↔ attestation ↔ nonce cross-validation (frozen loaders)

`load_launch_attestation` and `load_verification_receipt` (the frozen population-runner loaders)
ACCEPTED the pair. Equalities confirmed:
- `attestation_sha256` == the attestation file hash `e82468c3…`.
- `run_nonce` == the attestation's `run_nonce` `f3e0edf7…` (the single reserved v5 nonce).
- `canonical_signed_payload_sha256` == the attestation's `2704c606…`.
- `verification_tool_sha256` == the attestation's `33d08fe3…`.
- `signing_key_id` == the attestation's `ed25519:86c48f8f…`.
- `verification_exit_status` == 0.

## 9. Confirmations

- Verifier ran **exactly once** (one receipt file exists; one verify log).
- No files overwritten (receipt destination was vacant; the tool's `publish_immutable` refuses a
  non-vacant path; attestation and the four `/inputs` files unchanged post-run).
- `/inputs` still contains **exactly four** regular files, 0 symlinks, hashes unchanged
  (`167b1b6e…`, `59a23fc0…`, `9798302a…`, `846c6418…`); v4 quarantine untouched.
- `/out` EMPTY; `docker ps -a` zero.
- Receipt NOT staged in `/inputs` (none present there); attestation + receipt NOT committed.
- Validation/OOS SEALED AND UNREAD.

## Requested owner actions

1. Exact-byte review of the receipt (`d69b95be…`, 694 B).
2. On acceptance: the held sequence — commit/stage decisions for attestation + receipt, then the
   Phase-B execution binding (the next artifact, assembled AFTER attestation + receipt), its
   one-run execution countersignature, one empty `/out/cleanrun`, and Run 5 — each on your
   explicit authorization.
