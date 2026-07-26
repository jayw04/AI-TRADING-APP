"""The witness receipt protocol — algorithm-qualified and versioned (ADR 0045).

R5d's receipt was Ed25519-shaped and unversioned: a signature, a truncated key fingerprint and a
witness identity, over a signed message covering only the chain-tip fields. Nothing recorded WHAT
signed it, and nothing bound the protocol or the key identity into the signature. That made a
production signer impossible — no KMS key spec satisfies it, because `GetPublicKey` returns DER SPKI
for every spec including Ed25519, and a receipt with no algorithm field cannot record what produced it.

This module is the protocol itself, deliberately separate from the signer and sink implementations in
`chain_witness`:

  * ONE canonical envelope, built by ONE function, used by signer and verifier alike. Two
    near-identical JSON builders that drift by a separator are exactly how a chain becomes
    unverifiable, so there is no second one.
  * The envelope carries a domain prefix and binds `protocol_version`, `algorithm`, `key_id` and
    `public_key_fingerprint` alongside the tip. Change any of them and the signature stops verifying,
    so the receipt's labels cannot be rewritten by anyone who cannot sign.
  * Verification dispatches through a CLOSED allowlist keyed by algorithm, and only after the
    receipt's algorithm has been checked against the deployment's pinned one. The receipt never
    selects the terms on which it is judged.

## The prehashed contract (ADR 0045, corrected)

For P-256 the signer signs a PRECOMPUTED SHA-256 digest (KMS `MessageType=DIGEST`), so verification
must use `ECDSA(Prehashed(SHA-256))` over those same 32 digest bytes. Passing the digest to
`ECDSA(SHA256())` would hash it a second time — the verifier would be checking a signature over
`SHA256(SHA256(envelope))` and every valid signature would fail. `verify_receipt` recomputes the digest
from the reconstructed envelope, requires it to equal `receipt.message_digest`, and only then verifies.

Ed25519 is not a prehashed scheme: its signature covers the envelope bytes directly. The digest is
recomputed and compared for BOTH algorithms regardless, because that check is what proves the envelope
still reconstructs — a different question from whether the signature is mathematically valid, and
reported under a different refusal code.

Nothing here touches Account 4, imports the order path, or calls any external service.
"""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import ec, utils
from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
from cryptography.hazmat.primitives.serialization import load_der_public_key

from app.validation.forward_window import IntegrityStop

# ── protocol identifiers, defined once ───────────────────────────────────────────────────────────────
#
# Free algorithm strings scattered across modules are how a verifier ends up accepting something no one
# decided to support. Every identifier lives here.

PROTOCOL_VERSION = 2

ALGORITHM_ED25519 = "ED25519"
ALGORITHM_ECDSA_SHA256_P256 = "ECDSA_SHA_256_P256"

#: Algorithms a PRODUCTION deployment may pin. Exactly one, per ADR 0045.
PRODUCTION_ALGORITHMS = frozenset({ALGORITHM_ECDSA_SHA256_P256})
#: Algorithms available only to the REFERENCE profile — development and tests.
REFERENCE_ALGORITHMS = frozenset({ALGORITHM_ED25519})
#: The closed allowlist. An identifier outside this set is refused before anything else happens.
ALLOWLISTED_ALGORITHMS = PRODUCTION_ALGORITHMS | REFERENCE_ALGORITHMS

#: Domain separation. A signature produced under this protocol cannot be reinterpreted as one produced
#: under any other use of the same key.
ENVELOPE_DOMAIN_PREFIX = b"workbench.witness.v2\n"


class WitnessError(IntegrityStop):
    """The independent witness could not be produced or verified. Fails closed.

    Defined here rather than in `chain_witness` so the protocol module stays at the bottom of the
    dependency order while remaining the source of the error hierarchy. `chain_witness` re-exports it.
    """

    def __init__(self, message: str, *, code: str) -> None:
        super().__init__(message)
        self.code = code


class WitnessProtocolError(WitnessError):
    """The receipt does not satisfy the protocol SCHEMA — missing, unknown or wrongly typed fields.

    A WitnessError, so every existing handler that treats a witness failure as fail-closed continues to
    catch it. Before this hierarchy existed the protocol error was a SIBLING of WitnessError, which
    meant a protocol failure slipped past `except WitnessError` boundaries and could have changed
    rollback and refusal behaviour without an obvious test failure.
    """


