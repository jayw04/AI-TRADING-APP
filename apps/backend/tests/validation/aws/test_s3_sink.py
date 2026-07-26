"""The production external witness: S3 Object-Lock sink (ADR 0046, Step 4B).

Stubber-only; `conftest._no_live_aws` severs the transport.

The sink's job is truncation resistance, and the properties that deliver it are the ones that fail
quietly: that a republished tip is idempotent ONLY when it is byte-identical, that a divergent one is
refused rather than overwritten, that the immutability attestation was asked of the storage and is
bound to the storage actually written through, and that nothing on the class can delete or rewrite a
recorded tip.
"""

from __future__ import annotations

import io
import json

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import ConnectTimeoutError
from botocore.response import StreamingBody
from botocore.stub import Stubber

from app.validation.aws.s3_sink import (
    MAX_LIST_PAGES,
    S3ObjectLockAnchorSink,
    S3SinkError,
    build_s3_object_lock_sink,
)
from app.validation.witness_enforcement import ATTESTATION_FROM_STORAGE
from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    PROTOCOL_VERSION,
    SignedReceipt,
    WitnessedTip,
    serialize_receipt,
)

BUCKET = "workbench-forward-anchors"
PREFIX = "mr002/anchors"
REGION = "us-east-1"
IDENTITY = f"s3://{BUCKET}/{PREFIX}"

TIP = WitnessedTip(sequence=7, session_date="2026-07-27", commit_sha256="a" * 64,
                   anchor_sha256="b" * 64)
KEY = f"{PREFIX}/000007-2026-07-27.json"

RECEIPT = SignedReceipt(
    protocol_version=PROTOCOL_VERSION, algorithm=ALGORITHM_ECDSA_SHA256_P256,
    key_id="arn:aws:kms:us-east-1:219024422756:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d",
    public_key_fingerprint="c" * 64, message_digest="d" * 64, signature="ZmFrZQ==",
    signed_at="2026-07-27T14:00:00Z", witness_identity="kms-witness-forward-validation")


@pytest.fixture
def client():
    return boto3.client("s3", region_name=REGION, aws_access_key_id="testing",
                        aws_secret_access_key="testing", aws_session_token="testing")


@pytest.fixture
def sink(client):
    return S3ObjectLockAnchorSink(client=client, bucket=BUCKET, prefix=PREFIX)


def _payload(tip=TIP, receipt=RECEIPT) -> bytes:
    return S3ObjectLockAnchorSink._canonical_payload(tip, receipt)


def _body(raw: bytes) -> StreamingBody:
    return StreamingBody(io.BytesIO(raw), len(raw))


def _lock_response(*, versioning="Enabled", lock_enabled="Enabled", mode="COMPLIANCE", days=36500):
    retention = {}
    if mode:
        retention["Mode"] = mode
    if days:
        retention["Days"] = days
    configuration = {}
    if lock_enabled:
        configuration["ObjectLockEnabled"] = lock_enabled
    if retention:
        configuration["Rule"] = {"DefaultRetention": retention}
    return ({"Status": versioning} if versioning else {},
            {"ObjectLockConfiguration": configuration})


# ── publish is append-only ───────────────────────────────────────────────────────────────────────────

def test_publish_writes_a_deterministic_key_with_no_overwrite(client, sink):
    with Stubber(client) as stub:
        stub.add_response("put_object", {},
                          {"Bucket": BUCKET, "Key": KEY, "Body": _payload(),
                           "ContentType": "application/json", "IfNoneMatch": "*"})
        sink.publish(TIP, RECEIPT)
        stub.assert_no_pending_responses()        # exact key, exact body, IfNoneMatch present


def test_the_key_is_derived_from_the_governed_sequence_and_session(sink):
    assert sink._key_for(7, "2026-07-27") == KEY
    assert sink._key_for(1, "2026-01-02") == f"{PREFIX}/000001-2026-01-02.json"
    # Zero-padded so lexicographic listing order is sequence order.
    assert sink._key_for(2, "x") < sink._key_for(10, "x")


def test_republishing_the_identical_tip_is_idempotent(client, sink):
    """Only byte-identical counts. The stored object is READ and compared, not assumed."""
    with Stubber(client) as stub:
        stub.add_client_error("put_object", service_error_code="PreconditionFailed",
                              http_status_code=412)
        stub.add_response("get_object", {"Body": _body(_payload())},
                          {"Bucket": BUCKET, "Key": KEY})
        sink.publish(TIP, RECEIPT)                # no exception: already witnessed
        stub.assert_no_pending_responses()


