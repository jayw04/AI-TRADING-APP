"""Protocol v2 — golden vectors and the negative corpus (ADR 0045).

The protocol is the thing a future auditor re-derives evidence from, so its bytes are pinned here as
literals rather than recomputed by the same code under test. A golden vector that calls the function it
is checking proves only that the function is self-consistent.

Two properties are load-bearing throughout:

  * **Identity is checked before cryptography.** A receipt from the wrong key, algorithm or protocol is
    refused as a mismatch, never as a signature failure — the operator learns which of the two happened.
  * **Unsigned evidence is not authority.** `witness_identity` and `signed_at` are outside the signed
    envelope by design. They must survive mutation without invalidating the signature, and must never
    decide whether a receipt is trusted.
"""

from __future__ import annotations

import base64
import json
from dataclasses import replace

import pytest
from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey

from app.validation.witness_protocol import (
    ALGORITHM_ECDSA_SHA256_P256,
    ALGORITHM_ED25519,
    ALLOWLISTED_ALGORITHMS,
    ENVELOPE_DOMAIN_PREFIX,
    PRODUCTION_ALGORITHMS,
    PROTOCOL_VERSION,
    REFERENCE_ALGORITHMS,
    SignedReceipt,
    WitnessedTip,
    WitnessPersistenceError,
    WitnessProtocolError,
    WitnessSigningIdentity,
    WitnessVerificationError,
    build_verifier,
    build_witness_envelope,
    deserialize_receipt,
    envelope_digest,
    fingerprint_public_key,
    serialize_receipt,
    verify_receipt,
)

TIP = WitnessedTip(sequence=7, session_date="2026-07-24", commit_sha256="a" * 64,
                   anchor_sha256="b" * 64)
ARN = "arn:aws:kms:us-east-1:219024422756:key/1234abcd"
IDENTITY = WitnessSigningIdentity(protocol_version=2, algorithm=ALGORITHM_ECDSA_SHA256_P256,
                                  key_id=ARN, public_key_fingerprint="c" * 64)

# A FIXED Ed25519 seed. Ed25519 is deterministic, so the full serialized receipt below is a stable
# golden vector; ECDSA is not, which is why the P-256 vectors pin every field except the signature.
_ED25519_SEED = bytes(range(32))


# ── golden vectors ───────────────────────────────────────────────────────────────────────────────────

def test_the_canonical_envelope_is_byte_exact():
    """Pinned as a literal. If this changes, every previously signed tip stops verifying — so the
    change must be a deliberate protocol version bump, not an accident of serialization."""
    expected = (
        b"workbench.witness.v2\n"
        b'{"algorithm":"ECDSA_SHA_256_P256",'
        b'"anchor_sha256":"' + b"b" * 64 + b'",'
        b'"commit_sha256":"' + b"a" * 64 + b'",'
        b'"key_id":"arn:aws:kms:us-east-1:219024422756:key/1234abcd",'
        b'"protocol_version":2,'
        b'"public_key_fingerprint":"' + b"c" * 64 + b'",'
        b'"sequence":7,'
        b'"session_date":"2026-07-24"}'
    )
    assert build_witness_envelope(TIP, IDENTITY) == expected


def test_the_envelope_carries_the_domain_prefix_and_sorted_compact_json():
    envelope = build_witness_envelope(TIP, IDENTITY)
    assert envelope.startswith(ENVELOPE_DOMAIN_PREFIX)
    body = envelope[len(ENVELOPE_DOMAIN_PREFIX):]
    assert b", " not in body and b": " not in body          # compact separators
    assert list(json.loads(body)) == sorted(json.loads(body))  # sorted keys
    assert b'"protocol_version":2' in body                  # integer, not "2"


def test_the_envelope_digest_is_pinned():
    """The 32 bytes a production signer is handed (KMS `MessageType=DIGEST`), pinned as a literal.

    This is the value that actually crosses the trust boundary, so it is fixed here rather than
    recomputed — a vector that recomputed it would only prove the function agrees with itself.
    """
    digest = envelope_digest(build_witness_envelope(TIP, IDENTITY))
    assert len(digest) == 32
    assert digest.hex() == "97e40a2cb906ec51597bc65540fdfc15574b79dc9ca3402c3488a184498b4ebd"


