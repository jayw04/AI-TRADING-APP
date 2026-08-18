"""MR-002 — the CUSTODY-COMPLETE Phase 3C validation execution package (v2.0).

Supersedes v1.0 (6ba49fbe...), which bound the right components but not the COMPOSITION. It named
a runtime by a store-dependent identifier, did not assert that runtime's presence on the authorized
host, and inherited a dependency bundle that only closed against a different image.

v2.0 binds the composition itself and adds the invariant that closes that defect class:
a runtime is not validation-executable merely because its digest is known.

Every code identity is taken from GIT BLOBS.
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


def _canonical(obj: dict) -> bytes:
    return (json.dumps(obj, sort_keys=True, indent=1, ensure_ascii=True) + "\n").encode("ascii")


def blob_sha(path: str) -> str:
    out = subprocess.run(["git", "-C", REPO, "show", f"{REV}:{path}"], capture_output=True)
    if out.returncode != 0:
        raise SystemExit(f"not committed: {path}")
    return hashlib.sha256(out.stdout).hexdigest()


def _load(rel: str) -> dict:
    with open(os.path.join(REPO, rel), "rb") as fh:
        return json.loads(fh.read())


PREV = "docs/implementation/evidence/mr_002/MR002_Phase3C_ValidationExecutionPackage_v1.0.json"
EVID = "docs/implementation/evidence/mr_002/MR002_Phase3C_RuntimeCompositionCustodyEvidence_v1.0.json"
prev = _load(PREV)
ev = _load(EVID)
comp = ev["composition_qualification"]
build = ev["bundle_v12_build"]

PACKAGE = json.loads(json.dumps(prev))          # carry every existing binding forward unchanged
PACKAGE.pop("record_identity_sha256", None)
PACKAGE["version"] = "2.0"
PACKAGE["supersedes"] = {"path": PREV, "sha256": blob_sha(PREV)}
PACKAGE["supersession_note"] = (
    "v1.0 bound the right components but not the COMPOSITION. Corrections: (1) the runtime is now "
    "identified by portable, typed identities instead of one store-dependent .Id; (2) runtime "
    "PRESENCE on the authorized host is asserted, not assumed; (3) the dependency bundle is v1.2, "
    "which closes the boto3 import graph against THIS image rather than relying on a different "
    "image's site-packages. No economic, numerical, Phase 3C, Stage-3, 6+4 or gate binding changed."
)

PACKAGE["runtime_identity"] = {
    "note": (
        "three typed identities, never one generic 'image_id'. A generic field whose meaning "
        "depends on the daemon is precisely what caused the earlier false mismatch."
    ),
    "source_oci_index_digest": (
        "sha256:aa930021c072d01a5a14f389b53bea9d338e53b71e2aac08550972060a08610a"),
    "source_oci_index_digest_meaning": (
        "the OCI/index identity exposed by the qualification machine's containerd-backed image "
        "store, and the identity recorded during qualification. Source-side provenance only -- the "
        "authorized host's classic store does NOT report this through .Id, and must not be "
        "required to."
    ),
    "image_config_digest": (
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6"),
    "image_config_digest_meaning": (
        "the configuration blob contained in the transferred archive AND the classic Docker "
        "daemon's loaded .Id. This is the portable identity, because it binds runtime "
        "configuration that a filesystem-only digest would miss."
    ),
    "rootfs_diffid_sequence_digest": (
        "c16e7c09fba1fd33a3dc743caff8b8942b43252be3999ffc40e3a616d6a1507e"),
    "rootfs_diffid_count": 8,
    "platform": "amd64/linux",
    "export_archive_sha256": (
        "95076c14b32bee01a54e2d49a9a42bea47ef9c73ffb5c0a998c7a10d174c346e"),
    "export_archive_bytes": 142534656,
    "tag": "mr002-research:v1.4",
}

PACKAGE["runtime_availability"] = {
    "authorized_host": HOST,
    "image_present_on_host": True,
    "host_loaded_id": (
        "sha256:770553aeae6c3d47f1735f61a4e0df75515c105ddda0431dcc2a07b8bdbfe4b6"),
    "verified_by": "docs/implementation/evidence/mr_002/"
                   "MR002_Phase3C_RuntimeCompositionCustodyEvidence_v1.0.json",
    "custody_route": (
        "docker save on the qualification machine -> SHA-256 + byte count -> controlled S3 "
        "staging -> presigned GET (authorized by the operator's signature, so the instance role "
        "was NOT used and NO permission was added) -> host verifies bytes and SHA-256 BEFORE "
        "loading -> docker load -> identity proven. No container was started from it during "
        "staging and no sealed access occurred."
    ),
    "checks_passed": "9/9 content and configuration checks",
}

PACKAGE["dependency_bundle"] = {
    "version": "v1.2",
    "supersedes": "ExecutionDependencyBundle v1.1",
    "why": (
        "v1.1 was never a self-contained boto3 dependency bundle -- it was a DELTA against the "
        "evaluator image. Pairing that delta with the research image exposed an implicit "
        "dependency on the evaluator image's site-packages, and boto3 could not import."
    ),
    "closure_census": {
        "method": (
            "imported boto3 inside the REFERENCE composition (evaluator image + v1.1) and "
            "classified every loaded module by origin"
        ),
        "boto3_import_in_reference_composition": "SUCCEEDED",
        "supplied_by_the_image_and_absent_from_v1_1": ev["dependency_closure_census"],
    },
    "provenance": (
        "the exact installed distributions from the bound evaluator image that supported the "
        "successful v3.6 reader composition -- NOT PyPI, NOT today's resolution"
    ),
    "additive_only": build["ADDITIVE_ONLY"],
    "v1_1_files": build["v11_files"],
    "v1_2_files": build["v12_files"],
    "v1_1_files_missing_from_v1_2": build["v11_files_missing_from_v12"],
    "v1_1_files_changed_in_v1_2": build["v11_files_CHANGED_in_v12"],
    "added_file_count": build["added_file_count"],
    "added_top_level": build["added_top_level"],
    "v1_1_inventory_digest": build["v11_inventory_digest"],
    "v1_2_inventory_digest": build["v12_inventory_digest"],
    "zero_pyc": build["zero_pyc"],
    "zero_pycache": build["zero_pycache"],
    "test_files_among_the_ADDED_set": 0,
    "pre_existing_test_files_inherited_from_v1_1": (
        "95, all pyarrow's own tests/ subpackage -- inherited, not introduced by this amendment"
    ),
    "host_path": "/opt/mr002/deps_v12",
    "mount_point": "/opt/mr002/deps",
    "mount_mode": "read-only (proven by a refused write)",
}

PACKAGE["composed_runtime_preflight"] = {
    "pythonpath": "/work/apps/backend:/opt/mr002/deps",
    "network": "none",
    "boto3_imports": True,
    "reader_dependency_versions": comp["versions"],
    "reader_dependencies_all_from_projection": comp["all_from_projection"],
    "reader_dependency_provenance": comp["provenance"],
    "native_stack_versions": comp["native_versions"],
    "native_stack_not_shadowed_by_projection": comp["native_not_shadowed"],
    "native_stack_provenance": comp["native_provenance"],
    "phase3c_not_shadowed": comp["phase3c_not_shadowed"],
    "governed_reader_module": comp["readers_module"],
    "reader_behaviour_proven_without_aws": {
        "reads_pinned_object": comp["reader_reads_pinned_object"],
        "passes_version_id": comp["reader_passed_version_id"],
        "refuses_bad_checksum": comp["reader_refuses_bad_checksum"],
        "refuses_unpinned_read": comp["reader_refuses_unpinned"],
        "how": "a fake client was injected; no AWS call was made and the latch stayed closed",
    },
    "thread_env": comp["thread_env"],
    "thread_env_ok": comp["thread_env_ok"],
    "synthetic_materializer_suite": "12 passed in the FINAL composition",
}

PACKAGE["source_deployment"] = {
    "checkpoint": "34eeee00e03ee66fb9ac8702503b89463fa70f67",
    "archive_sha256": "d52e51f44b0fd67419b2dc9bf6e592805ddecd67e35fc3e1e5b7acb602972e32",
    "archive_bytes": 8079360,
    "host_path": "/opt/mr002/phase3c_src",
    "mount": "/work/apps/backend (read-only)",
    "note": "produced by git archive from the PUSHED ref, verified on the host before extraction",
}

PACKAGE["composition_invariant"] = (
    "A runtime may NOT be described as validation-executable merely because its digest is known. "
    "The package must carry evidence that the exact digest is locally resolvable on the authorized "
    "execution host, together with every external dependency required to launch it. Concretely: "
    "boto3 import and governed-reader import MUST succeed in the exact host composition before "
    "this package can be execution-authorized. This closes the repeated 'bound X + bound Y, but X "
    "and Y do not compose' defect class -- of which this program has now seen four instances: the "
    "omitted bundle mount, the image bound but absent from the host, the store-dependent .Id, and "
    "a bundle that only closed against a different image."
)

PACKAGE["pre_release_requirement"] = (
    "every condition in runtime_identity, runtime_availability, dependency_bundle and "
    "composed_runtime_preflight must be re-verified and still hold IMMEDIATELY before latch "
    "release; any difference STOPS without opening"
)

PACKAGE["requalification"] = {
    "stage3_governed_qualification": "REMAINS VALID — not rerun",
    "materializer_synthetic_qualification": "REMAINS VALID — and rerun anyway in the final "
                                            "composition (12 passed)",
    "development_equivalence_qualification": "REMAINS VALID — not rerun",
    "why": (
        "the amendment is additive-only and the runtime bytes are identical; transporting a "
        "qualified artifact and closing its import graph does not create a new numerical or "
        "semantic runtime. No 3,895-solve or 1,700-session rerun was performed."
    ),
}

PACKAGE["execution_authorized"] = False
PACKAGE["awaiting"] = "owner confirmation that the custody-complete package may be executed"
PACKAGE["custody_evidence"] = {"path": EVID, "sha256": blob_sha(EVID)}

PACKAGE["record_identity_sha256"] = hashlib.sha256(_canonical(PACKAGE)).hexdigest()
out = os.path.join(_HERE, "MR002_Phase3C_ValidationExecutionPackage_v2.0.json")
with open(out, "wb") as fh:
    fh.write(_canonical(PACKAGE))
print(json.dumps({
    "package_v2.0": PACKAGE["record_identity_sha256"],
    "image_config_digest": PACKAGE["runtime_identity"]["image_config_digest"],
    "bundle_v1.2_inventory": PACKAGE["dependency_bundle"]["v1_2_inventory_digest"],
    "sealed": PACKAGE["input_contract"]["validation_sealed_inputs"]["count"],
    "reference": PACKAGE["input_contract"]["reference_inputs"]["count"],
}, indent=1))
