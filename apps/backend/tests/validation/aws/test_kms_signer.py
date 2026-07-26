"""The production KMS witness signer (ADR 0046, Step 4A).

Every test here is driven by `botocore.stub.Stubber`; `conftest._no_live_aws` severs the transport, so
a test that escaped the stub fails rather than talking to AWS.

What these tests defend is not "the adapter calls KMS". It is the set of properties that are silent
when they break: that the signed bytes are the 32-byte prehashed digest the receipt names, that the
receipt records the key KMS actually used, that identity comparison is exact rather than helpful, and
that no AWS failure can turn into anything other than a governed refusal.
"""

from __future__ import annotations

import base64

import boto3
import pytest
from botocore.config import Config
from botocore.exceptions import NoCredentialsError
from botocore.stub import Stubber
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat

from app.validation.aws.kms_signer import (
    KMS_KEY_SPEC,
    KMS_SIGNING_ALGORITHM,
    KmsAnchorSigner,
    KmsWitnessError,
    build_kms_anchor_signer,
    parse_key_arn,
)
from app.validation.chain_witness import AnchorVerifier
from app.validation.witness_enforcement import _assert_no_in_process_private_key
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

TIP = WitnessedTip(sequence=1, session_date="2026-07-27", commit_sha256="a" * 64,
                   anchor_sha256="b" * 64)


# ── fixtures ─────────────────────────────────────────────────────────────────────────────────────────

@pytest.fixture
def kms_key():
    """A P-256 keypair standing in for the KMS-held key. The private half never reaches the adapter."""
    private = ec.generate_private_key(ec.SECP256R1())
    der = private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    return {"private": private, "der": der}


@pytest.fixture
def client():
    # Explicit dummy credentials so botocore never consults the ambient provider chain during tests.
    # They are inert: the transport is severed and every call is stubbed.
    return boto3.client("kms", region_name="us-east-1", aws_access_key_id="testing",
                        aws_secret_access_key="testing", aws_session_token="testing")


def _public_key_response(der: bytes, **overrides):
    response = {"KeyId": KEY_ARN, "KeySpec": KMS_KEY_SPEC,
                "SigningAlgorithms": [KMS_SIGNING_ALGORITHM], "PublicKey": der}
    response.update(overrides)
    return response


def _build_signer(client, kms_key, stub, **overrides) -> KmsAnchorSigner:
    stub.add_response("get_public_key", _public_key_response(kms_key["der"], **overrides),
                      {"KeyId": KEY_ARN})
    return KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)


def _sign_locally(kms_key, signer: KmsAnchorSigner, tip: WitnessedTip = TIP) -> tuple[bytes, bytes]:
    """The digest the adapter will produce, and a real signature over it."""
    identity = WitnessSigningIdentity(
        protocol_version=PROTOCOL_VERSION, algorithm=ALGORITHM_ECDSA_SHA256_P256,
        key_id=KEY_ARN, public_key_fingerprint=signer.public_key_fingerprint)
    digest = envelope_digest(build_witness_envelope(tip, identity))
    signature = kms_key["private"].sign(digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))
    return digest, signature


# ── the receipt verifies under the trusted verifier ──────────────────────────────────────────────────

def test_attest_produces_a_receipt_the_trusted_verifier_accepts(client, kms_key):
    """The end the whole adapter exists for: a receipt the deployment-installed key verifies."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": signature,
                                   "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})

        receipt = signer.attest(TIP)
        stub.assert_no_pending_responses()

    # The verifier is built from the INSTALLED key bytes, exactly as production composition does.
    verifier = AnchorVerifier(kms_key["der"], algorithm=ALGORITHM_ECDSA_SHA256_P256, key_id=KEY_ARN)
    verifier.verify(TIP, receipt)                 # raises if the receipt does not verify

    assert receipt.protocol_version == PROTOCOL_VERSION
    assert receipt.algorithm == ALGORITHM_ECDSA_SHA256_P256
    assert receipt.key_id == KEY_ARN
    assert receipt.public_key_fingerprint == fingerprint_public_key(kms_key["der"])
    assert receipt.message_digest == digest.hex()
    assert receipt.witness_identity == IDENTITY


def test_the_signature_is_stored_as_the_der_kms_returned(client, kms_key):
    """Never normalized to raw r||s — the stored bytes must be the bytes that were produced."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": signature,
                                   "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        receipt = signer.attest(TIP)

    assert base64.b64decode(receipt.signature) == signature


