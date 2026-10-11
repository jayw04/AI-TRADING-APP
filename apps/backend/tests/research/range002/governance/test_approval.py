"""Synthetic tests for the internal approval verifier (phase 3c).

Disposable in-memory P-256 keys only; nothing here is a real approval, key or signer. Every
signature below is produced with ``cryptography`` primitives inside the test process.
"""

from __future__ import annotations

import ast
import copy
import hashlib
import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives.asymmetric.utils import (
    decode_dss_signature,
    encode_dss_signature,
)

from app.research.range002.governance import approval as ap
from app.research.range002.governance.approval import (
    ApprovalError,
    ApprovalLedger,
    ErrorCode,
    KeyEntry,
    Policy,
    RoleAssignment,
    Roster,
    encode_envelope,
    signing_message,
    verify_approval,
)

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
SIGNED = "2026-10-20T11:59:00Z"
DOC = {"id": "SYNTH-DOC-1", "sha256": "ab" * 32, "spec_sha256": "cd" * 32}
SCOPE = "SYNTH-SCOPE"
ORDER = ap._P256_ORDER


def _keypair() -> tuple[ec.EllipticCurvePrivateKey, bytes]:
    private = ec.generate_private_key(ec.SECP256R1())
    spki = private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )
    return private, spki


def _sign(private: ec.EllipticCurvePrivateKey, message: bytes, *, low_s: bool = True) -> str:
    r, s = decode_dss_signature(private.sign(message, ec.ECDSA(hashes.SHA256())))
    if (s > ORDER // 2) == low_s:
        s = ORDER - s
    return encode_dss_signature(r, s).hex()


class World:
    """A synthetic roster with two human signers and a disposable outsider key."""

    def __init__(self) -> None:
        self.alice, alice_spki = _keypair()
        self.bob, bob_spki = _keypair()
        self.mallory, mallory_spki = _keypair()
        self.alice_id = hashlib.sha256(alice_spki).hexdigest()
        self.bob_id = hashlib.sha256(bob_spki).hexdigest()
        self.mallory_id = hashlib.sha256(mallory_spki).hexdigest()
        self.alice_entry = KeyEntry(
            self.alice_id, "SYNTH-ALICE", alice_spki, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
        )
        self.bob_entry = KeyEntry(
            self.bob_id, "SYNTH-BOB", bob_spki, "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
        )
        self.alice_role = RoleAssignment(
            "SYNTH-ALICE", "SYNTH-OWNER", (SCOPE,), "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
        )
        self.bob_role = RoleAssignment(
            "SYNTH-BOB", "SYNTH-VALIDATOR", (SCOPE,), "2026-01-01T00:00:00Z", "2027-01-01T00:00:00Z"
        )
        self.mallory_spki = mallory_spki
        self.policy = Policy(True, frozenset({"SYNTH-TSA"}), 300)

    def roster(self, keys: Any = None, assignments: Any = None, version: int = 1) -> Roster:
        return Roster(
            version,
            "SYNTH-ROSTER",
            tuple(keys if keys is not None else (self.alice_entry, self.bob_entry)),
            tuple(assignments if assignments is not None else (self.alice_role, self.bob_role)),
        )

    def payload(self, **over: Any) -> dict[str, Any]:
        base: dict[str, Any] = {
            "protocol": ap.PROTOCOL,
            "record_id": "SYNTH-REC-1",
            "roster_version": 1,
            "document": dict(DOC),
            "decision": {"outcome": "APPROVE", "scope": SCOPE, "purpose": "SYNTH-PURPOSE"},
            "signer": {"identity": "SYNTH-ALICE", "key_id": self.alice_id, "role": "SYNTH-OWNER"},
            "sig_alg": ap.SIG_ALG,
            "nonce": "11" * 16,
            "signed_at": SIGNED,
            "time_evidence": {
                "kind": ap.TIME_TRUSTED,
                "authority": "SYNTH-TSA",
                "token_sha256": "ee" * 32,
                "attested_at": SIGNED,
            },
            "supersedes": [],
        }
        for dotted, value in over.items():
            node = base
            *parents, leaf = dotted.split("__")
            for p in parents:
                node = node[p]
            if value is _DELETE:
                del node[leaf]
            else:
                node[leaf] = value
        return base

    def envelope(self, payload: dict[str, Any], signer: Any = None, **kw: Any) -> bytes:
        key = signer or self.alice
        return encode_envelope(payload, _sign(key, signing_message(payload), **kw))


_DELETE = object()


@pytest.fixture(scope="module")
def w() -> World:
    return World()


def _verify(w: World, raw: bytes, roster: Roster | None = None, **over: Any) -> ap.VerifiedApproval:
    roster = roster or w.roster()
    args: dict[str, Any] = {
        "roster": roster,
        "pinned_roster_sha256": roster.digest(),
        "policy": w.policy,
        "expected_document_id": DOC["id"],
        "expected_document_sha256": DOC["sha256"],
        "expected_spec_sha256": DOC["spec_sha256"],
        "expected_scope": SCOPE,
        "now": NOW,
    }
    args.update(over)
    return verify_approval(raw, **args)


def _code(w: World, raw: Any, roster: Roster | None = None, **over: Any) -> ErrorCode:
    with pytest.raises(ApprovalError) as info:
        _verify(w, raw, roster, **over)
    return info.value.code


# ---- valid path -----------------------------------------------------------------------------


def test_valid_approval_verifies(w):
    result = _verify(w, w.envelope(w.payload()))
    assert result.record.identity == "SYNTH-ALICE"
    assert result.record.outcome == "APPROVE"
    assert result.time_trusted is True
    assert result.roster_sha256 == w.roster().digest()


def test_valid_without_trusted_time_only_when_policy_allows_and_limitation_is_explicit(w):
    payload = w.payload(time_evidence={"kind": ap.TIME_NONE, "limitation": ap.TIME_LIMITATION})
    raw = w.envelope(payload)
    relaxed = Policy(require_trusted_time=False)
    assert _verify(w, raw, policy=relaxed).time_trusted is False
    assert _code(w, raw) == ErrorCode.TIME_EVIDENCE  # strict policy refuses it


def test_second_signer_with_a_different_role_verifies(w):
    payload = w.payload(
        signer={"identity": "SYNTH-BOB", "key_id": w.bob_id, "role": "SYNTH-VALIDATOR"},
        record_id="SYNTH-REC-2",
        nonce="22" * 16,
    )
    assert _verify(w, w.envelope(payload, w.bob)).record.role == "SYNTH-VALIDATOR"


# ---- altered content ------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("document__sha256", "00" * 32),
        ("document__spec_sha256", "00" * 32),
        ("document__id", "SYNTH-DOC-OTHER"),
        ("decision__scope", "SYNTH-OTHER-SCOPE"),
    ],
)
def test_record_bound_to_other_document_or_scope_is_refused_at_the_expectation(w, field, value):
    raw = w.envelope(w.payload(**{field: value}))
    assert _code(w, raw) in (ErrorCode.DOCUMENT_MISMATCH, ErrorCode.SCOPE_MISMATCH)


