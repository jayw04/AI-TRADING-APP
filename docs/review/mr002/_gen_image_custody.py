"""Emit the MR-002 evaluator image custody record.

Records durable custody of the image bound by the governing §4 execution binding
(source d1e7ffc / tree 01503f9a, RESOLVED at ef5af66).

This generator deliberately lives OUTSIDE docs/review/mr002/evaluator/: any .py
added there enters the §4 module inventory and would invalidate the now-RESOLVED
binding.

Scope: custody and availability ONLY. This record creates no authorization event,
amends no sealed package, satisfies no prerequisite, and is NOT permission to
begin P10.

Every digest below was read back from the registry with the AWS CLI and verified;
none is transcribed from the local Docker daemon's reporting.
"""
import hashlib
import json
import os
from pathlib import Path

HERE = os.path.dirname(os.path.abspath(__file__))

BOUND_DIGEST = "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"
REGISTRY = "219024422756.dkr.ecr.us-east-1.amazonaws.com"
REPOSITORY = "mr002-evaluator-p5"
TAG = "qualify-d1e7ffc"

record = {
    "record_type": "MR002_EvaluatorImageCustody",
    "version": "1.0",
    "date": "2026-07-22",
    "scope": "custody and availability of the bound evaluator image ONLY; creates no "
             "authorization event, amends no sealed package, satisfies no prerequisite, "
             "and is NOT permission to begin P10",
    "custodian": {
        "of_record": "Jay Wang / GlobalComplyAI, LLC (owner)",
        "aws_account": "219024422756",
        "note": "the assistant produced this artifact and the verification procedure; "
                "the custody obligation rests with the custodian of record",
    },
    "governing_binding": {
        "binding_commit": "ef5af66090b28ec9841eb60412bbaff05cf9e91c",
        "binding_state": "RESOLVED",
        "source_commit": "d1e7ffc6ef280b69d6244cfbff3bb18c5d412f4b",
        "source_tree": "01503f9a77f1ff88ac146d120c323c559ac6cb61",
        "included_module_count": 21,
        "bound_image_digest": BOUND_DIGEST,
    },

    # ---- what the bound digest actually addresses -------------------------
    # Established by reading the registry, not by trusting `docker images`.
    "digest_kind_correction": {
        "finding": "the bound digest is an OCI image INDEX digest "
                   "(application/vnd.oci.image.index.v1+json), not an image config digest",
        "documented_as": "MR002_EvaluatorImageManifest.json field image_digest_kind reads "
                         "'content-addressed image config digest (docker image ID)'",
        "actual_config_digest": "sha256:6962e4a78792cfbd36f999967a3cfaa26f0d8b1dc8d9ee27403"
                                "ca4be8556a746",
        "cause": "the local Docker daemon uses the containerd image store, which reports the "
                 "index digest as the image ID and as the RepoDigest; the manifest's "
                 "description was inferred from that reporting",
        "identity_impact": "NONE — the bound VALUE is correct and is registry-addressable "
                           "exactly as bound; only its type DESCRIPTION was wrong",
        "resolver_impact": "MATERIAL — a resolver written to the documented description would "
                           "look for a config object under this digest and fail; it must "
                           "resolve an image index",
        "disposition": "documentation-accuracy defect in the SS4 image-identity leg, recorded "
                       "here for adjudication; NOT corrected in place, because the manifest is "
                       "part of the RESOLVED binding and this record amends nothing",
    },
    "image_index": {
        "digest": BOUND_DIGEST,
        "media_type": "application/vnd.oci.image.index.v1+json",
        "members": [
            {
                "digest": "sha256:a4e3ac54151b0bd27dd527b4df13da47058dbb8596be8ec9a77f44b8"
                          "63191a3d",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "platform": "linux/amd64",
                "role": "runtime image",
                "config_digest": "sha256:6962e4a78792cfbd36f999967a3cfaa26f0d8b1dc8d9ee2740"
                                 "3ca4be8556a746",
                "layer_count": 7,
            },
            {
                "digest": "sha256:b81cd073e34445ec31f2bffff0bb1345c6ccc31940c20a29fb7d99879"
                          "15ae7cc",
                "media_type": "application/vnd.oci.image.manifest.v1+json",
                "platform": "unknown/unknown",
                "role": "buildkit attestation manifest",
                "note": "part of the bound index; retained, not stripped",
            },
        ],
    },
    "registry_location": {
        "registry": REGISTRY,
        "region": "us-east-1",
        "repository": REPOSITORY,
        "tag": TAG,
        "pull_by_digest": f"{REGISTRY}/{REPOSITORY}@{BOUND_DIGEST}",
        "tag_mutability": "IMMUTABLE",
        "encryption": "AES256",
        "lifecycle_policy": "NONE — confirmed absent; a lifecycle policy could expire the "
                            "bound image and must never be added to this repository",
        "colocation": "us-east-1, same region as the run-5 S3 archive "
                      "s3://workbench-backups-219024422756",
    },