def test_a_divergent_republish_is_refused_not_overwritten(client, sink):
    other = SignedReceipt(**{**RECEIPT.to_dict(), "signature": "ZGlmZmVyZW50"})
    with Stubber(client) as stub:
        stub.add_client_error("put_object", service_error_code="PreconditionFailed",
                              http_status_code=412)
        stub.add_response("get_object", {"Body": _body(_payload(receipt=other))},
                          {"Bucket": BUCKET, "Key": KEY})
        with pytest.raises(S3SinkError, match="refusing to overwrite") as exc:
            sink.publish(TIP, RECEIPT)
    assert exc.value.code == "EXTERNAL_WITNESS_DIVERGES"


def test_the_sink_exposes_no_way_to_delete_or_rewrite_a_tip(sink):
    """Structural, not guarded: there is no delete path to reach."""
    surface = {name for name in dir(sink) if not name.startswith("__")}
    forbidden = {n for n in surface
                 if any(word in n.lower() for word in ("delete", "remove", "overwrite", "truncate",
                                                       "purge", "rewrite"))}
    assert forbidden == set()


# ── read_all round-trips exactly ─────────────────────────────────────────────────────────────────────

def test_read_all_round_trips_the_canonical_receipt(client, sink):
    with Stubber(client) as stub:
        stub.add_response("list_objects_v2", {"Contents": [{"Key": KEY}], "IsTruncated": False},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"})
        stub.add_response("get_object", {"Body": _body(_payload())}, {"Bucket": BUCKET, "Key": KEY})
        records = sink.read_all()

    assert len(records) == 1
    tip, receipt = records[0]
    assert tip == TIP
    # The equality chain_anchor performs between the external and local receipts.
    assert serialize_receipt(receipt) == serialize_receipt(RECEIPT)


def test_read_all_returns_records_in_sequence_order(client, sink):
    tip_2 = WitnessedTip(sequence=2, session_date="2026-07-20", commit_sha256="e" * 64,
                         anchor_sha256="f" * 64)
    key_2 = f"{PREFIX}/000002-2026-07-20.json"
    with Stubber(client) as stub:
        stub.add_response("list_objects_v2",
                          {"Contents": [{"Key": KEY}, {"Key": key_2}], "IsTruncated": False},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"})
        stub.add_response("get_object", {"Body": _body(_payload())}, {"Bucket": BUCKET, "Key": KEY})
        stub.add_response("get_object", {"Body": _body(_payload(tip=tip_2))},
                          {"Bucket": BUCKET, "Key": key_2})
        records = sink.read_all()
    assert [tip.sequence for tip, _ in records] == [2, 7]


def test_pagination_is_followed(client, sink):
    key_2 = f"{PREFIX}/000002-2026-07-20.json"
    tip_2 = WitnessedTip(sequence=2, session_date="2026-07-20", commit_sha256="e" * 64,
                         anchor_sha256="f" * 64)
    with Stubber(client) as stub:
        stub.add_response("list_objects_v2",
                          {"Contents": [{"Key": KEY}], "IsTruncated": True,
                           "NextContinuationToken": "tok"},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"})
        stub.add_response("list_objects_v2",
                          {"Contents": [{"Key": key_2}], "IsTruncated": False},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/", "ContinuationToken": "tok"})
        stub.add_response("get_object", {"Body": _body(_payload())}, {"Bucket": BUCKET, "Key": KEY})
        stub.add_response("get_object", {"Body": _body(_payload(tip=tip_2))},
                          {"Bucket": BUCKET, "Key": key_2})
        assert len(sink.read_all()) == 2


def test_an_unbounded_listing_is_refused(client, sink):
    with Stubber(client) as stub:
        for _ in range(MAX_LIST_PAGES):
            stub.add_response("list_objects_v2",
                              {"Contents": [], "IsTruncated": True, "NextContinuationToken": "t"},
                              None)
        with pytest.raises(S3SinkError, match="pages") as exc:
            sink.read_all()
    assert exc.value.code == "EXTERNAL_WITNESS_INVALID"


# ── strict readback ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("raw, why", [
    (b"{not json", "not valid JSON"),
    (json.dumps({"tip": {}, "receipt": "", "extra": 1}).encode(), "unknown top-level field"),
    (json.dumps({"tip": {"sequence": 7}, "receipt": ""}).encode(), "short tip"),
    (json.dumps({"tip": {"sequence": 7, "session_date": "2026-07-27", "commit_sha256": "a" * 64,
                         "anchor_sha256": "b" * 64},
                 "receipt": {"protocol_version": 2}}).encode(), "receipt as an object"),
])
def test_a_corrupt_record_is_refused(client, sink, raw, why):
    with Stubber(client) as stub:
        stub.add_response("list_objects_v2", {"Contents": [{"Key": KEY}], "IsTruncated": False},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"})
        stub.add_response("get_object", {"Body": _body(raw)}, {"Bucket": BUCKET, "Key": KEY})
        with pytest.raises(S3SinkError) as exc:
            sink.read_all()
    assert exc.value.code == "EXTERNAL_WITNESS_INVALID", why


def test_an_object_filed_under_the_wrong_key_is_refused(client, sink):
    """The deterministic-identity check: content and location must agree."""
    wrong_key = f"{PREFIX}/000009-2026-07-27.json"
    with Stubber(client) as stub:
        stub.add_response("list_objects_v2", {"Contents": [{"Key": wrong_key}],
                                              "IsTruncated": False},
                          {"Bucket": BUCKET, "Prefix": f"{PREFIX}/"})
        stub.add_response("get_object", {"Body": _body(_payload())},
                          {"Bucket": BUCKET, "Key": wrong_key})
        with pytest.raises(S3SinkError, match="belongs at") as exc:
            sink.read_all()
    assert exc.value.code == "EXTERNAL_WITNESS_INVALID"


# ── the immutability attestation ─────────────────────────────────────────────────────────────────────

def test_the_attestation_reports_what_the_storage_answered(client, sink):
    versioning, lock = _lock_response()
    with Stubber(client) as stub:
        stub.add_response("get_bucket_versioning", versioning, {"Bucket": BUCKET})
        stub.add_response("get_object_lock_configuration", lock, {"Bucket": BUCKET})
        attestation = sink.immutability_attestation()

    assert attestation.enforced is True
    assert attestation.source == ATTESTATION_FROM_STORAGE      # asked, not declared
    assert attestation.mode == "COMPLIANCE"
    assert "36500 day(s)" in attestation.detail                # the retention PERIOD is evidenced
    assert "ObjectLockEnabled=Enabled" in attestation.detail
    assert "Status=Enabled" in attestation.detail


@pytest.mark.parametrize("kwargs, why", [
    ({"versioning": "Suspended"}, "versioning alone permits deleting the current version"),
    ({"versioning": None}, "versioning absent"),
    ({"lock_enabled": None}, "object lock not enabled"),
    ({"mode": None, "days": None}, "no default retention"),
    ({"mode": "SOMETHING_ELSE"}, "an unrecognised retention mode"),
    ({"days": None}, "a mode with no period"),
])
def test_a_bucket_that_does_not_enforce_write_once_is_reported_unenforced(client, sink, kwargs, why):
    """Reported, not raised: the GATE turns enforced=False into the refusal, and a failed QUERY is a
    different finding from a truthful 'no'."""
    versioning, lock = _lock_response(**kwargs)
    with Stubber(client) as stub:
        stub.add_response("get_bucket_versioning", versioning, {"Bucket": BUCKET})
        stub.add_response("get_object_lock_configuration", lock, {"Bucket": BUCKET})
        attestation = sink.immutability_attestation()
    assert attestation.enforced is False, why


def test_the_attestation_is_bound_to_the_storage_that_is_written_through(client, sink):
    versioning, lock = _lock_response()
    with Stubber(client) as stub:
        stub.add_response("get_bucket_versioning", versioning, {"Bucket": BUCKET})
        stub.add_response("get_object_lock_configuration", lock, {"Bucket": BUCKET})
        attestation = sink.immutability_attestation()

    # All four identities the gate requires to be equal.
    assert attestation.storage_identity == IDENTITY
    assert attestation.scope == IDENTITY
    assert sink.identity() == IDENTITY
    assert sink.publication_storage_identity() == IDENTITY


def test_a_failed_lock_query_raises_rather_than_reporting_unenforced(client, sink):
    with Stubber(client) as stub:
        stub.add_response("get_bucket_versioning", {"Status": "Enabled"}, {"Bucket": BUCKET})
        stub.add_client_error("get_object_lock_configuration",
                              service_error_code="AccessDenied", http_status_code=403)
        with pytest.raises(S3SinkError) as exc:
            sink.immutability_attestation()
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


# ── failures fail closed ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", ["AccessDenied", "NoSuchBucket", "SlowDown", "InternalError"])
def test_a_client_error_on_publish_becomes_a_governed_refusal(client, sink, code):
    with Stubber(client) as stub:
        stub.add_client_error("put_object", service_error_code=code, http_status_code=400)
        with pytest.raises(S3SinkError) as exc:
            sink.publish(TIP, RECEIPT)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"
    assert code in str(exc.value)


def test_a_transport_failure_on_publish_becomes_a_governed_refusal(sink, monkeypatch):
    def _raise(**_):
        raise ConnectTimeoutError(endpoint_url="https://s3.amazonaws.com")

    monkeypatch.setattr(sink, "_client", type("C", (), {"put_object": staticmethod(_raise)})())
    with pytest.raises(S3SinkError, match="ConnectTimeout") as exc:
        sink.publish(TIP, RECEIPT)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


def test_an_unexpected_sdk_exception_on_read_is_still_translated(sink, monkeypatch):
    def _raise(**_):
        raise RuntimeError("undocumented")

    monkeypatch.setattr(sink, "_client",
                        type("C", (), {"list_objects_v2": staticmethod(_raise)})())
    with pytest.raises(S3SinkError) as exc:
        sink.read_all()
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


# ── the factory ──────────────────────────────────────────────────────────────────────────────────────

def test_the_factory_verifies_the_bucket_region(client, monkeypatch):
    real_client = boto3.client
    captured = {}

    def _fake_client(service, **kwargs):
        captured.update({"service": service, **kwargs})
        made = real_client("s3", region_name=REGION, aws_access_key_id="t",
                           aws_secret_access_key="t", aws_session_token="t")
        stub = Stubber(made)
        # S3 OMITS LocationConstraint for us-east-1, for historical reasons — the case the adapter
        # has to get right, and the one a naive `response["LocationConstraint"]` would crash on.
        stub.add_response("get_bucket_location", {}, {"Bucket": BUCKET})
        stub.activate()
        return made

    monkeypatch.setattr("app.validation.aws.s3_sink.boto3.client", _fake_client)
    sink = build_s3_object_lock_sink(bucket=BUCKET, prefix=PREFIX, region=REGION)

    assert sink.identity() == IDENTITY
    assert captured["service"] == "s3"
    assert captured["region_name"] == REGION
    config: Config = captured["config"]
    assert config.retries == {"mode": "standard", "max_attempts": 3}
    assert config.connect_timeout == 5
    assert config.read_timeout == 10


def test_a_bucket_in_another_region_is_refused(client, monkeypatch):
    real_client = boto3.client

    def _fake_client(service, **kwargs):
        made = real_client("s3", region_name=REGION, aws_access_key_id="t",
                           aws_secret_access_key="t", aws_session_token="t")
        stub = Stubber(made)
        stub.add_response("get_bucket_location", {"LocationConstraint": "eu-west-1"},
                          {"Bucket": BUCKET})
        stub.activate()
        return made

    monkeypatch.setattr("app.validation.aws.s3_sink.boto3.client", _fake_client)
    with pytest.raises(S3SinkError, match="eu-west-1") as exc:
        build_s3_object_lock_sink(bucket=BUCKET, prefix=PREFIX, region=REGION)
    assert exc.value.code == "WITNESS_SINK_NOT_IMMUTABLE"


@pytest.mark.parametrize("missing", ["bucket", "prefix", "region"])
def test_the_factory_requires_its_storage_options(missing, monkeypatch):
    def _forbidden(*a, **k):                      # pragma: no cover - must never be reached
        raise AssertionError("a client was built for an incomplete sink declaration")

    monkeypatch.setattr("app.validation.aws.s3_sink.boto3.client", _forbidden)
    options = {"bucket": BUCKET, "prefix": PREFIX, "region": REGION, missing: "  "}
    with pytest.raises(S3SinkError) as exc:
        build_s3_object_lock_sink(**options)
    assert exc.value.code == "WITNESS_CONFIG_INCOMPLETE"


def test_the_factory_accepts_no_credential_options():
    import inspect

    params = set(inspect.signature(build_s3_object_lock_sink).parameters)
    assert params == {"bucket", "prefix", "region", "client"}
