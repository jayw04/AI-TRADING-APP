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

KNOWN LIMITATION (result objects): ``VerifiedApproval`` and ``HistoricalApproval`` are
tamper-evident, not unforgeable against code in the same process; see their docstrings.
``evaluate_requirement`` re-verifies every item from its signed bytes rather than trusting it.

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
import hmac
import json
import re
import secrets
from collections.abc import Sequence
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
_TAG_KEY = secrets.token_bytes(32)  # process-local; never stored, logged or exported


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
    HISTORY = "HISTORY"
    KEY_COMPROMISED = "KEY_COMPROMISED"


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
    compromised_since: str | None = None


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
    persons: tuple[tuple[str, str], ...] = ()

    def __post_init__(self) -> None:
        if isinstance(self.version, bool) or not isinstance(self.version, int) or self.version < 1:
            raise _fail(ErrorCode.ROSTER_UNTRUSTED, "roster version must be an int >= 1")
        seen: set[str] = set()
        points: set[bytes] = set()
        for key in self.keys:
            if key.key_id != hashlib.sha256(key.spki_der).hexdigest():
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, f"key_id {key.key_id!r} is not the digest")
            if key.key_id in seen:
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, f"duplicate key_id {key.key_id!r}")
            seen.add(key.key_id)
            point = _p256_public_key(key.spki_der).public_bytes(
                serialization.Encoding.X962, serialization.PublicFormat.UncompressedPoint
            )
            if point in points:
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, "one public key is enrolled more than once")
            points.add(point)
            parse_timestamp(key.not_before, "key.not_before")
            parse_timestamp(key.not_after, "key.not_after")
            if key.revoked_at is not None:
                parse_timestamp(key.revoked_at, "key.revoked_at")
            if key.compromised_since is not None:
                parse_timestamp(key.compromised_since, "key.compromised_since")
        _match(self.roster_id, _ID, "roster_id")
        mapped: set[str] = set()
        for pair in self.persons:
            if not isinstance(pair, tuple) or len(pair) != 2:
                raise _fail(
                    ErrorCode.ROSTER_UNTRUSTED, "persons entries must be (identity, person_id)"
                )
            _match(pair[0], _ID, "persons identity")
            _match(pair[1], _ID, "persons person_id")
            if pair[0] in mapped:
                raise _fail(ErrorCode.ROSTER_UNTRUSTED, "identity mapped to more than one person")
            mapped.add(pair[0])
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
        payload = self._base_payload()
        for entry in payload["keys"]:
            if entry["compromised_since"] is None:
                del entry["compromised_since"]
        if self.persons:
            payload["persons"] = sorted([list(pair) for pair in self.persons])
        return payload

    def _base_payload(self) -> dict[str, Any]:
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
                        "compromised_since": k.compromised_since,
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

    def person_of(self, identity: str) -> str | None:
        return dict(self.persons).get(identity)

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


def _verified_tag(envelope: bytes, roster_sha256: str, time_claimed: bool) -> str:
    body = {
        "envelope_sha256": hashlib.sha256(envelope).hexdigest(),
        "roster_sha256": roster_sha256,
        "time_evidence_claimed": time_claimed,
    }
    message = DOMAIN + b"verified\x00" + canonical_json(body)
    return hmac.new(_TAG_KEY, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class VerifiedApproval:
    """Evidence that :func:`verify_approval` accepted ``envelope`` in this process.

    This is not a P0 approval and not an unforgeable capability: Python cannot stop code running
    in the same process from reading module state. What it does guarantee is that a copy, a
    ``dataclasses.replace`` or a hand-built instance whose fields disagree with the signed bytes
    is refused. ``check`` re-derives the record from the signed envelope bytes and verifies a
    process-local MAC over (envelope digest, roster digest, time flag). Consumers that matter must
    call ``check`` (the ledger does) and rely on the record re-derived from ``envelope`` rather
    than on the type of the object or on any single field.
    """

    record: ApprovalRecord
    roster_sha256: str
    time_evidence_claimed: bool
    envelope_sha256: str
    envelope: bytes
    _seal: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        if not isinstance(self.envelope, bytes) or not isinstance(self._seal, str):
            raise _fail(ErrorCode.SCHEMA, "VerifiedApproval is malformed")
        if hashlib.sha256(self.envelope).hexdigest() != self.envelope_sha256:
            raise _fail(ErrorCode.SCHEMA, "VerifiedApproval envelope digest does not match")
        payload, _ = parse_envelope(self.envelope)
        if validate_payload(payload) != self.record:
            raise _fail(ErrorCode.SCHEMA, "VerifiedApproval record differs from the signed bytes")
        expected = _verified_tag(self.envelope, self.roster_sha256, self.time_evidence_claimed)
        if not hmac.compare_digest(self._seal, expected):
            raise _fail(
                ErrorCode.SCHEMA, "VerifiedApproval can only be produced by verify_approval"
            )

    def __copy__(self) -> VerifiedApproval:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> VerifiedApproval:
        return self

    def __reduce__(self) -> Any:
        raise _fail(ErrorCode.SCHEMA, "VerifiedApproval cannot be serialised")


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
        envelope=bytes(raw),
        _seal=_verified_tag(bytes(raw), pinned_roster_sha256, trusted_time),
    )


