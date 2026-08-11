"""Tests for WP-D / P11 — the access-control precondition snapshot.

A snapshot is only worth having if it cannot be produced when the controls are
absent. So nearly every test here removes one control and asserts the producer
REFUSES rather than emitting a record that documents the gap. A P11 instance
recording "the OOS DENY is missing" would not be evidence for a prerequisite;
it would be an incident report wearing a prerequisite's name.

The other thread is the P7 trap: this module must prove DENYs by simulation,
never by attempting a read, because CloudTrail logs a denied GetObject too.

Stub AWS clients throughout. No network.
"""

from __future__ import annotations

import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

MODULE_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(MODULE_DIR))


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, MODULE_DIR / f"{name}.py")
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


A = _load("access_control_snapshot")

BUCKET_POLICY = {
    "Version": "2012-10-17",
    "Statement": [
        {"Sid": "DenyInsecureTransport"},
        {"Sid": "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader"},
        {"Sid": "DenyValidationReadsToEveryPrincipalButTheValidationReader"},
        {"Sid": "DenyPermanentDeletionOfSealedObjectVersions"},
    ],
}

TRUST = {
    "Version": "2012-10-17",
    "Statement": [
        {
            "Effect": "Allow",
            "Condition": {
                "StringEquals": {
                    "aws:PrincipalArn":
                        "arn:aws:iam::219024422756:role/mr002-phase3c-run-host-"
                        "NOT-YET-PROVISIONED"
                }
            },
        }
    ],
}


class StubS3:
    def __init__(self, *, policy=None, versioning="Enabled"):
        self._policy = policy if policy is not None else BUCKET_POLICY
        self._versioning = versioning

    def get_bucket_policy(self, **_):
        return {"Policy": json.dumps(self._policy)}

    def get_bucket_versioning(self, **_):
        return {"Status": self._versioning} if self._versioning else {}

    def get_bucket_encryption(self, **_):
        return {"ServerSideEncryptionConfiguration": {"Rules": [
            {"ApplyServerSideEncryptionByDefault": {"SSEAlgorithm": "AES256"},
             "BucketKeyEnabled": True}
        ]}}

    def get_public_access_block(self, **_):
        return {"PublicAccessBlockConfiguration": {"BlockPublicAcls": True}}


class StubTrail:
    def __init__(self, *, logging=True, data_events=True, management=True):
        self._logging = logging
        self._data_events = data_events
        self._management = management

    def get_trail(self, **_):
        return {"Trail": {"TrailARN": "arn:trail", "IsMultiRegionTrail": True,
                          "LogFileValidationEnabled": True,
                          "S3BucketName": "workbench-cloudtrail-219024422756"}}

    def get_trail_status(self, **_):
        return {"IsLogging": self._logging}

    def get_event_selectors(self, **_):
        resources = []
        if self._data_events:
            resources = [{"Type": "AWS::S3::Object",
                          "Values": [f"arn:aws:s3:::{A.BUCKET}/"]}]
        return {"EventSelectors": [{"IncludeManagementEvents": self._management,
                                    "DataResources": resources}]}


class StubIAM:
    def __init__(self, *, trust=None, decisions=None, policies=("p",)):
        self._trust = trust if trust is not None else TRUST
        self._policies = list(policies)
        self._decisions = decisions or {
            ("reader", "validation"): "allowed",
            ("reader", "oos"): "explicitDeny",
            ("reader", "development"): "allowed",
            ("reader", "reference"): "allowed",
            ("admin", "validation"): "explicitDeny",
            ("admin", "oos"): "explicitDeny",
            ("admin", "development"): "allowed",
            ("admin", "reference"): "allowed",
        }

    def get_role(self, **_):
        return {"Role": {"Arn": "arn:role", "AssumeRolePolicyDocument": self._trust}}

    def list_role_policies(self, **_):
        return {"PolicyNames": self._policies}

    def get_role_policy(self, **_):
        return {"PolicyDocument": {"Version": "2012-10-17", "Statement": []}}

    def _decide(self, who, resource):
        prefix = resource.split(f"{A.BUCKET}/")[1].split("/")[0]
        return self._decisions[(who, prefix)]

    def simulate_custom_policy(self, **kwargs):
        return {"EvaluationResults": [
            {"EvalDecision": self._decide("reader", kwargs["ResourceArns"][0])}
        ]}

    def simulate_principal_policy(self, **kwargs):
        return {"EvaluationResults": [
            {"EvalDecision": self._decide("admin", kwargs["ResourceArns"][0])}
        ]}


UPLOAD_MANIFEST = {
    "produced_at_utc": "2026-08-11T15:00:00Z",
    "manifest_identity_sha256": "c" * 64,
}


