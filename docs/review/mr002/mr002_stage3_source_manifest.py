"""MR-002 Stage-3 — complete source manifest for the finalized cascade (review finding 6).

The execution package must byte-bind EVERY load-bearing dependency of the cascade, not only the three
new files. Naming the old modules as "source of truth" is insufficient: their exact Git blobs and
material configuration must be pinned, or the cascade can stay unchanged while its numerical behavior
changes underneath it.

This module:
  * declares the load-bearing SOURCE set (the numerical cascade path, the corpus-regeneration path, and
    the execution-package components) and their roles;
  * computes each file's Git blob SHA-1 (identical to `git hash-object`) AND SHA-256 AND byte length —
    pure Python, no Git subprocess, no solver stack, so it runs anywhere;
  * declares the material CONFIGURATION the numerical behavior depends on (registered acceptance LIMITS,
    signed-gap band, interval-width limit, the PIQP_P2 BASE settings, the cascade constants). These are
    governance-bound values; the preflight validator (`mr002_stage3_preflight.py`) ENFORCES them against
    the live imports inside the pinned image;
  * exposes `verify_source(manifest, root)` → list[defect], used by the preflight validator to prove the
    working tree matches the bound manifest and fail closed on any drift.

Generate:  python scripts/mr002_stage3_source_manifest.py  [--out PATH]
"""

from __future__ import annotations

import hashlib
import json
import os
import sys

VERSION = "1.0"
# cycle-5 finding 13: explicit manifest phase — finality is never inferred from a version number.
# PRE_EXECUTION_SOURCE permits governance artifacts to be declared absent; the FINAL closure is the
# EXTERNAL Phase-B execution-binding artifact (see population runner BINDING_RECORD_TYPE), which the
# countersignature binds. The Phase-A manifest is never regenerated inside the authorized container.
MANIFEST_PHASE = "PRE_EXECUTION_SOURCE"

# ── load-bearing source set ──────────────────────────────────────────────────────────────────────
# repo-root-relative paths. Grouped by role so a reviewer can see exactly what each file is for.
CASCADE_NUMERICAL_PATH = [
    "apps/backend/app/research/mr002/stage3_cascade.py",        # the finalized §7 cascade
    "apps/backend/scripts/mr002_coverage_signed_gap.py",       # SOLVERS, canonical_qualify, PRIMARY/FALLBACK
    "apps/backend/scripts/mr002_piqp.py",                      # PIQP_P2 solve + BASE settings
    "apps/backend/scripts/mr002_solver_intersection.py",       # QUADPROG_SQRT (solve_sqrt), LIMITS, corpus hash
    "apps/backend/scripts/mr002_characterize_native_qp.py",    # clarabel/highs (imported at module load)
    "apps/backend/app/research/mr002/certificate.py",          # the registered certifier
    "apps/backend/app/research/mr002/directed.py",             # correct directed rounding (certifier dep)
    "apps/backend/app/research/mr002/joint_portfolio.py",      # _qp_matrices, _acceptance, InvalidRun
    "apps/backend/app/research/mr002/repair.py",               # imported by coverage_signed_gap at load
]
CORPUS_REGENERATION_PATH = [
    "apps/backend/app/research/mr002/dataset.py",              # FrozenDataset (corpus regen only)
    "apps/backend/app/research/mr002/runner.py",               # CONFIGS (corpus regen only)
    "apps/backend/scripts/mr002_development_run.py",           # run_config (corpus regen only)
]
EXECUTION_PACKAGE_COMPONENTS = [
    "apps/backend/scripts/mr002_stage3_preflight.py",          # provenance/environment validator
    "apps/backend/scripts/mr002_stage3_population_runner.py",  # clean successor population runner
    "apps/backend/scripts/mr002_stage3_source_manifest.py",    # this generator
    "apps/backend/scripts/mr002_stage3_cascade_fixtures.py",   # in-image realism harness
    "apps/backend/tests/research/test_mr002_stage3_cascade_dispA.py",       # decision-table fixtures
    "apps/backend/tests/research/test_mr002_stage3_preflight.py",           # preflight tests
    "apps/backend/tests/research/test_mr002_stage3_population_runner.py",   # runner integration tests
    "apps/backend/tests/research/test_mr002_stage3_input_contract.py",      # _qp_matrices contract conformance
]
# Governance/execution artifacts that affect what is authorized/executed (finding 15). Bound here
# when present; a governance artifact cannot bind itself, and some do not exist until countersignature.
GOVERNANCE_ARTIFACTS = [
    "docs/implementation/evidence/mr_002/MR002_Stage3_QPMatrices_InputContract_v1.0.json",
    "docs/implementation/evidence/mr_002/MR002_Stage3_TestReport_v1.0.json",
    "docs/implementation/evidence/mr_002/MR002_Stage3_CascadeRealismHarness.json",
]
# Load-bearing artifacts produced only AT/BY the execution countersignature — declared, not yet bound.
PENDING_AT_COUNTERSIGNATURE = [
    "the execution-authorization artifact (bound commit/tree/image/manifest/pins)",
    "the countersigned expected-pins artifact (versions, fingerprints, material config)",
    "the in-image realism-harness PASS artifact at the pinned image",
    "the final regenerated MR002_Stage3_SourceManifest at the clean commit",
]