# ---- replay, supersession and conflict (in memory) ------------------------------------------


class ApprovalLedger:
    """Accepts :class:`VerifiedApproval` objects only once, in a consistent order.

    Rules: a record_id or nonce may be accepted once (replay); a record may supersede only
    records that exist, are still active, cover the same document, scope, purpose and digests,
    and were made by the SAME signer identity (one signer can never supersede another).

    Contrary decisions are never dropped. An APPROVE and a REJECT for the same binding may both
    be active; both are kept as independently identifiable evidence and the binding is reported
    as an explicit unresolved CONFLICT until the original signer supersedes their own record.
    ``decision_state`` is fail-closed: it never reports APPROVED while a conflict is unresolved.
    "APPROVED" means only that active evidence contains no contrary decision; it is not a quorum
    or sufficiency rule, and it is unrelated to the 17-member trading verdict contract.
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

    def unresolved_conflicts(
        self, document_id: str, document_sha256: str, spec_sha256: str, scope: str, purpose: str
    ) -> tuple[tuple[str, str], ...]:
        """(approve_record_id, reject_record_id) pairs that are both still active."""
        live = self.active(document_id, document_sha256, spec_sha256, scope, purpose)
        approves = sorted(r.record_id for r in live if r.outcome == "APPROVE")
        rejects = sorted(r.record_id for r in live if r.outcome == "REJECT")
        return tuple((a, r) for a in approves for r in rejects)

    def decision_state(
        self, document_id: str, document_sha256: str, spec_sha256: str, scope: str, purpose: str
    ) -> str:
        """NONE, APPROVED, REJECTED or CONFLICT (fail-closed: a conflict is never APPROVED)."""
        live = self.active(document_id, document_sha256, spec_sha256, scope, purpose)
        outcomes = {r.outcome for r in live}
        if outcomes == {"APPROVE", "REJECT"}:
            return "CONFLICT"
        if outcomes == {"APPROVE"}:
            return "APPROVED"
        if outcomes == {"REJECT"}:
            return "REJECTED"
        return "NONE"

    def accept(self, verified: VerifiedApproval) -> None:
        if not isinstance(verified, VerifiedApproval):
            raise _fail(ErrorCode.SCHEMA, "only a VerifiedApproval can be accepted")
        verified.check()  # re-derive from the signed bytes; refuses tampered instances
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
        self._records[rec.record_id] = rec
        self._nonces.add(rec.nonce)
        self._superseded.update(rec.supersedes)


# ---- slice 3d: roster history, as-of verification, distinct-person combinations -------------
#
# Synthetic, in-memory proof of behavior. The roster history is NOT the durable audit ledger,
# and a synthetic timestamp authority proves nothing about real-world time: it only shows that
# the verifier refuses signer-asserted time and checks a pinned countersignature instead.

GENESIS_HASH = "0" * 64
DOMAIN_TS = b"RANGE-002/timestamp/v1\x00"


def _link_hash(version: int, roster_sha256: str, prev_record_sha256: str, effective_at: str) -> str:
    body = {
        "version": version,
        "roster_sha256": roster_sha256,
        "prev_record_sha256": prev_record_sha256,
        "effective_at": effective_at,
    }
    return hashlib.sha256(DOMAIN + b"roster-link\x00" + canonical_json(body)).hexdigest()


@dataclass(frozen=True)
class RosterLink:
    """One hash-chained history record binding a roster version to its canonical digest."""

    version: int
    roster_sha256: str
    prev_record_sha256: str
    effective_at: str
    record_sha256: str


def make_roster_link(roster: Roster, prev_record_sha256: str, effective_at: str) -> RosterLink:
    return RosterLink(
        version=roster.version,
        roster_sha256=roster.digest(),
        prev_record_sha256=prev_record_sha256,
        effective_at=effective_at,
        record_sha256=_link_hash(roster.version, roster.digest(), prev_record_sha256, effective_at),
    )


def _history_error(message: str) -> ApprovalError:
    return _fail(ErrorCode.HISTORY, message)


def _check_roster_step(prev: Roster, nxt: Roster) -> None:
    """A new roster version may add keys and revoke or flag keys, but may not rewrite history."""
    for old in prev.keys:
        new = nxt.key(old.key_id)
        if new is None:
            raise _history_error(f"key {old.key_id!r} was removed from the roster")
        if (new.identity, new.spki_der, new.not_before) != (
            old.identity,
            old.spki_der,
            old.not_before,
        ):
            raise _history_error(f"key {old.key_id!r} was rewritten")
        if old.revoked_at is not None and new.revoked_at != old.revoked_at:
            raise _history_error(f"revocation of key {old.key_id!r} was changed or cleared")
        if old.compromised_since is not None and new.compromised_since != old.compromised_since:
            raise _history_error(f"compromise flag of key {old.key_id!r} was changed or cleared")
    old_people = dict(prev.persons)
    new_people = dict(nxt.persons)
    for identity, person in old_people.items():
        if new_people.get(identity) != person:
            raise _history_error(f"identity {identity!r} was remapped to a different person")


class RosterHistory:
    """Immutable, ordered, hash-chained roster versions. Construction verifies the whole chain;
    :meth:`verify_head` ties it to a head digest the caller pinned out of band, so substitution
    or truncation of the history is detected."""

    def __init__(self, links: tuple[RosterLink, ...], rosters: tuple[Roster, ...]) -> None:
        if not links or len(links) != len(rosters):
            raise _history_error("history needs one roster per link and at least one version")
        prev_hash = GENESIS_HASH
        prev_time: datetime | None = None
        for index, (link, roster) in enumerate(zip(links, rosters, strict=True), start=1):
            if link.version != index or roster.version != index:
                raise _history_error("versions must be consecutive from 1 and match their rosters")
            if link.prev_record_sha256 != prev_hash:
                raise _history_error(f"version {index} does not chain to the previous record")
            if link.roster_sha256 != roster.digest():
                raise _history_error(f"version {index} roster does not match its recorded digest")
            expected = _link_hash(
                index, link.roster_sha256, link.prev_record_sha256, link.effective_at
            )
            if link.record_sha256 != expected:
                raise _history_error(f"version {index} record hash is wrong")
            effective = parse_timestamp(link.effective_at, "effective_at")
            if prev_time is not None and effective <= prev_time:
                raise _history_error("effective_at must be strictly increasing")
            if index > 1:
                _check_roster_step(rosters[index - 2], roster)
            prev_hash, prev_time = link.record_sha256, effective
        self._links = tuple(links)
        self._rosters = tuple(rosters)

    @property
    def head_sha256(self) -> str:
        return self._links[-1].record_sha256

    @property
    def latest(self) -> Roster:
        return self._rosters[-1]

    def verify_head(self, pinned_head_sha256: str) -> None:
        if self.head_sha256 != pinned_head_sha256:
            raise _fail(ErrorCode.ROSTER_UNTRUSTED, "history head does not match the pinned head")

    def roster_for(self, version: int) -> Roster:
        if (
            isinstance(version, bool)
            or not isinstance(version, int)
            or not 1 <= version <= len(self._rosters)
        ):
            raise _fail(ErrorCode.ROSTER_VERSION, "roster version is not in the history")
        return self._rosters[version - 1]

    def interval(self, version: int) -> tuple[datetime, datetime | None]:
        self.roster_for(version)
        start = parse_timestamp(self._links[version - 1].effective_at)
        end = (
            parse_timestamp(self._links[version].effective_at)
            if version < len(self._links)
            else None
        )
        return start, end


@dataclass(frozen=True)
class TimeAuthority:
    """A pinned timestamp authority key (synthetic here; the real authority is an open decision)."""

    authority_id: str
    spki_der: bytes
    not_before: str
    not_after: str


@dataclass(frozen=True)
class TimeAuthorityRoster:
    authorities: tuple[TimeAuthority, ...]

    def __post_init__(self) -> None:
        seen: set[str] = set()
        for authority in self.authorities:
            _match(authority.authority_id, _ID, "authority_id")
            if authority.authority_id in seen:
                raise _fail(ErrorCode.TIME_EVIDENCE, "duplicate time authority")
            seen.add(authority.authority_id)
            _p256_public_key(authority.spki_der)
            if parse_timestamp(authority.not_before) > parse_timestamp(authority.not_after):
                raise _fail(ErrorCode.TIME_EVIDENCE, "time authority window is inverted")

    def digest(self) -> str:
        body = sorted(
            (
                {
                    "authority_id": a.authority_id,
                    "spki_der": a.spki_der.hex(),
                    "not_before": a.not_before,
                    "not_after": a.not_after,
                }
                for a in self.authorities
            ),
            key=lambda d: d["authority_id"],
        )
        return hashlib.sha256(DOMAIN_TS + b"authorities\x00" + canonical_json(body)).hexdigest()

    def get(self, authority_id: str) -> TimeAuthority | None:
        return next((a for a in self.authorities if a.authority_id == authority_id), None)


@dataclass(frozen=True)
class TimeStamp:
    """Countersignature over the exact signed payload, made by a pinned time authority."""

    authority_id: str
    attested_at: str
    signature_hex: str


def timestamp_message(authority_id: str, attested_at: str, payload: dict[str, Any]) -> bytes:
    body = {
        "authority_id": authority_id,
        "attested_at": attested_at,
        "payload_sha256": hashlib.sha256(signing_message(payload)).hexdigest(),
    }
    return DOMAIN_TS + canonical_json(body)


def _historical_tag(
    envelope: bytes,
    *,
    roster_version: int,
    roster_sha256: str,
    as_of: datetime,
    person_id: str | None,
    later_compromise: bool,
    key_revoked_later_at: str | None,
    history_head_sha256: str,
    time_authorities_sha256: str,
    stamp: TimeStamp,
) -> str:
    body = {
        "envelope_sha256": hashlib.sha256(envelope).hexdigest(),
        "roster_version": roster_version,
        "roster_sha256": roster_sha256,
        "as_of": as_of.strftime(_TS_FORMAT),
        "person_id": person_id,
        "later_compromise": later_compromise,
        "key_revoked_later_at": key_revoked_later_at,
        "history_head_sha256": history_head_sha256,
        "time_authorities_sha256": time_authorities_sha256,
        "stamp_authority_id": stamp.authority_id,
        "stamp_attested_at": stamp.attested_at,
        "stamp_signature_hex": stamp.signature_hex,
    }
    message = DOMAIN + b"historical\x00" + canonical_json(body)
    return hmac.new(_TAG_KEY, message, hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class HistoricalApproval:
    """A signature that verified as of an authenticated instant. ``acceptable`` is False when the
    key was flagged compromised later: the signature was genuine then, but the approval is not
    to be relied upon without an explicit human decision.

    Like :class:`VerifiedApproval` this is tamper-evident, not unforgeable against code running in
    the same process. It is NOT an independent source of authority: it carries the signed envelope,
    the time-authority countersignature and the pins it was verified under, and a process-local MAC
    binds every derived field (roster digest, person, compromise flags, as-of instant) to them.
    ``check`` re-derives the record from the signed bytes and verifies the MAC, so
    ``dataclasses.replace``, hand-built, copied or pickled instances are refused.
    Authority-sensitive consumers (:func:`evaluate_requirement`) additionally RE-VERIFY the
    envelope and stamp against a caller-supplied roster history and time-authority set, and use the
    freshly derived result rather than the fields of this object.
    """

    record: ApprovalRecord
    roster_version: int
    roster_sha256: str
    as_of: datetime
    envelope_sha256: str
    envelope: bytes
    stamp: TimeStamp
    history_head_sha256: str
    time_authorities_sha256: str
    person_id: str | None
    later_compromise: bool
    key_revoked_later_at: str | None
    _seal: str = field(default="", repr=False, compare=False)

    def __post_init__(self) -> None:
        self.check()

    def check(self) -> None:
        if (
            not isinstance(self.envelope, bytes)
            or not isinstance(self._seal, str)
            or not isinstance(self.stamp, TimeStamp)
            or not isinstance(self.as_of, datetime)
            or self.as_of.tzinfo is None
            or isinstance(self.roster_version, bool)
            or not isinstance(self.roster_version, int)
            or not isinstance(self.later_compromise, bool)
        ):
            raise _fail(ErrorCode.SCHEMA, "HistoricalApproval is malformed")
        if hashlib.sha256(self.envelope).hexdigest() != self.envelope_sha256:
            raise _fail(ErrorCode.SCHEMA, "HistoricalApproval envelope digest does not match")
        payload, _ = parse_envelope(self.envelope)
        record = validate_payload(payload)
        if record != self.record or record.roster_version != self.roster_version:
            raise _fail(ErrorCode.SCHEMA, "HistoricalApproval record differs from the signed bytes")
        expected = _historical_tag(
            self.envelope,
            roster_version=self.roster_version,
            roster_sha256=self.roster_sha256,
            as_of=self.as_of,
            person_id=self.person_id,
            later_compromise=self.later_compromise,
            key_revoked_later_at=self.key_revoked_later_at,
            history_head_sha256=self.history_head_sha256,
            time_authorities_sha256=self.time_authorities_sha256,
            stamp=self.stamp,
        )
        if not hmac.compare_digest(self._seal, expected):
            raise _fail(ErrorCode.SCHEMA, "HistoricalApproval can only be produced by the verifier")

    @property
    def acceptable(self) -> bool:
        return not self.later_compromise

    def __copy__(self) -> HistoricalApproval:
        return self

    def __deepcopy__(self, memo: dict[int, Any]) -> HistoricalApproval:
        return self

    def __reduce__(self) -> Any:
        raise _fail(ErrorCode.SCHEMA, "HistoricalApproval cannot be serialised")


def verify_approval_as_of(raw: bytes, **kwargs: Any) -> HistoricalApproval:
    """Typed-errors-only wrapper around :func:`_verify_approval_as_of`."""
    try:
        return _verify_approval_as_of(raw, **kwargs)
    except ApprovalError:
        raise
    except (TypeError, ValueError, RecursionError, OverflowError, AttributeError, KeyError):
        raise _fail(ErrorCode.SCHEMA, "malformed input") from None


def _verify_approval_as_of(
    raw: bytes,
    *,
    history: RosterHistory,
    pinned_head_sha256: str,
    expected_roster_sha256: str,
    time_authorities: TimeAuthorityRoster,
    pinned_time_authorities_sha256: str,
    stamp: TimeStamp | None,
    expected_document_id: str,
    expected_document_sha256: str,
    expected_spec_sha256: str,
    expected_scope: str,
    expected_outcome: str,
    expected_purpose: str,
    now: datetime,
    max_skew_seconds: int = 300,
) -> HistoricalApproval:
    """Verify against the roster version the record names, evaluated at the instant a pinned time
    authority attested. ``now`` is used only to refuse stamps from the future. The signer's own
    ``signed_at`` and ``time_evidence`` claims are never the time source."""
    if now.tzinfo is None or now.utcoffset() != timedelta(0):
        raise _fail(ErrorCode.TIME_RANGE, "now must be a UTC-aware datetime")
    Policy(max_skew_seconds=max_skew_seconds)  # validates the bound
    skew = timedelta(seconds=max_skew_seconds)
    history.verify_head(pinned_head_sha256)
    if time_authorities.digest() != pinned_time_authorities_sha256:
        raise _fail(ErrorCode.ROSTER_UNTRUSTED, "time-authority set does not match its pin")
    if not isinstance(stamp, TimeStamp):
        raise _fail(ErrorCode.TIME_EVIDENCE, "authenticated time evidence is required")

    payload, signature_hex = parse_envelope(raw)
    rec = validate_payload(payload)
    roster = history.roster_for(rec.roster_version)
    if roster.digest() != expected_roster_sha256:
        raise _fail(
            ErrorCode.ROSTER_UNTRUSTED, "history roster differs from the pinned roster reference"
        )
    expected = (expected_document_id, expected_document_sha256, expected_spec_sha256)
    if (rec.document_id, rec.document_sha256, rec.spec_sha256) != expected:
        raise _fail(ErrorCode.DOCUMENT_MISMATCH, "document or spec digest differs from expected")
    if rec.scope != expected_scope:
        raise _fail(ErrorCode.SCOPE_MISMATCH, "scope differs from the expected scope")
    if rec.outcome != expected_outcome or rec.purpose != expected_purpose:
        raise _fail(ErrorCode.DOCUMENT_MISMATCH, "outcome or purpose differs from expected")

    authority = time_authorities.get(stamp.authority_id)
    if authority is None:
        raise _fail(ErrorCode.TIME_EVIDENCE, "time authority is not pinned")
    as_of = parse_timestamp(stamp.attested_at, "stamp.attested_at")
    if not _active(authority.not_before, authority.not_after, as_of):
        raise _fail(ErrorCode.TIME_EVIDENCE, "time authority key is outside its validity window")
    _check_signature(
        _p256_public_key(authority.spki_der),
        stamp.signature_hex,
        timestamp_message(stamp.authority_id, stamp.attested_at, payload),
    )
    if as_of > now + skew or abs(as_of - rec.signed_at) > skew:
        raise _fail(ErrorCode.TIME_EVIDENCE, "attested time is inconsistent with the record or now")
    start, end = history.interval(rec.roster_version)
    if as_of < start or (end is not None and as_of >= end):
        raise _fail(
            ErrorCode.ROSTER_VERSION, "roster version was not in force at the attested time"
        )

    entry = roster.key(rec.key_id)
    if entry is None:
        raise _fail(ErrorCode.KEY_UNKNOWN, "key is not in the roster version in force")
    if entry.identity != rec.identity:
        raise _fail(ErrorCode.SIGNER_MISMATCH, "key is not bound to the claimed signer")
    if not _active(entry.not_before, entry.not_after, as_of):
        raise _fail(ErrorCode.KEY_INACTIVE, "key was outside its validity window at that time")
    current = history.latest.key(rec.key_id)
    if current is None:
        raise _history_error("key vanished from the latest roster")
    for flagged in (entry.revoked_at, current.revoked_at):
        if flagged is not None and parse_timestamp(flagged) <= as_of:
            raise _fail(ErrorCode.KEY_REVOKED, "key was already revoked at that time")
    if (
        current.compromised_since is not None
        and parse_timestamp(current.compromised_since) <= as_of
    ):
        raise _fail(ErrorCode.KEY_COMPROMISED, "key was already compromised at that time")
    authorized = any(
        a.identity == rec.identity
        and a.role == rec.role
        and rec.scope in a.scopes
        and rec.outcome in a.outcomes
        and _active(a.not_before, a.not_after, as_of)
        for a in roster.assignments
    )
    if not authorized:
        raise _fail(
            ErrorCode.NOT_AUTHORIZED, "roster did not authorize this signer/role/scope then"
        )
    _check_signature(_p256_public_key(entry.spki_der), signature_hex, signing_message(payload))
    later_compromise = current.compromised_since is not None
    person_id = roster.person_of(rec.identity)
    roster_sha256 = roster.digest()
    return HistoricalApproval(
        record=rec,
        roster_version=rec.roster_version,
        roster_sha256=roster_sha256,
        as_of=as_of,
        envelope_sha256=hashlib.sha256(raw).hexdigest(),
        envelope=bytes(raw),
        stamp=stamp,
        history_head_sha256=pinned_head_sha256,
        time_authorities_sha256=pinned_time_authorities_sha256,
        person_id=person_id,
        later_compromise=later_compromise,
        key_revoked_later_at=current.revoked_at,
        _seal=_historical_tag(
            bytes(raw),
            roster_version=rec.roster_version,
            roster_sha256=roster_sha256,
            as_of=as_of,
            person_id=person_id,
            later_compromise=later_compromise,
            key_revoked_later_at=current.revoked_at,
            history_head_sha256=pinned_head_sha256,
            time_authorities_sha256=pinned_time_authorities_sha256,
            stamp=stamp,
        ),
    )


@dataclass(frozen=True)
class ApprovalRequirement:
    """A synthetic document-class policy: which roles must approve and how many different
    natural persons are needed. Not an adopted P0 rule."""

    document_id: str
    document_sha256: str
    spec_sha256: str
    scope: str
    purpose: str
    required_roles: tuple[str, ...]
    min_distinct_persons: int

    def __post_init__(self) -> None:
        _match(self.document_id, _ID, "document_id")
        _match(self.document_sha256, _HEX64, "document_sha256")
        _match(self.spec_sha256, _HEX64, "spec_sha256")
        _match(self.scope, _ID, "scope")
        _match(self.purpose, _ID, "purpose")
        if not isinstance(self.required_roles, tuple) or len(set(self.required_roles)) != len(
            self.required_roles
        ):
            raise _fail(ErrorCode.SCHEMA, "required_roles must be a tuple without duplicates")
        for role in self.required_roles:
            _match(role, _ID, "required role")
        count = self.min_distinct_persons
        if isinstance(count, bool) or not isinstance(count, int) or count < 1:
            raise _fail(ErrorCode.SCHEMA, "min_distinct_persons must be an int >= 1")
        if count < len(self.required_roles):
            raise _fail(ErrorCode.SCHEMA, "each required role needs its own person")

    def binding(self) -> tuple[str, str, str, str, str]:
        return (self.document_id, self.document_sha256, self.spec_sha256, self.scope, self.purpose)


@dataclass(frozen=True)
class RequirementResult:
    """``state`` is SATISFIED, UNSATISFIED, REJECTED or CONFLICT (same vocabulary as
    :meth:`ApprovalLedger.decision_state`). ``conflicts`` lists every (approve, reject) record-id
    pair that is simultaneously active; dissent is reported, never discarded."""

    satisfied: bool
    distinct_persons: tuple[str, ...]
    reasons: tuple[str, ...]
    state: str = "UNSATISFIED"
    conflicts: tuple[tuple[str, str], ...] = ()


def _assign_roles(roles: tuple[str, ...], held: dict[str, set[str]]) -> bool:
    """Can every required role be filled by a different person who holds an approval in it?"""

    def place(index: int, used: frozenset[str]) -> bool:
        if index == len(roles):
            return True
        return any(
            place(index + 1, used | {person})
            for person, person_roles in held.items()
            if person not in used and roles[index] in person_roles
        )

    return place(0, frozenset())


def evaluate_requirement(
    approvals: Sequence[HistoricalApproval],
    requirement: ApprovalRequirement,
    *,
    history: RosterHistory,
    pinned_head_sha256: str,
    time_authorities: TimeAuthorityRoster,
    pinned_time_authorities_sha256: str,
    now: datetime,
    max_skew_seconds: int = 300,
) -> RequirementResult:
    """Count approvals by natural person. Raises for duplicate, mismatched, unmapped, tampered or
    badly superseded evidence; returns an explicit unsatisfied/CONFLICT/REJECTED result for missing,
    insufficient or contradictory evidence. Several keys, identities or roles held by one person
    count as one person.

    Every item is re-verified from its signed envelope and countersignature against the
    caller-supplied, pinned roster history and time-authority set; the freshly derived result,
    not the carried object, is what is counted. A contrary decision from any signer is never
    discarded and an unresolved APPROVE/REJECT contradiction can never satisfy a requirement.
    Supersession stays restricted to the original signer; no quorum or veto rule is invented."""
    if not isinstance(requirement, ApprovalRequirement):
        raise _fail(ErrorCode.SCHEMA, "requirement must be an ApprovalRequirement")
    reasons: list[str] = []
    seen_ids: set[str] = set()
    seen_nonces: set[str] = set()
    if not all(isinstance(a, HistoricalApproval) for a in approvals):
        raise _fail(ErrorCode.SCHEMA, "only HistoricalApproval evidence can be evaluated")
    for carried_item in approvals:
        carried_item.check()  # refuses replace()d, hand-built, mutated or tampered evidence
    ordered = sorted(approvals, key=lambda a: (a.as_of, a.record.record_id))
    active: dict[str, HistoricalApproval] = {}
    for carried in ordered:
        rec = carried.record
        if rec.record_id in seen_ids or rec.nonce in seen_nonces:
            raise _fail(ErrorCode.REPLAY, "duplicate approval evidence")
        seen_ids.add(rec.record_id)
        seen_nonces.add(rec.nonce)
        binding = (rec.document_id, rec.document_sha256, rec.spec_sha256, rec.scope, rec.purpose)
        if binding != requirement.binding():
            raise _fail(ErrorCode.DOCUMENT_MISMATCH, "approval is bound to a different document")
        item = verify_approval_as_of(
            carried.envelope,
            history=history,
            pinned_head_sha256=pinned_head_sha256,
            expected_roster_sha256=carried.roster_sha256,
            time_authorities=time_authorities,
            pinned_time_authorities_sha256=pinned_time_authorities_sha256,
            stamp=carried.stamp,
            expected_document_id=requirement.document_id,
            expected_document_sha256=requirement.document_sha256,
            expected_spec_sha256=requirement.spec_sha256,
            expected_scope=requirement.scope,
            expected_outcome=rec.outcome,
            expected_purpose=requirement.purpose,
            now=now,
            max_skew_seconds=max_skew_seconds,
        )
        if item.later_compromise != carried.later_compromise:
            reasons.append(f"{rec.record_id}: key state changed since the evidence was produced")
        for ref in rec.supersedes:
            prior = active.get(ref)
            if prior is None or prior.record.identity != rec.identity:
                raise _fail(
                    ErrorCode.SUPERSESSION, f"{ref!r} is unknown, withdrawn or another signer's"
                )
            del active[ref]
        if rec.outcome != "REVOKE":
            active[rec.record_id] = item
    live_approvals: list[HistoricalApproval] = []
    dissent: list[HistoricalApproval] = []
    for item in active.values():
        if item.later_compromise:
            reasons.append(f"{item.record.record_id}: signer key flagged compromised later")
            if item.record.outcome == "REJECT":
                dissent.append(item)  # fail closed: dissent is never silently dropped
            continue
        if item.person_id is None:
            raise _fail(ErrorCode.NOT_AUTHORIZED, "signer is not mapped to a natural person")
        if item.record.outcome == "REJECT":
            dissent.append(item)
        else:
            live_approvals.append(item)
    held: dict[str, set[str]] = {}
    for item in live_approvals:
        held.setdefault(item.person_id or "", set()).add(item.record.role)
    persons = tuple(sorted(held))
    if dissent:
        rejects = sorted(d.record.record_id for d in dissent)
        if live_approvals:
            approves = sorted(a.record.record_id for a in live_approvals)
            pairs = tuple((a, r) for a in approves for r in rejects)
            return RequirementResult(
                False,
                persons,
                (*reasons, "contradictory approvals are active and unresolved"),
                "CONFLICT",
                pairs,
            )
        return RequirementResult(
            False, (), (*reasons, "an active REJECT blocks approval"), "REJECTED", ()
        )
    blocking: list[str] = []
    if len(persons) < requirement.min_distinct_persons:
        blocking.append(
            f"{len(persons)} distinct person(s); {requirement.min_distinct_persons} required"
        )
    if not _assign_roles(requirement.required_roles, held):
        blocking.append("required roles are not filled by different persons")
    state = "UNSATISFIED" if blocking else "SATISFIED"
    return RequirementResult(not blocking, persons, (*reasons, *blocking), state, ())