@pytest.mark.parametrize(
    "over",
    [
        {"document__sha256": "00" * 32},
        {"document__spec_sha256": "00" * 32},
        {"decision__outcome": "REJECT"},
        {"decision__purpose": "SYNTH-OTHER-PURPOSE"},
        {"record_id": "SYNTH-REC-9"},
        {"nonce": "99" * 16},
        {"signed_at": "2026-10-20T11:58:00Z"},
    ],
)
def test_altering_a_signed_field_after_signing_breaks_the_signature(w, over):
    original = w.payload()
    signature = _sign(w.alice, signing_message(original))
    tampered = w.payload(**over)
    raw = encode_envelope(tampered, signature)
    expected = {"document__sha256", "document__spec_sha256"}
    code = _code(w, raw, **({} if not (set(over) & expected) else _expect_for(tampered)))
    assert code == ErrorCode.SIGNATURE


def _expect_for(tampered: dict[str, Any]) -> dict[str, Any]:
    """Make the expectation follow the tampered digests so the signature check is what fails."""
    return {
        "expected_document_sha256": tampered["document"]["sha256"],
        "expected_spec_sha256": tampered["document"]["spec_sha256"],
    }


def test_altered_approval_role_is_refused_by_the_roster_before_the_signature(w):
    assert (
        _code(w, w.envelope(w.payload(signer__role="SYNTH-VALIDATOR"))) == ErrorCode.NOT_AUTHORIZED
    )


