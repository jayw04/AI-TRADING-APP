"""Custody Requirement 7 — the fail-closed evaluator image resolver.

Authorized by the owner on 2026-08-10
(``docs/review/mr002/MR002_PrerequisiteProduction_Authorization_v1.0.json``,
Execution Order Step 3, WP-B). Before that record existed, building this was
research-side prerequisite production, which the closeout did not authorize.

Required behaviour, verbatim from ``MR002_EvaluatorImageCustody_v1.0.json``
(``7_resolver_fails_if_exact_digest_unavailable``):

    resolve by index digest; on any miss, mismatch, or unavailability FAIL
    CLOSED with no fallback to a tag, to a local image, or to a rebuild

===============================================================================
WHY THIS EXISTS
===============================================================================

Requirements 1-6 establish that the bound image IS in durable custody. None of
them constrains what a RUN does when it is not. Without this resolver a run
environment that cannot reach the bound digest has a menu of plausible,
catastrophic fallbacks: pull the ``qualify-d1e7ffc`` tag (mutable in principle,
even though this repository is IMMUTABLE), use whatever the local Docker daemon
has cached, or rebuild from source. Each produces *an* evaluator. None produces
*the* evaluator, and the resulting numbers would be attributed to a
preregistration they were not produced under.

The failure this prevents is silent. A rebuilt image runs perfectly and yields
plausible results.

===============================================================================
THE ONLY PERMITTED RESOLUTION PATH
===============================================================================

Plan v1.3.1 makes this resolver the SOLE permitted way to obtain P10's
container-image digest binding. Binding it by tag, by the local Docker daemon,
by rebuild, or by hand-copying the string does NOT satisfy P10 -- however
identical the resulting 64 hex characters look. P10 asserts the digest was
*resolved*, not that someone typed it correctly.

===============================================================================
FAIL-CLOSED MEANS RAISE, NEVER RETURN
===============================================================================

Every failure path raises ``ImageResolutionRefused``. There is no sentinel
return, no ``None``, no partially-populated result. A caller cannot accidentally
proceed by ignoring a return value, because on failure there is no return value
to ignore.

There is also no cache. Every call performs live resolution against the
registry. A cached "we checked earlier" is precisely the substitute this
requirement forbids -- and it is why the custody monitor's receipts carry
``satisfies_requirement_7: false`` and must never be consumed here.

===============================================================================
SCOPE
===============================================================================

Read-only registry calls. Opens no validation or OOS data, computes no
performance, releases no credentials, and grants no execution authority.
Resolution succeeding is a precondition for a run, never an authorization for
one -- ``validation_authorization`` is a separate CAS-guarded state.
"""

from __future__ import annotations

import hashlib
import json
import re
from datetime import UTC, datetime
from typing import Any

# NOTE: boto3 is deliberately NOT imported at module scope. The 2026-07-25
# defect in export_recovery_copy.py was exactly this: a module-scope SDK import
# made an offline path fail at IMPORT, before any logic ran, on a machine that
# had no boto3. Import lives at its single point of use in _fetch_index_bytes().

REGION = "us-east-1"
REGISTRY_ID = "219024422756"
REPOSITORY = "mr002-evaluator-p5"

# The bound OCI index digest. This is the identity the preregistration ties
# MR-002's evaluator to. Changing this constant is a governance event, not a
# code change: it would silently re-point every future run at a different
# evaluator while every downstream artifact still claimed the old binding.
BOUND_INDEX_DIGEST = (
    "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"
)

DIGEST_RE = re.compile(r"^sha256:[0-9a-f]{64}$")


class ImageResolutionRefused(RuntimeError):
    """Raised on ANY failure to resolve the bound image. Never caught internally.

    Carries a machine-readable ``reason`` so a refusal can be recorded as
    evidence without re-parsing a message string.
    """

    def __init__(self, reason: str, detail: str = "") -> None:
        self.reason = reason
        self.detail = detail
        super().__init__(f"{reason}: {detail}" if detail else reason)


def _refuse(reason: str, detail: str = "") -> None:
    raise ImageResolutionRefused(reason, detail)