class WitnessVerificationError(WitnessError):
    """The receipt is structurally valid but does not verify — a pinned-identity mismatch, an envelope
    that no longer reconstructs, or a mathematically invalid signature.

    Distinct from `WitnessProtocolError` on purpose: "this is not a well-formed receipt" and "this
    receipt does not verify" are different operational findings, and an operator needs to know which.
    """


class WitnessPersistenceError(WitnessError):
    """A stored receipt could not be read back as a receipt at all — unreadable or non-object storage,
    before any question of schema or signature arises."""


# ── the signed subject ───────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WitnessedTip:
    """The compact identity of a committed chain tip that is signed and externally recorded. It binds
    the observation tip (`commit_sha256`) and the LOCAL anchor line (`anchor_sha256`), so the external
    witness and the local log cannot silently disagree about which tip was witnessed."""

    sequence: int
    session_date: str
    commit_sha256: str
    anchor_sha256: str


@dataclass(frozen=True)
class WitnessSigningIdentity:
    """EXACTLY the cryptographically bound identity fields, and nothing else.

    Deliberately not a receipt, a signer object, a configuration object or a dict. Anything wider would
    let unsigned or incidental values reach the serializer, and the envelope must contain only what the
    signature actually covers.

    `protocol_version` is carried here rather than read from the module constant, so the envelope
    function has no hidden global input: everything it serializes arrives through this value.
    """

    protocol_version: int
    algorithm: str
    key_id: str                       # the full immutable key ARN in production; never an alias
    public_key_fingerprint: str       # sha256 hex over the exact installed key bytes


def fingerprint_public_key(installed_key_bytes: bytes) -> str:
    """The full SHA-256 hex of the EXACT installed key material.

    Full, not truncated: a fingerprint is a mismatch detector and there is no reason to weaken it. The
    bytes are whatever the deployment installed — DER SPKI for a production P-256 key, raw 32 bytes for
    the Ed25519 reference — hashed unchanged, so the fingerprint is a statement about the installed
    file rather than about a re-encoding of it.
    """
    return hashlib.sha256(installed_key_bytes).hexdigest()


# ── the ONE canonical envelope ───────────────────────────────────────────────────────────────────────

def build_witness_envelope(tip: WitnessedTip, identity: WitnessSigningIdentity) -> bytes:
    """The exact bytes that get signed. Pure, side-effect free, and the only such builder.

    Both the signer and the verifier call this. If either constructed its own JSON, a difference in key
    ordering, separators or integer rendering would silently break verification — and the failure would
    look like tampering rather than a serialization bug.
    """
    payload = {
        "algorithm": identity.algorithm,
        "anchor_sha256": tip.anchor_sha256,
        "commit_sha256": tip.commit_sha256,
        "key_id": identity.key_id,
        "protocol_version": identity.protocol_version,
        "public_key_fingerprint": identity.public_key_fingerprint,
        "sequence": tip.sequence,
        "session_date": tip.session_date,
    }
    canonical = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return ENVELOPE_DOMAIN_PREFIX + canonical


def envelope_digest(envelope: bytes) -> bytes:
    """The 32 bytes a production signer is asked to sign (KMS `MessageType=DIGEST`)."""
    return hashlib.sha256(envelope).digest()


# ── the receipt ──────────────────────────────────────────────────────────────────────────────────────