# ── the prehashed contract ───────────────────────────────────────────────────────────────────────────

def test_sign_is_called_with_message_type_digest_over_exactly_32_bytes(client, kms_key):
    """`MessageType=RAW` would make KMS hash server-side, so the signed bytes would stop being the
    bytes the receipt names. The Stubber's expected_params is the assertion."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        assert len(digest) == 32
        stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": signature,
                                   "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        signer.attest(TIP)
        stub.assert_no_pending_responses()        # the exact params matched, or this never runs


# ── exact identity comparison (ADR 0046 Decision 10) ─────────────────────────────────────────────────

def test_a_returned_key_id_differing_only_by_case_is_refused(client, kms_key):
    """A future implementer reaching for a 'helpful' casefold should fail here."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": KEY_ARN.upper(), "Signature": signature,
                                   "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        with pytest.raises(KmsWitnessError, match="exact") as exc:
            signer.attest(TIP)
    assert exc.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


def test_a_returned_bare_key_id_is_refused_even_though_it_names_the_same_key(client, kms_key):
    """Semantic equivalence is not textual equality. No ARN reconstruction, no key-id substitution."""
    bare = KEY_ARN.rsplit("/", 1)[1]
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": bare, "Signature": signature,
                                   "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        with pytest.raises(KmsWitnessError) as exc:
            signer.attest(TIP)
    assert exc.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


def test_a_returned_signing_algorithm_mismatch_is_refused(client, kms_key):
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, signature = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": signature,
                                   "SigningAlgorithm": "ECDSA_SHA_384"},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        with pytest.raises(KmsWitnessError) as exc:
            signer.attest(TIP)
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_PINNED"


def test_a_non_bytes_signature_is_refused(client, kms_key):
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        digest, _ = _sign_locally(kms_key, signer)
        stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": b"", "SigningAlgorithm":
                                   KMS_SIGNING_ALGORITHM},
                          {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                           "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
        with pytest.raises(KmsWitnessError) as exc:
            signer.attest(TIP)
    assert exc.value.code == "ANCHOR_SIGNATURE_INVALID"


# ── the ARN grammar ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("bad", [
    "arn:aws:kms:us-east-1:219024422756:alias/anchor-witness",          # an alias can be repointed
    "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d",                             # a bare key id names no region
    "arn:aws:kms:us-east-1:219024422756:key/mrk-1a2b3c4d5e6f4a1b8c2d3e4f5a6b7c8d",  # multi-Region
    "arn:aws:s3:::some-bucket",                                          # another service entirely
    "arn:aws:kms:us-east-1:21902442275:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d",   # 11-digit account
    "arn:aws:kms::219024422756:key/1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d",           # no region
    "",
])
def test_only_a_full_immutable_key_arn_is_accepted(bad):
    with pytest.raises(KmsWitnessError) as exc:
        parse_key_arn(bad)
    assert exc.value.code == "WITNESS_KMS_KEY_ARN_INVALID"


def test_the_region_is_derived_from_the_arn():
    assert parse_key_arn(KEY_ARN) == "us-east-1"
    assert parse_key_arn(
        "arn:aws-us-gov:kms:us-gov-west-1:219024422756:key/"
        "1a2b3c4d-5e6f-4a1b-8c2d-3e4f5a6b7c8d") == "us-gov-west-1"


# ── the construction-time cross-check ────────────────────────────────────────────────────────────────

