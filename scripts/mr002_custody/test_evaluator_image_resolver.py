"""Tests for custody Requirement 7 — the fail-closed evaluator image resolver.

These are not incidental unit tests. Plan v1.3.1 adds condition **C-R7** to the
future D3 submission:

    the Requirement-7 fail-closed resolver is BUILT, is the SOLE resolution path
    used by P10 and the run environment, and DEMONSTRATES FAIL-CLOSED on digest
    miss, mismatch, and registry unavailability

The three demonstrations C-R7 names are
:func:`test_fail_closed_on_digest_miss`,
:func:`test_fail_closed_on_digest_mismatch` and
:func:`test_fail_closed_on_registry_unavailable`. The rest exist because
"fails closed" is a claim about what the code will NOT do, and absence is only
demonstrable by trying the thing.

No network. A fake ECR client is injected; the resolver still rehashes whatever
bytes it is handed, so injection cannot be used to smuggle a pass.
"""

from __future__ import annotations

import contextlib
import hashlib
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_PATH = Path(__file__).resolve().parent / "resolve_evaluator_image.py"
_spec = importlib.util.spec_from_file_location("resolve_evaluator_image", MODULE_PATH)
R = importlib.util.module_from_spec(_spec)
sys.modules["resolve_evaluator_image"] = R
_spec.loader.exec_module(R)


def _index_bytes(manifest_count: int = 2) -> bytes:
    """A syntactically valid OCI index. Its digest is whatever it hashes to."""
    return json.dumps(
        {
            "schemaVersion": 2,
            "mediaType": "application/vnd.oci.image.index.v1+json",
            "manifests": [
                {
                    "mediaType": "application/vnd.oci.image.manifest.v1+json",
                    "digest": f"sha256:{i:064x}",
                    "size": 100 + i,
                }
                for i in range(manifest_count)
            ],
        },
        sort_keys=True,
    ).encode("utf-8")