ROLE = {}
for p in CASCADE_NUMERICAL_PATH:
    ROLE[p] = "cascade_numerical_path"
for p in CORPUS_REGENERATION_PATH:
    ROLE[p] = "corpus_regeneration_path"
for p in EXECUTION_PACKAGE_COMPONENTS:
    ROLE[p] = "execution_package_component"
ALL_FILES = CASCADE_NUMERICAL_PATH + CORPUS_REGENERATION_PATH + EXECUTION_PACKAGE_COMPONENTS

# ── material configuration (governance-bound; preflight enforces against live imports) ────────────
DECLARED_CONFIG = {
    "registered_acceptance_LIMITS": {
        "primal_residual": 1e-9, "dual_residual": 1e-9, "stationarity_residual": 1e-8,
        "complementarity_residual": 1e-8, "kkt_residual": 1e-8,
    },
    "signed_gap_band": [-1e-10, 1e-10],
    "max_interval_width": 1e-30,
    "registered_corpus_hash": "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b",
    "cascade": {"primary": "QUADPROG_SQRT", "fallback": "PIQP_P2",
                "numerical_allowlist": [["QUADPROG_SQRT", "ValueError",
                                         "constraints are inconsistent, no solution"]]},
    "piqp_P2_BASE": {
        "preconditioner_scale_cost": True, "eps_abs": 1e-10, "eps_rel": 1e-11,
        "check_duality_gap": True, "eps_duality_gap_abs": 1e-11, "eps_duality_gap_rel": 1e-11,
        "max_iter": 1000, "preconditioner_reuse_on_update": False,
        "iterative_refinement_always_enabled": True, "iterative_refinement_eps_abs": 1e-13,
        "iterative_refinement_eps_rel": 1e-13, "iterative_refinement_max_iter": 20,
        "kkt_solver": "sparse_ldlt",
    },
    "certifier_precision_dps": 100,
}


def _repo_root() -> str:
    # apps/backend/scripts/this.py -> repo root is three levels up.
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def _git_blob_sha1(data: bytes) -> str:
    """The exact object name `git hash-object` would produce: sha1('blob <len>\\0<bytes>')."""
    h = hashlib.sha1()
    h.update(b"blob " + str(len(data)).encode() + b"\x00")
    h.update(data)
    return h.hexdigest()


def _hash_file(abspath: str) -> dict:
    with open(abspath, "rb") as fh:
        data = fh.read()
    return {"sha256": hashlib.sha256(data).hexdigest(),
            "git_blob": _git_blob_sha1(data),
            "byte_length": len(data),
            "present": True}


def build_manifest(root: str | None = None) -> dict:
    root = root or _repo_root()
    files = {}
    missing = []
    for rel in ALL_FILES:
        ap = os.path.join(root, rel)
        if not os.path.exists(ap):
            files[rel] = {"present": False, "role": ROLE[rel]}
            missing.append(rel)
            continue
        files[rel] = {"role": ROLE[rel], **_hash_file(ap)}
    governance = {}
    for rel in GOVERNANCE_ARTIFACTS:
        ap = os.path.join(root, rel)
        governance[rel] = _hash_file(ap) if os.path.exists(ap) else {"present": False}
    return {
        "record_type": "MR002_STAGE3_SOURCE_MANIFEST",
        "version": VERSION,
        "manifest_phase": MANIFEST_PHASE,
        "note": "Byte-binds the load-bearing SOURCE dependencies of the finalized cascade (finding 6): "
                "SHA-256 + Git blob + byte length per file. This does NOT bind every governance artifact "
                "affecting authorization/execution — those are listed under `governance_artifacts` "
                "(bound when present) and `pending_at_countersignature` (finding 15).",
        "excluded_by_design": {
            "exact_repair/exact_simplex": "NOT on the cascade path — they belong to the quarantined "
            "full-population repair evidence and are deliberately not imported by the successor cascade.",
        },
        "files": files,
        "files_missing": missing,
        "governance_artifacts": governance,
        "pending_at_countersignature": PENDING_AT_COUNTERSIGNATURE,
        "declared_config": DECLARED_CONFIG,
    }


