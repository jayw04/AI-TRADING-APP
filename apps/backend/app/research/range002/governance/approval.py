"""Internal cryptographic approval-record verifier (RANGE-002 phase 3c; SYNTHETIC DEVELOPMENT).

A fail-closed, side-effect-free component that decides whether a signed approval record is
(a) well-formed in exactly one byte encoding, (b) bound to the exact document and spec digests
the caller expects, (c) signed by the key the roster binds to the claimed human, and (d) made by
a signer whom a TRUSTED, VERSIONED, PINNED authority roster authorizes for that role and scope.

It is NOT a signing ceremony, NOT a P0 approval, and holds no key material. The roster passed in
is the trust anchor: a valid signature alone proves only that some key signed; it never proves
the signer was allowed to approve, and no authorization claim inside a record is trusted
(``signer.role`` is a claim that is checked against the roster, never accepted).
``SpecView.is_signed`` is deliberately not consulted anywhere in this module.

Profile (``range002-approval/1``): ECDSA P-256 over SHA-256, DER signature with low-S enforced,
over ``DOMAIN || canonical_json(payload)``. The wire form is the canonical JSON of
``{"payload": {...}, "signature": "<hex>"}`` and is accepted only if the received bytes equal
their own canonical re-encoding, which rejects duplicate keys, reordering, whitespace, escapes,
floats, booleans and any other alternative spelling. No custom cryptography: primitives come from
``cryptography`` (already a backend dependency).

KNOWN LIMITATION (trusted time): the time evidence is SIGNER-ASSERTED. The authority name is
compared with the policy list, but ``token_sha256`` is only format-checked and no token is
resolved or verified, so ``VerifiedApproval.time_evidence_claimed`` is a claim, not assurance.
Real trusted time needs a decided authority and token verifier (unresolved human decision).

Replay, supersession and conflict handling live in :class:`ApprovalLedger` (in memory here; the
durable store is an unresolved human/engineering decision).
"""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from enum import StrEnum
from typing import Any

from cryptography.exceptions import InvalidSignature
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from app.research.range002.spec.hashing import CanonicalisationError, canonical_json

PROTOCOL = "range002-approval/1"
SIG_ALG = "ECDSA-P256-SHA256"
DOMAIN = b"RANGE-002/approval/v1\x00"
OUTCOMES = frozenset({"APPROVE", "REJECT", "REVOKE"})
TIME_TRUSTED = "TRUSTED_TIMESTAMP"
TIME_NONE = "NONE"
TIME_LIMITATION = "UNTRUSTED_SIGNER_CLOCK"