#: `signed_at` is EVIDENCE, never authority — but evidence still has to be readable. One canonical UTC
#: form only: offsets, fractional seconds and naive timestamps are refused, so two receipts are always
#: directly comparable as text and no reader has to guess a timezone.
_SIGNED_AT_RE = re.compile(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")

_RECEIPT_FIELDS = (
    "protocol_version", "algorithm", "key_id", "public_key_fingerprint",
    "message_digest", "signature", "signed_at", "witness_identity",
)


@dataclass(frozen=True)
class SignedReceipt:
    """A protocol-v2 witness receipt. Every field is REQUIRED.

    No field defaults from configuration. A receipt that is missing one is refused rather than
    completed, because a value supplied at read time is present in memory and absent from the stored
    evidence — and the stored evidence is the thing a future auditor has.
    """

    protocol_version: int
    algorithm: str
    key_id: str
    public_key_fingerprint: str
    message_digest: str               # sha256 hex of the canonical envelope
    signature: str                    # base64; ASN.1 DER for ECDSA, raw 64 bytes for Ed25519
    signed_at: str                    # ISO-8601 UTC. EVIDENCE ONLY — never ordering authority.
    witness_identity: str

    def to_dict(self) -> dict[str, Any]:
        return {f: getattr(self, f) for f in _RECEIPT_FIELDS}

    @classmethod
    def from_dict(cls, d: Any) -> SignedReceipt:
        """Strict parse. Missing fields and unknown fields are BOTH refused.

        Unknown fields are refused rather than ignored: a receipt carrying data the verifier does not
        understand is a receipt from a protocol this verifier does not implement, and quietly dropping
        the extra is how a downgrade goes unnoticed.
        """
        if not isinstance(d, dict):
            raise WitnessProtocolError(
                f"a witness receipt must be an object, got {type(d).__name__}",
                code="WITNESS_RECEIPT_MALFORMED")
        missing = [f for f in _RECEIPT_FIELDS if f not in d]
        if missing:
            raise WitnessProtocolError(
                f"the witness receipt is missing required field(s) {sorted(missing)}; a protocol-v2 "
                f"receipt carries every field or none of it is trustworthy",
                code="WITNESS_RECEIPT_MALFORMED")
        unknown = [k for k in d if k not in _RECEIPT_FIELDS]
        if unknown:
            raise WitnessProtocolError(
                f"the witness receipt carries unknown field(s) {sorted(unknown)}; it was produced by a "
                f"protocol this verifier does not implement", code="WITNESS_RECEIPT_MALFORMED")
        raw_version = d["protocol_version"]
        # A STRING "2" is not an integer 2. Coercing it would let a receipt from a sloppier producer
        # pass as v2 while its other fields went unchecked.
        if isinstance(raw_version, bool) or not isinstance(raw_version, int):
            raise WitnessProtocolError(
                f"protocol_version {raw_version!r} is {type(raw_version).__name__}, not an integer",
                code="WITNESS_RECEIPT_MALFORMED")
        version = raw_version

        for field_name in ("algorithm", "key_id", "public_key_fingerprint", "message_digest",
                           "signature", "signed_at", "witness_identity"):
            if not isinstance(d[field_name], str):
                raise WitnessProtocolError(
                    f"{field_name} is {type(d[field_name]).__name__}, not a string",
                    code="WITNESS_RECEIPT_MALFORMED")
        # Shape FIRST, then a real calendar parse. The regex alone accepts impossible values such as
        # 2026-99-99T29:88:77Z — digit-shaped but not a timestamp. The field is advertised as
        # canonically readable evidence, so it has to actually be readable.
        if not _SIGNED_AT_RE.match(d["signed_at"]):
            raise WitnessProtocolError(
                f"signed_at {d['signed_at']!r} is not canonical UTC (YYYY-MM-DDTHH:MM:SSZ); offsets, "
                f"fractional seconds and naive timestamps are refused",
                code="WITNESS_RECEIPT_MALFORMED")
        try:
            datetime.strptime(d["signed_at"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
        except ValueError as exc:
            raise WitnessProtocolError(
                f"signed_at {d['signed_at']!r} has the canonical shape but is not a real UTC "
                f"timestamp: {exc}", code="WITNESS_RECEIPT_MALFORMED") from exc
        return cls(
            protocol_version=version, algorithm=str(d["algorithm"]), key_id=str(d["key_id"]),
            public_key_fingerprint=str(d["public_key_fingerprint"]),
            message_digest=str(d["message_digest"]), signature=str(d["signature"]),
            signed_at=str(d["signed_at"]), witness_identity=str(d["witness_identity"]))


def serialize_receipt(receipt: SignedReceipt) -> str:
    """The canonical stored form of a receipt. The ONLY serializer.

    Storage layers must call this rather than `dataclasses.asdict` or their own field enumeration: a
    layer that builds its own mapping can silently bypass the strict parse on the way back in, and a
    later schema change would then land without the receipt boundary noticing.
    """
    return json.dumps(receipt.to_dict(), sort_keys=True, separators=(",", ":"))


def deserialize_receipt(text: str) -> SignedReceipt:
    """Parse a stored receipt through the STRICT schema — missing and unknown fields both refuse."""
    try:
        payload = json.loads(text)
    except (TypeError, ValueError) as exc:
        raise WitnessPersistenceError(
            f"the stored witness receipt is not valid JSON: {exc}", code="WITNESS_RECEIPT_MALFORMED"
        ) from exc
    return SignedReceipt.from_dict(payload)


# ── verifier strategies, selected by a closed dispatch ───────────────────────────────────────────────

class _AlgorithmVerifier(Protocol):
    """Verifies a signature for ONE algorithm. Selected by the pinned identifier, never by the
    receipt."""

    def verify(self, envelope: bytes, digest: bytes, signature: bytes) -> None: ...


class Ed25519Verifier:
    """Reference verifier. Ed25519 is not a prehashed scheme: the signature covers the envelope bytes
    directly, so the digest is compared separately but not signed over."""

    def __init__(self, installed_key_bytes: bytes) -> None:
        if len(installed_key_bytes) != 32:
            raise WitnessProtocolError(
                f"an Ed25519 verifying key is 32 raw bytes, got {len(installed_key_bytes)}",
                code="WITNESS_PUBLIC_KEY_UNUSABLE")
        self._public = Ed25519PublicKey.from_public_bytes(installed_key_bytes)

    def verify(self, envelope: bytes, digest: bytes, signature: bytes) -> None:
        self._public.verify(signature, envelope)


class P256PrehashedVerifier:
    """Production verifier: ECDSA over NIST P-256 with a PREHASHED SHA-256 digest.

    The installed material is DER SubjectPublicKeyInfo, exactly as `GetPublicKey` returns it. The key
    is required to be an EC key on SECP256R1 — an RSA key, an Ed25519 key, another curve, malformed DER
    or trailing garbage are all refused, because a verifier that accepts a key of the wrong shape is
    verifying something other than what the deployment pinned.

    Signatures stay in ASN.1 DER, as KMS returns them. They are never normalized into raw `r || s`:
    the protocol stores what the signer produced, and a re-encoding step is one more place for the
    stored bytes and the verified bytes to diverge.
    """

    def __init__(self, installed_key_bytes: bytes) -> None:
        try:
            key = load_der_public_key(installed_key_bytes)
        except Exception as exc:                  # noqa: BLE001 - any parse failure is a refusal
            raise WitnessProtocolError(
                f"the installed verifying key is not parseable DER SubjectPublicKeyInfo: {exc}",
                code="WITNESS_PUBLIC_KEY_UNUSABLE") from exc
        if not isinstance(key, ec.EllipticCurvePublicKey):
            raise WitnessProtocolError(
                f"the installed verifying key is {type(key).__name__}, not an EC public key; "
                f"{ALGORITHM_ECDSA_SHA256_P256} requires one",
                code="WITNESS_PUBLIC_KEY_UNUSABLE")
        if not isinstance(key.curve, ec.SECP256R1):
            raise WitnessProtocolError(
                f"the installed verifying key is on curve {key.curve.name}, not secp256r1 (P-256)",
                code="WITNESS_PUBLIC_KEY_UNUSABLE")
        self._public = key

    def verify(self, envelope: bytes, digest: bytes, signature: bytes) -> None:
        # PREHASHED: the signature is over `digest`, which is already SHA-256(envelope). Using
        # ECDSA(SHA256()) here would hash it again and every valid signature would fail.
        self._public.verify(signature, digest, ec.ECDSA(utils.Prehashed(hashes.SHA256())))


def build_verifier(algorithm: str, installed_key_bytes: bytes) -> _AlgorithmVerifier:
    """Closed dispatch. The receipt cannot name a class or an import path — only an identifier already
    checked against the pinned algorithm."""
    if algorithm == ALGORITHM_ECDSA_SHA256_P256:
        return P256PrehashedVerifier(installed_key_bytes)
    if algorithm == ALGORITHM_ED25519:
        return Ed25519Verifier(installed_key_bytes)
    raise WitnessProtocolError(
        f"no verifier is implemented for algorithm {algorithm!r}",
        code="WITNESS_ALGORITHM_NOT_ALLOWLISTED")


# ── the verification procedure ───────────────────────────────────────────────────────────────────────

def verify_receipt(tip: WitnessedTip, receipt: SignedReceipt, *, pinned: WitnessSigningIdentity,
                   verifier: _AlgorithmVerifier) -> None:
    """Verify a receipt against the deployment's PINNED identity. Order is load-bearing.

    Identity is checked before any cryptography runs, so a receipt from the wrong key or algorithm is
    refused as a mismatch rather than surfacing as a signature failure — the operator learns which of
    the two actually happened.
    """
    if receipt.protocol_version != PROTOCOL_VERSION:
        raise WitnessVerificationError(
            f"the receipt declares protocol version {receipt.protocol_version}; this verifier "
            f"implements version {PROTOCOL_VERSION} only",
            code="WITNESS_PROTOCOL_VERSION_UNSUPPORTED")
    if receipt.algorithm not in ALLOWLISTED_ALGORITHMS:
        raise WitnessVerificationError(
            f"the receipt declares algorithm {receipt.algorithm!r}, which is not allowlisted",
            code="WITNESS_ALGORITHM_NOT_ALLOWLISTED")
    if receipt.algorithm != pinned.algorithm:
        raise WitnessVerificationError(
            f"the receipt declares algorithm {receipt.algorithm!r}; this deployment pins "
            f"{pinned.algorithm!r}", code="WITNESS_ALGORITHM_NOT_PINNED")
    if receipt.key_id != pinned.key_id:
        raise WitnessVerificationError(
            f"the receipt names key {receipt.key_id!r}; this deployment pins {pinned.key_id!r}",
            code="WITNESS_KEY_IDENTITY_MISMATCH")
    if receipt.public_key_fingerprint != pinned.public_key_fingerprint:
        raise WitnessVerificationError(
            "the receipt's public-key fingerprint does not match the installed verifying key",
            code="WITNESS_KEY_IDENTITY_MISMATCH")

    envelope = build_witness_envelope(tip, pinned)
    digest = envelope_digest(envelope)
    if digest.hex() != receipt.message_digest:
        raise WitnessVerificationError(
            f"the reconstructed envelope for tip {tip.sequence} digests to {digest.hex()}, not the "
            f"{receipt.message_digest!r} the receipt records — the record no longer reconstructs",
            code="WITNESS_MESSAGE_DIGEST_MISMATCH")

    try:
        signature = base64.b64decode(receipt.signature, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise WitnessVerificationError(
            f"the receipt's signature is not valid base64: {exc}", code="ANCHOR_SIGNATURE_INVALID"
        ) from exc

    try:
        verifier.verify(envelope, digest, signature)
    except InvalidSignature as exc:
        raise WitnessVerificationError(
            f"the witness signature for tip {tip.sequence} does not verify — the tip was altered after "
            f"it was signed", code="ANCHOR_SIGNATURE_INVALID") from exc
    except Exception as exc:                      # noqa: BLE001 - malformed DER etc. is a refusal
        raise WitnessVerificationError(
            f"the witness signature for tip {tip.sequence} could not be verified: "
            f"{type(exc).__name__}: {exc}", code="ANCHOR_SIGNATURE_INVALID") from exc


__all__ = [
    "ALGORITHM_ECDSA_SHA256_P256",
    "ALGORITHM_ED25519",
    "ALLOWLISTED_ALGORITHMS",
    "ENVELOPE_DOMAIN_PREFIX",
    "PRODUCTION_ALGORITHMS",
    "PROTOCOL_VERSION",
    "REFERENCE_ALGORITHMS",
    "Ed25519Verifier",
    "P256PrehashedVerifier",
    "SignedReceipt",
    "WitnessError",
    "WitnessPersistenceError",
    "WitnessProtocolError",
    "WitnessVerificationError",
    "WitnessSigningIdentity",
    "WitnessedTip",
    "build_verifier",
    "build_witness_envelope",
    "deserialize_receipt",
    "envelope_digest",
    "fingerprint_public_key",
    "serialize_receipt",
    "verify_receipt",
]
