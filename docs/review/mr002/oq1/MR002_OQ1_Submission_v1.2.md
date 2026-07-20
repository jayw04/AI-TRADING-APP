# MR-002 OQ-1 v1.2 — build-context provenance correction (evidence-only)

**Status: resubmitted for review.** Narrow provenance-evidence correction of `container-build-identity.json`.
**No evaluator, governance, refusal, fixture, or boundary code changed** (128 evaluator tests still
pass; 24 OQ-1 tests still pass; ruff clean). No container rebuild — the SHA-256 identities were
computed from the existing images/logs and bound.

## Corrections

1. **Stale parent commit → v1.1 build commit.** `build_context_identity` now binds
   `source_commit = 1e3db0a00903f2ca692644caa6199164e4836f5f`, `source_tree = 66c86234…` (was the
   parent `125941d`, a chicken-and-egg from generating the file pre-commit), plus `Dockerfile` SHA-256,
   `requirements.lock` SHA-256, `wheelhouse-bundle-manifest` SHA-256, and the separate
   `governance_input_aggregate_sha256` (`1a998bfc…`) and `evaluator_code_aggregate_sha256` (`020d39b5…`).
2. **`resulting_image_digest = "n/a"` → concrete `resulting_images[]`.** Records both legitimately
   distinct image digests with per-image `runtime_preflight_verified` (each build re-verified against
   its own expected digest → OQ1_PASS):
   `A sha256:abbd9424…`, `B sha256:36def133…`. The misleading single-digest field is removed.
3. **Governing installed-distribution fingerprint is now SHA-256.**
   `installed_distributions_sha256 = a4953ba56d1073ebc8df44d634ba6dbd834110fbde30b2f7c6cf170fe470dd14`
   (identical across both builds); the MD5 `5f145965…` is retained as informational only. Also bound in
   `canonical_rebuild_equivalence_identity` alongside `application_governance_bytes_sha256`
   (`9b494ac4…`) and `accepted_evaluator_output_hash` (`42c5cee0…`).

## Verification

| item | result |
|---|---|
| build context binds commit `1e3db0a` | ✔ |
| build context binds tree `66c86234` | ✔ |
| both concrete image digests recorded | ✔ (A/B) |
| each run verifies its own expected image digest | ✔ (OQ1_PASS both) |
| equivalence projection uses SHA-256 identities | ✔ |
| wheelhouse asset id `483744510` + archive hash `a40bbb82…` unchanged | ✔ |
| accepted replay hash `42c5cee0…` | ✔ unchanged |
| 128 evaluator tests | ✔ (unchanged; container run recorded) |
| 24 OQ-1 tests | ✔ |
| ruff clean | ✔ |
| no evaluator or boundary code change | ✔ |

Regenerated (identity-affected only): `container-build-identity.json`,
`MR002_OQ1_RebuildEquivalence.json`, `MR002_OQ1_Qualification.json`/`Preflight.json` (re-captured with
the corrected build-identity), test log, and the self-hashed `MR002_OQ1_Manifest.json` (19 artifacts).
Validation/OOS sealed; real-data / performance / EC2 / production remain unauthorized; run-5 untouched.