def test_every_bound_field_changes_the_envelope():
    """Each bound field must actually affect the signed bytes; one that did not would be recorded but
    not protected."""
    base = build_witness_envelope(TIP, IDENTITY)
    assert build_witness_envelope(replace(TIP, sequence=8), IDENTITY) != base
    assert build_witness_envelope(replace(TIP, session_date="2026-07-27"), IDENTITY) != base
    assert build_witness_envelope(replace(TIP, commit_sha256="d" * 64), IDENTITY) != base
    assert build_witness_envelope(replace(TIP, anchor_sha256="e" * 64), IDENTITY) != base
    for field in ("protocol_version", "algorithm", "key_id", "public_key_fingerprint"):
        altered = replace(IDENTITY, **{field: 3 if field == "protocol_version" else "different"})
        assert build_witness_envelope(TIP, altered) != base, field


def test_the_serialized_ed25519_receipt_is_a_stable_golden_vector():
    """Ed25519 is deterministic, so the WHOLE serialized receipt is pinned."""
    key = Ed25519PrivateKey.from_private_bytes(_ED25519_SEED)
    public = key.public_key().public_bytes_raw()
    identity = WitnessSigningIdentity(
        protocol_version=2, algorithm=ALGORITHM_ED25519, key_id="reference:ed25519:fixed",
        public_key_fingerprint=fingerprint_public_key(public))
    envelope = build_witness_envelope(TIP, identity)
    receipt = SignedReceipt(
        protocol_version=2, algorithm=ALGORITHM_ED25519, key_id="reference:ed25519:fixed",
        public_key_fingerprint=identity.public_key_fingerprint,
        message_digest=envelope_digest(envelope).hex(),
        signature=base64.b64encode(key.sign(envelope)).decode("ascii"),
        signed_at="2026-07-24T20:00:00Z", witness_identity="golden")

    text = serialize_receipt(receipt)
    assert text == json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"))
    assert deserialize_receipt(text) == receipt              # exact round-trip
    # the signature is stable for a fixed seed — this is what "deterministic" buys
    assert receipt.signature == base64.b64encode(key.sign(envelope)).decode("ascii")


# ── the P-256 production shape ───────────────────────────────────────────────────────────────────────

@pytest.fixture
def p256():
    key = ec.generate_private_key(ec.SECP256R1())
    spki = key.public_key().public_bytes(serialization.Encoding.DER,
                                         serialization.PublicFormat.SubjectPublicKeyInfo)
    identity = WitnessSigningIdentity(
        protocol_version=2, algorithm=ALGORITHM_ECDSA_SHA256_P256, key_id=ARN,
        public_key_fingerprint=fingerprint_public_key(spki))
    envelope = build_witness_envelope(TIP, identity)
    digest = envelope_digest(envelope)

    def sign(d: bytes = digest) -> str:
        return base64.b64encode(
            key.sign(d, ec.ECDSA(utils.Prehashed(hashes.SHA256())))).decode("ascii")

    receipt = SignedReceipt(
        protocol_version=2, algorithm=ALGORITHM_ECDSA_SHA256_P256, key_id=ARN,
        public_key_fingerprint=identity.public_key_fingerprint, message_digest=digest.hex(),
        signature=sign(), signed_at="2026-07-24T20:00:00Z", witness_identity="kms-witness")
    return {"key": key, "spki": spki, "identity": identity, "digest": digest,
            "receipt": receipt, "sign": sign,
            "verifier": build_verifier(ALGORITHM_ECDSA_SHA256_P256, spki)}


def _verify(p256, receipt=None, pinned=None):
    verify_receipt(TIP, receipt or p256["receipt"], pinned=pinned or p256["identity"],
                   verifier=p256["verifier"])


def test_a_production_shaped_receipt_verifies(p256):
    _verify(p256)


def test_ecdsa_signatures_are_nondeterministic_but_all_verify(p256):
    """A behavioural constraint, stated safely: rather than asserting two signatures always differ,
    sign a bounded sample, require every one to verify, and require at least two distinct DER values.
    """
    signatures = {p256["sign"]() for _ in range(16)}
    assert len(signatures) >= 2, "ECDSA must not be deterministic across repeated signings"
    for sig in signatures:
        _verify(p256, replace(p256["receipt"], signature=sig))


# ── unsigned evidence is not authority ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("field,value", [("witness_identity", "renamed-after-the-fact"),
                                         ("signed_at", "2030-01-01T00:00:00Z")])
def test_unsigned_evidence_fields_do_not_invalidate_the_signature(p256, field, value):
    """They are deliberately outside the envelope (ADR 0045), so mutating them cannot break the
    signature. Documented as an intended boundary rather than left as an accidental property."""
    _verify(p256, replace(p256["receipt"], **{field: value}))


@pytest.mark.parametrize("field,value", [("witness_identity", "attacker-controlled"),
                                         ("signed_at", "1999-01-01T00:00:00Z")])
