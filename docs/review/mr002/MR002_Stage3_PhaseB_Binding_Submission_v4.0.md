# MR-002 Stage-3 — v4 Phase-B Execution Binding Submission for the New Execution Countersignature

- **Date:** 2026-07-19
- **Authorization:** v4 replacement pre-Phase-B verdict (v4 Phase-B assembly AUTHORIZED).
- **The launcher `exec` and the registered run remain locked** until you countersign these
  exact bytes.

## The v4 binding

- **Artifact:** `docs/review/mr002/MR002_Stage3_ExecutionBinding_v4.0.json` (review copy;
  staged copy byte-identical on the host)
- **sha256:** `83d1bcbfe891614cb35359f8a0e01d9672c71231419723e8b938e4490bb02e30` · **1,436 B · 21 keys**
- Frozen closed schema exactly; disposition retained (`EXECUTION_PACKAGE_COUNTERSIGNED`,
  `execution_authorized true`, `MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`, `IMMUTABLE`);
  distinct from all three prior bindings.

| Field | Value | |
|---|---|---|
| launch_attestation_sha256 | `7c65a9017b86fccbbc8c8aa31d4c80e6a81e9778de2679b9166403f277600453` | **v4 REPLACEMENT** |
| launch_verification_receipt_sha256 | `6462e6c8681e3d866ab3b9cf70c4694868d83214b46352c769569e4aa75c364f` | **v4 REPLACEMENT** |
| authorization_sha256 | `487c6ecbcbf06d21b247ec429d0af216e256a279c7c112903cef1b279bf1f8ca` | retained |
| expected_pins_sha256 | `ddfa43d0766ba12e7ac1816e1d67962e1edb56c75524a6a25265d982861dad3c` | retained |
| implementation_manifest_sha256 | `27d2819bb116d7b00e0a8e78a9bcce3b4a07930eddfbe7e67f802579ee7010fe` | retained |
| execution_package_sha256 | `66c8d42fb39d2afdc996f5be98676786aaceb0af3160850bd303b68d0bd52a60` | retained |
| realism_pass_sha256 | `f7cccd6522f05f175c11fa481e3672aeb1b518d1ef58fe2b2ada81d2d75a0242` | retained |
| final_test_report_sha256 | `26bbdff8339117311cb4d5beda45f542db031ed3156f6724a3bafd59509944ae` | retained |
| bound_commit / bound_tree | `d26bd9edbd875d2e3e11d4a6f6e06bad933b168e` / `c0e52d8ec61f881a2058c9c9686fde1ec33123a0` | retained |
| image_digest = oci_config_digest | `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea` | retained |

## Validation evidence

1. **`load_execution_binding` ACCEPTED** the exact bytes.
2. **`cross_validate_binding` PASS** against the ACTUAL v4 artifact bytes (attestation
   hashed live; authorization loaded via the frozen loader; receipt bytes compared —
   equal).
3. The bound v4 attestation/receipt carry your independent verification from the v4
   pre-Phase-B verdict (canonical payload `42436d8e…`; nonce `abef3641…`; template
   byte-identical to the accepted v3 form).

## Staging + confirmation (per the required list)

Staged via no-replace creation at `/inputs/execution_binding.json` (vacant since the v3
quarantine); **staged bytes == submitted bytes** (`83d1bcbf…`); **all nine inputs
read-only** (2× `-r--------`, 7× `-r--r--r--`); directory re-locked; **zero symlinks**;
**`docker ps -a` empty**; **launcher checkout `b6e5d278…`**; **numrepo `d26bd9e…` /
`c0e52d8e…`**; **`/out` contains exactly one empty `cleanrun` directory and nothing else**
(the corrected governing condition).

## After your countersignature

`exec --attestation --receipt --binding` re-validates the template, re-hashes the governed
inputs, cross-validates this binding, proves the mounted binding bytes, injects
`MR002_EXECUTION_BINDING_SHA256=83d1bcbf…` exactly once, and starts the registered
command. Run 3 already proved this configuration passes the FULL registered preflight and
enters the orchestrator; the output-root gate that stopped it is now satisfied. The
remaining gates are the corpus-regeneration hash equality and the 3,895-row population
itself.

## Held state

New execution countersignature NOT issued; exec NOT authorized; registered run PAUSED;
performance NOT computed; validation/OOS SEALED AND UNREAD. All nine prior-chain
artifacts remain preserved in quarantine.
