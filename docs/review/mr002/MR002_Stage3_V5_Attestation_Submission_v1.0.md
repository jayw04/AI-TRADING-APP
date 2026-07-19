# MR-002 Stage-3 — v5 Launch Attestation Candidate Submission v1.0

- **Date:** 2026-07-19. STOPPED immediately after producing the single candidate. No verifier
  was invoked; no receipt exists; the attestation is NOT staged in `/inputs` and NOT committed.
- Option A executed exactly as authorized: closed v4 inputs quarantined (not deleted), a fresh
  four-file `/inputs` staged from committed bytes, verified, locked; then one fresh nonce and one
  attestation candidate produced to a path OUTSIDE `/inputs`.

## 1. v4 quarantine (preserved, untouched)

- Path: `/home/ec2-user/mr002/inputs_v4_closed_quarantine/` (moved with `mv -n`, then locked
  files `444` / dir `555`).
- All nine closed-v4 hashes preserved byte-identical pre/post move: authorization `487c6ecb…`,
  expected_pins `ddfa43d0…`, source_manifest `27d2819b…`, execution_package `66c8d42f…`,
  execution_binding `83d1bcbf…`, launch_attestation `7c65a901…`,
  launch_verification_receipt `6462e6c8…`, realism_pass `f7cccd65…`, final_test_report
  `26bbdff8…`.

## 2. v5 `/inputs` inventory (exactly four files, committed bytes)

| File | realpath | SHA-256 | bytes | mode |
|---|---|---|---|---|
| authorization.json | `/home/ec2-user/mr002/inputs/authorization.json` | `167b1b6e2b15fcce5f1e7f68a95a237184b94892f69867a8bec90c701f818c37` | 2,395 | 444 |
| expected_pins.json | `/home/ec2-user/mr002/inputs/expected_pins.json` | `59a23fc092b5e0ccdf4dfedc2873f584f722aaa71f62a3d3c19990da916a6e13` | 1,530 | 444 |
| source_manifest.json | `/home/ec2-user/mr002/inputs/source_manifest.json` | `9798302a868724ac92fab57274100bef928bb0ccdf29f393dcaf65850bbf76f8` | 9,131 | 444 |
| execution_package.json | `/home/ec2-user/mr002/inputs/execution_package.json` | `846c6418c3b23b36c61da260fcf0953b5245a0967df8187355887d51d5c9ea24` | 5,313 | 444 |

Owner `ec2-user`; directory `/home/ec2-user/mr002/inputs` mode `555`; **zero symlinks**; exactly
four regular files. Bytes were extracted from the committed git blobs (`bb5e99d7`, `23e480e2`,
`af90440c`, `200901fd`) at `e4ca2a6`/`ccca220`, hash-verified at extraction, after transfer, and
again after placement — all equal.

## 3. Fresh nonce

- **`f3e0edf795a6998eb99fb1eca45ea9f9501ca1c9e9389e6a711db4be392594fc`** — 64 lowercase hex = 256
  bits.
- Method: `python3.11 -c "import secrets; print(secrets.token_hex(32))"` (CSPRNG), generated
  after the four-file staging, passed once to the producer via `--run-nonce`, recorded exactly
  once in the attestation.
- **Distinct from every prior nonce** (all four collected from produce logs + attestation files +
  revoked/quarantine copies): v1 `3d0455f4…bebbb27e`, v2 `d9d6b49c…4a0a1891`, v3
  `c7e6700e…96045944`, v4 `abef3641…9503bd37`. No match.

## 4. Attestation candidate

- Path (outside `/inputs`): `/home/ec2-user/mr002/v5_stage_tmp/launch_attestation_v5.json`
- **SHA-256 `e82468c3f94ea90f2f7c8d23c8a8abfde16f7aa5717004e3eac7efdf084d4fb2`, 4,096 bytes.**
- Local review copy (uncommitted): `docs/review/mr002/MR002_Stage3_LaunchAttestation_v5.0.json`
  (byte-identical; same sha256). Exact argv also copied: `..._v5_argv.json` sha `c820a677…`.
- Produced by the committed launcher `mr002_stage3_launch_attestation.py` (content sha
  `8d9874be…`, git blob `cc40b60e…` at `b6e5d27`), python3.11, key
  `~/keys/mr002_launcher_ed25519.pem` (0600). The producer self-verified through the frozen
  `load_launch_attestation` loader before reporting success.

### Closed-schema key inventory (21 keys — exactly ATTESTATION_REQUIRED_FIELDS + record_type/version/record_status)