def test_unsigned_evidence_fields_confer_no_authority(p256, field, value):
    """The mirror of the above, and the more important half: neither field may make an OTHERWISE
    invalid receipt acceptable. Authority is the pinned algorithm, key ARN and fingerprint."""
    tampered = replace(p256["receipt"], key_id="arn:aws:kms:us-east-1:1:key/attacker", **{field: value})
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, tampered)
    assert exc.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


# ── identity checks precede cryptographic dispatch ───────────────────────────────────────────────────

def test_a_valid_p256_signature_relabelled_as_ed25519_is_refused_before_dispatch(p256):
    """THE ordering proof. The signature is genuine, but the receipt claims a different algorithm than
    the deployment pins — so it is refused on identity, and no Ed25519 verifier is ever constructed or
    invoked (an Ed25519 verifier would raise on this DER signature, a different and misleading error).
    """
    relabelled = replace(p256["receipt"], algorithm=ALGORITHM_ED25519)
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, relabelled)
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_PINNED"


def test_an_unallowlisted_algorithm_is_refused(p256):
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], algorithm="ECDSA_SHA_1_P192"))
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_ALLOWLISTED"


def test_a_v1_receipt_is_refused_not_upgraded(p256):
    """Protocol v1 is retired (ADR 0045 clause 7). A v1 receipt refuses; it is never upgraded."""
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], protocol_version=1))
    assert exc.value.code == "WITNESS_PROTOCOL_VERSION_UNSUPPORTED"


@pytest.mark.parametrize("field,value", [
    ("key_id", "arn:aws:kms:us-east-1:1:key/someone-elses"),
    ("public_key_fingerprint", "f" * 64),
])
def test_key_identity_mismatches_are_refused(p256, field, value):
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], **{field: value}))
    assert exc.value.code == "WITNESS_KEY_IDENTITY_MISMATCH"


def test_an_altered_digest_is_refused_as_a_digest_mismatch(p256):
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], message_digest="0" * 64))
    assert exc.value.code == "WITNESS_MESSAGE_DIGEST_MISMATCH"


def test_a_signature_over_a_different_envelope_is_refused(p256):
    """Identity and digest both check out; only the signature is wrong. This is the one case that
    should surface as ANCHOR_SIGNATURE_INVALID."""
    other = envelope_digest(build_witness_envelope(replace(TIP, sequence=99), p256["identity"]))
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], signature=p256["sign"](other)))
    assert exc.value.code == "ANCHOR_SIGNATURE_INVALID"


def test_a_malformed_base64_signature_is_refused(p256):
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], signature="not!base64!"))
    assert exc.value.code == "ANCHOR_SIGNATURE_INVALID"


def test_a_malformed_der_signature_is_refused(p256):
    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, replace(p256["receipt"], signature=base64.b64encode(b"\x30\x09garbage").decode()))
    assert exc.value.code == "ANCHOR_SIGNATURE_INVALID"


# ── the double-hash regression (ADR 0045's corrected contract) ───────────────────────────────────────

def test_the_prehashed_contract_is_pinned_and_double_hashing_fails(p256):
    """Proves the exact trap the ADR correction closes.

    A signature produced over SHA256(envelope) verifies under Prehashed(SHA-256) and FAILS under
    ECDSA(SHA256()) when handed the digest, because that hashes the digest a second time.
    """
    public = p256["key"].public_key()
    signature = base64.b64decode(p256["receipt"].signature)
    digest = p256["digest"]

    public.verify(signature, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))   # the contract
    with pytest.raises(InvalidSignature):
        public.verify(signature, digest, ec.ECDSA(hashes.SHA256()))                # double-hashed


# ── strict schema and storage boundaries ─────────────────────────────────────────────────────────────

def _good_dict():
    return {"protocol_version": 2, "algorithm": ALGORITHM_ED25519, "key_id": "k",
            "public_key_fingerprint": "a" * 64, "message_digest": "b" * 64, "signature": "c2ln",
            "signed_at": "2026-07-24T20:00:00Z", "witness_identity": "w"}


@pytest.mark.parametrize("field", sorted(_good_dict()))
def test_every_receipt_field_is_required(field):
    payload = _good_dict()
    payload.pop(field)
    with pytest.raises(WitnessProtocolError) as exc:
        SignedReceipt.from_dict(payload)
    assert exc.value.code == "WITNESS_RECEIPT_MALFORMED"


def test_an_unknown_receipt_field_is_refused():
    """A receipt carrying data this verifier does not understand came from another protocol. Dropping
    the extra quietly is how a downgrade goes unnoticed."""
    with pytest.raises(WitnessProtocolError):
        SignedReceipt.from_dict({**_good_dict(), "extra": "value"})