def verify_source(manifest: dict, root: str | None = None) -> list[str]:
    """Recompute hashes from the working tree and return a list of defects (empty = OK). Fail-closed.

    Completeness (finding 14): every declared ALL_FILES entry must appear in the manifest, no
    unexpected manifest path may exist, the role must match, and byte_length + both hashes must match
    the on-disk bytes.
    """
    root = root or _repo_root()
    defects: list[str] = []
    files = manifest.get("files", {})

    # header + governance sections are verified too (cycle-3 finding 23)
    if manifest.get("record_type") != "MR002_STAGE3_SOURCE_MANIFEST":
        defects.append(f"MANIFEST_WRONG_RECORD_TYPE:{manifest.get('record_type')}")
    if manifest.get("version") != VERSION:
        defects.append(f"MANIFEST_VERSION_MISMATCH:{manifest.get('version')}!={VERSION}")
    if manifest.get("manifest_phase") != MANIFEST_PHASE:
        defects.append(f"MANIFEST_PHASE_MISMATCH:{manifest.get('manifest_phase')}")
    if manifest.get("files_missing"):
        defects.append(f"MANIFEST_DECLARES_MISSING_FILES:{manifest['files_missing']}")
    # cycle-4 finding 20: the manifest's own configuration declaration must equal the generator's
    if manifest.get("declared_config") != DECLARED_CONFIG:
        defects.append("DECLARED_CONFIG_MISMATCH")
    if manifest.get("pending_at_countersignature") != PENDING_AT_COUNTERSIGNATURE:
        defects.append("PENDING_LIST_MISMATCH")
    # cycle-4 finding 21: the governance key set is exact — no unexpected governance paths
    if set(manifest.get("governance_artifacts", {})) != set(GOVERNANCE_ARTIFACTS):
        defects.append("GOVERNANCE_KEY_SET_MISMATCH")
    # cycle-6 finding 6: the standalone contract JSON must be SEMANTICALLY equal to the embedded one
    cpath = os.path.join(root, "docs/implementation/evidence/mr_002/"
                               "MR002_Stage3_QPMatrices_InputContract_v1.0.json")
    if os.path.exists(cpath):
        try:
            from app.research.mr002.stage3_cascade import INPUT_CONTRACT
            with open(cpath, encoding="utf-8") as fh:
                if json.load(fh) != INPUT_CONTRACT:
                    defects.append("INPUT_CONTRACT_ARTIFACT_DRIFT")
        except Exception:  # noqa: BLE001
            defects.append("INPUT_CONTRACT_ARTIFACT_UNREADABLE")
    for rel, rec in manifest.get("governance_artifacts", {}).items():
        if not rec.get("present", False):
            continue                                 # declared-absent governance artifact: allowed
        ap = os.path.join(root, rel)
        if not os.path.exists(ap):
            defects.append(f"GOVERNANCE_MISSING_ON_DISK:{rel}")
        else:
            got = _hash_file(ap)
            # cycle-4 finding 21: sha256 AND git blob AND byte length for governance artifacts
            if got["sha256"] != rec.get("sha256"):
                defects.append(f"GOVERNANCE_SHA256_DRIFT:{rel}")
            if got["git_blob"] != rec.get("git_blob"):
                defects.append(f"GOVERNANCE_BLOB_DRIFT:{rel}")
            if got["byte_length"] != rec.get("byte_length"):
                defects.append(f"GOVERNANCE_LENGTH_DRIFT:{rel}")

    # completeness: manifest key set must exactly equal the declared load-bearing set
    for rel in ALL_FILES:
        if rel not in files:
            defects.append(f"MANIFEST_MISSING_DECLARED_FILE:{rel}")
    for rel in files:
        if rel not in ROLE:
            defects.append(f"MANIFEST_UNEXPECTED_FILE:{rel}")

    for rel, rec in files.items():
        if rel in ROLE and rec.get("role") != ROLE[rel]:
            defects.append(f"ROLE_MISMATCH:{rel}")
        ap = os.path.join(root, rel)
        if not rec.get("present", False):
            defects.append(f"MANIFEST_DECLARES_ABSENT:{rel}")
            continue
        if not os.path.exists(ap):
            defects.append(f"MISSING_ON_DISK:{rel}")
            continue
        got = _hash_file(ap)
        if got["sha256"] != rec.get("sha256"):
            defects.append(f"SHA256_DRIFT:{rel}")
        if got["git_blob"] != rec.get("git_blob"):
            defects.append(f"GIT_BLOB_DRIFT:{rel}")
        if got["byte_length"] != rec.get("byte_length"):
            defects.append(f"BYTE_LENGTH_DRIFT:{rel}")
    return defects


def main() -> int:
    out = None
    args = sys.argv[1:]
    if "--out" in args:
        out = args[args.index("--out") + 1]
    m = build_manifest()
    blob = json.dumps(m, indent=2, sort_keys=False)
    if out:
        with open(out, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(blob + "\n")
        print(f"wrote {out}")
    else:
        print(blob)
    if m["files_missing"]:
        print(f"\n⚠ {len(m['files_missing'])} declared file(s) not yet present: {m['files_missing']}",
              file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