def test_altered_signer_identity_is_refused(w):
    raw = w.envelope(w.payload(signer__identity="SYNTH-BOB"))
    assert _code(w, raw) == ErrorCode.SIGNER_MISMATCH


# ---- keys -----------------------------------------------------------------------------------


def test_wrong_signing_key_with_a_trusted_key_id_is_refused(w):
    raw = w.envelope(w.payload(), signer=w.mallory)
    assert _code(w, raw) == ErrorCode.SIGNATURE


def test_unknown_key_is_refused(w):
    payload = w.payload(signer__key_id=w.mallory_id)
    assert _code(w, w.envelope(payload, w.mallory)) == ErrorCode.KEY_UNKNOWN


def test_revoked_key_is_refused(w):
    revoked = KeyEntry(**{**w.alice_entry.__dict__, "revoked_at": "2026-10-19T00:00:00Z"})
    roster = w.roster(keys=(revoked, w.bob_entry))
    assert _code(w, w.envelope(w.payload()), roster) == ErrorCode.KEY_REVOKED


@pytest.mark.parametrize(
    ("not_before", "not_after"),
    [
        ("2026-11-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-10-20T11:59:30Z"),
    ],
)
def test_key_outside_validity_window_is_refused(w, not_before, not_after):
    entry = KeyEntry(**{**w.alice_entry.__dict__, "not_before": not_before, "not_after": not_after})
    roster = w.roster(keys=(entry, w.bob_entry))
    assert _code(w, w.envelope(w.payload()), roster) == ErrorCode.KEY_INACTIVE


def test_roster_rejects_a_key_id_that_is_not_the_key_digest(w):
    bad = KeyEntry(**{**w.alice_entry.__dict__, "key_id": "00" * 32})
    with pytest.raises(ApprovalError) as info:
        w.roster(keys=(bad,))
    assert info.value.code == ErrorCode.ROSTER_UNTRUSTED


def test_roster_rejects_a_non_p256_key(w):
    other = (
        ec.generate_private_key(ec.SECP384R1())
        .public_key()
        .public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    )
    entry = KeyEntry(
        hashlib.sha256(other).hexdigest(), "SYNTH-X", other, SIGNED, "2027-01-01T00:00:00Z"
    )
    with pytest.raises(ApprovalError) as info:
        w.roster(keys=(entry,))
    assert info.value.code == ErrorCode.ROSTER_UNTRUSTED


# ---- authorization is checked against the roster, never the record --------------------------


def test_valid_signature_without_a_roster_role_assignment_is_not_authorized(w):
    roster = w.roster(assignments=(w.bob_role,))
    assert _code(w, w.envelope(w.payload()), roster) == ErrorCode.NOT_AUTHORIZED


def test_self_claimed_role_in_the_signed_record_is_not_trusted(w):
    # Bob holds a real key but is only a validator; he signs a record claiming the owner role.
    payload = w.payload(signer={"identity": "SYNTH-BOB", "key_id": w.bob_id, "role": "SYNTH-OWNER"})
    assert _code(w, w.envelope(payload, w.bob)) == ErrorCode.NOT_AUTHORIZED


def test_scope_outside_the_assignment_is_not_authorized(w):
    narrow = RoleAssignment(
        "SYNTH-ALICE",
        "SYNTH-OWNER",
        ("SYNTH-ELSEWHERE",),
        "2026-01-01T00:00:00Z",
        "2027-01-01T00:00:00Z",
    )
    roster = w.roster(assignments=(narrow, w.bob_role))
    assert _code(w, w.envelope(w.payload()), roster) == ErrorCode.NOT_AUTHORIZED


@pytest.mark.parametrize(
    ("not_before", "not_after"),
    [
        ("2026-11-01T00:00:00Z", "2027-01-01T00:00:00Z"),
        ("2026-01-01T00:00:00Z", "2026-10-20T11:59:30Z"),
    ],
)
def test_expired_or_not_yet_active_assignment_is_not_authorized(w, not_before, not_after):
    stale = RoleAssignment("SYNTH-ALICE", "SYNTH-OWNER", (SCOPE,), not_before, not_after)
    roster = w.roster(assignments=(stale, w.bob_role))
    assert _code(w, w.envelope(w.payload()), roster) == ErrorCode.NOT_AUTHORIZED


