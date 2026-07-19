# MR-002 Stage-3 — Launcher `ro=false` Remediation Resubmission (v1.5)

- **Date:** 2026-07-19
- **In response to:** refusal review verdict (stop COMPLIANT; root cause CONFIRMED;
  **Option A — explicit `ro=false` — AUTHORIZED**; mode omission NOT authorized; prior
  attestation/receipt/binding/execution-countersignature REVOKED; pins countersign,
  execution authorization, trusted key, QUAL3, and host qualification RETAINED).
- **Scope:** ONLY the `ro=false` launcher/parser/documentation delta + new tests, per the
  authorized recovery sequence. The frozen verifier and report generator are
  **byte-unchanged** (diff-verified vs their committed accepted identities). The stop
  report + refusal log were committed unchanged first (`f56ddd5`).

## The delta (producer parser + docs)

- `_MOUNT_SPEC_FLAGS` = `{ro, readonly}` — **bare `rw` is gone from the grammar** and now
  refuses as `MOUNT_SPEC_UNKNOWN_FLAG:rw` (the token Docker's real CLI rejects is refused
  by OUR grammar too).
- The ONE approved explicit read-write declaration is the exact Docker-valid token
  **`ro=false`** (`_MOUNT_EXPLICIT_RW_TOKEN`), matched before key=value parsing and
  normalized internally to the marker flag "rw".
- `ro=true`, `readonly=true`, `readonly=false` refuse as
  `MOUNT_MODE_TOKEN_NOT_APPROVED:<token>` (closed set: bare `ro`/`readonly` for
  read-only, exactly `ro=false` for read-write, nothing else).
- `/out` therefore requires exactly `ro=false`: bare `rw` refused, omitted mode refused
  (`OUTPUT_MOUNT_NOT_EXPLICITLY_RW`, unchanged), `ro`/`readonly` refused, contradictions
  (`ro` + `ro=false`) refused. Non-output mounts continue to require the explicit
  read-only bare flag.
- The derived output identity remains the NORMALIZED logical form `<src>:/out:rw`; the
  code comments and module docstring now explicitly distinguish that identity from the
  Docker CLI token `ro=false` that the command itself carries.

## Required tests — all present

Grammar level (no mocks needed): `test_rofalse_canonical_output_mount_accepted` (canonical
spec carries `ro=false`, derives `<src>:/out:rw`); `test_rofalse_legacy_bare_rw_refused_by_grammar`;
parametrized `test_rofalse_other_mode_value_tokens_refused` (`ro=true` / `readonly=true` /
`readonly=false`); `test_rofalse_ro_true_on_output_refused_and_contradiction_refused`;
the pre-existing omitted-mode and bare-`ro` /out refusals retained.

**Real-CLI test** (`test_realcli_canonical_template_parses_legacy_rw_refused`): invokes the
ACTUAL Docker CLI — no `subprocess.run` mock — gated by `MR002_REAL_CLI_TEST=1` (host-only
by design; it exists precisely because mocks cannot catch CLI-grammar incompatibility).
With EXISTING mount sources and a deliberately unresolvable image it proves: the canonical
`ro=false` command passes Docker option parsing AND daemon mount validation and reaches
only the image-resolution failure; the legacy bare-`rw` command fails at `--mount` flag
parsing with exit 125; `docker ps -a` is unchanged (no container created by either).
Its first host run caught its own initial design gap (nonexistent dummy mount sources
stopped at daemon mount validation instead of image resolution) — fixed to use real
temporary sources; that iteration is itself evidence the test exercises the real stack.

All 79 prior tests retained (6 mount specs updated from the now-refused bare `rw` to
`ro=false`; zero semantic changes otherwise). Suite: **79 → 86 tests.**

## Evidence

| Artifact | sha256 · bytes | Result |
|---|---|---|
| `MR002_LauncherTools_HostSuite86_v1.5.log` | `c30247aa…` · 19,274 | **QUALIFIED HOST, real CLI enabled: collected 86, 86 passed, ZERO skips, exit 0** (log records the exact producer/tests hashes below, Docker 25.0.14, containerd snapshotter) |
| `MR002_RealCLI_ParseEvidence_v1.5.log` | `8cc9455c…` · 3,483 | Dedicated probe log with every required field: docker version + storage driver, exact 45-token argv, full stderr, exit codes (canonical → image-resolution failure only, "invalid argument" appears exactly once in the file = the legacy probe's parser refusal), `docker ps -a` before `[]` / after `[]`, "0 containers exist" |
| `MR002_LauncherTools_DevSuite_v1.5.log` | `a7ab8b61…` · 19,726 | dev venv: 85 passed + 1 skipped (the host-only real-CLI test, reason string in log), exit 0 |
| `MR002_LauncherTools_Ruff_v1.5.log` | `aec346dc…` · 416 | ruff 0.15.13, all four paths, `All checks passed!`, exit 0 |
| `MR002_LauncherTools_Delta_v1.5.patch` | `d1c45d3b…` · 12,420 | exact incremental diff vs the COMMITTED v1.4 bytes (`c6c8e841…` / `1400c896…`) |

Host-suite integrity: the delta files ran on the qualified host from a SEPARATE scratch
clone (`~/mr002/delta-test/`, bundle-cloned at 595b9c1 + the two revised files, scp'd
byte-verified) — the qualified launch checkout was NOT touched and remains at the
committed 595b9c1 state.

## Revised hashes and byte lengths (working tree; review copies byte-identical)

| File | sha256 | Bytes |
|---|---|---|
| `apps/backend/scripts/mr002_stage3_launch_attestation.py` (REVISED) | `0fe474aa7d092d9f6eec9217ccb67d2123e259ba497f6a447bc5174186109288` | 41,884 |
| `apps/backend/scripts/mr002_stage3_attestation_verify.py` (UNCHANGED — committed `33d08fe3…`) | `33d08fe345b3b88f49cc85ee50cf6a53233d3523164bb7f927eb7333c4464e94` | 9,834 |
| `apps/backend/scripts/mr002_stage3_final_test_report.py` (UNCHANGED — committed `4b9ffb4d…`) | `4b9ffb4de0ddc90d26d6d5b46539731b943dbb94aa8079ccf9328ecf0a25fca2` | 6,019 |
| `apps/backend/tests/research/test_mr002_stage3_launcher_tools.py` (EXPANDED 79→86) | `9bdffc701c4deb2ca7b5f99567153dfdc99587fc948cb5ce4a3efbaf2c6407d7` | 52,730 |

## Held state (per the verdict)

Prior attestation `f845cbbd…`, receipt `e3a202b6…`, binding `efbd290c…`, and the execution
countersignature are REVOKED — none will be reused, nor the old nonce. Registered-run
authorization PAUSED. After acceptance: commit the corrected bytes → verify on the
qualified host → full recheck → NEW attestation → NEW receipt → NEW Phase-B binding →
NEW execution countersignature → one clean registered run. Validation/OOS sealed;
performance interpretation not authorized. Host remains in the qualified state
(scratch delta-test tree and real-CLI staging live outside the governed directories).
