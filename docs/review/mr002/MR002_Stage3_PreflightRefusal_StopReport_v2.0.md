# MR-002 Stage-3 — Registered-Execution STOP Report v2.0: In-Container Preflight Refusal (Run 2)

- **Date:** 2026-07-19 (launch 01:04:53Z)
- **Disposition:** **STOPPED per the countersignature stop conditions.** The registered
  container launched, ran the registered command, and the runner's in-container preflight
  **REFUSED** — the fail-closed gate working as designed. No patch, retry, resume, input
  alteration, or bypass was attempted. **Zero rows attempted, zero completed; `/out`
  empty before and after; validation/OOS SEALED AND UNREAD.**

## Required post-run submission (refusal outcome)

| Item | Value |
|---|---|
| Launcher stdout/stderr | `~/mr002/launch/exec2_stdout_stderr.log` (2,519 B; review copy `MR002_Exec2_Refusal_20260719.log` below). Contains the container's refusal line AND the launcher's executed-argv print. ⚠ Evidence-reading note: the launcher's own print is block-buffered and flushed at process exit, so it appears AFTER the container's output in the file — the initial "empty container output" reading was wrong; the refusal line was at the file head throughout. |
| Launcher exit code | not captured by the nohup wrapper (disclosed); the container exit code is authoritative from docker events, and the launcher returns it verbatim |
| Exact executed argv | printed in full in the log: the attested 45-token `ro=false` template + the derived field — Docker parsed it, the daemon validated all 11 mounts, the container ran (the blocker-1..8 launch chain is now proven END-TO-END through container execution) |
| Derived binding token | `--env=MR002_EXECUTION_BINDING_SHA256=a3fd33f5e8a2bca3eb055a5725f9b438ac15f5fa88cd65a0b4f00f5659ab70a4`, present exactly once (grep count 1) |
| Container / image identity | container `bf05fb4b0f09ac2a6272625eccfc01f8616712eb6b2705e6fbfdea55f2a59126` (auto-removed by the attested `--rm`), image `sha256:81e8d7a7be6b…` (docker events record both) |
| Runner stdout | `REFUSED: preflight failed: ['git_commit', 'git_tree', 'image_digest', 'oci_config_digest']` |
| Preflight outcome | REFUSED — exactly those four checks; **every other preflight gate PASSED** (source-manifest verification, solver/certifier fingerprints, package pins, python/ABI, AVX2-present/AVX-512-absent, thread env, working-tree-clean, corpus constant) |
| Start / end | container start `2026-07-19T01:04:53.716Z`, die `2026-07-19T01:04:54.800Z` (execDuration ~1.08 s), exitCode **2** (docker events, authoritative) |
| Rows attempted / completed | **0 / 0** (refusal precedes population resolution and corpus regeneration) |
| Output inventory before / after | empty / empty (0 entries both) |
| Output hashes / row-manifest hash | none produced |
| Failure/refusal inventory | the single preflight refusal above; no other failure |
| Host-state recheck | post-refusal: `docker ps -a` empty; `/out` empty; inputs `dr-xr-xr-x` with all 9 staged hashes unchanged; zero symlinks; checkout `d8992ac` porcelain-clean; image digest exact; key 0600 |
| Validation / OOS | SEALED AND UNREAD — the refusal precedes any data access; the corpus DB was never opened |

## Root cause — two independent launch-chain design defects (runner is correct)

**1. `/work` mounts the launcher checkout, not the registered numerical commit.**
`gather_env` observes the git identity of the mounted `/work` worktree; the countersigned
pins bind the REGISTERED identity `git_commit d26bd9e…` / `git_tree c0e52d8e…`. The
attested template mounts `/home/ec2-user/mr002/repo`, which (per the accepted replacement
sequence) is the LAUNCHER checkout — `d8992ac` — so the observed identity can never equal
the pinned one. This conflation has been present since the first canonical template; it
was unreachable until now because earlier failures (bare-`rw` CLI parse) masked it. The
correct design: `/work` must be a **pristine checkout of the registered numerical commit
`d26bd9e`** (a separate host directory with the corpus DB staged inside it); the launcher
tools continue to run host-side from the corrected launcher checkout — two different
trees for two different roles.

**2. The finite environment grammar omits the preflight's identity channels.**
`gather_env` reads `MR002_IMAGE_DIGEST` and `MR002_OCI_CONFIG_DIGEST` from the container
environment (a container cannot observe its own digest); with the keys absent it observes
`None` ≠ pins. My blocker-6 "demonstrably required" derivation enumerated only
`population_runner.py`'s `os.environ` reads and missed `mr002_stage3_preflight.py`'s —
the finite set therefore REFUSES the two keys the preflight needs. They must be added to
the closed grammar with a STRONG rule: each must equal the attestation's own
`image_digest` / `oci_config_digest` field exactly (checkable at produce AND exec — no
free operator value).

## Diagnostics performed (all disclosed, read-only, no governed change, no retry)

Docker events + journal (container lifecycle + exit code); fast-exit output-capture
probes A/B on the pinned image (both captured — ruling out an attach race); image-config
inspection (no entrypoint, root user, `PYTHONUNBUFFERED=1`); one container run with the
EXACT attested mounts/env/workdir but a trivial introspection command (NOT the registered
entrypoint): python 3.13.14, correct cwd, runner file present, env channels present,
governed inputs readable — proving the environment sound and isolating the refusal to the
two identity classes above. The registered command was executed exactly once.

## Remediation options (OWNER DECISION — nothing executed)

Both defects require a launcher/template correction and therefore a NEW chain
(the current attestation `4f8eade6…` signs the defective template):

- **(a) Template:** `/work` mount source becomes a new pristine host checkout of
  `d26bd9e` (e.g., `~/mr002/numrepo`, DB staged inside, locked read-only, porcelain-clean
  with only the gitignored DB). No grammar change needed for this — the mount source is a
  path; the attestation binds it via the signed template.
- **(b) Grammar delta (launcher code — delta review + recommit):** add
  `MR002_IMAGE_DIGEST` and `MR002_OCI_CONFIG_DIGEST` to the finite env set, each REQUIRED
  and validated equal to the attestation's corresponding identity field at produce and
  exec; plus an exhaustive env-read sweep across ALL in-container modules the runner
  imports (`population_runner`, `preflight`, `source_manifest`, `cascade`) so the set is
  complete by construction this time, with the enumeration recorded in the resubmission.
- Then: recommit → host verification → NEW attestation (new nonce) → NEW receipt → NEW
  Phase-B binding → NEW execution countersignature → one clean run. The current
  authorization `487c6ecb…` binds only the registered numerical identities and pins —
  unchanged by either correction — so per the prior precedent it can be retained at your
  discretion.

## Authorization accounting (for your ruling)

The container executed the registered command once and was refused by preflight before
touching any row, the corpus DB, or `/out`. Whether this consumed the one-run
authorization, and whether the chain artifacts are revoked wholesale (as with the first
refusal) pending the corrected template/grammar, is your call — this report executes the
mandatory STOP either way.