@pytest.mark.parametrize("value", ["2", 2.0, True, None])
def test_a_non_integer_protocol_version_is_refused(value):
    """`"2"` must not be coerced into 2 — that would let a sloppier producer's receipt pass as v2."""
    with pytest.raises(WitnessProtocolError):
        SignedReceipt.from_dict({**_good_dict(), "protocol_version": value})


@pytest.mark.parametrize("value", ["2026-07-24T20:00:00+00:00", "2026-07-24T20:00:00.123Z",
                                   "2026-07-24 20:00:00", "2026-07-24T20:00:00", "yesterday"])
def test_signed_at_must_be_canonical_utc(value):
    """Unsigned evidence still has to be readable: one canonical form, so two receipts are always
    directly comparable and no reader has to guess a timezone."""
    with pytest.raises(WitnessProtocolError):
        SignedReceipt.from_dict({**_good_dict(), "signed_at": value})


@pytest.mark.parametrize("field", ["algorithm", "key_id", "public_key_fingerprint",
                                   "message_digest", "signature", "witness_identity"])
def test_non_string_scalars_are_refused(field):
    with pytest.raises(WitnessProtocolError):
        SignedReceipt.from_dict({**_good_dict(), field: 12345})


@pytest.mark.parametrize("payload", ["not json at all", "[1,2,3]", '"a string"', "17", "null"])
def test_malformed_or_non_object_storage_is_refused(payload):
    """Storage that is not a receipt is refused as a storage/schema fault — never normalized, and never
    reported as a signature failure."""
    with pytest.raises((WitnessPersistenceError, WitnessProtocolError)):
        deserialize_receipt(payload)


def test_a_stored_receipt_round_trips_every_field_exactly():
    receipt = SignedReceipt.from_dict(_good_dict())
    restored = deserialize_receipt(serialize_receipt(receipt))
    assert restored == receipt
    for field in _good_dict():
        assert getattr(restored, field) == getattr(receipt, field)


def test_storage_tampering_survives_schema_validation_but_fails_verification(p256):
    """Schema validity and cryptographic validity are different questions.

    A stored receipt whose `message_digest` was altered still PARSES — it is structurally a receipt —
    and is caught only when the envelope is reconstructed and compared. Proving both halves separately
    is what stops a tampering finding being misreported as a malformed-storage one.
    """
    stored = serialize_receipt(p256["receipt"])
    tampered_text = json.dumps({**json.loads(stored), "message_digest": "9" * 64},
                               sort_keys=True, separators=(",", ":"))

    reloaded = deserialize_receipt(tampered_text)                 # parses fine
    assert reloaded.message_digest == "9" * 64

    with pytest.raises(WitnessVerificationError) as exc:
        _verify(p256, reloaded)
    assert exc.value.code == "WITNESS_MESSAGE_DIGEST_MISMATCH"


# ── the allowlist itself ─────────────────────────────────────────────────────────────────────────────

def test_the_allowlist_is_closed_and_production_pins_exactly_one():
    assert {ALGORITHM_ECDSA_SHA256_P256} == PRODUCTION_ALGORITHMS
    assert {ALGORITHM_ED25519} == REFERENCE_ALGORITHMS
    assert ALLOWLISTED_ALGORITHMS == PRODUCTION_ALGORITHMS | REFERENCE_ALGORITHMS
    assert PROTOCOL_VERSION == 2


def test_no_verifier_exists_for_an_unallowlisted_algorithm():
    with pytest.raises(WitnessProtocolError) as exc:
        build_verifier("RSASSA_PSS_SHA_256", b"\x00" * 32)
    assert exc.value.code == "WITNESS_ALGORITHM_NOT_ALLOWLISTED"


@pytest.mark.parametrize("bad_key", [b"\x00" * 32, b"", b"\x30\x03garbage"])
def test_a_key_of_the_wrong_shape_is_refused_for_p256(bad_key):
    with pytest.raises(WitnessProtocolError) as exc:
        build_verifier(ALGORITHM_ECDSA_SHA256_P256, bad_key)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNUSABLE"


def test_an_ed25519_key_is_refused_for_the_p256_verifier():
    """Right DER, wrong key type — an Ed25519 SPKI is parseable but is not an EC key."""
    spki = Ed25519PrivateKey.generate().public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(WitnessProtocolError) as exc:
        build_verifier(ALGORITHM_ECDSA_SHA256_P256, spki)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNUSABLE"


def test_another_curve_is_refused_for_the_p256_verifier():
    spki = ec.generate_private_key(ec.SECP384R1()).public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    with pytest.raises(WitnessProtocolError) as exc:
        build_verifier(ALGORITHM_ECDSA_SHA256_P256, spki)
    assert exc.value.code == "WITNESS_PUBLIC_KEY_UNUSABLE"
