"""MR-002 evaluator — qualifying container-image leg of the SS4 binding (P5 continuation).

Completes the one element `mr002_valoos_binding` leaves `UNRESOLVED`: the content-addressed image
identity. The rules this module enforces exist because each is a way a container binding can look
complete while certifying nothing:

  * a mutable repository tag is NOT an identity — `repo:tag` is rejected, only `sha256:<64hex>` (or
    `repo@sha256:<64hex>`) is accepted;
  * the image must have been built from the SAME source commit and tree the binding names;
  * the evaluator modules INSIDE the image must be byte-identical to the bound set, with no module
    omitted and no additional included module present;
  * the dependency lock inside the image must be the bound lock.

Stdlib only: this module is part of the qualification gate, so it must not depend on the numeric
stack it will later help qualify. It builds nothing and runs no container — the caller supplies
observations, so the same verification runs identically inside or outside the image.

Scope: this is the SS4 IMAGE IDENTITY leg. It is NOT P10 numeric-runtime production and asserts
nothing about the numeric stack.
"""

from __future__ import annotations

import hashlib
import json
import re

IMAGE_REFUSED = "REFUSED_EVALUATOR_IMAGE"
DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
REPO_DIGEST_RE = re.compile(r"^[^\s@]+@sha256:[0-9a-f]{64}$")


class ImageRefused(Exception):
    """REFUSED_EVALUATOR_IMAGE — the image is not the bound image."""


def _refuse(detail: str):
    raise ImageRefused(f"{IMAGE_REFUSED}:{detail}")


def is_content_addressed(reference: str) -> bool:
    """True only for a content-addressed reference. A `repo:tag` is never an identity."""
    if not isinstance(reference, str):
        return False
    return bool(DIGEST_RE.match(reference) or REPO_DIGEST_RE.match(reference))


def normalize_digest(reference: str) -> str:
    if not is_content_addressed(reference):
        _refuse(f"not_content_addressed:{reference!r}")
    return reference.split("@")[-1]


def build_image_manifest(*, image_digest: str, base_image_digest: str, platform: str,
                         builder: str, build_definition: str, build_definition_sha256: str,
                         source_commit: str, source_tree: str, dependency_lock: str,
                         dependency_lock_sha256: str, evaluator_path_in_image: str,
                         module_digests: dict, build_inputs: dict,
                         sealed_data_mounted: bool = False) -> dict:
    """Record the build. Refuses a manifest that cannot serve as an identity."""
    if sealed_data_mounted:
        _refuse("sealed_data_mounted_during_build")
    for label, ref in (("image_digest", image_digest), ("base_image_digest", base_image_digest)):
        if not is_content_addressed(ref):
            _refuse(f"not_content_addressed:{label}:{ref!r}")
    if not module_digests:
        _refuse("empty_module_set")
    return {
        "record_type": "MR002_EvaluatorImageManifest", "version": "1.0",
        "image_digest": normalize_digest(image_digest),
        "image_digest_kind": "content-addressed image config digest (docker image ID)",
        "base_image_digest": normalize_digest(base_image_digest),
        "platform": platform,
        "builder": builder,
        "build_definition": build_definition,
        "build_definition_sha256": build_definition_sha256,
        "source_commit": source_commit,
        "source_tree": source_tree,
        "dependency_lock": dependency_lock,
        "dependency_lock_sha256": dependency_lock_sha256,
        "evaluator_path_in_image": evaluator_path_in_image,
        "module_digests_in_image": dict(sorted(module_digests.items())),
        "module_count_in_image": len(module_digests),
        "build_inputs": build_inputs,
        "sealed_data_mounted": False,
        "scope": "SS4 image-identity leg only; NOT a P10 numeric-runtime qualification",
    }


def verify_image_against_binding(manifest: dict, binding: dict, *,
                                 observed_image_digest: str | None = None,
                                 observed_modules: dict | None = None) -> dict:
    """Compare a built image against the SS4 source binding. Reports; does not raise."""
    problems = []
    if not isinstance(manifest, dict) or \
            manifest.get("record_type") != "MR002_EvaluatorImageManifest":
        return {"matches": False,
                "problems": [{"kind": "image_manifest_absent_or_wrong_type"}]}
    if not isinstance(binding, dict) or binding.get("record_type") != "MR002_EvaluatorBinding":
        return {"matches": False, "problems": [{"kind": "binding_absent_or_wrong_type"}]}

    if not is_content_addressed(manifest.get("image_digest", "")):
        problems.append({"kind": "image_not_content_addressed",
                         "value": manifest.get("image_digest")})

    for field in ("source_commit", "source_tree"):
        if manifest.get(field) != binding["section4_elements"][field]["value"]:
            problems.append({"kind": "source_identity_mismatch", "field": field,
                             "bound": binding["section4_elements"][field]["value"],
                             "image": manifest.get(field)})

    bound_lock = binding["section4_elements"]["dependency_lock"]["sha256"]
    if manifest.get("dependency_lock_sha256") != bound_lock:
        problems.append({"kind": "dependency_lock_mismatch", "bound": bound_lock,
                         "image": manifest.get("dependency_lock_sha256")})

    bound_modules = binding.get("included_modules") or {}
    in_image = observed_modules if observed_modules is not None \
        else manifest.get("module_digests_in_image", {})
    for name, digest in sorted(bound_modules.items()):
        if name not in in_image:
            problems.append({"kind": "module_omitted_from_image", "module": name})
        elif in_image[name] != digest:
            problems.append({"kind": "module_drift_in_image", "module": name,
                             "bound": digest, "in_image": in_image[name]})
    for name in sorted(set(in_image) - set(bound_modules)):
        problems.append({"kind": "additional_unbound_module_in_image", "module": name,
                         "in_image": in_image[name]})

    if observed_image_digest is not None and \
            normalize_digest(observed_image_digest) != manifest.get("image_digest"):
        problems.append({"kind": "image_digest_mismatch",
                         "manifest": manifest.get("image_digest"),
                         "observed": normalize_digest(observed_image_digest)})

    return {"matches": not problems, "problems": problems,
            "bound_module_count": len(bound_modules), "image_module_count": len(in_image)}


def require_image(manifest: dict, binding: dict, **observed) -> dict:
    """Fail-closed gate for the image leg. MUST pass before the container leg may be resolved."""
    report = verify_image_against_binding(manifest, binding, **observed)
    if not report["matches"]:
        _refuse(",".join(sorted({p["kind"] for p in report["problems"]})))
    return report


def manifest_sha256(manifest: dict) -> str:
    return hashlib.sha256(
        json.dumps(manifest, sort_keys=True, ensure_ascii=True).encode("ascii")).hexdigest()