def test_roster_that_does_not_match_the_pinned_digest_is_untrusted(w):
    attacker = w.roster(
        assignments=(
            w.alice_role,
            w.bob_role,
            RoleAssignment("SYNTH-ALICE", "X", (SCOPE,), SIGNED, "2027-01-01T00:00:00Z"),
        )
    )
    raw = w.envelope(w.payload())
    assert (
        _code(w, raw, attacker, pinned_roster_sha256=w.roster().digest())
        == ErrorCode.ROSTER_UNTRUSTED
    )


def test_record_from_another_roster_version_is_refused(w):
    assert _code(w, w.envelope(w.payload(roster_version=2))) == ErrorCode.ROSTER_VERSION


def test_roster_digest_is_order_independent_and_content_sensitive(w):
    a = w.roster(keys=(w.alice_entry, w.bob_entry))
    b = w.roster(keys=(w.bob_entry, w.alice_entry))
    assert a.digest() == b.digest()
    assert a.digest() != w.roster(version=2).digest()


# ---- algorithm / version / encoding ---------------------------------------------------------


def test_unsupported_algorithm_protocol_and_version_are_refused(w):
    assert _code(w, w.envelope(w.payload(sig_alg="ECDSA-P256-SHA1"))) == ErrorCode.ALGORITHM
    assert _code(w, w.envelope(w.payload(protocol="range002-approval/2"))) == ErrorCode.PROTOCOL
    assert _code(w, w.envelope(w.payload(roster_version=True))) == ErrorCode.ENCODING


def _raw(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":")).encode()


def test_non_canonical_encodings_are_refused(w):
    good = w.envelope(w.payload())
    doc = json.loads(good)
    assert _code(w, json.dumps(doc, sort_keys=True).encode()) == ErrorCode.ENCODING  # spaces
    assert _code(w, json.dumps(doc).encode()) == ErrorCode.ENCODING  # unsorted + spaces
    assert _code(w, good + b"\n") == ErrorCode.ENCODING
    assert _code(w, good.replace(b"SYNTH", b"\\u0053YNTH", 1)) == ErrorCode.ENCODING
    assert _code(w, b"\xef\xbb\xbf" + good) == ErrorCode.ENCODING
    assert _code(w, "not bytes") == ErrorCode.ENCODING
    assert _code(w, b"{") == ErrorCode.ENCODING
    assert _code(w, b"\xff\xfe") == ErrorCode.ENCODING


def test_duplicate_fields_are_refused(w):
    good = w.envelope(w.payload()).decode()
    dup = good.replace('"nonce":', '"nonce":"' + "33" * 16 + '","nonce":', 1)
    assert _code(w, dup.encode()) == ErrorCode.ENCODING
    assert _code(w, b'{"payload":{},"payload":{},"signature":"aa"}') == ErrorCode.ENCODING


def test_floats_booleans_and_non_finite_numbers_are_refused(w):
    doc = json.loads(w.envelope(w.payload()))
    doc["payload"]["roster_version"] = 1.0
    assert _code(w, _raw(doc)) == ErrorCode.ENCODING
    doc["payload"]["roster_version"] = True
    assert _code(w, _raw(doc)) == ErrorCode.ENCODING
    assert _code(w, b'{"payload":{"x":NaN},"signature":"aa"}') == ErrorCode.ENCODING


def test_envelope_and_payload_shape_is_exact(w):
    doc = json.loads(w.envelope(w.payload()))
    extra = {**doc, "extra": 1}
    assert _code(w, _raw(extra)) == ErrorCode.SCHEMA
    payload_extra = copy.deepcopy(doc)
    payload_extra["payload"]["surprise"] = 1
    assert _code(w, _raw(payload_extra)) == ErrorCode.SCHEMA
    assert _code(w, _raw([1])) == ErrorCode.SCHEMA


