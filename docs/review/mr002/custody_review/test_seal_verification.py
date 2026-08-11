"""Tests for WP-C — P7 access history and P8 seal verification.

P7's whole claim is a zero. A producer that emits "zero reads" because it
failed to parse the events, dropped the denied ones, or scanned the wrong
prefix would look identical to a producer reporting the truth. So the tests
feed it events it MUST notice: a successful validation read, a successful OOS
read, a denied attempt, a sealing write.

P8 is a conjunction, so each condition is knocked out in turn and the producer
must refuse rather than report a partial pass.

Synthetic CloudTrail records throughout. No network.
"""

from __future__ import annotations

import gzip
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


V = _load("seal_verification")

UPLOAD_MANIFEST = {"manifest_identity_sha256": "c" * 64}


def _event(*, key, name="GetObject", read_only=True, error=None, when="2026-08-11T15:00:00Z",
           principal="arn:aws:iam::219024422756:user/admin", event_id="e1"):
    record = {
        "eventTime": when,
        "eventName": name,
        "eventID": event_id,
        "readOnly": read_only,
        "userIdentity": {"arn": principal},
        "requestParameters": {"bucketName": V.SEALED_BUCKET, "key": key},
    }
    if error:
        record["errorCode"] = error
    return record


def _p7(events, **overrides):
    history = V.build_access_history(events)
    gates = V.gate_values(history["rows"])
    kwargs = {
        "coverage_start": "2026-08-11T14:40:00Z",
        "custodian": "c",
        "authority": "a",
        "produced_at": "2026-08-11T16:00:00Z",
        "upload_manifest": UPLOAD_MANIFEST,
    }
    kwargs.update(overrides)
    return V.build_p7(history, gates, **kwargs)


# ---------------------------------------------------------------------------
# P7 must actually notice reads
# ---------------------------------------------------------------------------


def test_a_successful_validation_read_refuses_the_gate():
    """The single most important negative: P7 must not emit a zero when a read happened."""
    with pytest.raises(V.VerificationRefused) as exc:
        _p7([_event(key="validation/prices.parquet")])
    assert "validation_read_before_authorization" in str(exc.value)


def test_a_successful_oos_read_refuses_the_gate():
    with pytest.raises(V.VerificationRefused) as exc:
        _p7([_event(key="oos/prices.parquet")])
    assert "oos_read_before_validation" in str(exc.value)


def test_sealing_writes_do_not_trip_the_read_gate():
    """PutObject during sealing is expected; counting it as a read would make the
    prerequisite unsatisfiable by construction."""
    record = _p7([_event(key="validation/prices.parquet", name="PutObject", read_only=False)])
    assert record["observed_gate_values"]["sealing_writes"] == 1
    assert record["observed_gate_values"]["validation_access_events_before_authorization"] == 0


def test_denied_attempts_are_recorded_but_do_not_trip_the_gate():
    """A denied read is evidence, not a violation — and must not be silently dropped."""
    record = _p7([_event(key="oos/prices.parquet", error="AccessDenied")])
    assert record["observed_gate_values"]["oos_read_attempts_denied"] == 1
    assert record["observed_gate_values"]["oos_access_events_before_validation"] == 0
    assert record["access_history"][0]["authorized"] is False


def test_open_prefix_reads_are_not_gated():
    record = _p7([_event(key="development/prices.parquet")])
    assert record["gates_met"] is True


# ---------------------------------------------------------------------------
# Hash chain
# ---------------------------------------------------------------------------


def test_chain_links_every_row_and_verifies():
    events = [
        _event(key="validation/prices.parquet", name="PutObject", read_only=False,
               when="2026-08-11T14:50:00Z", event_id="a"),
        _event(key="oos/prices.parquet", name="PutObject", read_only=False,
               when="2026-08-11T14:51:00Z", event_id="b"),
    ]
    history = V.build_access_history(events)
    assert V.chain_verifies(history["rows"])
    assert history["rows"][0]["hash_chain_prev"] == V.ZERO
    assert history["rows"][1]["hash_chain_prev"] == history["rows"][0]["hash_chain_row"]


def test_a_tampered_row_breaks_the_chain():
    events = [
        _event(key="validation/prices.parquet", name="PutObject", read_only=False,
               event_id="a"),
        _event(key="validation/actions.parquet", name="PutObject", read_only=False,
               event_id="b"),
    ]
    history = V.build_access_history(events)
    history["rows"][0]["principal"] = "arn:aws:iam::219024422756:user/someone-else"
    assert not V.chain_verifies(history["rows"])


def test_a_deleted_row_breaks_the_chain():
    events = [
        _event(key="validation/a.parquet", name="PutObject", read_only=False, event_id="a"),
        _event(key="validation/b.parquet", name="PutObject", read_only=False, event_id="b"),
        _event(key="validation/c.parquet", name="PutObject", read_only=False, event_id="c"),
    ]
    history = V.build_access_history(events)
    del history["rows"][1]
    assert not V.chain_verifies(history["rows"])


def test_empty_history_is_a_valid_chain():
    record = _p7([])
    assert record["hash_chain"]["rows"] == 0
    assert record["hash_chain"]["verifies"] is True


