# MR-002 Stage-3 — Registered-Execution STOP Report v3.0: Orchestrator Output-Root Refusal (Run 3)

- **Date:** 2026-07-19 (launch 02:05:16.650Z)
- **Disposition:** **STOPPED per the v3 countersignature stop conditions.** The registered
  container ran; the ENTIRE governance chain and — for the first time in a registered
  launch — the FULL in-container preflight PASSED; the run was then refused by the
  orchestrator's fail-closed output-root control before any corpus or row work.
  No patch, retry, resume, or bypass. **Zero rows; corpus never accessed
  (`corpus_hash: null`); `/out` untouched (0 entries before and after);
  validation/OOS SEALED AND UNREAD.**

## Required post-run evidence (refusal outcome)

| Item | Value |
|---|---|
| Launcher stdout/stderr | `MR002_Exec3_Refusal_20260719.log` — sha256 `2cc09c4dd4839ae9e2a9135a1f8bacd7564d321e145e45f8543f2e5e6cdae77b`, 2,757 B (launched with `python3.11 -u`, so ordering is natural this time: argv print first, container output after) |
| Exact executed argv | in the log: the attested 47-token v3 template + the derived field |
| Derived binding token | `MR002_EXECUTION_BINDING_SHA256=cb067a3a…` — present exactly once (grep count 1) |
| Container / image | `ac591e2e05e79dc1d8e1a9da189c3fc2a01c7b6016586ea4471b1ef60533ebf5` (auto-removed by the attested `--rm`), image `sha256:81e8d7a7…` (docker events authoritative) |
| Runner stdout | `{"disposition": "REFUSED", "detail": "OUTPUT_ROOT:OUT_DIR_MISSING", "corpus_hash": null, "run_manifest": null}` |
| Preflight result | **PASSED** — no preflight refusal line; the governance-chain loaders (authorization, pins, manifest, package, Phase B, attestation, realism, report, receipt, cross-validation) and the full `evaluate` all cleared, exactly as the committed smoke evidence predicted for this configuration |
| Start / end | container create `02:05:16.881Z`, die `02:05:18.161Z` (~1.28 s — consistent with the smoke-measured full-preflight cost), exitCode **2** |
| Rows attempted / completed | **0 / 0** |
| Output inventory before / after | `/out`: 0 entries / 0 entries |
| Output hashes / row-manifest hash | none produced |
| Failure/refusal inventory | the single orchestrator refusal above; nothing else |
| Host-state recheck | `docker ps -a` empty; `/out` empty; all 9 staged input hashes unchanged; zero symlinks; numrepo `d26bd9e…`/`c0e52d8e…`; launcher `b6e5d27…`; image digest exact; key 0600 |
| Validation / OOS | SEALED AND UNREAD (the refusal precedes all data access) |

## Root cause — a host-staging gap; the runner and the entire v3 chain are correct

The registered output-root control (`_output_root_defect`, cycle-4 finding 18, frozen
code) requires the output directory — the runner's default **`/out/cleanrun`**, since
`MR002_OUT` is deliberately grammar-refused — to **already exist**, be a real directory
(not a symlink), and be **empty**. The runner never creates it: fail-closed by design, so
output placement is always intentional.

Every launch checklist to date required "**/out empty**" — which we satisfied literally:
the mounted `/out` contained nothing, including no `cleanrun` subdirectory. The gate
therefore refused with `OUT_DIR_MISSING`. This is the first stop with **no code, template,
grammar, or chain defect**: the v3 attested command, launcher, and runner all behaved
exactly as designed. The gap is one `mkdir` of launch staging that no procedure ever
ordered.

## Remediation (OWNER DECISION — nothing executed)

- **Operational only:** create the empty directory `/home/ec2-user/mr002/out/cleanrun`
  (owner `ec2-user`, non-symlink, empty) as a sanctioned pre-launch staging step, and
  amend the checklist item from "/out empty" to "**/out contains exactly one empty
  `cleanrun` directory** (and nothing else)". No launcher, template, grammar, runner, or
  binding change is required or proposed — the attested v3 template is agnostic to the
  subdirectory (it mounts `/out`; the registered default path binds inside it).
- Whether the v3 single-run countersignature is consumed (the container ran the registered
  command and executed the registered preflight, as in the v2 precedent) and a v4 chain
  (new nonce; otherwise byte-identical template) is required, is your ruling. If a v4
  chain is ordered it needs NO code or review delta — produce/verify/bind under the
  committed launcher at `b6e5d27` with the corrected host staging.

## Gate-progression record (for perspective)

Run 1: refused at the Docker CLI flag parser (bare `rw`). Run 2: refused at the
in-container preflight (identity channels + `/work` tree). Run 3: governance chain +
preflight PASSED; refused at the orchestrator output-root gate. Each stop has moved one
gate deeper with zero rows ever touched; the remaining gates after output-root are the
corpus regeneration hash equality (historically reproduced on c6a hardware twice), the
3,895-row identity manifest, and the resolution loop itself.
