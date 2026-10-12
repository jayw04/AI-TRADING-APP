"""Synthetic tests for slice 3d: roster history and as-of approval verification.

Disposable in-memory P-256 keys only. The synthetic time authority proves nothing about
real-world time; these tests show that signer-asserted time is refused and that a pinned
countersignature, roster history and key state are checked instead.
"""

from __future__ import annotations

import ast
import hashlib
from dataclasses import replace
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
    ErrorCode,
    HistoricalApproval,
    KeyEntry,
    RoleAssignment,
    Roster,
    RosterHistory,
    TimeAuthority,
    TimeAuthorityRoster,
    TimeStamp,
    encode_envelope,
    make_roster_link,
    signing_message,
    timestamp_message,
    verify_approval_as_of,
)

NOW = datetime(2026, 10, 20, 12, 0, 0, tzinfo=UTC)
V1_START = "2026-01-01T00:00:00Z"
V2_START = "2026-06-01T00:00:00Z"
SIGNED = "2026-03-10T12:00:00Z"
Y_START, Y_END = "2026-01-01T00:00:00Z", "2026-12-31T00:00:00Z"
DOC = {"id": "SYNTH-DOC-1", "sha256": "ab" * 32, "spec_sha256": "cd" * 32}
SCOPE = "SYNTH-SCOPE"
PURPOSE = "SYNTH-PURPOSE"
ALL = ("APPROVE", "REJECT", "REVOKE")
ORDER = ap._P256_ORDER
PEOPLE = {
    "ALICE-LAPTOP": "P-ALICE",
    "ALICE-TOKEN": "P-ALICE",
    "BOB": "P-BOB",
    "CAROL": "P-CAROL",
    "DAVE": "P-DAVE",
}
ROLES = {
    "ALICE-LAPTOP": ("SYNTH-OWNER", "SYNTH-RESEARCH"),
    "ALICE-TOKEN": ("SYNTH-OWNER",),
    "BOB": ("SYNTH-RESEARCH",),
    "CAROL": ("SYNTH-TRADING",),
    "DAVE": ("SYNTH-VALIDATOR",),
}


def _spki(private: ec.EllipticCurvePrivateKey) -> bytes:
    return private.public_key().public_bytes(
        serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo
    )