`authorization_sha256, bound_commit, bound_tree, canonical_signed_payload_sha256, exact_command,
execution_package_sha256, expected_pins_sha256, image_digest, launcher_identity,
oci_config_digest, output_mount_identity, record_status, record_type, run_nonce, signature,
signature_algorithm, signing_key_id, source_manifest_sha256, verification_tool,
verification_tool_sha256, version`

### Direct bindings (all EQUAL the committed/staged identities)

authorization `167b1b6e…`, expected_pins `59a23fc0…`, source_manifest `9798302a…`,
execution_package `846c6418…`, bound_commit `ecaa262…`, bound_tree `1cb95e25…`, image +
oci_config `sha256:81e8d7a7…`, output_mount_identity `/home/ec2-user/mr002/out:/out:rw`,
verification_tool `scripts/mr002_stage3_attestation_verify.py` (sha `33d08fe3…`, referenced, NOT
invoked), record_type `MR002_STAGE3_LAUNCH_ATTESTATION`, version 1.0, record_status IMMUTABLE.

### Transitive bindings (disclosed — the frozen attestation schema is closed to the 21 keys above)

The attestation cannot carry a `final_test_report`, `realism`, or archive-qualification field —
its schema is closed. Those bind TRANSITIVELY: `authorization_sha256` = `167b1b6e…` is the v5
execution authorization, which itself binds final_test_report `e51a4920…`, realism `490e168a…`,
archive-qualification report `3a399021…` + publication `1a0eb4f9…`, the qualification commit
`ccca220…`, the authorization-pair commit `e4ca2a6…`, corpus `1d231930…`, evidence schema 2.0,
and scope `MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`. This is the same transitive structure v1–v4 used.

## 5. Signature verification output (independent — NOT the receipt verifier)

Using `cryptography` Ed25519 directly against the host public key
`~/keys/mr002_launcher_ed25519.pub.pem` and the frozen `canonical_payload`:
- **SIGNATURE VALID (ed25519).**
- `canonical_signed_payload_sha256` = `2704c606…4b27fa87` recomputed and MATCHES.
- `signing_key_id` = `ed25519:86c48f8f19affc3a81b8b263f0244c03379e9a03593a86ae1bcd4c851cb35a87`
  matches the key id derived from the host public key.
- Public-key identity: `ed25519:86c48f8f…` (the trusted launcher key, same as v1–v4 —
  the KEY is retained; only the chain is fresh).

The frozen verification tool (`mr002_stage3_attestation_verify.py`) was NOT invoked and no
receipt was produced.

## 6. Exact command + governed-binding validation

`exact_command` (full argv in the attestation, verbatim) uses the canonical container
destinations `/inputs/{authorization,expected_pins,source_manifest,execution_package}.json` with
host mount sources `/home/ec2-user/mr002/inputs/*.json`, and
`MR002_EXECUTION_COUNTERSIGN_SHA256=167b1b6e…`. It is byte-identical to the accepted v4 frozen
grammar EXCEPT that single countersign-hash env value (v4 was `487c6ecb…`). The producer's
built-in checks passed: closed-grammar parse, DERIVED output-mount identity ==
`/home/ec2-user/mr002/out:/out:rw`, governed-input realpath binding (each argv mount source ==
the hashed `--authorization`/pins/manifest/package file), and the countersign-env == observed
authorization-hash rule.

## 7. Confirmations

- No receipt exists (searched; zero).
- `/out` EMPTY; `docker ps -a` zero.
- `/inputs` = exactly the four files above; v4 quarantine preserved (9 files).
- Validation/OOS SEALED AND UNREAD.
- Attestation NOT staged in `/inputs`, NOT committed.

## 8. Proposed next-step artifacts (for reference; NOT executed)

- Proposed committed filename: `docs/review/mr002/MR002_Stage3_LaunchAttestation_v5.0.json`.
- Proposed host staging filename (LATER, on your authorization):
  `/home/ec2-user/mr002/inputs/launch_attestation.json`.
- Exact frozen-verifier command proposed for the NEXT step (receipt — NOT run now):
  `PYTHONPATH=/home/ec2-user/mr002/repo/apps/backend python3.11
  scripts/mr002_stage3_attestation_verify.py verify --attestation <path> --public-key
  ~/keys/mr002_launcher_ed25519.pub.pem --out <receipt path outside /inputs>` (exact form to be
  confirmed against the frozen verifier CLI at that step).

## Requested owner actions

1. Exact-byte review of the attestation candidate (`e82468c3…`, 4,096 B).
2. On acceptance: authorization to produce the frozen-verifier receipt (next single step), then
   commit/stage decisions for the attestation.