_P256_ORDER = int("FFFFFFFF00000000FFFFFFFFFFFFFFFFBCE6FAADA7179E84F3B9CAC2FC632551", 16)
_ID = re.compile(r"^[A-Za-z0-9._:-]{1,128}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_NONCE = re.compile(r"^[0-9a-f]{32,64}$")
_SIG = re.compile(r"^[0-9a-f]{16,200}$")
_TS_FORMAT = "%Y-%m-%dT%H:%M:%SZ"
_MAX_ENVELOPE_BYTES = 65536
_MAX_DEPTH = 8
_SEAL = object()


class ErrorCode(StrEnum):
    ENCODING = "ENCODING"
    SCHEMA = "SCHEMA"
    PROTOCOL = "PROTOCOL"
    ALGORITHM = "ALGORITHM"
    ROSTER_UNTRUSTED = "ROSTER_UNTRUSTED"
    ROSTER_VERSION = "ROSTER_VERSION"
    DOCUMENT_MISMATCH = "DOCUMENT_MISMATCH"
    SCOPE_MISMATCH = "SCOPE_MISMATCH"
    KEY_UNKNOWN = "KEY_UNKNOWN"
    KEY_REVOKED = "KEY_REVOKED"
    KEY_INACTIVE = "KEY_INACTIVE"
    SIGNER_MISMATCH = "SIGNER_MISMATCH"
    NOT_AUTHORIZED = "NOT_AUTHORIZED"
    SIGNATURE = "SIGNATURE"
    TIME_EVIDENCE = "TIME_EVIDENCE"
    TIME_RANGE = "TIME_RANGE"
    REPLAY = "REPLAY"
    SUPERSESSION = "SUPERSESSION"
    CONFLICT = "CONFLICT"


class ApprovalError(Exception):
    """Verification or ledger refusal. ``code`` is the machine-readable reason."""

    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(f"{code.value}: {message}")
        self.code = code


def _fail(code: ErrorCode, message: str) -> ApprovalError:
    return ApprovalError(code, message)


def parse_timestamp(value: Any, what: str = "timestamp") -> datetime:
    """Strict ``YYYY-MM-DDTHH:MM:SSZ`` (UTC). Anything else, including an offset, is refused."""
    if not isinstance(value, str):
        raise _fail(ErrorCode.SCHEMA, f"{what} must be a string")
    try:
        parsed = datetime.strptime(value, _TS_FORMAT).replace(tzinfo=UTC)
    except ValueError:
        raise _fail(ErrorCode.SCHEMA, f"{what} is not YYYY-MM-DDTHH:MM:SSZ") from None
    if parsed.strftime(_TS_FORMAT) != value:
        raise _fail(ErrorCode.SCHEMA, f"{what} is not canonical")
    return parsed


# ---- trusted authority roster (the trust anchor) --------------------------------------------


@dataclass(frozen=True)
class KeyEntry:
    """One trusted public key. ``key_id`` must be sha256(SubjectPublicKeyInfo DER), so the
    identifier cannot be repointed at a different key without detection."""

    key_id: str
    identity: str
    spki_der: bytes
    not_before: str
    not_after: str
    revoked_at: str | None = None


@dataclass(frozen=True)
class RoleAssignment:
    """An independently recorded fact: ``identity`` may act as ``role`` for ``scopes``."""

    identity: str
    role: str
    scopes: tuple[str, ...]
    outcomes: tuple[str, ...]
    not_before: str
    not_after: str


def _p256_public_key(spki_der: bytes) -> ec.EllipticCurvePublicKey:
    try:
        key = serialization.load_der_public_key(spki_der)
    except (ValueError, TypeError):
        raise _fail(ErrorCode.ROSTER_UNTRUSTED, "key is not a valid SubjectPublicKeyInfo") from None
    if not isinstance(key, ec.EllipticCurvePublicKey) or not isinstance(key.curve, ec.SECP256R1):
        raise _fail(ErrorCode.ROSTER_UNTRUSTED, "key is not an ECDSA P-256 public key")
    return key


@dataclass(frozen=True)
class Roster:
    """Versioned authority roster. Constructed by trusted code and PINNED by digest at verify
    time; never read from an approval record."""

    version: int
    roster_id: str
    keys: tuple[KeyEntry, ...]
    assignments: tuple[RoleAssignment, ...]

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise _fail(ErrorCode.ROSTER_UNTRUSTED, "roster version must be an int >= 1")
        seen: set[str] = set()
        for key in self.keys:
            if key.key_id != hashlib.sha256(key.spki_der).hexdigest():
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, f"key_id {key.key_id!r} is not the digest")
            if key.key_id in seen:
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, f"duplicate key_id {key.key_id!r}")
            seen.add(key.key_id)
            _p256_public_key(key.spki_der)
            parse_timestamp(key.not_before, "key.not_before")
            parse_timestamp(key.not_after, "key.not_after")
            if key.revoked_at is not None:
                parse_timestamp(key.revoked_at, "key.revoked_at")
        _match(self.roster_id, _ID, "roster_id")
        for key in self.keys:
            _match(key.identity, _ID, "key.identity")
            if parse_timestamp(key.not_before) > parse_timestamp(key.not_after):
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, "key window is inverted")
        for assignment in self.assignments:
            _match(assignment.identity, _ID, "assignment.identity")
            _match(assignment.role, _ID, "assignment.role")
            for field_name in ("scopes", "outcomes"):
                values = getattr(assignment, field_name)
                if not isinstance(values, tuple) or not values or len(set(values)) != len(values):
                    raise _fail(ErrorCode.ROSTER_UNTRUSTED, f"assignment.{field_name} invalid")
                for value in values:
                    _match(value, _ID, f"assignment.{field_name} entry")
            if not set(assignment.outcomes) <= OUTCOMES:
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, "assignment.outcomes unrecognised")
            if parse_timestamp(assignment.not_before) > parse_timestamp(assignment.not_after):
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, "assignment window is inverted")

    def _payload(self) -> dict[str, Any]:
        return {
            "version": self.version,
            "roster_id": self.roster_id,
            "keys": sorted(
                (
                    {
                        "key_id": k.key_id,
                        "identity": k.identity,
                        "spki_der": k.spki_der.hex(),
                        "not_before": k.not_before,
                        "not_after": k.not_after,
                        "revoked_at": k.revoked_at,
                    }
                    for k in self.keys
                ),
                key=lambda d: d["key_id"],
            ),
            "assignments": sorted(
                (
                    {
                        "identity": a.identity,
                        "role": a.role,
                        "scopes": sorted(a.scopes),
                        "outcomes": sorted(a.outcomes),
                        "not_before": a.not_before,
                        "not_after": a.not_after,
                    }
                    for a in self.assignments
                ),
                key=lambda d: json.dumps(d, sort_keys=True),
            ),
        }

    def digest(self) -> str:
        return hashlib.sha256(DOMAIN + b"roster\x00" + canonical_json(self._payload())).hexdigest()

    def key(self, key_id: str) -> KeyEntry | None:
        return next((k for k in self.keys if k.key_id == key_id), None)


