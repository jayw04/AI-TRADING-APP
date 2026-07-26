"""The KMS signer reaches production the way a deployment actually wires it (ADR 0046).

The unit tests construct `KmsAnchorSigner` directly. That proves the adapter, not the seam. This module
drives the REAL gate — `enforce_production_witness` — with the real `witness.signer.factory` string
from governed configuration, so what is under test is the whole path a deployment uses: config load,
private-key-material scan, factory import, reference refusal, in-process-key refusal, and the signer
challenge against the deployment-installed verifying key.

Only KMS itself is a stub. Nothing here creates an AWS resource or reaches the network
(`conftest._no_live_aws`).

Step 4A adds no code to composition, and that is the finding rather than an omission: R5e's factory
seam already accepts a production signer, so the adapter plugs in without touching
`witness_enforcement` or `session_composition`. These tests are what proves it.
"""

from __future__ import annotations

import hashlib
from typing import Any

import boto3
import pytest
from botocore.stub import Stubber
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.validation.aws.kms_signer import KMS_KEY_SPEC, KMS_SIGNING_ALGORITHM
from app.validation.witness_config import WitnessConfigError, load_witness_config
from app.validation.witness_enforcement import (
    CHALLENGE_SEQUENCE,
    CHALLENGE_SESSION,
    WitnessEnforcementError,
    _can_enforce_path_guarantees,
    enforce_production_witness,
)
from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    PROTOCOL_VERSION,
    WitnessedTip,
    WitnessSigningIdentity,
    build_witness_envelope,
    envelope_digest,
    fingerprint_public_key,
)

KEY_ARN = "arn:aws:kms:us-east-1:219024422756:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d"
IDENTITY = "kms-witness-forward-validation"
SIGNER_FACTORY = "app.validation.aws.kms_signer:build_kms_anchor_signer"
DOUBLES = "tests.validation.witness_doubles"
NONCE = "2026-07-26T00:00:00Z"

# The same POSIX-only guard the rest of the enforcement suite uses: the key-path walk needs ownership
# and O_NOFOLLOW guarantees Windows cannot provide, so the gate fails closed there by design and
# exercising it would test nothing. Linux CI runs these.
POSIX_ONLY = pytest.mark.skipif(
    not _can_enforce_path_guarantees(),
    reason="a PRODUCTION witness requires POSIX ownership/no-follow guarantees; the gate fails closed "
           "here by design")


@pytest.fixture
def aws(monkeypatch):
    """The single patch point for `boto3.client`, dispatching by service name.

    Two things make a per-test or per-fixture patch wrong here, and both produce a PASSING test that
    proves nothing:

      * `app.validation.aws.kms_signer.boto3` and `app.validation.aws.s3_sink.boto3` are the SAME
        module object, so two fixtures each patching "their" module silently clobber each other and one
        adapter receives the other's client.
      * A test that captures `real_client = boto3.client` in its own body captures whatever a fixture
        already installed — so a test meaning to substitute a different client ends up wrapping the
        original stub, and the behaviour it intended to break never breaks.

    So the genuine factory is captured ONCE, here, before anything is patched, and tests register a
    builder per service instead of patching again.
    """
    real_client = boto3.client                    # captured before any patching
    builders: dict[str, Any] = {}

    def _dispatch(service: str, **kwargs: Any) -> Any:
        if service not in builders:
            raise AssertionError(
                f"no stub is registered for AWS service {service!r}; the test must register one "
                f"rather than reach a real client")
        return builders[service](real_client)

    monkeypatch.setattr("app.validation.aws.kms_signer.boto3.client", _dispatch)
    return builders