@pytest.mark.parametrize(
    "path",
    [
        "record_id",
        "document",
        "document__sha256",
        "decision__scope",
        "signer__key_id",
        "nonce",
        "signed_at",
        "time_evidence",
        "supersedes",
    ],
)
def test_every_required_evidence_field_is_required(w, path):
    raw = w.envelope(w.payload(**{path: _DELETE}))
    assert _code(w, raw) in (ErrorCode.SCHEMA, ErrorCode.TIME_EVIDENCE)


@pytest.mark.parametrize(
    "over",
    [
        {"document__sha256": "AB" * 32},
        {"document__sha256": "ab" * 31},
        {"nonce": "11" * 8},
        {"record_id": "has space"},
        {"signed_at": "2026-10-20 11:59:00"},
        {"signed_at": "2026-10-20T11:59:00+00:00"},
        {"decision__outcome": "approve"},
        {"supersedes": ["B", "A"]},
        {"supersedes": ["A", "A"]},
        {"decision__outcome": "REVOKE"},
    ],
)
def test_malformed_values_are_refused(w, over):
    assert _code(w, w.envelope(w.payload(**over))) == ErrorCode.SCHEMA


# ---- signatures -----------------------------------------------------------------------------


def test_high_s_signature_is_refused_even_though_it_verifies_mathematically(w):
    payload = w.payload()
    raw = w.envelope(payload, low_s=False)
    assert _code(w, raw) == ErrorCode.SIGNATURE


def test_malformed_signatures_are_refused(w):
    payload = w.payload()
    for bad in (
        "",
        "zz",
        "00" * 8,
        "30" + "00" * 40,
        _sign(w.alice, signing_message(payload))[:-2],
    ):
        assert _code(w, encode_envelope(payload, bad)) in (ErrorCode.SCHEMA, ErrorCode.SIGNATURE)


def test_signature_without_domain_separation_is_refused(w):
    payload = w.payload()
    plain = _sign(w.alice, ap.canonical_json(payload))
    assert _code(w, encode_envelope(payload, plain)) == ErrorCode.SIGNATURE


def test_signature_over_a_different_roster_signing_domain_is_refused(w):
    payload = w.payload()
    other = _sign(w.alice, b"RANGE-002/other/v1\x00" + ap.canonical_json(payload))
    assert _code(w, encode_envelope(payload, other)) == ErrorCode.SIGNATURE


# ---- trusted time ---------------------------------------------------------------------------


def test_missing_untrusted_or_inconsistent_time_evidence_is_refused(w):
    untrusted = w.payload(time_evidence__authority="SYNTH-OTHER-TSA")
    assert _code(w, w.envelope(untrusted)) == ErrorCode.TIME_EVIDENCE
    skewed = w.payload(time_evidence__attested_at="2026-10-20T11:00:00Z")
    assert _code(w, w.envelope(skewed)) == ErrorCode.TIME_EVIDENCE
    no_limit = w.payload(time_evidence={"kind": ap.TIME_NONE, "limitation": "none"})
    assert _code(w, w.envelope(no_limit), policy=Policy(False)) == ErrorCode.TIME_EVIDENCE
    unknown = w.payload(time_evidence={"kind": "WALL_CLOCK"})
    assert _code(w, w.envelope(unknown)) == ErrorCode.TIME_EVIDENCE


def test_future_signing_time_and_naive_now_are_refused(w):
    future = w.payload(
        signed_at="2026-10-20T13:00:00Z", time_evidence__attested_at="2026-10-20T13:00:00Z"
    )
    assert _code(w, w.envelope(future)) == ErrorCode.TIME_RANGE
    assert (
        _code(w, w.envelope(w.payload()), now=datetime(2026, 10, 20, 12, 0, 0))
        == ErrorCode.TIME_RANGE
    )


# ---- replay, supersession, conflict ---------------------------------------------------------


def _accept(w: World, ledger: ApprovalLedger, **over: Any) -> None:
    signer = over.pop("_signer", w.alice)
    ledger.accept(_verify(w, w.envelope(w.payload(**over), signer)))


