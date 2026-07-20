# MR-002 OQ-1 v1.1 submission — base-image immutability + self-contained offline build

**Status: resubmitted for review.** Narrow v1.1 correction of the two blocking operational-identity
defects; no evaluator/governance/refusal/fixture/boundary change. The accepted synthetic replay
(`increment3-v1.1-synthetic`, `42c5cee0…`) is unchanged and still reproduces byte-identically.

## Defect 1 — mutable base-image reference → digest-pinned + verified

- `Dockerfile.oq1` now pins the base by digest:
  `FROM python:3.13-slim@sha256:6771159cd4fa5d9bba1258caf0b82e6b73458c694d178ad97c5e925c2d0e1a91`
  (linux/amd64 manifest `sha256:afe18987…`).
- `container-build-identity.json` binds base repo, tag (informational), index digest, amd64 digest,
  `Dockerfile` SHA-256, and build-context commit. Preflight now refuses
  `REFUSED_ENVIRONMENT_IDENTITY:BASE_IMAGE_DIGEST` (proven: tampered build-identity → **exit 11, no
  session**) and `REFUSED_ENVIRONMENT_IDENTITY:CONTAINER_IMAGE_DIGEST` (proven: wrong
  `OQ1_EXPECTED_CONTAINER_DIGEST` → **exit 11, no session**).
- **Two independent `--no-cache` builds** — image IDs differ (`abbd9424…` vs `36def133…`, Docker build
  metadata; **not** called "the same image") — proven equivalent by projection: same pinned base
  digest, **identical installed distributions** (`md5 5f145965`), **identical application + governance
  bytes** (`sha256 9b494ac4`), and **evaluator output reproduced** (`42c5cee0`). Recorded in
  `MR002_OQ1_RebuildEquivalence.json`.

## Defect 2 — offline build inputs → immutable published wheelhouse bundle

- The 9 exact wheels are packaged as `wheelhouse-bundle.tar.gz` (sha256 `a40bbb8286d3e280…`, 64,235,470
  bytes) and **published as an immutable GitHub release asset** — tag `mr002-oq1-wheelhouse-v1`, asset
  id `483744510`, `https://github.com/jayw04/AI-TRADING-APP/releases/tag/mr002-oq1-wheelhouse-v1`.
  `wheelhouse-bundle-manifest.json` binds the archive sha/bytes, each wheel filename + sha256, ABI
  (cp313), platform tags, and the release location/object id. The OQ-1 manifest binds that bundle. The
  repo continues to ignore `.whl` and the 64 MB tar (both on the release).
- **Self-contained offline build proven**: downloaded the release asset → sha matches the manifest →
  reconstructed the wheelhouse **from the bundle** → built the image offline (`--no-index`,
  `--require-hashes`, digest-pinned base; no PyPI, no resolution, no host cache) → **OQ1_PASS, accepted
  hash reproduced**.

## Requalification evidence (owner checklist)

| item | status |
|---|---|
| digest-pinned Dockerfile | ✔ `FROM …@sha256:6771159c` |
| immutable wheelhouse bundle identity | ✔ release asset `483744510`, sha `a40bbb82…` |
| fresh offline build from empty cache | ✔ built from bundle, `--no-index`, OQ1_PASS |
| second independent offline build | ✔ two `--no-cache` builds |
| base/rootfs equivalence | ✔ same pinned base digest; projection (metadata excluded) |
| installed-package equivalence | ✔ `md5 5f145965` identical |
| accepted replay hash reproduced | ✔ `42c5cee0…` in every build |
| 128 evaluator tests passed | ✔ in-container (read-only, network none, non-root) |
| OQ-1 tests passed | ✔ 24 in-process, ruff clean |
| ruff clean | ✔ in-process and in-container |
| network disabled | ✔ `--network none`; network-reachable → exit 12 |
| working tree clean | ✔ |

## Evidence-count clarification

Canonical OQ-1 artifact count is now **19** (self-hashed `MR002_OQ1_Manifest.json`) after adding the
v1.1 artifacts (rebuild-equivalence, bundle manifest, build identity). The earlier "12 vs 16": the
v1.0 manifest bound **16** (12 evidence JSONs + the 4 oq1-root lock/recipe files); the "12" in the
prose was only the `evidence/` JSONs. The manifest self-hash enumerates every file.

## Boundary

No evaluator/governance/refusal/fixture change. No validation/OOS/real-data/broker/DB/EC2/ECS/live
execution; no performance interpretation or research-gate; the run-5 archive is untouched (the release
bundle is a new dedicated artifact, not the run-5 archive). S3 remains a dry-run adapter only.
