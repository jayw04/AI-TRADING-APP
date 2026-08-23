"""Stub-driven tests for the EC2 fleet audit — no AWS resource is touched.

Mirrors the custody-monitor test pattern: a fake EC2 client drives run_checks()
through every verdict path. Never probes the real fleet.
"""

from __future__ import annotations

from datetime import datetime, timezone

import ec2_fleet_audit as audit


class StubEC2:
    def __init__(self, instances=None, volumes=None):
        self._instances = instances or []
        self._volumes = volumes if volumes is not None else []

    def describe_instances(self):
        return {"Reservations": [{"Instances": self._instances}]}

    def describe_volumes(self, Filters=None):  # noqa: N803 - boto3 signature
        return {"Volumes": self._volumes}


def _instance(iid, state="running", name="box"):
    return {
        "InstanceId": iid,
        "State": {"Name": state},
        "Tags": [{"Key": "Name", "Value": name}],
    }


NOW = datetime(2026, 8, 17, 13, 5, tzinfo=timezone.utc)
AFTER_WS5_LAPSE = datetime(2026, 8, 19, 13, 5, tzinfo=timezone.utc)

ALLOWED = list(audit.AUTHORIZED_RUNNING)


def _fleet(states=None):
    states = states or {}
    return [_instance(iid, states.get(iid, "running")) for iid in ALLOWED]


def _by_name(findings):
    return {f["check"]: f for f in findings}


def test_all_authorized_running_passes():
    verdict, findings = audit.run_checks(StubEC2(instances=_fleet()), NOW)
    assert verdict == "PASS"
    assert all(f["status"] == "PASS" for f in findings)


def test_unauthorized_running_instance_fails_and_is_named():
    fleet = _fleet() + [_instance("i-0deadbeefcafe0000", name="mystery-box")]
    verdict, findings = audit.run_checks(StubEC2(instances=fleet), NOW)
    assert verdict == "FAIL"
    bad = _by_name(findings)["no_unauthorized_running"]
    assert bad["status"] == "FAIL"
    assert "i-0deadbeefcafe0000" in bad["detail"]
    assert "mystery-box" in bad["detail"]


def test_pending_counts_as_running():
    fleet = _fleet() + [_instance("i-0deadbeefcafe0000", state="pending")]
    verdict, findings = audit.run_checks(StubEC2(instances=fleet), NOW)
    assert verdict == "FAIL"
    assert _by_name(findings)["no_unauthorized_running"]["status"] == "FAIL"


def test_stopped_unlisted_instance_is_not_a_violation():
    fleet = _fleet() + [_instance("i-0deadbeefcafe0000", state="stopped")]
    verdict, findings = audit.run_checks(StubEC2(instances=fleet), NOW)
    assert verdict == "PASS"


SYNTHETIC_EXPIRING = {
    "i-0synthetic0expiry0": {
        "name": "synthetic-time-boxed",
        "reason": "Test fixture: exercises the expiry checks without depending on whichever entries the production allowlist happens to carry.",
        "authorized_until": "2026-08-18T21:41:00+00:00",
    },
}


def _with_expiring(monkeypatch):
    """Install a time-boxed allowlist entry for the duration of one test.

    The expiry checks used to be exercised by whatever time-boxed entry the real
    allowlist happened to hold — ADR-0043 WS5, until it was pruned at closeout.
    Pruning it left zero time-boxed entries, so those tests either failed on their
    own precondition or silently stopped asserting anything. The fixture makes the
    coverage independent of production data.
    """
    combined = {**audit.AUTHORIZED_RUNNING, **SYNTHETIC_EXPIRING}
    monkeypatch.setattr(audit, "AUTHORIZED_RUNNING", combined)
    return combined


def test_expired_authorization_fails_while_instance_runs(monkeypatch):
    combined = _with_expiring(monkeypatch)
    expiring = [iid for iid, e in combined.items() if e["authorized_until"]]
    assert expiring, "fixture must supply a time-boxed allowlist entry"
    fleet = [_instance(iid) for iid in combined]
    verdict, findings = audit.run_checks(StubEC2(instances=fleet), AFTER_WS5_LAPSE)
    assert verdict == "FAIL"
    bad = _by_name(findings)["no_expired_authorization"]
    assert bad["status"] == "FAIL"
    assert expiring[0] in bad["detail"]


def test_expired_entry_for_terminated_instance_does_not_fail(monkeypatch):
    combined = _with_expiring(monkeypatch)
    states = {iid: "terminated" for iid, e in combined.items() if e["authorized_until"]}
    assert states, "fixture must supply a time-boxed allowlist entry"
    fleet = [_instance(iid, states.get(iid, "running")) for iid in combined]
    _, findings = audit.run_checks(StubEC2(instances=fleet), AFTER_WS5_LAPSE)
    assert _by_name(findings)["no_expired_authorization"]["status"] == "PASS"


def test_allowlist_entry_with_no_matching_instance_fails():
    fleet = [_instance(iid) for iid in ALLOWED[1:]]
    verdict, findings = audit.run_checks(StubEC2(instances=fleet), NOW)
    assert verdict == "FAIL"
    stale = _by_name(findings)["allowlist_entries_exist"]
    assert stale["status"] == "FAIL"
    assert ALLOWED[0] in stale["detail"]


def test_orphaned_volume_fails_and_is_named():
    vols = [{"VolumeId": "vol-0dbd2b85247c52911", "Size": 30}]
    verdict, findings = audit.run_checks(StubEC2(instances=_fleet(), volumes=vols), NOW)
    assert verdict == "FAIL"
    bad = _by_name(findings)["no_orphaned_ebs_volumes"]
    assert bad["status"] == "FAIL"
    assert "vol-0dbd2b85247c52911" in bad["detail"]


def test_every_allowlist_entry_carries_a_reason():
    for entry in audit.AUTHORIZED_RUNNING.values():
        assert entry["reason"].strip()


def test_receipt_is_detection_only_and_self_hashed():
    verdict, findings = audit.run_checks(StubEC2(instances=_fleet()), NOW)
    receipt = audit.build_receipt(verdict, findings, NOW)
    assert receipt["record_type"] == "WorkbenchFleetAuditReceipt"
    assert "authorizes nothing" in receipt["scope"]
    assert len(receipt["body_sha256"]) == 64
    assert receipt["authorized_running"] == audit.AUTHORIZED_RUNNING
