# MR-002 Stage-3 — Registered-Execution STOP Report: Launch Refused at the Docker CLI Boundary (v1.0)

- **Date:** 2026-07-19 (00:13:38Z launch attempt)
- **Disposition:** **STOPPED per the countersignature terms.** The launch refused before any
  container was created. No patch, retry, resume, or bypass was attempted. **Zero rows
  touched; `/out` empty; no container has ever existed on the host; validation/OOS remain
  SEALED AND UNREAD.**

## What happened

The governance commit was completed (`31bfedd`, tree `4f9d3445…`, parent `b650018` — binding
blob `968eb3b7…` and submission blob `2564ac89…` byte-equal to the countersigned identities),
the corpus database was staged (disclosed below), the full pre-launch recheck passed
(image `81e8d7a7…`; checkout `595b9c1` porcelain-clean INCLUDING after DB staging; launcher
hashes; key 0600; inputs `dr-xr-xr-x` with the staged binding exactly `efbd290c…`,
attestation `f845cbbd…`, receipt `e3a202b6…`; zero symlinks; `/out` empty), and the
committed launcher was invoked with python3.11:

    exec --attestation /home/ec2-user/mr002/inputs/launch_attestation.json
         --receipt     /home/ec2-user/mr002/inputs/launch_verification_receipt.json
         --binding     /home/ec2-user/mr002/inputs/execution_binding.json

**Every launcher gate passed**: frozen loaders (attestation, receipt, binding), template
grammar re-validation, governed-input re-hash, binding cross-validation, mounted-binding
byte proof, and the single derived-field injection
(`MR002_EXECUTION_BINDING_SHA256=efbd290c…`, exactly once, before the image token — the
executed argv is printed in full in the log). The launcher then spawned the executed argv,
and **the Docker CLI refused it at flag parsing**:

    invalid argument "type=bind,src=/home/ec2-user/mr002/out,dst=/out,rw" for "--mount" flag:
    invalid field 'rw' must be a key=value pair

Docker exits at the parser — before contacting the daemon, before image resolution, before
container creation. `docker ps -a` was and remains empty.

- **Log:** `MR002_Exec_Refusal_20260719.log` — sha256
  `b036244eb515926768f5d16ba2246e954677291ef7ca278c2ea37f57ac832742`, 2,581 B (docker's
  stderr + the full executed argv). The launcher's process exit code was not captured by
  the nohup wrapper (disclosed); the log content is authoritative, and the refusal is
  deterministically reproducible (probe 1 below reproduces it byte-for-byte).

## Root cause

**The accepted closed grammar's explicit-`rw` requirement is not expressible in Docker's
`--mount` syntax.** Docker accepts `ro`/`readonly` as bare flags but has NO bare `rw`
token — read-write is the default, expressed by omission or by `ro=false`/`readonly=false`.
The blocker-2 requirement ("read-write mode explicitly present") was implemented — and
reviewed through v1.0→v1.4 — as a literal `rw` element in the mount spec, which OUR parser
requires (`OUTPUT_MOUNT_NOT_EXPLICITLY_RW` otherwise) but the real CLI rejects.

Why the 79-test suite did not catch it: every exec-path test monkeypatches
`subprocess.run` (correctly, to prove no spawn on refusal) — no test ever handed the argv
to a real Docker CLI. The incompatibility could only surface at the genuine launch
boundary. The nine read-only mounts (`ro` bare) are NOT affected — only the `/out` spec's
`rw` token.

## Diagnostic probes (disclosed; parse-layer only, nothing created)

Four `docker run` probes against the deliberately unresolvable image
`inval.invalid/none:none` — CLI parse acceptance moves the error PAST the flag parser to
the daemon's image lookup, which fails on DNS; no container is created either way
(`docker ps -a` verified empty after):

| /out mount spec ending | Result |
|---|---|
| `…,dst=/out,rw` | **CLI parse REFUSED** (reproduces the launch refusal exactly) |
| `…,dst=/out,ro=false` | parses (fails later at image lookup) |
| `…,dst=/out,readonly=false` | parses (fails later at image lookup) |
| `…,dst=/out` (no mode token) | parses (Docker default = read-write) |

## Host state (preserved, untouched)

Qualified state intact: staging read-only, zero symlinks, `/out` empty (0 entries), all
nine `/inputs` hashes unchanged, checkout clean, image at the pinned digest. One disclosed
pre-launch staging action: the registered corpus database
`apps/backend/data/mr002_research.duckdb` (gitignored; not part of any commit) was staged
into the read-only checkout — md5 `92a985c1663b8e72c5bee8a3f394d591` (the historically
verified corpus-DB identity), sha256
`24e5153cc0ebed77c7b422562e5a8ebfa147aad3019b27035b5314aaaacfad5a`, 132,395,008 B; the
checkout porcelain remains EMPTY; its decisive integrity gate is in-container corpus-hash
regeneration against the countersigned pins (`1d231930…`), which was never reached.

## Remediation options (OWNER DECISION — nothing executed)

Any fix touches the committed launcher and therefore requires: delta review → commit →
**new attestation → new receipt → new Phase-B binding → new execution countersignature**
(the current attestation `f845cbbd…` signs the defective template and cannot launch).

- **Option A (recommended):** express explicit-rw in Docker-valid syntax — grammar accepts
  the `/out` mount's mode as exactly `ro=false` (an explicit, parseable read-write
  declaration; probes verified) and the template uses it. Keeps the "explicitly present"
  property with a real token; minimal delta to `_parse_mount_spec`/out-mount check + template.
- **Option B:** the `/out` spec carries no mode token (Docker default rw); the grammar's
  explicitness requirement becomes "no `ro` on `/out`" — weakens the blocker-2 explicitness
  property; not preferred.
- Either way, one new test class is owed: a REAL-CLI parse check of the canonical template
  (e.g., against an unresolvable image, as in the probes) so grammar↔Docker compatibility
  is exercised without running anything.

## Authorization accounting (for your ruling)

The countersigned single-run authorization was **not consumed in substance**: no container
was created, no image was resolved, no input was read by any run process, `/out` was never
written. Whether the authorization instrument survives for a corrected chain, or a fresh
countersignature is issued with the corrected artifacts, is your call — this report
executes the mandatory STOP either way.