@dataclass(frozen=True)
class Policy:
    require_trusted_time: bool = True
    trusted_time_authorities: frozenset[str] = frozenset()
    max_skew_seconds: int = 300

    def __post_init__(self) -> None:
        skew = self.max_skew_seconds
        if isinstance(skew, bool) or not isinstance(skew, int) or not 0 <= skew <= 900:
            raise _fail(ErrorCode.TIME_RANGE, "max_skew_seconds must be an int in 0..900")
        if not all(isinstance(a, str) for a in self.trusted_time_authorities):
            raise _fail(ErrorCode.TIME_EVIDENCE, "trusted_time_authorities must be strings")


# ---- canonical encoding and schema ----------------------------------------------------------


def signing_message(payload: dict[str, Any]) -> bytes:
    """The exact bytes that are signed: domain separator then canonical JSON."""
    return DOMAIN + canonical_json(payload)


def encode_envelope(payload: dict[str, Any], signature_hex: str) -> bytes:
    return canonical_json({"payload": payload, "signature": signature_hex})


def _no_dupes(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for key, value in pairs:
        if key in out:
            raise _fail(ErrorCode.ENCODING, f"duplicate field {key!r}")
        out[key] = value
    return out


def _reject_constant(name: str) -> Any:
    raise _fail(ErrorCode.ENCODING, f"non-finite number {name}")


def _strict_types(node: Any, path: str = "$", depth: int = 0) -> None:
    """Only str, non-bool int, None, list and dict. Floats and bools are ambiguous."""
    if depth > _MAX_DEPTH:
        raise _fail(ErrorCode.ENCODING, f"{path}: nesting too deep")
    if node is None or isinstance(node, str):
        return
    if isinstance(node, bool | float):
        raise _fail(ErrorCode.ENCODING, f"{path}: bool/float not permitted")
    if isinstance(node, int):
        return
    if isinstance(node, list):
        for i, item in enumerate(node):
            _strict_types(item, f"{path}[{i}]", depth + 1)
        return
    if isinstance(node, dict):
        for k, v in node.items():
            _strict_types(v, f"{path}.{k}", depth + 1)
        return
    raise _fail(ErrorCode.ENCODING, f"{path}: unsupported type")


def parse_envelope(raw: bytes) -> tuple[dict[str, Any], str]:
    """Decode and require ``raw`` to be byte-identical to its own canonical encoding."""
    if not isinstance(raw, bytes | bytearray):
        raise _fail(ErrorCode.ENCODING, "envelope must be bytes")
    raw = bytes(raw)
    if len(raw) > _MAX_ENVELOPE_BYTES:
        raise _fail(ErrorCode.ENCODING, "envelope is too large")
    try:
        doc = json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_dupes, parse_constant=_reject_constant
        )
    except ApprovalError:
        raise
    except (ValueError, RecursionError):
        raise _fail(ErrorCode.ENCODING, "not valid UTF-8 JSON") from None
    if not isinstance(doc, dict) or set(doc) != {"payload", "signature"}:
        raise _fail(ErrorCode.SCHEMA, "envelope must be exactly {payload, signature}")
    _strict_types(doc)
    try:
        canonical = canonical_json(doc)
    except CanonicalisationError:
        raise _fail(ErrorCode.ENCODING, "not canonicalisable") from None
    if canonical != raw:
        raise _fail(ErrorCode.ENCODING, "envelope is not in canonical form")
    payload, signature = doc["payload"], doc["signature"]
    if not isinstance(payload, dict) or not isinstance(signature, str):
        raise _fail(ErrorCode.SCHEMA, "payload must be an object and signature a string")
    return payload, signature


