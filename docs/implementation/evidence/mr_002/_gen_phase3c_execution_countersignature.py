"""MR-002 Phase 3C — the narrow EXECUTION COUNTERSIGNATURE.

Binds the finalized implementation, the composition, the fixtures and manifest, the applicable
form of the regenerated-population protocol, and the clean-run stop gates with an explicit
applicability mapping.

It does NOT authorize execution. Authority arrives later, through a separately sealed
authorization record, and only after both authority artifacts reproduce from pushed Git.

Every identity is taken from GIT BLOBS.
"""
from __future__ import annotations

import hashlib
import json
import os
import subprocess

_HERE = os.path.dirname(os.path.abspath(__file__))
REPO = os.path.abspath(os.path.join(_HERE, "..", "..", "..", ".."))
REV = "HEAD"
HOST = "i-00c1034f7026db45e"
STAGE3_CORPUS = "1d2319301a7b52dfe369819bc8029f7b6d64ad820d828f041eba15a91348390b"


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed: {path}")
    return hashlib.sha256(out.stdout).hexdigest()



def bound(path: str) -> dict:
    """Bind BOTH identities with typed names: the Git blob AND the record's self-identity.

    A single unlabelled "sha256" is ambiguous -- the file blob and the record_identity_sha256 are
    different values, and conflating them is the same defect class as a generic image_id.
    """
    out = {"path": path, "file_blob_sha256": blob_sha(path)}
    try:
        with open(os.path.join(REPO, path), "rb") as fh:
            doc = json.loads(fh.read())
        if isinstance(doc, dict) and "record_identity_sha256" in doc:
            out["record_identity_sha256"] = doc["record_identity_sha256"]
    except Exception:
        pass
    return out


E = "docs/implementation/evidence/mr_002/"
PKG = E + "MR002_Phase3C_ValidationExecutionPackage_v2.0.json"
CUSTODY = E + "MR002_Phase3C_RuntimeCompositionCustodyEvidence_v1.0.json"
MANIFEST = E + "MR002_Stage3_SourceManifest_v1.0.json"
ELIGIBILITY = E + "MR002_Stage3EligibilityStatusMapping_v1.0.json"
STAGE3_PKG = E + "MR002_Stage3_ExecutionPackage_v2.1.json"
CASCADE = "apps/backend/app/research/mr002/stage3_cascade.py"
SEAM = "apps/backend/app/research/mr002/stage3_route.py"
MATERIALIZER = "apps/backend/app/research/mr002/phase3c/materialize.py"
READER = "apps/backend/app/research/mr002/phase3b/readers.py"
FIXTURES = [
    "apps/backend/scripts/mr002_stage3_cascade_fixtures.py",
    "apps/backend/tests/research/test_mr002_stage3_cascade.py",
    "apps/backend/tests/research/test_mr002_stage3_cascade_dispA.py",
    "apps/backend/tests/research/test_mr002_stage3_input_contract.py",
]
PHASE3C = [
    "apps/backend/app/research/mr002/phase3c/__init__.py",
    "apps/backend/app/research/mr002/phase3c/adopted.py",
    "apps/backend/app/research/mr002/phase3c/exits.py",
    "apps/backend/app/research/mr002/phase3c/folds.py",
    "apps/backend/app/research/mr002/phase3c/gates.py",
    "apps/backend/app/research/mr002/phase3c/materialize.py",
    "apps/backend/app/research/mr002/phase3c/replay.py",
]

_h = hashlib.sha256()
for p in sorted(PHASE3C):
    _h.update(f"{p}:{blob_sha(p)}\n".encode("ascii"))
PHASE3C_IDENTITY = _h.hexdigest()

