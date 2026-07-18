# MR-002 Stage-3 — Launcher-Tool Blocker Remediation Resubmission (v1.4)

- **Date:** 2026-07-18
- **In response to:** owner v1.3 verdict (blockers 6–7 ACCEPTED; final architectural
  blocker 8: circular execution-binding hash dependency).
- **Scope of change:** attestation producer + tests ONLY, implementing exactly the
  owner-specified bounded correction (template + one launcher-derived field; the
  alternative of weakening the Phase-B binding schema was not taken). The frozen
  verification tool is **byte-unchanged since v1.2** (`33d08fe3…`) and the final-test-report
  generator remains the accepted bytes (`4b9ffb4d…`) — both diff-verified. No keypair,
  authorization, attestation, or receipt generated.

## Blocker 8 — circular binding-hash dependency → CLOSED

**The cycle, acknowledged:** the Phase-B binding must contain the attestation and receipt
hashes; the receipt binds the attestation; so the binding's own hash cannot appear inside
the signed command without a fixed-point/preimage problem. (The v1.3 tests masked this by
creating the synthetic binding before the attestation — an ordering unavailable to the
real Phase B.)

**The correction, as specified:**

1. **The attestation signs the template without the binding hash.**
   `MR002_EXECUTION_BINDING_SHA256` is now `DERIVED_BINDING_ENV_KEY` — FORBIDDEN in the
   attested template (refused as an unknown key at produce and again at exec, so an
   operator-supplied value cannot enter by either door). The countersign hash channel
   stays in the template (no cycle: the authorization pre-exists the attestation). The
   attestation still binds `MR002_EXECUTION_BINDING=/inputs/execution_binding.json` and
   its fixed read-only mount destination.
2. **`exec` receives the final binding path explicitly** — new required `--binding`
   argument, usable only after Phase B is assembled.
3. **The hash is derived from actual bytes** (`sha256` of the `--binding` file), never
   operator-supplied.
4. **The binding is verified through the frozen loader** (`load_execution_binding` with
   the derived hash — full closed schema, decision, countersigner, scope) **and
   cross-validated against the attestation and receipt**: `launch_attestation_sha256` ==
   the actual attestation file hash, `launch_verification_receipt_sha256` == the actual
   receipt file hash, plus authorization/pins/package/manifest hashes and all four
   identity fields against the attestation (`BINDING_CROSS_VALIDATION_MISMATCH`).
5. **The mounted bytes are proven**: sha256 of the file at the attested
   `/inputs/execution_binding.json` mount source must equal the derived hash
   (`BINDING_MOUNT_BYTES_MISMATCH`) — the injected hash corresponds to what the container
   will actually read.
6. **Exactly one derived field is injected**, immediately before the image token:

       executed argv = attested_command_template
                       + --env=MR002_EXECUTION_BINDING_SHA256=<observed hash>

   and the executed argv is **re-validated in executed mode**, where the derived key is
   REQUIRED (in template mode it is refused) — so template + exactly this one field is the
   only shape that passes both modes. No other field may be added, removed, or rewritten.

The template/executed distinction is a single `executed: bool` mode on the one shared
parser — the grammar itself remains closed and identical otherwise.

## Required tests — all present

- `test_blocker8_attestation_template_carries_no_binding_hash` — attestation production
  requires no binding hash; the signed template provably contains none; supplying one is
  refused (also `test_blocker8_operator_supplied_binding_hash_refused_at_produce`).
- `test_blocker8_end_to_end_construction_order` — **the real sequence with real artifact
  hashes**: authorization (pre-existing) → attestation → receipt → execution binding
  assembled ONLY afterwards (binding the actual attestation + receipt hashes) → exec
  validation. Proves: binding assembled after attestation and receipt; hash derived from
  actual mounted bytes; **injected exactly once** (`count == 1`); **executed argv differs
  from the attested template by only the one authorized derived field** (token-exact
  reconstruction check).