def _obj(parent: dict[str, Any], key: str, fields: set[str]) -> dict[str, Any]:
    node = parent.get(key)
    if not isinstance(node, dict) or set(node) != fields:
        raise _fail(ErrorCode.SCHEMA, f"{key} must be an object with exactly {sorted(fields)}")
    return node


def _match(value: Any, pattern: re.Pattern[str], what: str) -> str:
    if not isinstance(value, str) or not pattern.fullmatch(value):
        raise _fail(ErrorCode.SCHEMA, f"{what} is missing or malformed")
    return value


@dataclass(frozen=True)
class ApprovalRecord:
    record_id: str
    document_id: str
    document_sha256: str
    spec_sha256: str
    outcome: str
    scope: str
    purpose: str
    identity: str
    key_id: str
    role: str
    nonce: str
    signed_at: datetime
    roster_version: int
    time_kind: str
    time_authority: str | None
    time_attested_at: datetime | None
    supersedes: tuple[str, ...]


_PAYLOAD_FIELDS = {
    "protocol",
    "record_id",
    "roster_version",
    "document",
    "decision",
    "signer",
    "sig_alg",
    "nonce",
    "signed_at",
    "time_evidence",
    "supersedes",
}


def validate_payload(payload: dict[str, Any]) -> ApprovalRecord:
    if set(payload) != _PAYLOAD_FIELDS:
        raise _fail(ErrorCode.SCHEMA, f"payload fields must be exactly {sorted(_PAYLOAD_FIELDS)}")
    if payload["protocol"] != PROTOCOL:
        raise _fail(ErrorCode.PROTOCOL, "unsupported protocol/version")
    if payload["sig_alg"] != SIG_ALG:
        raise _fail(ErrorCode.ALGORITHM, "unsupported signature algorithm")
    version = payload["roster_version"]
    if isinstance(version, bool) or not isinstance(version, int) or version < 1:
        raise _fail(ErrorCode.SCHEMA, "roster_version must be an int >= 1")
    doc = _obj(payload, "document", {"id", "sha256", "spec_sha256"})
    dec = _obj(payload, "decision", {"outcome", "scope", "purpose"})
    sig = _obj(payload, "signer", {"identity", "key_id", "role"})
    if not isinstance(dec["outcome"], str) or dec["outcome"] not in OUTCOMES:
        raise _fail(ErrorCode.SCHEMA, "decision.outcome is not a recognised outcome")
    supersedes = payload["supersedes"]
    if not isinstance(supersedes, list) or len(set(map(str, supersedes))) != len(supersedes):
        raise _fail(ErrorCode.SCHEMA, "supersedes must be a list without duplicates")
    refs = tuple(_match(s, _ID, "supersedes entry") for s in supersedes)
    if list(refs) != sorted(refs):
        raise _fail(ErrorCode.SCHEMA, "supersedes must be sorted")
    if dec["outcome"] == "REVOKE" and not refs:
        raise _fail(ErrorCode.SCHEMA, "a REVOKE must name the record(s) it supersedes")
    evidence = payload["time_evidence"]
    if not isinstance(evidence, dict) or evidence.get("kind") not in (TIME_TRUSTED, TIME_NONE):
        raise _fail(ErrorCode.TIME_EVIDENCE, "time_evidence.kind missing or unrecognised")
    authority: str | None = None
    attested: datetime | None = None
    if evidence["kind"] == TIME_TRUSTED:
        node = _obj(payload, "time_evidence", {"kind", "authority", "token_sha256", "attested_at"})
        authority = _match(node["authority"], _ID, "time_evidence.authority")
        _match(node["token_sha256"], _HEX64, "time_evidence.token_sha256")
        attested = parse_timestamp(node["attested_at"], "time_evidence.attested_at")
    else:
        node = _obj(payload, "time_evidence", {"kind", "limitation"})
        if node["limitation"] != TIME_LIMITATION:
            raise _fail(ErrorCode.TIME_EVIDENCE, "the time limitation must be stated explicitly")
    return ApprovalRecord(
        record_id=_match(payload["record_id"], _ID, "record_id"),
        document_id=_match(doc["id"], _ID, "document.id"),
        document_sha256=_match(doc["sha256"], _HEX64, "document.sha256"),
        spec_sha256=_match(doc["spec_sha256"], _HEX64, "document.spec_sha256"),
        outcome=dec["outcome"],
        scope=_match(dec["scope"], _ID, "decision.scope"),
        purpose=_match(dec["purpose"], _ID, "decision.purpose"),
        identity=_match(sig["identity"], _ID, "signer.identity"),
        key_id=_match(sig["key_id"], _HEX64, "signer.key_id"),
        role=_match(sig["role"], _ID, "signer.role"),
        nonce=_match(payload["nonce"], _NONCE, "nonce"),
        signed_at=parse_timestamp(payload["signed_at"], "signed_at"),
        roster_version=version,
        time_kind=evidence["kind"],
        time_authority=authority,
        time_attested_at=attested,
        supersedes=refs,
    )