def test_a_get_public_key_key_id_mismatch_is_refused(client, kms_key):
    with Stubber(client) as stub:
        stub.add_response("get_public_key",
                          _public_key_response(kms_key["der"], KeyId=KEY_ARN.upper()),
                          {"KeyId": KEY_ARN})
        with pytest.raises(KmsWitnessError) as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


def test_a_wrong_key_spec_is_refused(client, kms_key):
    with Stubber(client) as stub:
        stub.add_response("get_public_key",
                          _public_key_response(kms_key["der"], KeySpec="RSA_4096"),
                          {"KeyId": KEY_ARN})
        with pytest.raises(KmsWitnessError, match="KeySpec") as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_PINNED"


def test_a_key_that_cannot_sign_with_the_pinned_algorithm_is_refused(client, kms_key):
    with Stubber(client) as stub:
        stub.add_response("get_public_key",
                          _public_key_response(kms_key["der"], SigningAlgorithms=["ECDSA_SHA_512"]),
                          {"KeyId": KEY_ARN})
        with pytest.raises(KmsWitnessError, match="signing algorithms") as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_PINNED"


def test_a_public_key_on_the_wrong_curve_is_refused(client):
    """KeySpec could say P-256 while the bytes say otherwise; the bytes are checked too."""
    p384 = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        Encoding.DER, PublicFormat.SubjectPublicKeyInfo)
    with Stubber(client) as stub:
        stub.add_response("get_public_key", _public_key_response(p384), {"KeyId": KEY_ARN})
        with pytest.raises(KmsWitnessError, match="P-256") as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNUSABLE"


def test_unparseable_public_key_bytes_are_refused(client):
    with Stubber(client) as stub:
        stub.add_response("get_public_key", _public_key_response(b"not der at all"),
                          {"KeyId": KEY_ARN})
        with pytest.raises(KmsWitnessError, match="DER") as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNUSABLE"


def test_get_public_key_is_called_exactly_once(client, kms_key):
    """Once at construction. A per-signature fetch would make the key a moving target."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        for _ in range(2):
            digest, signature = _sign_locally(kms_key, signer)
            stub.add_response("sign", {"KeyId": KEY_ARN, "Signature": signature,
                                       "SigningAlgorithm": KMS_SIGNING_ALGORITHM},
                              {"KeyId": KEY_ARN, "Message": digest, "MessageType": "DIGEST",
                               "SigningAlgorithm": KMS_SIGNING_ALGORITHM})
            signer.attest(TIP)
        stub.assert_no_pending_responses()        # no second get_public_key was queued or needed


# ── every AWS failure fails closed ───────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("code", [
    "AccessDeniedException",                      # IAM is wrong
    "KMSInvalidStateException",                   # the key is disabled or pending deletion
    "ThrottlingException",                        # survived the retry budget
    "NotFoundException",                          # the ARN names nothing
])
def test_a_client_error_during_signing_becomes_a_governed_refusal(client, kms_key, code):
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
        stub.add_client_error("sign", service_error_code=code, http_status_code=400)
        with pytest.raises(KmsWitnessError) as exc:
            signer.attest(TIP)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"
    assert code in str(exc.value)


def test_a_client_error_during_construction_becomes_a_governed_refusal(client):
    with Stubber(client) as stub:
        stub.add_client_error("get_public_key", service_error_code="AccessDeniedException",
                              http_status_code=400)
        with pytest.raises(KmsWitnessError) as exc:
            KmsAnchorSigner(client=client, key_arn=KEY_ARN, witness_identity=IDENTITY)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


def test_a_botocore_error_becomes_a_governed_refusal(client, kms_key, monkeypatch):
    """Missing credentials, endpoint resolution, connect/read timeouts — the client-side family."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)

    def _raise(**_):
        raise NoCredentialsError()

    monkeypatch.setattr(signer, "_client", type("C", (), {"sign": staticmethod(_raise)})())
    with pytest.raises(KmsWitnessError, match="NoCredentialsError") as exc:
        signer.attest(TIP)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


