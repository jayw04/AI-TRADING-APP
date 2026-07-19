# MR-002 Stage-3 — REPLACEMENT Phase-B Execution Binding Submission for the New Execution Countersignature (v2.0)

- **Date:** 2026-07-19
- **Authorization:** v2.0 replacement pre-Phase-B verdict (replacement Phase-B assembly
  AUTHORIZED with the retained identities + the two replacement values).
- **The launcher `exec` and the registered run remain locked** until you countersign these
  exact bytes.

## The replacement binding

- **Artifact:** `docs/review/mr002/MR002_Stage3_ExecutionBinding_v2.0.json` (review copy;
  staged copy byte-identical on the host)
- **sha256:** `a3fd33f5e8a2bca3eb055a5725f9b438ac15f5fa88cd65a0b4f00f5659ab70a4` · **1,436 B**
- **Distinct from the revoked binding** `efbd290c…` (which stays quarantined at
  `~/mr002/revoked/` and in governance history).
- **Schema:** the frozen closed 21-key schema exactly — decision
  `EXECUTION_PACKAGE_COUNTERSIGNED`, `execution_authorized true`, scope
  `MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`, `record_status IMMUTABLE`, countersigner, date
  2026-07-19, repository, and the 12 required fields; no other key.

Bound identities — retained values unchanged, exactly two replacements:

| Field | Value | |
|---|---|---|
| launch_attestation_sha256 | `4f8eade6fb401e3d59919eb8b1a6956d848d51a6da495242ec513e5259d19c77` | **REPLACEMENT** |
| launch_verification_receipt_sha256 | `6a8cebe69ff2a5aa9a4d3c55703c2f169ba6e8d6d8b633bfc0e0f57e5fef4185` | **REPLACEMENT** |
| authorization_sha256 | `487c6ecbcbf06d21b247ec429d0af216e256a279c7c112903cef1b279bf1f8ca` | retained |
| expected_pins_sha256 | `ddfa43d0766ba12e7ac1816e1d67962e1edb56c75524a6a25265d982861dad3c` | retained |
| implementation_manifest_sha256 | `27d2819bb116d7b00e0a8e78a9bcce3b4a07930eddfbe7e67f802579ee7010fe` | retained |
| execution_package_sha256 | `66c8d42fb39d2afdc996f5be98676786aaceb0af3160850bd303b68d0bd52a60` | retained |
| realism_pass_sha256 | `f7cccd6522f05f175c11fa481e3672aeb1b518d1ef58fe2b2ada81d2d75a0242` | retained |
| final_test_report_sha256 | `26bbdff8339117311cb4d5beda45f542db031ed3156f6724a3bafd59509944ae` | retained |
| bound_commit | `d26bd9edbd875d2e3e11d4a6f6e06bad933b168e` | retained |
| bound_tree | `c0e52d8ec61f881a2058c9c9686fde1ec33123a0` | retained |
| image_digest = oci_config_digest | `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea` | retained |

## Validation evidence (dev machine, this session)

1. **`load_execution_binding` ACCEPTED** the exact bytes (hash-bound; closed schema; all
   formats valid).
2. **`cross_validate_binding` PASS** — the runner's own cross-check run early: every
   binding hash compared against the ACTUAL replacement artifact bytes (the v2 attestation
   file hashed live; authorization loaded through its frozen loader; identity fields
   matched), plus the receipt-bytes comparison — equal.
3. The replacement attestation and receipt it binds were accepted by your v2.0 pre-Phase-B
   verdict (canonical payload `cc7a1ef4…` independently recomputed; Ed25519 signature
   verified; new nonce `d9d6b49c…`).

## Staging evidence (host, per the required sequence)

Staged at the fixed destination `/home/ec2-user/mr002/inputs/execution_binding.json`;
staged bytes verified equal to the submitted binding (`a3fd33f5…`); directory re-locked
(`dr-xr-xr-x`); **zero symlinks**; **/out empty**; **`docker ps -a` empty**. The governed
input directory is COMPLETE: all nine artifacts the corrected attested template mounts are
staged read-only.

## After your countersignature (nothing runs until then)

`exec --attestation --receipt --binding` on the qualified host re-validates the corrected
`ro=false` template (real-CLI-proven), re-hashes the four governed inputs, cross-validates
this binding, proves the mounted binding bytes, injects the single derived field
`MR002_EXECUTION_BINDING_SHA256=a3fd33f5…`, and starts the exact registered container
command; the runner's in-container preflight remains the final barrier before any of the
3,895 rows.

## Held state

New execution countersignature NOT yet issued; launcher exec NOT authorized; registered
run PAUSED; performance NOT computed; validation/OOS SEALED AND UNREAD. Revoked chain
(attestation `f845cbbd…`, receipt `e3a202b6…`, binding `efbd290c…`, old nonce, old
countersignature) remains revoked and unused.