# ---- verification ---------------------------------------------------------------------------


@dataclass(frozen=True)
class VerifiedApproval:
    """Result of a successful verification. Not a P0 approval by itself."""

    record: ApprovalRecord
    roster_sha256: str
    time_evidence_claimed: bool
    envelope_sha256: str
    _seal: object = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if self._seal is not _SEAL:
            raise _fail(
                ErrorCode.SCHEMA, "VerifiedApproval can only be produced by verify_approval"
            )


def _check_signature(key: ec.EllipticCurvePublicKey, signature_hex: str, message: bytes) -> None:
    _match(signature_hex, _SIG, "signature")
    try:
        der = bytes.fromhex(signature_hex)
        r, s = decode_dss_signature(der)
    except ValueError:
        raise _fail(ErrorCode.SIGNATURE, "signature is not a DER ECDSA signature") from None
    if encode_dss_signature(r, s) != der or not (0 < s <= _P256_ORDER // 2):
        raise _fail(ErrorCode.SIGNATURE, "signature is not canonical low-S DER")
    try:
        key.verify(der, message, ec.ECDSA(hashes.SHA256()))
    except InvalidSignature:
        raise _fail(ErrorCode.SIGNATURE, "signature does not verify") from None


def _active(not_before: str, not_after: str, at: datetime) -> bool:
    return parse_timestamp(not_before) <= at <= parse_timestamp(not_after)


def verify_approval(raw: bytes, **kwargs: Any) -> VerifiedApproval:
    """Return a :class:`VerifiedApproval` or raise :class:`ApprovalError`, never anything else."""
    try:
        return _verify_approval(raw, **kwargs)
    except ApprovalError:
        raise
    except (TypeError, ValueError, RecursionError, OverflowError, AttributeError, KeyError):
        raise _fail(ErrorCode.SCHEMA, "malformed input") from None


def _verify_approval(
    raw: bytes,
    *,
    roster: Roster,
    pinned_roster_sha256: str,
    policy: Policy,
    expected_document_id: str,
    expected_document_sha256: str,
    expected_spec_sha256: str,
    expected_scope: str,
    expected_outcome: str,
    expected_purpose: str,
    now: datetime,
) -> VerifiedApproval:
    """Every check must pass; there is no partial success and no I/O."""
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise _fail(ErrorCode.TIME_RANGE, "now must be a UTC-aware datetime")
    if roster.digest() != pinned_roster_sha256:
        raise _fail(ErrorCode.ROSTER_UNTRUSTED, "roster digest does not match the pinned digest")
    payload, signature_hex = parse_envelope(raw)
    rec = validate_payload(payload)
    if rec.roster_version != roster.version:
        raise _fail(ErrorCode.ROSTER_VERSION, "record was made against a different roster version")
    expected = (expected_document_id, expected_document_sha256, expected_spec_sha256)
    if (rec.document_id, rec.document_sha256, rec.spec_sha256) != expected:
        raise _fail(ErrorCode.DOCUMENT_MISMATCH, "document or spec digest differs from expected")
    if rec.scope != expected_scope:
        raise _fail(ErrorCode.SCOPE_MISMATCH, "scope differs from the expected scope")

    if rec.outcome != expected_outcome:
        raise _fail(ErrorCode.DOCUMENT_MISMATCH, "outcome differs from the expected outcome")
    if rec.purpose != expected_purpose:
        raise _fail(ErrorCode.DOCUMENT_MISMATCH, "purpose differs from the expected purpose")

    entry = roster.key(rec.key_id)
    if entry is None:
        raise _fail(ErrorCode.KEY_UNKNOWN, "key is not in the trusted roster")
    if entry.identity != rec.identity:
        raise _fail(ErrorCode.SIGNER_MISMATCH, "key is not bound to the claimed signer")
    if entry.revoked_at is not None:
        raise _fail(ErrorCode.KEY_REVOKED, "key is revoked (fail-closed: any revocation rejects)")
    skew = timedelta(seconds=policy.max_skew_seconds)
    if rec.signed_at > now + skew:
        raise _fail(ErrorCode.TIME_RANGE, "signed_at is in the future")

    trusted_time = False
    if rec.time_kind == TIME_TRUSTED:
        if rec.time_authority not in policy.trusted_time_authorities:
            raise _fail(ErrorCode.TIME_EVIDENCE, "time authority is not trusted by policy")
        attested = rec.time_attested_at
        if attested is None or abs(attested - rec.signed_at) > skew or attested > now + skew:
            raise _fail(ErrorCode.TIME_EVIDENCE, "attested time inconsistent with signed_at")
        trusted_time = True
    elif policy.require_trusted_time:
        raise _fail(ErrorCode.TIME_EVIDENCE, "policy requires trusted-time evidence")

    for moment in (rec.signed_at, now):
        if not _active(entry.not_before, entry.not_after, moment):
            raise _fail(ErrorCode.KEY_INACTIVE, "key is outside its validity window")
    authorized = any(
        a.identity == rec.identity
        and a.role == rec.role
        and rec.scope in a.scopes
        and rec.outcome in a.outcomes
        and _active(a.not_before, a.not_after, rec.signed_at)
        and _active(a.not_before, a.not_after, now)
        for a in roster.assignments
    )
    if not authorized:
        raise _fail(ErrorCode.NOT_AUTHORIZED, "roster does not authorize this signer/role/scope")

    _check_signature(_p256_public_key(entry.spki_der), signature_hex, signing_message(payload))
    return VerifiedApproval(
        record=rec,
        roster_sha256=pinned_roster_sha256,
        time_evidence_claimed=trusted_time,
        envelope_sha256=hashlib.sha256(raw).hexdigest(),
        _seal=_SEAL,
    )


# ---- replay, supersession and conflict (in memory) ------------------------------------------


class ApprovalLedger:
    """Accepts :class:`VerifiedApproval` objects only once, in a consistent order.

    Rules: a record_id or nonce may be accepted once (replay); a record may supersede only
    records that exist, are still active, cover the same document and scope, and were made by the
    same signer identity; an APPROVE and a REJECT for the same (document, scope) cannot both be
    active, so a contrary decision must supersede the earlier one explicitly (conflict).
    """

    def __init__(self) -> None:
        self._records: dict[str, ApprovalRecord] = {}
        self._superseded: set[str] = set()
        self._nonces: set[str] = set()

    @staticmethod
    def _binding(r: ApprovalRecord) -> tuple[str, ...]:
        return (r.document_id, r.document_sha256, r.spec_sha256, r.scope, r.purpose)

    def active(
        self, document_id: str, document_sha256: str, spec_sha256: str, scope: str, purpose: str
    ) -> list[ApprovalRecord]:
        key = (document_id, document_sha256, spec_sha256, scope, purpose)
        return [
            r
            for rid, r in self._records.items()
            if rid not in self._superseded and r.outcome != "REVOKE" and self._binding(r) == key
        ]

    def accept(self, verified: VerifiedApproval) -> None:
        if not isinstance(verified, VerifiedApproval):
            raise _fail(ErrorCode.SCHEMA, "only a VerifiedApproval can be accepted")
        rec = verified.record
        if rec.record_id in self._records or rec.nonce in self._nonces:
            raise _fail(ErrorCode.REPLAY, "record_id or nonce already accepted")
        for ref in rec.supersedes:
            prior = self._records.get(ref)
            if prior is None or ref in self._superseded:
                raise _fail(ErrorCode.SUPERSESSION, f"{ref!r} is unknown or already superseded")
            same = (*self._binding(prior), prior.identity) == (*self._binding(rec), rec.identity)
            if not same:
                raise _fail(ErrorCode.SUPERSESSION, f"{ref!r} is a different document/scope/signer")
        survivors = [
            r for r in self.active(*self._binding(rec)) if r.record_id not in rec.supersedes
        ]
        if rec.outcome != "REVOKE" and any(r.outcome != rec.outcome for r in survivors):
            raise _fail(ErrorCode.CONFLICT, "contrary active decision exists; supersede it first")
        self._records[rec.record_id] = rec
        self._nonces.add(rec.nonce)
        self._superseded.update(rec.supersedes)