def sign_low_s(private: ec.EllipticCurvePrivateKey, message: bytes, *, low_s: bool = True) -> str:
    r, s = decode_dss_signature(private.sign(message, ec.ECDSA(hashes.SHA256())))
    if (s > ORDER // 2) == low_s:
        s = ORDER - s
    return encode_dss_signature(r, s).hex()


class Cast:
    """Disposable people, keys, a time authority and helpers to build history and evidence."""

    def __init__(self) -> None:
        self.keys = {name: ec.generate_private_key(ec.SECP256R1()) for name in PEOPLE}
        self.tsa = ec.generate_private_key(ec.SECP256R1())
        self.outsider = ec.generate_private_key(ec.SECP256R1())
        self.key_id = {n: hashlib.sha256(_spki(k)).hexdigest() for n, k in self.keys.items()}
        self.authorities = TimeAuthorityRoster(
            (TimeAuthority("SYNTH-TSA", _spki(self.tsa), Y_START, Y_END),)
        )

    def roster(
        self,
        version: int,
        *,
        revoked: dict[str, str] | None = None,
        compromised: dict[str, str] | None = None,
        persons: dict[str, str] | None = None,
        key_window: tuple[str, str] = (Y_START, Y_END),
    ) -> Roster:
        revoked, compromised = revoked or {}, compromised or {}
        keys = tuple(
            KeyEntry(
                self.key_id[n],
                n,
                _spki(self.keys[n]),
                key_window[0],
                key_window[1],
                revoked.get(n),
                compromised.get(n),
            )
            for n in PEOPLE
        )
        assignments = tuple(
            RoleAssignment(n, role, (SCOPE,), ALL, Y_START, Y_END)
            for n, roles in ROLES.items()
            for role in roles
        )
        mapping = PEOPLE if persons is None else persons
        return Roster(version, "SYNTH-ROSTER", keys, assignments, tuple(sorted(mapping.items())))

    def history(self, rosters: list[Roster], starts: list[str]) -> RosterHistory:
        links, prev = [], ap.GENESIS_HASH
        for roster, start in zip(rosters, starts, strict=True):
            link = make_roster_link(roster, prev, start)
            links.append(link)
            prev = link.record_sha256
        return RosterHistory(tuple(links), tuple(rosters))

    def payload(
        self, who: str = "ALICE-TOKEN", role: str = "SYNTH-OWNER", **over: Any
    ) -> dict[str, Any]:
        base: dict[str, Any] = {
            "protocol": ap.PROTOCOL,
            "record_id": f"REC-{who}-{role}",
            "roster_version": 1,
            "document": dict(DOC),
            "decision": {"outcome": "APPROVE", "scope": SCOPE, "purpose": PURPOSE},
            "signer": {"identity": who, "key_id": self.key_id[who], "role": role},
            "sig_alg": ap.SIG_ALG,
            "nonce": hashlib.sha256(f"{who}{role}".encode()).hexdigest()[:32],
            "signed_at": SIGNED,
            "time_evidence": {"kind": ap.TIME_NONE, "limitation": ap.TIME_LIMITATION},
            "supersedes": [],
        }
        for dotted, value in over.items():
            node = base
            *parents, leaf = dotted.split("__")
            for p in parents:
                node = node[p]
            node[leaf] = value
        return base

    def envelope(self, payload: dict[str, Any], who: str | None = None) -> bytes:
        signer = self.keys[who or payload["signer"]["identity"]]
        return encode_envelope(payload, sign_low_s(signer, signing_message(payload)))

    def stamp(self, payload: dict[str, Any], at: str = SIGNED, **kw: Any) -> TimeStamp:
        key = kw.pop("key", self.tsa)
        authority = kw.pop("authority", "SYNTH-TSA")
        message = timestamp_message(authority, at, payload)
        return TimeStamp(authority, at, sign_low_s(key, message))


@pytest.fixture(scope="module")
def cast() -> Cast:
    return Cast()


@pytest.fixture(scope="module")
def hist(cast: Cast) -> RosterHistory:
    return cast.history([cast.roster(1), cast.roster(2)], [V1_START, V2_START])


def as_of_args(
    cast: Cast, hist: RosterHistory, payload: dict[str, Any], **over: Any
) -> dict[str, Any]:
    version = payload["roster_version"]
    args: dict[str, Any] = {
        "history": hist,
        "pinned_head_sha256": hist.head_sha256,
        "expected_roster_sha256": hist.roster_for(version).digest() if version <= 2 else "00" * 32,
        "time_authorities": cast.authorities,
        "pinned_time_authorities_sha256": cast.authorities.digest(),
        "stamp": cast.stamp(payload),
        "expected_document_id": DOC["id"],
        "expected_document_sha256": DOC["sha256"],
        "expected_spec_sha256": DOC["spec_sha256"],
        "expected_scope": SCOPE,
        "expected_outcome": payload["decision"]["outcome"],
        "expected_purpose": PURPOSE,
        "now": NOW,
    }
    args.update(over)
    return args


def verify(
    cast: Cast, hist: RosterHistory, payload: dict[str, Any], raw: bytes | None = None, **over: Any
) -> HistoricalApproval:
    return verify_approval_as_of(
        raw or cast.envelope(payload), **as_of_args(cast, hist, payload, **over)
    )


def code(
    cast: Cast, hist: RosterHistory, payload: dict[str, Any], raw: Any = None, **over: Any
) -> ErrorCode:
    with pytest.raises(ApprovalError) as info:
        verify(cast, hist, payload, raw, **over)
    return info.value.code


def history_code(links: Any, rosters: Any) -> ErrorCode:
    with pytest.raises(ApprovalError) as info:
        RosterHistory(tuple(links), tuple(rosters))
    return info.value.code


# ---- roster history: chain integrity --------------------------------------------------------


def test_valid_history_chains_and_pins_a_head(cast, hist):
    assert hist.roster_for(1).version == 1 and hist.latest.version == 2
    hist.verify_head(hist.head_sha256)
    start, end = hist.interval(1)
    assert (start.isoformat(), end.isoformat()) == (
        "2026-01-01T00:00:00+00:00",
        "2026-06-01T00:00:00+00:00",
    )
    assert hist.interval(2)[1] is None


def test_truncated_or_substituted_history_fails_the_pinned_head(cast, hist):
    shorter = cast.history([cast.roster(1)], [V1_START])
    with pytest.raises(ApprovalError) as info:
        shorter.verify_head(hist.head_sha256)
    assert info.value.code == ErrorCode.ROSTER_UNTRUSTED
    other = cast.history(
        [cast.roster(1), cast.roster(2, revoked={"BOB": "2026-07-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    with pytest.raises(ApprovalError):
        other.verify_head(hist.head_sha256)


def test_broken_links_are_detected(cast):
    r1, r2 = cast.roster(1), cast.roster(2)
    l1 = make_roster_link(r1, ap.GENESIS_HASH, V1_START)
    l2 = make_roster_link(r2, l1.record_sha256, V2_START)
    RosterHistory((l1, l2), (r1, r2))  # control: the intact chain builds
    # missing link / skipped version
    l3 = make_roster_link(cast.roster(3), l1.record_sha256, V2_START)
    assert history_code([l1, l3], [r1, cast.roster(3)]) == ErrorCode.HISTORY
    # wrong ordering
    assert history_code([l2, l1], [r2, r1]) == ErrorCode.HISTORY
    # wrong previous hash
    bad_prev = make_roster_link(r2, "11" * 32, V2_START)
    assert history_code([l1, bad_prev], [r1, r2]) == ErrorCode.HISTORY
    # tampered record hash
    assert history_code([l1, replace(l2, record_sha256="22" * 32)], [r1, r2]) == ErrorCode.HISTORY
    # roster substituted under a valid-looking link
    assert (
        history_code([l1, l2], [r1, cast.roster(2, revoked={"BOB": "2026-07-01T00:00:00Z"})])
        == ErrorCode.HISTORY
    )
    # empty / mismatched lengths / non-increasing time
    assert history_code([], []) == ErrorCode.HISTORY
    assert history_code([l1, l2], [r1]) == ErrorCode.HISTORY
    same_time = make_roster_link(r2, l1.record_sha256, V1_START)
    assert history_code([l1, same_time], [r1, r2]) == ErrorCode.HISTORY


def test_unauthorized_roster_rewrites_are_detected(cast):
    r1 = cast.roster(
        1, revoked={"BOB": "2026-02-01T00:00:00Z"}, compromised={"DAVE": "2026-02-02T00:00:00Z"}
    )
    l1 = make_roster_link(r1, ap.GENESIS_HASH, V1_START)

    def second(roster: Roster) -> ErrorCode:
        link = make_roster_link(roster, l1.record_sha256, V2_START)
        return history_code([l1, link], [r1, roster])

    base = {
        "revoked": {"BOB": "2026-02-01T00:00:00Z"},
        "compromised": {"DAVE": "2026-02-02T00:00:00Z"},
    }
    assert second(cast.roster(2, **{**base, "revoked": {}})) == ErrorCode.HISTORY  # un-revoke
    assert (
        second(cast.roster(2, **{**base, "revoked": {"BOB": "2026-09-01T00:00:00Z"}}))
        == ErrorCode.HISTORY
    )
    assert (
        second(cast.roster(2, **{**base, "compromised": {}})) == ErrorCode.HISTORY
    )  # clear compromise
    remap = dict(PEOPLE, BOB="P-DAVE")
    assert second(cast.roster(2, **base, persons=remap)) == ErrorCode.HISTORY  # identity remapped
    dropped = cast.roster(2, **base)
    dropped = Roster(2, dropped.roster_id, dropped.keys[:-1], dropped.assignments, dropped.persons)
    assert second(dropped) == ErrorCode.HISTORY  # key removed
    rewritten_key = replace(r1.keys[0], identity="ALICE-TOKEN")
    rewritten = Roster(2, r1.roster_id, (rewritten_key, *r1.keys[1:]), r1.assignments, r1.persons)
    assert second(rewritten) == ErrorCode.HISTORY  # key rebound to another identity


def test_roster_persons_validation_and_digest_compatibility(cast):
    plain = Roster(1, "SYNTH-ROSTER", (), ())
    assert "persons" not in plain._payload()
    assert Roster(1, "SYNTH-ROSTER", (), (), (("A", "P"),)).digest() != plain.digest()
    for bad in ((("A", "P"), ("A", "Q")), (("A",),), (("bad id", "P"),), (("A", ""),)):
        with pytest.raises(ApprovalError):
            Roster(1, "SYNTH-ROSTER", (), (), bad)  # type: ignore[arg-type]
    flagged = cast.roster(1, compromised={"BOB": "2026-02-02T00:00:00Z"})
    assert flagged.digest() != cast.roster(1).digest()


def test_history_accessors_reject_bad_versions(hist):
    for bad in (0, 3, True, "1", None):
        with pytest.raises(ApprovalError) as info:
            hist.roster_for(bad)  # type: ignore[arg-type]
        assert info.value.code == ErrorCode.ROSTER_VERSION


# ---- as-of verification: positive and historical-state behavior -----------------------------


def test_valid_as_of_verification(cast, hist):
    result = verify(cast, hist, cast.payload())
    assert result.record.identity == "ALICE-TOKEN"
    assert result.person_id == "P-ALICE"
    assert result.as_of == datetime(2026, 3, 10, 12, 0, 0, tzinfo=UTC)
    assert result.roster_version == 1 and result.later_compromise is False
    assert result.acceptable is True and result.key_revoked_later_at is None


def test_signature_stays_verifiable_after_the_key_window_closes(cast):
    short = cast.roster(1, key_window=(Y_START, "2026-04-01T00:00:00Z"))
    hist = cast.history([short], [V1_START])
    assert verify(cast, hist, cast.payload()).acceptable is True  # `now` is months later


def test_later_ordinary_revocation_does_not_erase_an_earlier_approval(cast):
    later = cast.history(
        [cast.roster(1), cast.roster(2, revoked={"ALICE-TOKEN": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    result = verify(cast, later, cast.payload())
    assert result.acceptable is True
    assert result.key_revoked_later_at == "2026-08-01T00:00:00Z"


def test_later_compromise_is_reported_and_not_acceptable(cast):
    later = cast.history(
        [cast.roster(1), cast.roster(2, compromised={"ALICE-TOKEN": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    result = verify(cast, later, cast.payload())
    assert result.later_compromise is True and result.acceptable is False


@pytest.mark.parametrize("flag", ["revoked", "compromised"])
def test_key_revoked_or_compromised_by_the_attested_time_is_refused(cast, flag):
    state = {flag: {"ALICE-TOKEN": "2026-03-10T12:00:00Z"}}  # exactly at the instant
    broken = cast.history([cast.roster(1, **state)], [V1_START])
    expected = ErrorCode.KEY_REVOKED if flag == "revoked" else ErrorCode.KEY_COMPROMISED
    assert code(cast, broken, cast.payload()) == expected
    later_roster = cast.history([cast.roster(1), cast.roster(2, **state)], [V1_START, V2_START])
    assert code(cast, later_roster, cast.payload()) == expected


def test_key_not_yet_valid_at_the_attested_time_is_refused(cast):
    late = cast.history([cast.roster(1, key_window=("2026-04-01T00:00:00Z", Y_END))], [V1_START])
    assert code(cast, late, cast.payload()) == ErrorCode.KEY_INACTIVE


# ---- authenticated time: forged or missing evidence is refused ------------------------------


def test_missing_or_mistyped_stamp_fails_closed(cast, hist):
    payload = cast.payload()
    for bad in (None, "stamp", {"authority_id": "SYNTH-TSA"}):
        assert code(cast, hist, payload, stamp=bad) == ErrorCode.TIME_EVIDENCE


def test_signer_asserted_trusted_time_is_never_enough(cast, hist):
    claim = {
        "kind": ap.TIME_TRUSTED,
        "authority": "SYNTH-TSA",
        "token_sha256": "ee" * 32,
        "attested_at": SIGNED,
    }
    payload = cast.payload(time_evidence=claim)
    assert code(cast, hist, payload, stamp=None) == ErrorCode.TIME_EVIDENCE
    assert (
        verify(cast, hist, payload).as_of.isoformat().startswith("2026-03-10")
    )  # needs a real stamp


def test_forged_stamps_are_refused(cast, hist):
    payload = cast.payload()
    assert (
        code(cast, hist, payload, stamp=cast.stamp(payload, key=cast.outsider))
        == ErrorCode.SIGNATURE
    )
    other = cast.payload("BOB", "SYNTH-RESEARCH")
    assert code(cast, hist, payload, stamp=cast.stamp(other)) == ErrorCode.SIGNATURE
    good = cast.stamp(payload)
    assert (
        code(cast, hist, payload, stamp=replace(good, attested_at="2026-03-10T12:01:00Z"))
        == ErrorCode.SIGNATURE
    )
    assert (
        code(cast, hist, payload, stamp=cast.stamp(payload, authority="SYNTH-OTHER"))
        == ErrorCode.TIME_EVIDENCE
    )
    high_s = TimeStamp(
        "SYNTH-TSA",
        SIGNED,
        sign_low_s(cast.tsa, timestamp_message("SYNTH-TSA", SIGNED, payload), low_s=False),
    )
    assert code(cast, hist, payload, stamp=high_s) == ErrorCode.SIGNATURE


def test_time_authority_pin_window_and_consistency(cast, hist):
    payload = cast.payload()
    assert (
        code(cast, hist, payload, pinned_time_authorities_sha256="00" * 32)
        == ErrorCode.ROSTER_UNTRUSTED
    )
    expired = TimeAuthorityRoster(
        (TimeAuthority("SYNTH-TSA", _spki(cast.tsa), "2026-04-01T00:00:00Z", Y_END),)
    )
    assert (
        code(
            cast,
            hist,
            payload,
            time_authorities=expired,
            pinned_time_authorities_sha256=expired.digest(),
        )
        == ErrorCode.TIME_EVIDENCE
    )
    far = "2026-03-10T13:00:00Z"
    assert code(cast, hist, payload, stamp=cast.stamp(payload, at=far)) == ErrorCode.TIME_EVIDENCE
    future = cast.payload(signed_at="2026-10-21T00:00:00Z")
    assert (
        code(cast, hist, future, stamp=cast.stamp(future, at="2026-10-21T00:00:00Z"))
        == ErrorCode.TIME_EVIDENCE
    )


# ---- roster replacement and reference mismatches --------------------------------------------


def test_roster_replacement_against_the_pinned_head_is_refused(cast, hist):
    forged_roster = cast.roster(1, persons=dict(PEOPLE, BOB="P-ALICE"))
    forged = cast.history(
        [forged_roster, cast.roster(2, persons=dict(PEOPLE, BOB="P-ALICE"))], [V1_START, V2_START]
    )
    payload = cast.payload()
    args = as_of_args(cast, forged, payload, pinned_head_sha256=hist.head_sha256)
    with pytest.raises(ApprovalError) as info:
        verify_approval_as_of(cast.envelope(payload), **args)
    assert info.value.code == ErrorCode.ROSTER_UNTRUSTED


def test_history_inconsistent_with_the_approvals_pinned_roster_reference(cast, hist):
    payload = cast.payload()
    assert (
        code(cast, hist, payload, expected_roster_sha256=hist.roster_for(2).digest())
        == ErrorCode.ROSTER_UNTRUSTED
    )


def test_roster_version_must_exist_and_be_in_force(cast, hist):
    ghost = cast.payload(roster_version=3)
    assert code(cast, hist, ghost) == ErrorCode.ROSTER_VERSION
    stale = cast.payload()  # names v1 but is stamped after v2 took effect
    late = "2026-07-01T00:00:00Z"
    stale = cast.payload(signed_at=late)
    assert code(cast, hist, stale, stamp=cast.stamp(stale, at=late)) == ErrorCode.ROSTER_VERSION
    early = cast.payload(roster_version=2, signed_at="2026-03-01T00:00:00Z")
    assert (
        code(cast, hist, early, stamp=cast.stamp(early, at="2026-03-01T00:00:00Z"))
        == ErrorCode.ROSTER_VERSION
    )


# ---- authorization at the attested time -----------------------------------------------------


def test_authorization_is_checked_against_the_historical_roster(cast, hist):
    assert (
        code(cast, hist, cast.payload("BOB", "SYNTH-OWNER")) == ErrorCode.NOT_AUTHORIZED
    )  # self-claimed role
    off_scope = cast.payload(decision__scope="SYNTH-OTHER-SCOPE")
    assert (
        code(cast, hist, off_scope, expected_scope="SYNTH-OTHER-SCOPE") == ErrorCode.NOT_AUTHORIZED
    )
    mismatch = cast.payload(signer__identity="BOB")
    assert code(cast, hist, mismatch) == ErrorCode.SIGNER_MISMATCH
    unknown = cast.payload(signer__key_id="00" * 32)
    assert code(cast, hist, unknown) == ErrorCode.KEY_UNKNOWN


def test_expired_assignment_at_the_attested_time_is_not_authorized(cast):
    roster = cast.roster(1)
    short = tuple(
        replace(a, not_after="2026-03-01T00:00:00Z") if a.identity == "ALICE-TOKEN" else a
        for a in roster.assignments
    )
    narrowed = Roster(1, roster.roster_id, roster.keys, short, roster.persons)
    assert (
        code(cast, cast.history([narrowed], [V1_START]), cast.payload()) == ErrorCode.NOT_AUTHORIZED
    )


def test_outcome_permission_is_checked(cast):
    roster = cast.roster(1)
    only_reject = tuple(
        replace(a, outcomes=("REJECT",)) if a.identity == "ALICE-TOKEN" else a
        for a in roster.assignments
    )
    narrowed = Roster(1, roster.roster_id, roster.keys, only_reject, roster.persons)
    assert (
        code(cast, cast.history([narrowed], [V1_START]), cast.payload()) == ErrorCode.NOT_AUTHORIZED
    )


# ---- content binding, encoding and typed errors ---------------------------------------------


def test_altered_content_after_signing_is_refused(cast, hist):
    payload = cast.payload()
    stamp = cast.stamp(payload)
    tampered = cast.payload(decision__outcome="REJECT")
    raw = encode_envelope(tampered, sign_low_s(cast.keys["ALICE-TOKEN"], signing_message(payload)))
    assert code(cast, hist, tampered, raw, stamp=stamp) == ErrorCode.SIGNATURE


def test_document_digest_scope_and_expectation_mismatches(cast, hist):
    payload = cast.payload()
    assert (
        code(cast, hist, payload, expected_document_sha256="00" * 32) == ErrorCode.DOCUMENT_MISMATCH
    )
    assert code(cast, hist, payload, expected_spec_sha256="00" * 32) == ErrorCode.DOCUMENT_MISMATCH
    assert code(cast, hist, payload, expected_scope="SYNTH-OTHER") == ErrorCode.SCOPE_MISMATCH
    assert code(cast, hist, payload, expected_outcome="REJECT") == ErrorCode.DOCUMENT_MISMATCH
    assert code(cast, hist, payload, expected_purpose="SYNTH-OTHER") == ErrorCode.DOCUMENT_MISMATCH


def test_high_s_and_malformed_records_are_refused_with_typed_errors(cast, hist):
    payload = cast.payload()
    high = encode_envelope(
        payload, sign_low_s(cast.keys["ALICE-TOKEN"], signing_message(payload), low_s=False)
    )
    assert code(cast, hist, payload, high) == ErrorCode.SIGNATURE
    for bad in (b"{", b"[]", "text", b'{"payload":{},"signature":"aa"}'):
        assert code(cast, hist, payload, bad, stamp=cast.stamp(payload)) in (
            ErrorCode.ENCODING,
            ErrorCode.SCHEMA,
        )


def test_wrong_typed_arguments_surface_as_typed_errors(cast, hist):
    payload = cast.payload()
    assert code(cast, hist, payload, now="later") == ErrorCode.SCHEMA
    assert code(cast, hist, payload, now=datetime(2026, 10, 20)) == ErrorCode.TIME_RANGE
    assert code(cast, hist, payload, history=None) == ErrorCode.SCHEMA
    with pytest.raises(ApprovalError):
        verify(cast, hist, payload, max_skew_seconds=-1)


def test_historical_approval_cannot_be_forged(cast, hist):
    real = verify(cast, hist, cast.payload())
    fields: dict[str, Any] = {
        "record": real.record,
        "roster_version": real.roster_version,
        "roster_sha256": real.roster_sha256,
        "as_of": real.as_of,
        "envelope_sha256": real.envelope_sha256,
        "envelope": real.envelope,
        "stamp": real.stamp,
        "history_head_sha256": real.history_head_sha256,
        "time_authorities_sha256": real.time_authorities_sha256,
        "person_id": real.person_id,
        "later_compromise": real.later_compromise,
        "key_revoked_later_at": real.key_revoked_later_at,
    }
    with pytest.raises(ApprovalError):
        HistoricalApproval(**fields)  # no seal
    with pytest.raises(ApprovalError):
        HistoricalApproval(**fields, _seal="00" * 32)
    with pytest.raises(ApprovalError):
        HistoricalApproval(**fields, _seal=object())  # type: ignore[arg-type]
    with pytest.raises(ApprovalError):
        replace(real, person_id="P-SOMEONE-ELSE")
    HistoricalApproval(**fields, _seal=real._seal)  # control: the genuine seal is accepted


def test_as_of_path_does_not_use_signer_time_or_is_signed():
    source = Path(ap.__file__).read_text(encoding="utf-8")
    body = source[
        source.index("def _verify_approval_as_of") : source.index("class ApprovalRequirement")
    ]
    assert "time_kind" not in body and "time_attested_at" not in body
    names = {getattr(n, "attr", getattr(n, "id", "")) for n in ast.walk(ast.parse(source))}
    assert "is_signed" not in names


def test_one_public_key_cannot_be_enrolled_as_two_identities(cast):
    # Same key, different SPKI spelling (compressed point), hence a different key_id digest.
    alice = cast.keys["ALICE-TOKEN"].public_key()
    compressed = alice.public_bytes(
        serialization.Encoding.X962, serialization.PublicFormat.CompressedPoint
    )
    header = bytes.fromhex("3039301306072a8648ce3d020106082a8648ce3d030107032200")
    alias = header + compressed
    assert alias != _spki(cast.keys["ALICE-TOKEN"])
    base = cast.roster(1)
    aliased = KeyEntry(hashlib.sha256(alias).hexdigest(), "BOB-ALIAS", alias, Y_START, Y_END)
    with pytest.raises(ApprovalError) as info:
        Roster(1, "SYNTH-ROSTER", (*base.keys, aliased), base.assignments, base.persons)
    assert info.value.code == ErrorCode.ROSTER_UNTRUSTED
    assert "more than once" in str(info.value)