def _kms_stub(real_client: Any, *, der: bytes, private: Any, sign: bool = True) -> Any:
    """A KMS client stubbed to return `der` from GetPublicKey and, optionally, a REAL signature over
    the gate's deterministic challenge probe.

    The signature has to be real: a canned one would make the challenge fail and the test would prove
    the opposite of what it claims.
    """
    client = real_client("kms", region_name="us-east-1", aws_access_key_id="t",
                         aws_secret_access_key="t", aws_session_token="t")
    stub = Stubber(client)
    stub.add_response("get_public_key",
                      {"KeyId": KEY_ARN, "KeySpec": KMS_KEY_SPEC,
                       "SigningAlgorithms": [KMS_SIGNING_ALGORITHM], "PublicKey": der},
                      {"KeyId": KEY_ARN})
    if sign:
        probe_digest = hashlib.sha256(f"{CHALLENGE_SESSION}|{NONCE}".encode()).hexdigest()
        probe = WitnessedTip(sequence=CHALLENGE_SEQUENCE, session_date=CHALLENGE_SESSION,
                             commit_sha256=probe_digest,
                             anchor_sha256=hashlib.sha256(probe_digest.encode()).hexdigest())
        identity = WitnessSigningIdentity(
            protocol_version=PROTOCOL_VERSION, algorithm=ALGORITHM_ECDSA_SHA256_P256,
            key_id=KEY_ARN, public_key_fingerprint=fingerprint_public_key(der))
        digest = envelope_digest(build_witness_envelope(probe, identity))
        signature = private.sign(digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
        stub.add_response("sign",
                          {"KeyId": KEY_ARN, "Signature": signature,
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
    stub.activate()
    return client


@pytest.fixture
def deployment(tmp_path, aws):
    """A deployment-installed P-256 key, plus a KMS stub holding the matching private half.

    `trusted_root` is `tmp_path` itself rather than an ancestor: pytest's temporary directories live
    under a world-writable /tmp, which the key-path walk correctly refuses.
    """
    private = ec.generate_private_key(ec.SECP256R1())
    der = private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    key_path = tmp_path / "anchor_witness.der"
    key_path.write_bytes(der)

    aws["kms"] = lambda real: _kms_stub(real, der=der, private=private)
    return {"private": private, "der": der, "path": key_path, "root": tmp_path, "aws": aws}


def _config(deployment, *, signer_options=None):
    return load_witness_config({
        "profile": "PRODUCTION",
        "algorithm": "ECDSA_SHA_256_P256",
        "key_id": KEY_ARN,
        "trusted_root": str(deployment["root"]),
        "public_key_path": str(deployment["path"]),
        "signer": {
            "factory": SIGNER_FACTORY,
            "identity": IDENTITY,
            "options": signer_options if signer_options is not None
            else {"key_arn": KEY_ARN, "witness_identity": IDENTITY},
        },
        "sink": {"factory": f"{DOUBLES}:build_sink", "identity": "s3://anchors/prod",
                 "options": {}},
    })


@POSIX_ONLY
def test_the_gate_accepts_the_kms_signer_and_evidences_the_challenge(deployment):
    """The property Step 4A exists to establish: a governed session can now be witnessed."""
    witness = enforce_production_witness(_config(deployment), nonce=NONCE)

    assert type(witness.signer).__name__ == "KmsAnchorSigner"
    challenge = witness.evidence["signer"]["key_challenge"]
    assert challenge["challenged"] is True
    # The two fingerprints the challenge compared: the installed key, and the key the signer used.
    assert challenge["trusted_public_key_fingerprint"] == fingerprint_public_key(deployment["der"])
    assert challenge["receipt_public_key_fingerprint"] == challenge["trusted_public_key_fingerprint"]
    assert challenge["receipt_algorithm"] == ALGORITHM_ECDSA_SHA256_P256
    assert challenge["receipt_key_id"] == KEY_ARN
    # The verifying key came from the deployment, never from the signer.
    assert witness.evidence["verifying_key"]["obtained_from_signer"] is False


@POSIX_ONLY
def test_a_signer_wired_to_a_different_key_is_refused_by_the_challenge(deployment):
    """The wrong-key wiring the returned-ARN rule exists to expose.

    The signer is pointed at a key whose material differs from the installed one. Nothing about the
    configuration looks wrong; the refusal comes from the challenge comparing fingerprints.
    """
    other = ec.generate_private_key(ec.SECP256R1())
    other_der = other.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    # Re-register the KMS builder rather than patching boto3 again — see the `aws` fixture for why a
    # second patch would quietly wrap the first stub instead of replacing it.
    deployment["aws"]["kms"] = lambda real: _kms_stub(real, der=other_der, private=other)

    with pytest.raises(WitnessEnforcementError) as exc:
        enforce_production_witness(_config(deployment), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_KEY_UNTRUSTED"


@POSIX_ONLY
def test_an_unreachable_kms_is_a_refusal_not_a_degraded_run(deployment):
    def _unreachable(_real):
        raise RuntimeError("KMS endpoint unreachable")

    deployment["aws"]["kms"] = _unreachable
    with pytest.raises(WitnessEnforcementError) as exc:
        enforce_production_witness(_config(deployment), nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED"


@POSIX_ONLY
def test_a_bad_arn_in_governed_options_is_refused_at_composition(deployment):
    with pytest.raises(WitnessEnforcementError) as exc:
        enforce_production_witness(
            _config(deployment, signer_options={"key_arn": f"{KEY_ARN}-alias",
                                                "witness_identity": IDENTITY}),
            nonce=NONCE)
    assert exc.value.code == "WITNESS_SIGNER_NOT_SEPARATELY_CONTROLLED"
    assert "immutable KMS key ARN" in str(exc.value)


def test_credentials_in_signer_options_are_refused_before_the_factory_is_imported(tmp_path):
    """The config-level control that keeps the ambient provider chain the only credential source.

    Not POSIX-gated: `load_witness_config` refuses this before any path walk happens.
    """
    for bad_option in ({"aws_secret_access_key": "AKIAIOSFODNN7EXAMPLE"},
                       {"credentials": "profile-x"},
                       {"access_key": "AKIAIOSFODNN7EXAMPLE"}):
        with pytest.raises(WitnessConfigError) as exc:
            load_witness_config({
                "profile": "PRODUCTION", "algorithm": "ECDSA_SHA_256_P256", "key_id": KEY_ARN,
                "public_key_path": str(tmp_path / "k.der"),
                "signer": {"factory": SIGNER_FACTORY, "identity": IDENTITY,
                           "options": {"key_arn": KEY_ARN, **bad_option}},
                "sink": {"factory": f"{DOUBLES}:build_sink", "identity": "s3://a", "options": {}},
            })
        assert exc.value.code == "WITNESS_PRIVATE_KEY_IN_CONFIG"


# ── Step 4B: the whole production witness, both real adapters ────────────────────────────────────────

SINK_FACTORY = "app.validation.aws.s3_sink:build_s3_object_lock_sink"
BUCKET = "workbench-forward-anchors"
SINK_PREFIX = "mr002/anchors"
SINK_IDENTITY = f"s3://{BUCKET}/{SINK_PREFIX}"


@pytest.fixture
def s3_stubbed(monkeypatch):
    """A stubbed S3 whose bucket answers 'versioned, Object-Locked, COMPLIANCE, 100 years'."""
    real_client = boto3.client

    def _fake_client(service, **kwargs):
        client = real_client("s3", region_name="us-east-1", aws_access_key_id="t",
                             aws_secret_access_key="t", aws_session_token="t")
        stub = Stubber(client)
        stub.add_response("get_bucket_location", {}, {"Bucket": BUCKET})     # us-east-1 omits it
        stub.add_response("get_bucket_versioning", {"Status": "Enabled"}, {"Bucket": BUCKET})
        stub.add_response("get_object_lock_configuration",
                          {"ObjectLockConfiguration": {
                              "ObjectLockEnabled": "Enabled",
                              "Rule": {"DefaultRetention": {"Mode": "COMPLIANCE", "Days": 36500}}}},
                          {"Bucket": BUCKET})
        stub.activate()
        return client

    monkeypatch.setattr("app.validation.aws.s3_sink.boto3.client", _fake_client)


def _full_config(deployment, *, sink_identity=SINK_IDENTITY):
    return load_witness_config({
        "profile": "PRODUCTION",
        "algorithm": "ECDSA_SHA_256_P256",
        "key_id": KEY_ARN,
        "trusted_root": str(deployment["root"]),
        "public_key_path": str(deployment["path"]),
        "signer": {"factory": SIGNER_FACTORY, "identity": IDENTITY,
                   "options": {"key_arn": KEY_ARN, "witness_identity": IDENTITY}},
        "sink": {"factory": SINK_FACTORY, "identity": sink_identity,
                 "options": {"bucket": BUCKET, "prefix": SINK_PREFIX, "region": "us-east-1"}},
    })


@POSIX_ONLY
def test_the_gate_accepts_the_real_kms_signer_and_the_real_s3_sink(deployment, s3_stubbed):
    """The complete production witness triple, assembled the way a deployment assembles it.

    Nothing is a double here except AWS itself: the config is governed configuration, the factories are
    the real factory strings, and the gate is the real gate. This is the property Steps 4A and 4B exist
    together to establish.
    """
    witness = enforce_production_witness(_full_config(deployment), nonce=NONCE)

    assert type(witness.signer).__name__ == "KmsAnchorSigner"
    assert type(witness.sink).__name__ == "S3ObjectLockAnchorSink"

    immutability = witness.evidence["sink"]["immutability"]
    assert immutability["enforced"] is True
    assert immutability["source"] == "STORAGE"        # asked of the bucket, not declared
    assert immutability["mode"] == "COMPLIANCE"
    assert "36500 day(s)" in immutability["detail"]   # the retention PERIOD is in the evidence
    # The four identities the gate requires to be one.
    assert immutability["storage_identity"] == SINK_IDENTITY
    assert witness.evidence["sink"]["reported_identity"] == SINK_IDENTITY
    assert witness.evidence["signer"]["key_challenge"]["challenged"] is True


@POSIX_ONLY
def test_a_sink_declared_as_one_bucket_but_writing_to_another_is_refused(deployment, s3_stubbed):
    """The mis-wiring the identity binding exists to catch: the declaration names a bucket the
    adapter does not write through, so the attestation would float free of the record."""
    with pytest.raises(WitnessEnforcementError) as exc:
        enforce_production_witness(
            _full_config(deployment, sink_identity="s3://some-other-bucket/anchors"), nonce=NONCE)
    assert exc.value.code == "WITNESS_SINK_STORAGE_MISBOUND"