def _digest_of(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


class FakeEcr:
    """Minimal ECR double. Records what it was asked for so we can prove intent."""

    def __init__(
        self, *, manifest: bytes | None = None, failures=None, raises=None, images=None
    ):
        self.manifest = manifest
        self.failures = failures or []
        self.raises = raises
        self.images = images
        self.calls: list[dict] = []

    def batch_get_image(self, **kwargs):
        self.calls.append(kwargs)
        if self.raises:
            raise self.raises
        if self.images is not None:
            return {"images": self.images, "failures": self.failures}
        if self.failures:
            return {"images": [], "failures": self.failures}
        return {
            "images": [{"imageManifest": self.manifest.decode("utf-8")}],
            "failures": [],
        }


# ---------------------------------------------------------------- happy path


def test_resolves_when_registry_serves_the_bound_bytes():
    body = _index_bytes()
    client = FakeEcr(manifest=body)

    record = R.resolve_bound_image(expected_digest=_digest_of(body), client=client)

    assert record["image_digest"] == _digest_of(body)
    assert record["resolved_by"] == "digest"
    assert record["satisfies_requirement_7"] is True
    assert record["cached"] is False
    assert record["manifest_count"] == 2


def test_require_image_binding_returns_the_digest():
    body = _index_bytes()
    digest = _digest_of(body)
    assert (
        R.require_image_binding(expected_digest=digest, client=FakeEcr(manifest=body))
        == digest
    )


# ------------------------------------------- C-R7: the three named demonstrations


def test_fail_closed_on_digest_miss():
    """C-R7 (1/3): the bound digest is not in the registry."""
    client = FakeEcr(failures=[{"failureCode": "ImageNotFound", "imageId": {}}])

    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(client=client)

    assert exc.value.reason == "digest_not_found"


def test_fail_closed_on_digest_mismatch():
    """C-R7 (2/3): the registry serves something else under the requested digest.

    This is the case a resolver that trusts the registry's own answer would miss
    entirely, which is why the bytes are rehashed rather than assumed.
    """
    served = _index_bytes(manifest_count=3)
    requested = _digest_of(_index_bytes(manifest_count=2))
    assert _digest_of(served) != requested

    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(
            expected_digest=requested, client=FakeEcr(manifest=served)
        )

    assert exc.value.reason == "digest_mismatch"
    assert requested in exc.value.detail


def test_fail_closed_on_registry_unavailable():
    """C-R7 (3/3): the registry cannot be reached at all."""
    client = FakeEcr(raises=ConnectionError("endpoint unreachable"))

    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(client=client)

    assert exc.value.reason == "registry_unavailable"
    assert "ConnectionError" in exc.value.detail


# -------------------------------------------------- no fallback of any kind


def test_never_requests_a_tag():
    """'No fallback to a tag' has to be observable, not asserted in a comment."""
    body = _index_bytes()
    client = FakeEcr(manifest=body)

    R.resolve_bound_image(expected_digest=_digest_of(body), client=client)

    assert len(client.calls) == 1
    image_ids = client.calls[0]["imageIds"]
    assert image_ids == [{"imageDigest": _digest_of(body)}]
    assert all("imageTag" not in i for i in image_ids), "a tag is not an identity"


def test_does_not_retry_or_fall_back_after_a_failure():
    """One attempt. A retry loop is where a tag fallback historically appears."""
    client = FakeEcr(failures=[{"failureCode": "ImageNotFound"}])

    with pytest.raises(R.ImageResolutionRefused):
        R.resolve_bound_image(client=client)

    assert len(client.calls) == 1


def test_failure_returns_nothing_at_all():
    """Fail-closed means RAISE. A sentinel return can be ignored by a caller."""
    client = FakeEcr(raises=TimeoutError("boom"))
    result = "untouched"
    with contextlib.suppress(R.ImageResolutionRefused):
        result = R.resolve_bound_image(client=client)
    assert result == "untouched"


def test_a_custody_monitor_receipt_can_never_substitute():
    """The monitor's receipts say satisfies_requirement_7: false. Enforce it."""
    receipt = {
        "satisfies_requirement_7": False,
        "verified": "11/11",
        "when": "yesterday",
    }

    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.refuse_receipt(receipt)

    assert exc.value.reason == "receipt_is_not_resolution"


def test_resolution_is_not_cached_between_calls():
    """A cached success is exactly the substitute Requirement 7 forbids.

    The image can become unavailable between calls; that is the condition this
    must catch, so a prior success must not make a later call succeed.
    """
    body = _index_bytes()
    digest = _digest_of(body)
    ok = FakeEcr(manifest=body)
    R.resolve_bound_image(expected_digest=digest, client=ok)

    gone = FakeEcr(failures=[{"failureCode": "ImageNotFound"}])
    with pytest.raises(R.ImageResolutionRefused):
        R.resolve_bound_image(expected_digest=digest, client=gone)


# ------------------------------------------------------ malformed responses


@pytest.mark.parametrize(
    ("images", "reason"),
    [
        ([], "digest_not_found"),
        ([{"imageManifest": "x"}, {"imageManifest": "y"}], "ambiguous_resolution"),
        ([{}], "malformed_response"),
        ([{"imageManifest": ""}], "malformed_response"),
        ([{"imageManifest": 42}], "malformed_response"),
    ],
)
def test_malformed_registry_responses_refuse(images, reason):
    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(client=FakeEcr(images=images))
    assert exc.value.reason == reason


def test_non_json_body_that_hashes_correctly_still_refuses():
    """Digest agreement alone is not enough; it must be a usable OCI index.

    Contrived, but the alternative is returning a 'resolved' record for bytes
    that cannot be an image.
    """
    body = b"not json at all"
    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(
            expected_digest=_digest_of(body), client=FakeEcr(manifest=body)
        )
    assert exc.value.reason == "malformed_index"


def test_json_without_manifests_refuses():
    body = json.dumps({"schemaVersion": 2}, sort_keys=True).encode("utf-8")
    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(
            expected_digest=_digest_of(body), client=FakeEcr(manifest=body)
        )
    assert exc.value.reason == "malformed_index"


@pytest.mark.parametrize(
    "bad", ["", "sha256:short", "60b15568" * 8, "sha512:" + "a" * 64, None, 12345]
)
def test_malformed_expected_digest_refuses_before_any_call(bad):
    client = FakeEcr(manifest=_index_bytes())
    with pytest.raises(R.ImageResolutionRefused) as exc:
        R.resolve_bound_image(expected_digest=bad, client=client)
    assert exc.value.reason == "malformed_expected_digest"
    assert client.calls == [], "must refuse before touching the registry"


# -------------------------------------------------------------- the binding


def test_bound_digest_is_the_preregistered_evaluator_index():
    """Guards the constant itself. Changing it is a governance event."""
    assert R.BOUND_INDEX_DIGEST == (
        "sha256:60b15568aa5960ee04cf10b8c9b006d2ee702aa815a17384beffc979ed4554c9"
    )
    assert R.REPOSITORY == "mr002-evaluator-p5"
    assert R.REGISTRY_ID == "219024422756"


def test_module_does_not_import_boto3_at_module_scope():
    """The 2026-07-25 defect: a module-scope SDK import breaks offline paths."""
    source = MODULE_PATH.read_text(encoding="utf-8")
    top_level = [
        line
        for line in source.splitlines()
        if line.startswith(
            ("import boto3", "from boto3", "import botocore", "from botocore")
        )
    ]
    assert not top_level, f"boto3 imported at module scope: {top_level}"


def test_resolution_record_claims_no_authority():
    body = _index_bytes()
    record = R.resolve_bound_image(
        expected_digest=_digest_of(body), client=FakeEcr(manifest=body)
    )
    assert "NOTHING" in record["authorizes"]