def _snapshot(s3=None, ct=None, iam=None):
    s3, ct, iam = s3 or StubS3(), ct or StubTrail(), iam or StubIAM()
    bucket_state, bucket_policy = A.collect_bucket_state(s3)
    trail_state = A.collect_trail_state(ct)
    iam_state, identity_policy = A.collect_iam_state(iam)
    decisions = A.prove_access_decisions(
        iam, identity_policy=identity_policy, bucket_policy=bucket_policy
    )
    return A.build_p11(
        bucket_state=bucket_state, trail_state=trail_state, iam_state=iam_state,
        decisions=decisions, upload_manifest=UPLOAD_MANIFEST, custodian="c",
        authority="a", produced_at="2026-08-11T15:30:00Z",
    )


# ---------------------------------------------------------------------------
# The happy path
# ---------------------------------------------------------------------------


def test_snapshot_records_every_p11_criterion(self=None):
    record = _snapshot()
    assert record["prerequisite_id"] == "P11"
    assert record["artifact_kind"] == "RUNTIME_INSTANCE"
    assert all(record["criteria"].values())


def test_snapshot_is_deterministic():
    assert _snapshot()["snapshot_identity_sha256"] == _snapshot()["snapshot_identity_sha256"]


def test_snapshot_grants_nothing():
    assert "validation_authorization remains false" in _snapshot()["boundary"]


def test_reader_role_is_not_assumable_yet():
    iam_state = _snapshot()["iam_state"]
    assert iam_state["assumable_now"] is False
    assert "credential release" in iam_state["credential_release_mechanism"]


# ---------------------------------------------------------------------------
# Fail-closed: remove one control at a time
# ---------------------------------------------------------------------------


def test_refuses_when_the_oos_deny_is_absent():
    policy = copy.deepcopy(BUCKET_POLICY)
    policy["Statement"] = [
        s for s in policy["Statement"]
        if s["Sid"] != "DenyOOSReadsToEveryPrincipalButTheFutureOOSReader"
    ]
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(s3=StubS3(policy=policy))
    assert "bucket_policy_missing_statement" in str(exc.value)


def test_refuses_when_data_events_are_not_enabled():
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(ct=StubTrail(data_events=False))
    assert "s3_data_events_not_enabled_for_bucket" in str(exc.value)


def test_refuses_when_the_trail_is_not_logging():
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(ct=StubTrail(logging=False))
    assert "trail_not_logging" in str(exc.value)


def test_refuses_when_management_events_were_lost():
    """Adding data events replaces the selector set; dropping management events would
    silently disable the ECR custody detection this trail exists for."""
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(ct=StubTrail(management=False))
    assert "management_events_disabled" in str(exc.value)


def test_refuses_when_versioning_is_off():
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(s3=StubS3(versioning=None))
    assert "versioning_not_enabled" in str(exc.value)


def test_refuses_when_the_reader_role_has_no_policy():
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(iam=StubIAM(policies=()))
    assert "reader_role_has_no_inline_policy" in str(exc.value)


def test_refuses_when_the_reader_role_is_already_assumable():
    """An assumable reader before P12 would mean the credential was released early."""
    trust = {"Version": "2012-10-17", "Statement": [
        {"Effect": "Allow", "Condition": {"StringEquals": {
            "aws:PrincipalArn": "arn:aws:iam::219024422756:role/some-live-host"}}}
    ]}
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(iam=StubIAM(trust=trust))
    assert "reader_role_trust_is_not_gated" in str(exc.value)


def test_refuses_when_the_reader_could_read_oos():
    decisions = dict(StubIAM()._decisions)
    decisions[("reader", "oos")] = "allowed"
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(iam=StubIAM(decisions=decisions))
    assert "access_decision_wrong:dedicated_reader:oos" in str(exc.value)


def test_refuses_when_ordinary_development_can_read_validation():
    """The control spec requires read credentials be unavailable to ordinary development."""
    decisions = dict(StubIAM()._decisions)
    decisions[("admin", "validation")] = "allowed"
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(iam=StubIAM(decisions=decisions))
    assert "access_decision_wrong:ordinary_development_principal:validation" in str(exc.value)


def test_refuses_when_the_reader_cannot_read_validation():
    """A DENY so broad the authorized run cannot work is also a failed precondition."""
    decisions = dict(StubIAM()._decisions)
    decisions[("reader", "validation")] = "explicitDeny"
    with pytest.raises(A.SnapshotRefused) as exc:
        _snapshot(iam=StubIAM(decisions=decisions))
    assert "access_decision_wrong:dedicated_reader:validation" in str(exc.value)


# ---------------------------------------------------------------------------
# The P7 trap
# ---------------------------------------------------------------------------


def test_snapshot_module_never_reads_a_sealed_object():
    source = (MODULE_DIR / "access_control_snapshot.py").read_text(encoding="utf-8")
    for forbidden in ("get_object", "head_object", "download_file", "select_object_content"):
        assert f".{forbidden}(" not in source


def test_decisions_record_the_simulation_method():
    method = _snapshot()["access_decisions"]["method"]
    assert "simulation" in method.lower()
    assert "DENIED GetObject" in method


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