def test_an_unexpected_sdk_exception_is_still_translated(client, kms_key, monkeypatch):
    """The backstop: an untranslated SDK exception would surface somewhere that does not know it
    means stop."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)

    def _raise(**_):
        raise RuntimeError("something the SDK did not document")

    monkeypatch.setattr(signer, "_client", type("C", (), {"sign": staticmethod(_raise)})())
    with pytest.raises(KmsWitnessError) as exc:
        signer.attest(TIP)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


def test_a_non_mapping_response_is_refused(client, kms_key, monkeypatch):
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)

    monkeypatch.setattr(signer, "_client",
                        type("C", (), {"sign": staticmethod(lambda **_: "not a mapping")})())
    with pytest.raises(KmsWitnessError) as exc:
        signer.attest(TIP)
    assert exc.value.code == "INDEPENDENT_WITNESS_UNAVAILABLE"


# ── the separation property the whole boundary rests on ──────────────────────────────────────────────

def test_the_signer_holds_no_private_key_in_this_process(client, kms_key):
    """`_assert_no_in_process_private_key` must pass on the merits, not by accident."""
    with Stubber(client) as stub:
        signer = _build_signer(client, kms_key, stub)
    _assert_no_in_process_private_key(signer)     # raises if a private key is reachable
    assert not hasattr(signer, "_private")


# ── the factory ──────────────────────────────────────────────────────────────────────────────────────

def test_the_factory_builds_a_client_in_the_arn_region_with_bounded_retries(kms_key, monkeypatch):
    captured = {}
    # Captured BEFORE patching: `kms_signer.boto3` is the same module object as this module's `boto3`,
    # so patching the attribute would make a naive fake call itself.
    real_client = boto3.client

    def _fake_client(service, **kwargs):
        captured["service"] = service
        captured.update(kwargs)
        client = real_client("kms", region_name="us-east-1", aws_access_key_id="t",
                             aws_secret_access_key="t", aws_session_token="t")
        stub = Stubber(client)
        stub.add_response("get_public_key", _public_key_response(kms_key["der"]), {"KeyId": KEY_ARN})
        stub.activate()
        return client

    monkeypatch.setattr("app.validation.aws.kms_signer.boto3.client", _fake_client)
    signer = build_kms_anchor_signer(key_arn=KEY_ARN, witness_identity=IDENTITY)

    assert captured["service"] == "kms"
    assert captured["region_name"] == "us-east-1"          # derived from the ARN, never configured
    config: Config = captured["config"]
    assert config.retries == {"mode": "standard", "max_attempts": 3}
    assert config.connect_timeout == 5
    assert config.read_timeout == 10
    assert signer.identity() == f"{IDENTITY}@{KEY_ARN}"


def test_the_factory_refuses_a_bad_arn_before_building_a_client(monkeypatch):
    def _forbidden(*a, **k):                      # pragma: no cover - must never be reached
        raise AssertionError("a client was built for an invalid ARN")

    monkeypatch.setattr("app.validation.aws.kms_signer.boto3.client", _forbidden)
    with pytest.raises(KmsWitnessError) as exc:
        build_kms_anchor_signer(key_arn="arn:aws:kms:us-east-1:219024422756:alias/x",
                                witness_identity=IDENTITY)
    assert exc.value.code == "WITNESS_KMS_KEY_ARN_INVALID"


def test_the_factory_requires_a_witness_identity(monkeypatch):
    def _forbidden(*a, **k):                      # pragma: no cover - must never be reached
        raise AssertionError("a client was built without a witness identity")

    monkeypatch.setattr("app.validation.aws.kms_signer.boto3.client", _forbidden)
    with pytest.raises(KmsWitnessError) as exc:
        build_kms_anchor_signer(key_arn=KEY_ARN, witness_identity="  ")
    assert exc.value.code == "WITNESS_CONFIG_INCOMPLETE"


def test_the_factory_accepts_no_credential_options():
    """Credentials come from the ambient provider chain. There is no option to override them."""
    import inspect

    params = set(inspect.signature(build_kms_anchor_signer).parameters)
    assert params == {"key_arn", "witness_identity", "client"}