def sha256_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _fetch_index_bytes(expected_digest: str, *, client: Any = None) -> bytes:
    """Fetch the image index BY DIGEST. Never by tag.

    ``client`` is injectable so the fail-closed behaviour can be tested against
    registry unavailability without a network. It is never used to bypass
    verification: the bytes returned are hashed and compared regardless of where
    the client came from.
    """
    if client is None:
        try:
            import boto3  # noqa: PLC0415 — see module note
        except ImportError as exc:
            _refuse("registry_sdk_unavailable", str(exc))
        try:
            client = boto3.client("ecr", region_name=REGION)
        except Exception as exc:  # noqa: BLE001 — any client failure is unavailability
            _refuse("registry_client_unavailable", f"{type(exc).__name__}: {exc}")

    try:
        response = client.batch_get_image(
            registryId=REGISTRY_ID,
            repositoryName=REPOSITORY,
            # BY DIGEST. There is deliberately no imageTag key here; a tag is not
            # an identity, and offering one as a fallback is the failure mode
            # Requirement 7 exists to prevent.
            imageIds=[{"imageDigest": expected_digest}],
            acceptedMediaTypes=[
                "application/vnd.oci.image.index.v1+json",
                "application/vnd.docker.distribution.manifest.list.v2+json",
            ],
        )
    except Exception as exc:  # noqa: BLE001 — unreachable registry is unavailability
        _refuse("registry_unavailable", f"{type(exc).__name__}: {exc}")

    failures = response.get("failures") or []
    if failures:
        _refuse("digest_not_found", json.dumps(failures, sort_keys=True, default=str))

    images = response.get("images") or []
    if not images:
        _refuse("digest_not_found", "registry returned no image for the bound digest")
    if len(images) != 1:
        _refuse(
            "ambiguous_resolution",
            f"registry returned {len(images)} images for one digest",
        )

    manifest = images[0].get("imageManifest")
    if not isinstance(manifest, str) or not manifest:
        _refuse("malformed_response", "imageManifest absent or not a string")

    return manifest.encode("utf-8")


def resolve_bound_image(
    *,
    expected_digest: str = BOUND_INDEX_DIGEST,
    client: Any = None,
) -> dict[str, Any]:
    """Resolve the evaluator image by digest, or REFUSE.

    Returns a resolution record only when the registry served bytes whose
    SHA-256 recomputes byte-exact to ``expected_digest``. Every other outcome
    raises :class:`ImageResolutionRefused`.

    The recomputation is the actual control. Asking a registry for a digest and
    trusting that what came back matches it is trusting the registry to be
    honest about the one property being verified.
    """
    if not isinstance(expected_digest, str) or not DIGEST_RE.match(expected_digest):
        _refuse("malformed_expected_digest", repr(expected_digest))

    index_bytes = _fetch_index_bytes(expected_digest, client=client)
    observed = sha256_of(index_bytes)

    if observed != expected_digest:
        # The registry served SOMETHING under the requested digest, and it was
        # not the bound artifact. Never return it, never fall back.
        _refuse("digest_mismatch", f"expected {expected_digest}, computed {observed}")

    try:
        index = json.loads(index_bytes)
    except json.JSONDecodeError as exc:
        _refuse("malformed_index", str(exc))
    if not isinstance(index, dict) or not index.get("manifests"):
        _refuse("malformed_index", "index has no manifests array")

    return {
        "record_type": "MR002_EvaluatorImageResolution",
        "resolved_at": datetime.now(UTC).isoformat().replace("+00:00", "Z"),
        "registry_id": REGISTRY_ID,
        "repository": REPOSITORY,
        "region": REGION,
        "resolved_by": "digest",
        "image_digest": observed,
        "index_media_type": index.get("mediaType"),
        "manifest_count": len(index["manifests"]),
        "resolution_method": "live registry batch_get_image by imageDigest, bytes rehashed",
        "cached": False,
        "satisfies_requirement_7": True,
        "authorizes": (
            "NOTHING - resolution is a precondition for a run, never an authorization for one. "
            "validation_authorization is separate CAS-guarded state."
        ),
    }


def require_image_binding(
    *, expected_digest: str = BOUND_INDEX_DIGEST, client: Any = None
) -> str:
    """The gate a run environment calls BEFORE any evaluation. Returns the digest.

    Thin by design: callers that only need the digest should not have to
    remember which field of the record is authoritative, nor be tempted to read
    a field off a record they obtained some other way.
    """
    return resolve_bound_image(expected_digest=expected_digest, client=client)[
        "image_digest"
    ]


def refuse_receipt(receipt: Any) -> None:
    """Reject any attempt to substitute a custody-monitor receipt for resolution.

    The daily monitor verifies the bound OCI graph and writes receipts. Those
    receipts carry ``satisfies_requirement_7: false`` precisely because a past
    observation is not a present resolution: the image could have become
    unavailable in the interval, which is the exact condition this must catch.

    This exists as a named, tested refusal rather than a comment because the
    substitution is *tempting* -- a receipt is cheap, authoritative-looking, and
    already in the bucket.
    """
    _refuse(
        "receipt_is_not_resolution",
        "a custody-monitor receipt records a PAST observation and can never substitute for "
        "live pre-read resolution (satisfies_requirement_7 is false on every receipt)",
    )


if __name__ == "__main__":  # pragma: no cover - operator entry point
    import sys

    try:
        record = resolve_bound_image()
    except ImageResolutionRefused as exc:
        print(f"RESOLUTION REFUSED: {exc.reason}")
        if exc.detail:
            print(f"  detail: {exc.detail}")
        print(
            "\nFAIL CLOSED. No fallback to a tag, a local image, or a rebuild is permitted."
        )
        sys.exit(1)
    print(json.dumps(record, indent=2, sort_keys=True))