    # ---- the seven requirements, each with how it was tested ---------------
    "custody_requirements_status": {
        "1_retain_exact_digest_in_content_addressable_registry": {
            "status": "SATISFIED",
            "evidence": f"pushed to {REGISTRY}/{REPOSITORY}; ECR describe-images reports the "
                        f"image under digest {BOUND_DIGEST} — the bound value, unchanged",
        },
        "2_retrieval_by_digest_reproduces_manifest_and_config": {
            "status": "SATISFIED",
            "evidence": "ecr batch-get-image by imageDigest returned the index; sha256 of the "
                        "returned bytes recomputes to the bound digest BYTE-EXACT. Verified "
                        "twice: once after push, once after the cleanup described below",
        },
        "3_record_registry_location_and_platform_manifest": {
            "status": "SATISFIED",
            "evidence": "registry_location and image_index above, including the linux/amd64 "
                        "platform manifest, its config digest, and the attestation manifest",
        },
        "4_cannot_be_overwritten_under_the_bound_digest": {
            "status": "SATISFIED",
            "evidence": "tested negatively — pushing a DIFFERENT image under tag "
                        f"'{TAG}' was rejected by the registry: 'the tag is immutable'. "
                        "Digest addressing is content-addressed and cannot collide by "
                        "construction",
            "test_residue": "the rejected push created 2 foreign untagged sub-manifests "
                            "(sha256:ecb95a08…, sha256:e5d2126e…) before the index was "
                            "refused; both were deleted by explicit digest, and the bound "
                            "index was re-verified byte-exact afterward. The repository now "
                            "holds exactly the 3 original entries",
        },
        "5_local_only_availability_not_mistaken_for_durable_custody": {
            "status": "SATISFIED",
            "evidence": "custody no longer depends on the laptop daemon; the image is durable "
                        "in ECR. The local copy is now a convenience replica, not the "
                        "custodial copy",
        },
        "6_superseded_and_current_bindings_independently_verifiable": {
            "status": "SATISFIED",
            "evidence": "the current binding is verifiable via this registry entry; the "
                        "superseded 20-module binding at 6708c59 remains in-tree as "
                        "MR002_EvaluatorBinding_superseded_6708c59.json and is unaffected. "
                        "The superseded binding is historical evidence, NOT a candidate "
                        "execution binding",
        },
        "7_resolver_fails_if_exact_digest_unavailable": {
            "status": "SPECIFIED_NOT_IMPLEMENTED",
            "evidence": "no resolver exists yet; building one would be research-side "
                        "prerequisite production, which the closeout explicitly does not "
                        "authorize",
            "required_behavior": "resolve by index digest; on any miss, mismatch, or "
                                 "unavailability FAIL CLOSED with no fallback to a tag, to a "
                                 "local image, or to a rebuild",
        },
    },
    "verification_procedure": {
        "step_1": f"aws ecr batch-get-image --repository-name {REPOSITORY} --region us-east-1 "
                  f"--image-ids imageDigest={BOUND_DIGEST} --query 'images[0].imageManifest' "
                  f"--output text",
        "step_2": "sha256 of the returned manifest bytes MUST equal the bound digest",
        "step_3": f"docker pull {REGISTRY}/{REPOSITORY}@{BOUND_DIGEST}",
        "step_4": "on ANY mismatch or unavailability, STOP — do not rebuild, do not substitute "
                  "a later image, do not fall back to the tag",
    },
    "scope_limits_carried_forward": [
        "instance identity, NOT bit-for-bit build reproducibility — do not claim reproducible "
        "builds, do not rebuild and assume equivalence, do not replace the bound digest with a "
        "later rebuild without a superseding qualification",
        "no numerical library/BLAS/LAPACK/CPU-dispatch/threading/floating-point/seed/"
        "determinism claim; P10 is not implied",
    ],
    "authorization_state_unchanged": {
        "validation_authorization": False,
        "validation_opening": "UNCONSUMED",
        "validation_partition": "CLOSED",
        "oos": "UNDER DENY",
        "_rev": 0,
    },
    "explicitly_not_authorized_by_this_record": [
        "beginning P10",
        "grant-readiness verifier",
        "D3 submission or authorization event",
        "validation or OOS access",
        "credential release",
        "performance computation",
    ],
    "open_items_for_adjudication": [
        "the digest-kind description defect in MR002_EvaluatorImageManifest.json (identity "
        "unaffected, resolver behavior materially affected)",
        "whether an ECR repository policy denying BatchDeleteImage/DeleteRepository should be "
        "applied — recommended, matching the run-5 'deletion FORBIDDEN' precedent, but NOT "
        "applied unilaterally because it constrains the owner's own administrative access",
        "requirement 7 resolver remains unimplemented by design",
    ],
}

out = os.path.join(HERE, "MR002_EvaluatorImageCustody_v1.0.json")
payload = json.dumps(record, sort_keys=True, indent=2) + "\n"
Path(out).write_text(payload, encoding="utf-8", newline="\n")

print("image custody recorded")
print(f"  registry {REGISTRY}/{REPOSITORY}@{BOUND_DIGEST[:19]}…")
print("  requirements 1-6 SATISFIED; 7 SPECIFIED_NOT_IMPLEMENTED")
print(f"  record sha256 {hashlib.sha256(payload.encode()).hexdigest()[:16]}…")
