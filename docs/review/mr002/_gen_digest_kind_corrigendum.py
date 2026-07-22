"""Emit the digest-kind corrigendum for MR002_EvaluatorImageManifest.json.

Required by the custody adjudication of 2026-07-22 (custody package be0a6ac
ACCEPTED; requirements 1-6 SATISFIED, requirement 7 UNSATISFIED).

The affected artifact belongs to the RESOLVED P5 §4 binding and is NOT modified
in place. This corrigendum is documentation and custody clarification only. It is
NOT a new evaluator binding and NOT a P5 requalification. It creates no
authorization event, advances no prerequisite, and leaves validation_authorization
false.

Like the other MR-002 governance generators, this file lives OUTSIDE
docs/review/mr002/evaluator/: any .py added there enters the §4 module inventory
and would invalidate the RESOLVED binding.
"""
import hashlib
import json
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))
TARGET_REL = "docs/review/mr002/evaluator/MR002_EvaluatorImageManifest.json"
TARGET_ABS = os.path.join(HERE, "evaluator", "MR002_EvaluatorImageManifest.json")

# Read the affected artifact to bind the corrigendum to its exact current bytes.
# Read-only: this generator never writes to the evaluator directory.
target_sha = hashlib.sha256(Path(TARGET_ABS).read_bytes()).hexdigest()

BOUND_DIGEST = "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"

record = {
    "record_type": "MR002_EvaluatorImageManifest_DigestKindCorrigendum",
    "version": "1.0",
    "date": "2026-07-22",
    "classification": "documentation and custody clarification",
    "explicitly_not": [
        "a new evaluator binding",
        "a P5 requalification",
        "an amendment to the RESOLVED §4 binding",
        "an authorization event",
        "satisfaction of any prerequisite, including custody requirement 7",
    ],
    "authority": "custody adjudication 2026-07-22 — custody package be0a6ac ACCEPTED; "
                 "corrigendum required for the digest-kind defect",

    "affected_artifact": {
        "path": TARGET_REL,
        "field": "image_digest_kind",
        "line": 18,
        "source_commit": "ef5af66090b28ec9841eb60412bbaff05cf9e91c",
        "artifact_sha256": target_sha,
        "artifact_state": "UNMODIFIED since its source commit; verified by git diff and by "
                          "sha256, which matches the value recorded in the P5 closeout",
        "modified_in_place": False,
    },

    "erroneous_description": {
        "verbatim": "content-addressed image config digest (docker image ID)",
        "field_identity": f"{TARGET_REL}#image_digest_kind",
        "why_wrong": "it names the wrong OCI object kind for the bound digest",
        "cause": "the producing host's Docker daemon uses the containerd image store, which "
                 "reports the image INDEX digest as both the image ID and the RepoDigest; the "
                 "description was inferred from that reporting rather than from the registry",
    },

    "correction": {
        "statement": f"{BOUND_DIGEST} is an OCI image-index digest "
                     "(application/vnd.oci.image.index.v1+json). It is NOT an image "
                     "configuration digest and NOT a platform manifest digest.",
        "corrected_digest_kind": "OCI image index digest",
        "evidence": "retrieval from the governing custody registry by this digest returned "
                    "index bytes whose sha256 reproduces the bound identity byte-exact; "
                    "verified twice, before and after the immutability-probe remediation",
    },

    "object_hierarchy": {
        "note": "the INDEX is the governing bound object. The platform manifest and the image "
                "configuration are subordinate identities, NOT substitutes for it. The "
                "attestation descriptor is bound into the index and is part of the governing "
                "object.",
        "1_index": {
            "digest": BOUND_DIGEST,
            "media_type": "application/vnd.oci.image.index.v1+json",
            "role": "GOVERNING bound object",
        },
        "2_platform_manifest": {
            "digest": "sha256:a4e3ac54151b0bd27dd527b4df13da47058dbb8596be8ec9a77f44b863191a3d",
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "platform": "linux/amd64",
            "role": "subordinate identity",
        },
        "3_image_configuration": {
            "digest": "sha256:6962e4a78792cfbd36f999967a3cfaa26f0d8b1dc8d9ee27403ca4be8556a746",
            "media_type": "application/vnd.oci.image.config.v1+json",
            "role": "subordinate identity",
        },
        "attestation_manifest": {
            "digest": "sha256:b81cd073e34445ec31f2bffff0bb1345c6ccc31940c20a29fb7d9987915ae7cc",
            "media_type": "application/vnd.oci.image.manifest.v1+json",
            "platform": "unknown/unknown",
            "producer": "BuildKit",
            "role": "descriptor bound into the governing index; retained, not stripped",
        },
    },

    "unchanged_by_this_corrigendum": {
        "bound_digest_value": f"{BOUND_DIGEST} — CORRECT as bound, and registry-addressable "
                              "exactly as bound",
        "p5_binding": "the §4 binding at ef5af66 (source d1e7ffc / tree 01503f9a, 21 modules) "
                      "remains RESOLVED and unamended",
        "binding_identity_impact": "NONE",
        "image_integrity_impact": "NONE",
        "authorization_state": "unchanged — validation_authorization false, single opening "
                               "unconsumed, validation partition closed, OOS under DENY",
    },

    "impact": {
        "binding_identity": "NONE",
        "image_integrity": "NONE",
        "implementation": "MATERIAL — a resolver that trusts the erroneous object-kind "
                          "description would attempt to resolve a configuration object under "
                          "the bound digest and fail",
    },

    "disposition_of_original": "HISTORICALLY PRESERVED, SEMANTICALLY CORRECTED. The original "
                               "artifact remains in place, unmodified, as part of the RESOLVED "
                               "binding. Its image_digest_kind field is superseded in meaning "
                               "by this corrigendum.",

    "binding_on_future_consumers": [
        "future consumers MUST treat the bound digest as an OCI image-index digest",
        "future consumers MUST NOT rely on the erroneous image_digest_kind description",
        "the index is the governing identity; a platform manifest or configuration digest "
        "MUST NOT be substituted for it",
        "this corrigendum MUST be read together with the affected artifact",
    ],

    "related_records": {
        "custody": "docs/review/mr002/MR002_EvaluatorImageCustody_v1.0.json (be0a6ac)",
        "closeout": "docs/review/mr002/MR002_ResearchSidePrerequisiteCloseout_v1.0.json "
                    "(e15baa0)",
        "binding": "docs/review/mr002/evaluator/MR002_EvaluatorBinding.json (ef5af66)",
    },

    "still_unsatisfied": {
        "custody_requirement_7": "fail-closed resolver — SPECIFIED_NOT_IMPLEMENTED. This "
                                 "corrigendum supplies the corrected object-kind a future "
                                 "resolver must implement against; it does NOT implement it "
                                 "and does NOT satisfy the requirement. Building the resolver "
                                 "is not authorized.",
    },
}

out = os.path.join(HERE, "MR002_EvaluatorImageManifest_DigestKindCorrigendum_v1.0.json")
payload = json.dumps(record, sort_keys=True, indent=2) + "\n"
Path(out).write_text(payload, encoding="utf-8", newline="\n")

print("digest-kind corrigendum recorded")
print(f"  affected {TARGET_REL}#image_digest_kind (line 18)")
print(f"  artifact sha256 {target_sha[:16]}… — UNMODIFIED in place")
print(f"  corrected kind: OCI image index digest ({BOUND_DIGEST[:19]}…)")
print(f"  corrigendum sha256 {hashlib.sha256(payload.encode()).hexdigest()[:16]}…")