- `test_blocker8_operator_supplied_binding_hash_refused_at_exec` — a cryptographically
  VALID attestation whose template smuggles the key passes the verify tool, then exec
  refuses with no spawn.
- `test_blocker8_substituted_binding_mount_bytes_refused` — mounted copy diverges from the
  `--binding` bytes → refused, no spawn.
- `test_blocker8_tampered_binding_cross_validation_refused` — binding whose
  `launch_attestation_sha256` does not match the actual attestation bytes → refused by
  cross-validation (the loader's schema alone would pass), no spawn.
- The prior exec tests now run the full three-artifact flow
  (`test_blocker3_exec_runs_validated_command` asserts the template+derived-field argv;
  unsafe-command and substituted-pins refusals re-proven with `--binding` present).

## Evidence

- `MR002_LauncherTools_79Tests_v1.4.log` — exact command, environment (Python 3.13.14,
  pytest 9.0.3, cryptography 45.0.7, win32 dev venv — NOT the pinned numerical venv),
  **collected 79 items, 79 PASSED listed individually, exit 0** (74 → 79).
- `MR002_LauncherTools_Ruff_v1.4.log` — ruff 0.15.13, exact command over ALL FOUR paths,
  `All checks passed!`, exit 0.
- `MR002_LauncherTools_Delta_v1.4.patch` — exact incremental unified diff against the v1.3
  bytes (producer `65424205…`, tests `9e641779…`). Verifier and report generator absent
  (byte-unchanged).

## Hash and byte-length table (working tree; review copies verified byte-identical)

| File | sha256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_launch_attestation.py` (REVISED) | `c6c8e84182cd36ce2f3246e0b287ddb6abc4b2ef53afa4834f091cee1b1c0d68` | 40,501 |
| `apps/backend/scripts/mr002_stage3_attestation_verify.py` (UNCHANGED since v1.2) | `33d08fe345b3b88f49cc85ee50cf6a53233d3523164bb7f927eb7333c4464e94` | 9,834 |
| `apps/backend/scripts/mr002_stage3_final_test_report.py` (UNCHANGED — accepted) | `4b9ffb4de0ddc90d26d6d5b46539731b943dbb94aa8079ccf9328ecf0a25fca2` | 6,019 |
| `apps/backend/tests/research/test_mr002_stage3_launcher_tools.py` (EXPANDED 74→79) | `1400c896e71288ef6eee0bf3c9779f028ec403fbd3373b5c9518975f0d0dd5a2` | 47,961 |
| `docs/review/mr002/MR002_LauncherTools_Delta_v1.4.patch` | `4303108ed4e6b263bd6a8153685534c6d7aef1da2677aba4490a9e82e5500c87` | 31,283 |
| `docs/review/mr002/MR002_LauncherTools_79Tests_v1.4.log` | `29187206903276f956f2b47749435b75c7bedc441a5848b9de066505c488a2af` | 18,692 |
| `docs/review/mr002/MR002_LauncherTools_Ruff_v1.4.log` | `1e64f47e120b351f69f575e792e193575e03dc3fed0d20714a899fd40300f1f5` | 478 |

⚠ Windows working-tree hashes; committed LF blob hashes get recorded at step 3 of the
owner's ordered sequence.

## Construction order (now cycle-free, for the launch runbook)

    authorization → attestation (template, no binding hash) → receipt
    → Phase-B binding (binds attestation + receipt hashes) → countersign
    → exec --attestation --receipt --binding
        (derive hash → frozen-loader verify → cross-validate → mount-bytes proof
         → inject one field → executed-mode re-validate → docker run)

## Held state (per the verdict)

No keypair, no authorization artifact, no attestation, no receipt generated. Launcher
commit awaits this delta's acceptance. Registered execution remains NOT authorized;
validation/OOS sealed and unread. Launch host: fresh dedicated c6a; the TOCTOU staging
controls remain recorded for the step-4 runbook.
