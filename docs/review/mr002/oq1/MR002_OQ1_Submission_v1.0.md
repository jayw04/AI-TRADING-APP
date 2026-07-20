# MR-002 Workstream B — Operational Qualification Increment OQ-1 (submission v1.0)

**Status: submitted for review.** Proves the accepted Increment-1..3 synthetic evaluator can be
**built, executed, refused, reproduced, and published** under controlled operational conditions
**without any sealed-data access**. OQ-1 runs no development/validation/OOS performance; it qualifies
the operational envelope only. The governing synthetic replay is unchanged — schema
`increment3-v1.1-synthetic`, accepted `output_hash 42c5cee0…`.

## Headline result

**The accepted Windows-generated hash `42c5cee0fc121f1fabf9ff1916a02cc8bd922ce69b8f80d85be7852dc5fde907`
reproduces byte-identically inside a Linux container** — network-disabled, read-only code, non-root
(uid 10001), offline dependency install — across two runs and an independent `--no-cache` rebuild. The
economic payload is isolated from operational provenance (the container digest differs on rebuild; the
economic-payload hash does not). This retires the cross-platform reproducibility risk.

## Components (in `docs/review/mr002/oq1/`)

1. **Dependency lock** — `requirements.lock` (pip `--require-hashes`, no floating ranges),
   `wheelhouse-manifest.json` (9 wheels, exact filenames + SHA-256), `dependency-resolution-report.json`.
   Offline install via `--no-index --find-links`. `oq1_environment.py` fails closed
   `REFUSED_ENVIRONMENT_IDENTITY` on version/missing/python drift. (The 62 MB wheelhouse is regenerable
   from the pinned hashes and is not stored in git.)
2. **Container** — `Dockerfile.oq1`: `python:3.13-slim`, offline `--require-hashes` install, non-root,
   read-only code, network-disabled entrypoint, fixed locale/TZ, explicit entrypoint. Manifests:
   `container-build-manifest.json` (image id, base, dep-lock, schema, governance ids),
   `container-runtime-policy.json`.
3. **Preflight** — `oq1_preflight.py` verifies governance identities (registry `edb7ff22`, resolution
   `860c8cde`, prereg/ledger/census), pinned evaluator file hashes, environment lock, python, container
   digest, output-dir policy, network-disabled, and sealed-path denial **before any pipeline import**;
   `PREFLIGHT_PASS/REFUSED/INTEGRITY_STOP`. A failed preflight runs **no** portfolio session.
4. **Sealed-access boundary** — `oq1_sealed_access.py`: deny-by-default; guards for direct open, path
   traversal, symlink escape, credential env discovery, AWS shared-credentials paths, forbidden
   adapter/subprocess imports, and network reachability → all `REFUSED_SEALED_ACCESS`. The run-5
   archive is never read/copied/modified.
5. **Refusal + exit-code contract** — `oq1_exit_codes.py`: frozen taxonomy (0 pass; 10 identity; 11
   environment; 12 sealed-access; 13 integrity; 14 determinism; 15 publication; 16 unsupported; 20
   internal) + canonical, deterministic refusal record with no secrets/host paths (basenames only).
6. **Deterministic run** — `oq1_determinism.py` reproduces the accepted report in-memory (read-only-code
   safe), proves byte-determinism, and defines the economic-payload comparison projection.
7. **Publication** — `oq1_publish.py`: immutable local bundle with a self-hashed manifest (every
   artifact: path/bytes/sha256/content-type/producer/governing-role); overwrite and partial-completion
   fail closed. **S3 dry-run adapter** enforces versioning/object-lock/SSE, refuses the run-5 archive as
   a destination, and uses no credentials/network.
8. **Entrypoint** — `oq1_qualify.py`: preflight → (only if PASS) run + determinism → qualification
   report → exit code. Container run: `OQ1_PASS`, exit 0.

## Qualification (35 cases; `MR002_OQ1_QualificationMatrix.json`)

- **In-process** (`test_oq1.py`, 21 tests, ruff clean): environment identity (01-06), sealed-access
  (13-18, 20), refusal contract (21-23), determinism/exact-float (25/27/29), publication (31-35).
- **Container** (`docker run`, recorded in the evidence bundle): expected digest (07), altered
  evaluator file → **exit 10, no session** (08/24), altered governance (09), non-root uid 10001 (10),
  read-only code (11), network-disabled run succeeds (12), network-reachable → **exit 12** (19),
  two-run byte-identical (25), independent rebuild equivalent (26), accepted hash reproduced (27),
  economic payload unchanged across packaging (28), **full evaluator suite 128 passed in container**
  (30), in-container ruff clean.

## Evidence bundle (`oq1/evidence/`, self-hashed `MR002_OQ1_Manifest.json`)

Qualification, Preflight, SealedAccess, Refusal, Determinism reports; container build manifest +
runtime policy; qualification matrix; container suite + ruff + test logs. The qualification report
asserts: `validation_authorization=false`, `validation_data_read=false`, `oos_data_read=false`,
`development_performance_computed=false`, `real_data_accessed=false`, `synthetic_fixture_only=true`,
`performance_interpretation_authorized=false`, `production_promotion_authorized=false`.

## Boundary

No development/validation/OOS access; no real residual/z/sigma; no broker/DB/vendor connectivity; no
EC2/ECS/scheduled/live execution; no performance evaluation or research-gate adjudication; the run-5
archive is untouched. Actual AWS publication is a dry-run adapter only (real publication would require
explicit destination authorization; it does not authorize EC2 or sealed-data access).