# ---------------------------------------------------------------------------
# Event parsing
# ---------------------------------------------------------------------------


def test_events_are_matched_by_resource_arn_when_key_is_absent():
    record = {
        "eventTime": "2026-08-11T15:00:00Z", "eventName": "GetObject", "readOnly": True,
        "userIdentity": {"arn": "arn:x"},
        "resources": [{"ARN": f"arn:aws:s3:::{V.SEALED_BUCKET}/validation/prices.parquet"}],
    }
    assert V._names_sealed_bucket(record)
    assert V._object_key(record) == "validation/prices.parquet"
    assert V._partition(V._object_key(record)) == "validation"


def test_events_on_other_buckets_are_ignored():
    record = {"requestParameters": {"bucketName": "some-other-bucket", "key": "x"}}
    assert not V._names_sealed_bucket(record)


def test_collect_events_reads_gzipped_cloudtrail_objects():
    payload = {"Records": [_event(key="validation/prices.parquet", name="PutObject",
                                  read_only=False)]}
    blob = gzip.compress(json.dumps(payload).encode())

    class StubS3:
        def list_objects_v2(self, **_):
            return {"Contents": [{"Key": "AWSLogs/x.json.gz"}], "IsTruncated": False}

        def get_object(self, **_):
            class Body:
                def read(self_inner):
                    return blob
            return {"Body": Body()}

    events = V.collect_events(StubS3(), ["2026-08-11"])
    assert len(events) == 1


def test_log_prefixes_are_day_scoped():
    assert V.log_prefixes(["2026-08-11"]) == [
        f"AWSLogs/{V.ACCOUNT}/CloudTrail/us-east-1/2026/08/11/"
    ]


# ---------------------------------------------------------------------------
# P7 honesty about coverage
# ---------------------------------------------------------------------------


def test_p7_discloses_what_it_does_not_cover():
    """A P7 implying continuous coverage since the procedural seal would be false."""
    record = _p7([])
    assert "NOT_covered" in record["coverage"]
    assert "DuckDB file on the developer workstation" in record["coverage"]["NOT_covered"]
    assert record["coverage"]["covers_partition_from_before_it_existed"] is True


def test_p7_grants_nothing():
    assert "validation_authorization remains false" in _p7([])["boundary"]


# ---------------------------------------------------------------------------
# P8 — a conjunction, knocked out one condition at a time
# ---------------------------------------------------------------------------


def _p11(reader_oos="explicitDeny", admin_oos="explicitDeny"):
    return {
        "snapshot_identity_sha256": "d" * 64,
        "access_decisions": {
            "dedicated_reader": {"oos": reader_oos},
            "ordinary_development_principal": {"oos": admin_oos},
        },
    }


def _p6():
    return {
        "commitment_identity_sha256": "e" * 64,
        "validation_partition": {"partition_content_sha256": "f" * 64},
    }


def _p8(**overrides):
    kwargs = {
        "p6": _p6(),
        "p7": _p7([]),
        "p11": _p11(),
        "commitment": {"stable": True, "committed_sha256": "f" * 64},
        "custodian": "c",
        "authority": "a",
        "produced_at": "2026-08-11T16:00:00Z",
    }
    kwargs.update(overrides)
    return V.build_p8(**kwargs)


def test_p8_reports_all_four_conditions():
    record = _p8()
    assert set(record["conditions"]) == {
        "content_commitment_stable",
        "no_access_before_authorization",
        "opened_object_ledger_reconciles",
        "oos_deny_in_force",
    }
    assert record["all_conditions_met"] is True


def test_p8_refuses_when_the_oos_deny_is_not_in_force():
    with pytest.raises(V.VerificationRefused) as exc:
        _p8(p11=_p11(reader_oos="allowed"))
    assert "oos_deny_not_in_force" in str(exc.value)


def test_p8_refuses_when_ordinary_development_can_read_oos():
    with pytest.raises(V.VerificationRefused) as exc:
        _p8(p11=_p11(admin_oos="allowed"))
    assert "oos_deny_not_in_force" in str(exc.value)


def test_p8_states_the_ledger_reconciliation_is_trivial():
    """Overstating an empty reconciliation as a substantive check is how a verifier
    later mistakes it for one."""
    note = _p8()["conditions"]["opened_object_ledger_reconciles"]["note"]
    assert "trivial" in note
    assert "No authorized run has occurred" in note


def test_p8_binds_the_three_records_it_depends_on():
    bound = _p8()["bound_identities"]
    assert bound["p6_commitment_identity_sha256"] == "e" * 64
    assert bound["p11_snapshot_identity_sha256"] == "d" * 64
    assert len(bound["p7_history_identity_sha256"]) == 64


def test_p8_grants_nothing():
    boundary = _p8()["boundary"]
    assert "does not" in boundary and "authorize a run" in boundary
    assert "single validation opening remains unconsumed" in boundary


def test_identity_hashes_are_stable_and_content_sensitive():
    first = _p8()
    assert V._identity(first) == first["report_identity_sha256"]
    mutated = dict(first)
    mutated["all_conditions_met"] = False
    assert V._identity(mutated) != first["report_identity_sha256"]


if __name__ == "__main__":
    raise SystemExit(pytest.main([__file__, "-q"]))