CS = {
    "record_type": "MR002_PHASE3C_EXECUTION_COUNTERSIGNATURE",
    "countersignature_id": "MR002_Phase3C_ExecutionCountersignature_v1.0",
    "version": "1.0",
    "produced_at": "2026-08-18T00:00:00Z",
    "status": "DRAFT — awaiting the owner's seal",
    "grants": (
        "NOTHING. This countersignature binds WHAT would execute. Authority to execute arrives "
        "only through a separately sealed authorization record, after both authority artifacts "
        "reproduce from pushed Git."
    ),
    "execution_authorized": False,

    "binds": {
        "validation_execution_package": bound(PKG),
        "pushed_source_checkpoint": "c803613331c34e7504fe93bf453c5152a8433456",
        "phase3c_identity": PHASE3C_IDENTITY,
        "phase3c_modules": {p: blob_sha(p) for p in PHASE3C},
        "finalized_implementation": {
            "stage3_cascade": {"path": CASCADE, "file_blob_sha256": blob_sha(CASCADE)},
            "stage3_routing_seam": {"path": SEAM, "file_blob_sha256": blob_sha(SEAM)},
            "materializer": {"path": MATERIALIZER, "file_blob_sha256": blob_sha(MATERIALIZER)},
            "governed_pinned_reader": {"path": READER, "file_blob_sha256": blob_sha(READER)},
        },
        "runtime_identity": {
            "source_oci_index_digest":
                "sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a",
            "image_config_digest":
                "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6",
            "rootfs_diffid_sequence_digest":
                "c16e7c09fba1fd33a3dc743caff8b8942b43252be3999ffc40e3a616d6a1507e",
            "platform": "amd64/linux",
            "export_archive_sha256":
                "95076c14b32bee01a54e2d49a9a42bea47ef9c73ffb5c0a998c7a10d174c346e",
            "export_archive_bytes": 142534656,
            "note": "three typed identities; never a generic image_id whose meaning depends on "
                    "the daemon",
        },
        "dependency_bundle": {
            "version": "v1.2",
            "inventory_digest":
                "cbf588cb482edd96847f2f5016dbb6dfe03f5e435c921d620c0031e97ea92919",
            "files": 2954,
            "supersedes_inventory_digest":
                "d3a323ca04eda5937724ba86e8dedbbd8b955cbd87cac97b51d06f985909f807",
            "additive_only": True,
            "host_path": "/opt/mr002/deps_v12",
            "mount": "/opt/mr002/deps (read-only)",
        },
        "authorized_host": HOST,
        "frozen_runtime_environment": {
            "OMP_NUM_THREADS": "1", "OPENBLAS_NUM_THREADS": "1", "MKL_NUM_THREADS": "1",
            "NUMEXPR_NUM_THREADS": "1", "OPENBLAS_CORETYPE": "HASWELL",
            "PYTHONPATH": "/work/apps/backend:/opt/mr002/deps",
            "network": "none",
        },
        "source_manifest": bound(MANIFEST),
        "eligibility_status_mapping": bound(ELIGIBILITY),
        "eligibility_fixtures": {p: blob_sha(p) for p in FIXTURES},
        "stage3_execution_package": bound(STAGE3_PKG),
        "stage3_countersignature_id": "MR002_Stage3ExecutionCountersignature_v1.0",
        "composition_custody_evidence": bound(CUSTODY),
    },

    # ---- regenerated-population protocol, with an EXPLICIT applicability mapping -------------
    "regenerated_population_protocol": {
        "applicable_form_BINDING": [
            "fresh checkout at the countersigned implementation commit",
            "freshly regenerated source manifest",
            "fresh runtime binding recorded",
            "no reuse of any quarantined artifact, checkpoint, record, certificate, aggregate or "
            "row disposition",
        ],
        "satisfied_by": {
            "fresh_checkout": "clean worktree materialized at 8e8f078; package chain now at "
                              "c8036133",
            "fresh_source_manifest": "regenerated on Linux from the clean worktree -> 9798302a...",
            "fresh_runtime_binding": "image transferred under custody and bound by three typed "
                                     "identities; dependency bundle v1.2 inventory cbf588cb...",
            "no_quarantined_reuse": "no artifact from any prior Stage-3 quarantine is referenced "
                                    "or consumed by this package chain",
        },
        "NOT_APPLICABLE": [
            {
                "clause_verbatim": (
                    "the complete corpus and all overlap/coverage manifests regenerated anew and "
                    f"re-verified against the registered corpus hash {STAGE3_CORPUS}"
                ),
                "disposition": "NOT APPLICABLE to Phase 3C validation",
                "scope_reason": (
                    "this clause is Stage-3 POPULATION scoped. The corpus hash it names is the "
                    "Stage-3 QP-instance characterization corpus, which is not the Phase 3C "
                    "validation population. Requiring it here would bind the validation replay to "
                    "a corpus identity that is not actually its population."
                ),
                "retained_not_deleted": (
                    "carried verbatim so a later reader cannot mistake this for an accidental "
                    "omission"
                ),
            },
        ],
        "phase3c_population_integrity_is_governed_instead_by": [
            "the 6 sealed validation objects + 4 identity-bound reference objects (the 6+4 "
            "contract)",
            "the ValidationOpenedObjectLedger",
            "the logical-content identity over the read-ordered opened objects",
            "the eligibility/status mapping already bound in Stage-3 package v2.1",
        ],
    },

    # ---- clean-run stop gates, with an EXPLICIT applicability mapping ------------------------
    "clean_run_stop_gates": {
        "instance_level_BINDING": {
            "closed_enum": ["QUALIFIED", "NUMERICAL_STATUS_NONQUALIFICATION",
                            "CERTIFICATE_NONQUALIFICATION", "INTEGRITY_DEFECT"],
            "default_for_unrecognized": "INTEGRITY_DEFECT — never fallback-eligible, never by "
                                        "analogy",
            "terminal_dispositions": {
                "PRIMARY_QUALIFIED": "accept primary; fallback NOT invoked; continue",
                "FALLBACK_QUALIFIED": "eligible primary nonqualification; fallback qualifies; "
                                      "accept; continue",
                "UNRESOLVED_NUMERICAL_FAILURE": "STOP",
                "INVALID_RUN": "STOP; on a PRIMARY integrity defect the fallback is never invoked",
            },
            "enforced_in_code": "stage3_route raises Stage3Stop on either stop disposition",
        },
        "population_level_APPLICABLE_BINDING": [
            "source mismatch",
            "any INVALID_RUN",
            "any UNRESOLVED_NUMERICAL_FAILURE",
            "any outcome outside the total decision table",
        ],
        "population_level_NOT_APPLICABLE": [
            {
                "clause_verbatim": "corpus-hash mismatch",
                "disposition": "NOT APPLICABLE to Phase 3C validation",
                "scope_reason": f"refers to the Stage-3 population corpus hash {STAGE3_CORPUS}, "
                                "not the validation partition",
                "retained_not_deleted": True,
            },
            {
                "clause_verbatim": "an unexpected Phase-I-positive result",
                "disposition": "NOT APPLICABLE to Phase 3C validation",
                "scope_reason": "a Stage-3 population-workstream condition with no referent in a "
                                "validation replay",
                "retained_not_deleted": True,
            },
        ],
        "on_stop": "preserve evidence, restore containment, stop; no automatic replacement opening",
    },

    "phase3c_validation_stop_conditions": [
        "sealed object VersionId or hash mismatch",
        "missing or additional sealed/reference object",
        "schema mismatch or required-column absence",
        "true first-match registry overlap (crosswalk / security_sector_overrides / sic_mapping)",
        "logical-content identity failure",
        "DuckDB materialization failure",
        "Phase 3C cannot consume the materialized store",
        "unexpected sealed or OOS access",
        "any accounting or replay integrity failure",
    ],

    "no_sealed_byte_before_the_latch_opens": {
        "rule": (
            "no sealed validation or OOS byte may be read before the authorization latch is "
            "opened, and none has been"
        ),
        "enforced_in_code": (
            "stage3_route.routed() refuses to install without the Stage-3 countersignature "
            "identity; the S3PinnedReader is constructed only by the governed run and does no "
            "client work at construction"
        ),
        "current_latch_state": "canonical 44f5549a... / host->reader explicitDeny / 8 statements",
        "reader_behaviour_proven_without_aws": (
            "a fake client was injected in the composed runtime: reads a pinned object, passes "
            "VersionId, refuses a bad checksum, refuses an unpinned read"
        ),
    },

    "authorization_sequence_required_before_any_latch_release": [
        "1. this countersignature sealed, committed and PUSHED",
        "2. its identities re-derived from PUSHED Git",
        "3. a SEPARATE authorization record moving execution_authorized false -> true "
        "(v2.0 is NOT rewritten)",
        "4. that record committed, pushed and re-derived from pushed Git",
        "5. full pre-release preflight re-verified immediately before release",
        "6. only then release the latch and run exactly the bound execution",
    ],

    "unchanged_by_this_countersignature": [
        "the 6+4 input contract",
        "Phase 3C semantics",
        "Stage-3 cascade semantics (QUADPROG_SQRT -> PIQP_P2, fallback at most once)",
        "costs, borrow, exits, folds, construction and reduction semantics",
        "the two validation gates and the verdict domain",
    ],
}

CS["record_identity_sha256"] = hashlib.sha256(_canonical(CS)).hexdigest()
out = os.path.join(_HERE, "MR002_Phase3C_ExecutionCountersignature_v1.0_DRAFT.json")
with open(out, "wb") as fh:
    fh.write(_canonical(CS))
print(json.dumps({
    "countersignature_draft": CS["record_identity_sha256"],
    "binds_package_record_identity": CS["binds"]["validation_execution_package"].get("record_identity_sha256"),
    "binds_package_file_blob": CS["binds"]["validation_execution_package"]["file_blob_sha256"],
    "phase3c_identity": PHASE3C_IDENTITY,
    "execution_authorized": CS["execution_authorized"],
}, indent=1))
