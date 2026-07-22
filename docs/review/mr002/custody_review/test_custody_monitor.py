"""Negative tests for the MR-002 custody-integrity monitor.

The adjudication requires that immutability/drift testing NEVER occur against the
governing custody repository. These tests therefore drive run_checks() with a
stubbed ECR client and touch no AWS resource at all — no repository, disposable
or otherwise, is mutated.

A monitor that has only ever returned PASS is not a proven control. Each test
below breaks exactly one custody property and asserts the monitor reports FAIL on
the corresponding check.
"""
import json

import pytest
from botocore.exceptions import ClientError

from custody_monitor import AMD64, ATTEST, CONFIG, INDEX, INDEX_MEDIA_TYPE, run_checks

LIFECYCLE_ABSENT = ClientError(
    {"Error": {"Code": "LifecyclePolicyNotFoundException", "Message": "absent"}},
    "GetLifecyclePolicy",
)


def _index_manifest(members=None):
    return json.dumps({
        "schemaVersion": 2,
        "mediaType": INDEX_MEDIA_TYPE,
        "manifests": members if members is not None else [
            {"digest": AMD64, "platform": {"architecture": "amd64", "os": "linux"}},
            {"digest": ATTEST, "platform": {"architecture": "unknown", "os": "unknown"}},
        ],
    })


class FakeEcr:
    """Minimal stub of the ECR client surface run_checks() uses."""

    def __init__(self, *, mutability="IMMUTABLE", lifecycle=None, inventory=None,
                 tags=("qualify-d1e7ffc",), index_body=None, config=CONFIG):
        self.mutability = mutability
        self.lifecycle = lifecycle
        self.inventory = inventory if inventory is not None else [INDEX, AMD64, ATTEST]
        self.tags = list(tags)
        self.index_body = index_body if index_body is not None else _index_manifest()
        self.config = config

    def describe_repositories(self, **_):
        return {"repositories": [{"imageTagMutability": self.mutability}]}

    def get_lifecycle_policy(self, **_):
        if self.lifecycle is None:
            raise LIFECYCLE_ABSENT
        return {"lifecyclePolicyText": self.lifecycle}

    def get_paginator(self, _name):
        inventory, tags = self.inventory, self.tags

        class _P:
            def paginate(self, **_kw):
                yield {"imageDetails": [
                    {"imageDigest": d, "imageTags": tags if d == INDEX else []}
                    for d in inventory
                ]}
        return _P()

    def batch_get_image(self, *, imageIds, **_):  # noqa: N803 - AWS casing
        digest = imageIds[0]["imageDigest"]
        if digest == INDEX:
            return {"images": [{"imageManifest": self.index_body}]}
        return {"images": [{"imageManifest": json.dumps({"config": {"digest": self.config}})}]}


def status_of(findings, name):
    return next(f["status"] for f in findings if f["check"] == name)


def test_byte_exactness_cannot_be_forged_by_a_stub():
    """Every structural check passes on a healthy stub EXCEPT byte-exactness.

    A stub cannot fabricate bytes that hash to the bound index digest — that would
    require a SHA-256 preimage. This is the property content addressing exists to
    provide, so the residual FAIL here is the correct and desirable outcome, not a
    gap in the test. Byte-exactness against the real registry is covered by the
    live run recorded in the submission evidence.
    """
    verdict, findings = run_checks(FakeEcr())
    failed = [f["check"] for f in findings if f["status"] == "FAIL"]
    assert failed == ["index_byte_exact"], failed
    assert verdict == "FAIL"


def test_foreign_object_breaks_single_artifact_invariant():
    """Exactly the probe-residue condition that prompted the invariant."""
    ecr = FakeEcr(inventory=[INDEX, AMD64, ATTEST, "sha256:" + "ec" * 32])
    verdict, findings = run_checks(ecr)
    assert verdict == "FAIL"
    assert status_of(findings, "single_artifact_invariant") == "FAIL"


def test_missing_bound_object_detected():
    verdict, findings = run_checks(FakeEcr(inventory=[INDEX, AMD64]))
    assert verdict == "FAIL"
    assert status_of(findings, "single_artifact_invariant") == "FAIL"


def test_tampered_index_bytes_detected():
    """Substituted content under the bound digest must never read as PASS."""
    tampered = json.dumps({"schemaVersion": 2, "mediaType": INDEX_MEDIA_TYPE, "manifests": []})
    verdict, findings = run_checks(FakeEcr(index_body=tampered))
    assert verdict == "FAIL"
    assert status_of(findings, "index_byte_exact") == "FAIL"


def test_attestation_descriptor_stripped_detected():
    body = _index_manifest([{"digest": AMD64, "platform": {"architecture": "amd64", "os": "linux"}}])
    verdict, findings = run_checks(FakeEcr(index_body=body))
    assert verdict == "FAIL"
    assert status_of(findings, "attestation_accounted") == "FAIL"


def test_extra_platform_descriptor_detected():
    body = _index_manifest([
        {"digest": AMD64, "platform": {"architecture": "amd64", "os": "linux"}},
        {"digest": ATTEST, "platform": {"architecture": "unknown", "os": "unknown"}},
        {"digest": "sha256:" + "aa" * 32, "platform": {"architecture": "arm64", "os": "linux"}},
    ])
    verdict, findings = run_checks(FakeEcr(index_body=body))
    assert verdict == "FAIL"
    assert status_of(findings, "no_extra_descriptors") == "FAIL"


def test_lifecycle_policy_present_detected():
    verdict, findings = run_checks(FakeEcr(lifecycle='{"rules":[]}'))
    assert verdict == "FAIL"
    assert status_of(findings, "no_lifecycle_policy") == "FAIL"


def test_tag_mutability_regression_detected():
    verdict, findings = run_checks(FakeEcr(mutability="MUTABLE"))
    assert verdict == "FAIL"
    assert status_of(findings, "tag_immutability") == "FAIL"


def test_config_digest_drift_detected():
    verdict, findings = run_checks(FakeEcr(config="sha256:" + "cc" * 32))
    assert verdict == "FAIL"
    assert status_of(findings, "config_digest") == "FAIL"


def test_repository_absent_fails_closed_on_detection():
    class Gone(FakeEcr):
        def describe_repositories(self, **_):
            raise ClientError({"Error": {"Code": "RepositoryNotFoundException"}},
                              "DescribeRepositories")

    verdict, findings = run_checks(Gone())
    assert verdict == "FAIL"
    assert status_of(findings, "repository_present") == "FAIL"


def test_registry_unavailable_reports_custody_failure_not_pass():
    """Unavailability must never be mistaken for a healthy custody state."""
    class Down(FakeEcr):
        def batch_get_image(self, **_):
            raise ClientError({"Error": {"Code": "ServiceUnavailable"}}, "BatchGetImage")

    verdict, findings = run_checks(Down())
    assert verdict == "FAIL"
    assert status_of(findings, "index_retrieval") == "FAIL"


def test_receipt_never_claims_to_satisfy_requirement_7():
    from datetime import datetime, timezone

    from custody_monitor import build_receipt
    receipt = build_receipt("PASS", [], datetime.now(timezone.utc))
    assert receipt["satisfies_requirement_7"] is False
    assert receipt["not_an_execution_gate"] is True
    assert receipt["reads_sealed_data"] is False


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