def test_replay_of_the_same_record_or_nonce_is_refused(w):
    ledger = ApprovalLedger()
    _accept(w, ledger)
    with pytest.raises(ApprovalError) as same:
        _accept(w, ledger)
    assert same.value.code == ErrorCode.REPLAY
    with pytest.raises(ApprovalError) as nonce:
        _accept(w, ledger, record_id="SYNTH-REC-2")
    assert nonce.value.code == ErrorCode.REPLAY


def test_supersession_must_name_an_existing_active_record_by_the_same_signer(w):
    ledger = ApprovalLedger()
    with pytest.raises(ApprovalError) as unknown:
        _accept(w, ledger, supersedes=["SYNTH-NOPE"])
    assert unknown.value.code == ErrorCode.SUPERSESSION
    _accept(w, ledger)
    bob = {"signer": {"identity": "SYNTH-BOB", "key_id": w.bob_id, "role": "SYNTH-VALIDATOR"}}
    with pytest.raises(ApprovalError) as other_signer:
        _accept(
            w,
            ledger,
            record_id="R2",
            nonce="22" * 16,
            supersedes=["SYNTH-REC-1"],
            _signer=w.bob,
            **bob,
        )
    assert other_signer.value.code == ErrorCode.SUPERSESSION
    _accept(w, ledger, record_id="R3", nonce="33" * 16, supersedes=["SYNTH-REC-1"])
    with pytest.raises(ApprovalError) as twice:
        _accept(w, ledger, record_id="R4", nonce="44" * 16, supersedes=["SYNTH-REC-1"])
    assert twice.value.code == ErrorCode.SUPERSESSION


def test_conflicting_decisions_need_an_explicit_supersession(w):
    ledger = ApprovalLedger()
    _accept(w, ledger)
    bob = {"signer": {"identity": "SYNTH-BOB", "key_id": w.bob_id, "role": "SYNTH-VALIDATOR"}}
    with pytest.raises(ApprovalError) as info:
        _accept(
            w,
            ledger,
            record_id="R2",
            nonce="22" * 16,
            decision__outcome="REJECT",
            _signer=w.bob,
            **bob,
        )
    assert info.value.code == ErrorCode.CONFLICT
    _accept(
        w,
        ledger,
        record_id="R3",
        nonce="33" * 16,
        decision__outcome="REJECT",
        supersedes=["SYNTH-REC-1"],
    )
    assert [r.outcome for r in ledger.active(DOC["id"], SCOPE)] == ["REJECT"]


def test_a_revoke_withdraws_the_record_it_supersedes(w):
    ledger = ApprovalLedger()
    _accept(w, ledger)
    _accept(
        w,
        ledger,
        record_id="R2",
        nonce="22" * 16,
        decision__outcome="REVOKE",
        supersedes=["SYNTH-REC-1"],
    )
    assert ledger.active(DOC["id"], SCOPE) == []


def test_agreeing_approvals_by_two_signers_coexist(w):
    ledger = ApprovalLedger()
    _accept(w, ledger)
    bob = {"signer": {"identity": "SYNTH-BOB", "key_id": w.bob_id, "role": "SYNTH-VALIDATOR"}}
    _accept(w, ledger, record_id="R2", nonce="22" * 16, _signer=w.bob, **bob)
    assert len(ledger.active(DOC["id"], SCOPE)) == 2


# ---- boundaries -----------------------------------------------------------------------------


def test_verifier_does_not_depend_on_is_signed_or_the_spec_loader():
    tree = ast.parse(Path(ap.__file__).read_text(encoding="utf-8"))
    imported = {n.module or "" for n in ast.walk(tree) if isinstance(n, ast.ImportFrom)} | {
        a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names
    }
    assert not any("spec_view" in m or "spec.loader" in m or "spec.schema" in m for m in imported)
    assert not any(
        isinstance(n, ast.Attribute | ast.Name)
        and getattr(n, "attr", getattr(n, "id", "")) == "is_signed"
        for n in ast.walk(tree)
    )
    assert not any(
        m.startswith(
            ("boto3", "botocore", "app.validation", "app.orders", "app.risk", "app.brokers")
        )
        for m in imported
    )


def test_module_holds_no_private_key_material_and_does_not_sign():
    source = Path(ap.__file__).read_text(encoding="utf-8")
    for needle in ("generate_private_key", "load_pem_private_key", ".sign(", "PrivateFormat"):
        assert needle not in source
