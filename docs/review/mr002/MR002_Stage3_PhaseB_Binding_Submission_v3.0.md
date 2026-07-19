# MR-002 Stage-3 — v3 Phase-B Execution Binding Submission for the New Execution Countersignature

- **Date:** 2026-07-19
- **Authorization:** v3 replacement pre-Phase-B verdict (v3 Phase-B assembly AUTHORIZED
  with the retained identities + the two v3 replacement fields).
- **The launcher `exec` and the registered run remain locked** until you countersign these
  exact bytes.

## The v3 binding

- **Artifact:** `docs/review/mr002/MR002_Stage3_ExecutionBinding_v3.0.json` (review copy;
  staged copy byte-identical on the host)
- **sha256:** `cb067a3ab8b9ff50ad3d807b73f455b802a10db8dcfec150a06d370aaa66c9e6` · **1,436 B · 21 keys**
- Frozen closed schema exactly: decision `EXECUTION_PACKAGE_COUNTERSIGNED`,
  `execution_authorized true`, scope `MR002_STAGE3_CLEAN_SUCCESSOR_ONLY`,
  `record_status IMMUTABLE`, countersigner, date 2026-07-19, repository, the 12 required
  fields, no other key. Distinct from both revoked bindings.

| Field | Value | |
|---|---|---|
| launch_attestation_sha256 | `edef7483def8f25ed62d5f7b39df3084d5772d4aac8dff3a973f56dbefb26bd9` | **v3 REPLACEMENT** |
| launch_verification_receipt_sha256 | `0d6cd66973a50a4b905825c076c6ee9714226c87f0502db6a3db1ba6bcc8950a` | **v3 REPLACEMENT** |
| authorization_sha256 | `487c6ecbcbf06d21b247ec429d0af216e256a279c7c112903cef1b279bf1f8ca` | retained |
| expected_pins_sha256 | `ddfa43d0766ba12e7ac1816e1d67962e1edb56c75524a6a25265d982861dad3c` | retained |
| implementation_manifest_sha256 | `27d2819bb116d7b00e0a8e78a9bcce3b4a07930eddfbe7e67f802579ee7010fe` | retained |
| execution_package_sha256 | `66c8d42fb39d2afdc996f5be98676786aaceb0af3160850bd303b68d0bd52a60` | retained |
| realism_pass_sha256 | `f7cccd6522f05f175c11fa481e3672aeb1b518d1ef58fe2b2ada81d2d75a0242` | retained |
| final_test_report_sha256 | `26bbdff8339117311cb4d5beda45f542db031ed3156f6724a3bafd59509944ae` | retained |
| bound_commit / bound_tree | `d26bd9edbd875d2e3e11d4a6f6e06bad933b168e` / `c0e52d8ec61f881a2058c9c9686fde1ec33123a0` | retained |
| image_digest = oci_config_digest | `sha256:81e8d7a7be6bb022d7bde68e923ea6ef2a41b029390200e0240235f35aa173ea` | retained |

## Validation evidence

1. **`load_execution_binding` ACCEPTED** the exact bytes (hash-bound; closed schema).
2. **`cross_validate_binding` PASS** against the ACTUAL v3 artifact bytes (the v3
   attestation hashed live; the countersigned authorization loaded via its frozen loader
   with identity equality) — plus the receipt-bytes comparison, equal.
3. The v3 attestation/receipt it binds carry your independent verification from the v3
   pre-Phase-B verdict (canonical payload `0272e413…` recomputed; nonce `c7e6700e…`;
   template with numrepo `/work`, `ro=false`, both digest channels, no binding-sha).

## Staging + confirmation (per the required list)

Staged via no-replace creation at `/inputs/execution_binding.json` (destination vacant
since the v2 quarantine); **staged bytes == submitted bytes** (`cb067a3a…`); directory
re-locked (`dr-xr-xr-x`); **all nine inputs read-only** (modes listed in evidence);
**zero symlinks**; **`/out` empty**; **`docker ps -a` empty**;
**numrepo `d26bd9e…` / `c0e52d8e…`**; **launcher checkout `b6e5d278…`**.

## After your countersignature

`exec --attestation --receipt --binding` re-validates the corrected template (real-CLI
proven; smoke-proven preflight configuration), re-hashes the four governed inputs,
cross-validates this binding, proves the mounted binding bytes, injects the single
derived field `MR002_EXECUTION_BINDING_SHA256=cb067a3a…`, and starts the exact registered
command — whose in-container preflight has already passed 17/17 in this exact
configuration. The runner's preflight and integrity gates remain the final barriers.

## Held state

New execution countersignature NOT issued; exec NOT authorized; registered run PAUSED;
performance NOT computed; validation/OOS SEALED AND UNREAD. Both revoked chains
(v1 `f845cbbd…`/`e3a202b6…`/`efbd290c…`, v2 `4f8eade6…`/`6a8cebe6…`/`a3fd33f5…`) remain
quarantined and unused.
