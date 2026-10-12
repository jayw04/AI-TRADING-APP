"""Synthetic tests for slice 3d: distinct-natural-person approval combinations.

Policies below are synthetic fixtures. They are NOT the adopted P0 rule, and nothing here
creates a document-class quorum policy.
"""

from __future__ import annotations

from dataclasses import replace
from typing import Any

import pytest

from app.research.range002.governance import approval as ap
from app.research.range002.governance.approval import (
    ApprovalError,
    ApprovalRequirement,
    ErrorCode,
    HistoricalApproval,
    RosterHistory,
    evaluate_requirement,
)

from .test_approval_history import (
    DOC,
    NOW,
    PEOPLE,
    PURPOSE,
    SCOPE,
    V1_START,
    V2_START,
    Cast,
    as_of_args,
)

FOUR = ("SYNTH-OWNER", "SYNTH-RESEARCH", "SYNTH-TRADING", "SYNTH-VALIDATOR")


@pytest.fixture(scope="module")
def cast() -> Cast:
    return Cast()


_SHARED: dict[str, Any] = {}


@pytest.fixture(scope="module")
def hist(cast: Cast) -> RosterHistory:
    built = cast.history([cast.roster(1), cast.roster(2)], [V1_START, V2_START])
    _SHARED.update(cast=cast, hist=built)
    return built


def ctx(cast: Cast | None = None, hist: RosterHistory | None = None) -> dict[str, Any]:
    """Pins and trusted sets the consumer supplies when it re-verifies evidence."""
    cast, hist = cast or _SHARED["cast"], hist or _SHARED["hist"]
    return {
        "history": hist,
        "pinned_head_sha256": hist.head_sha256,
        "time_authorities": cast.authorities,
        "pinned_time_authorities_sha256": cast.authorities.digest(),
        "now": NOW,
    }


def requirement(
    roles: tuple[str, ...] = FOUR, minimum: int = 4, **over: Any
) -> ApprovalRequirement:
    fields: dict[str, Any] = {
        "document_id": DOC["id"],
        "document_sha256": DOC["sha256"],
        "spec_sha256": DOC["spec_sha256"],
        "scope": SCOPE,
        "purpose": PURPOSE,
        "required_roles": roles,
        "min_distinct_persons": minimum,
    }
    fields.update(over)
    return ApprovalRequirement(**fields)


def approve(
    cast: Cast,
    hist: RosterHistory,
    who: str,
    role: str,
    *,
    outcome: str = "APPROVE",
    record_id: str | None = None,
    nonce: str | None = None,
    supersedes: tuple[str, ...] = (),
    signed_at: str = "2026-03-10T12:00:00Z",
    compromised_hist: RosterHistory | None = None,
    **over: Any,
) -> HistoricalApproval:
    payload = cast.payload(
        who,
        role,
        decision__outcome=outcome,
        signed_at=signed_at,
        supersedes=list(supersedes),
        **over,
    )
    if record_id:
        payload["record_id"] = record_id
    if nonce:
        payload["nonce"] = nonce
    args = as_of_args(
        cast, compromised_hist or hist, payload, stamp=cast.stamp(payload, at=signed_at)
    )
    return ap.verify_approval_as_of(cast.envelope(payload), **args)


def four(cast: Cast, hist: RosterHistory) -> list[HistoricalApproval]:
    return [
        approve(cast, hist, "ALICE-TOKEN", "SYNTH-OWNER"),
        approve(cast, hist, "BOB", "SYNTH-RESEARCH"),
        approve(cast, hist, "CAROL", "SYNTH-TRADING"),
        approve(cast, hist, "DAVE", "SYNTH-VALIDATOR"),
    ]


def raises(approvals: Any, req: Any = None, context: Any = None) -> ErrorCode:
    with pytest.raises(ApprovalError) as info:
        evaluate_requirement(approvals, req or requirement(), **(context or ctx()))
    return info.value.code


# ---- satisfied ------------------------------------------------------------------------------


def test_four_distinct_persons_in_four_roles_satisfy_the_requirement(cast, hist):
    result = evaluate_requirement(four(cast, hist), requirement(), **ctx())
    assert result.satisfied is True
    assert result.distinct_persons == ("P-ALICE", "P-BOB", "P-CAROL", "P-DAVE")
    assert result.reasons == ()


def test_result_does_not_depend_on_input_order(cast, hist):
    items = four(cast, hist)
    forward = evaluate_requirement(items, requirement(), **ctx())
    backward = evaluate_requirement(list(reversed(items)), requirement(), **ctx())
    assert forward == backward


def test_extra_approvers_beyond_the_minimum_still_satisfy(cast, hist):
    items = [
        *four(cast, hist),
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-OWNER", record_id="EXTRA-1", nonce="ab" * 16),
    ]
    assert evaluate_requirement(items, requirement(), **ctx()).satisfied is True


def test_role_assignment_needs_backtracking_not_greedy_choice(cast, hist):
    # ALICE holds RESEARCH and OWNER approvals; BOB holds RESEARCH only. Roles (RESEARCH, OWNER)
    # are satisfiable only by BOB->RESEARCH and ALICE->OWNER.
    items = [
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-RESEARCH"),
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-OWNER"),
        approve(cast, hist, "BOB", "SYNTH-RESEARCH"),
    ]
    assert (
        evaluate_requirement(
            items, requirement(("SYNTH-RESEARCH", "SYNTH-OWNER"), 2), **ctx()
        ).satisfied
        is True
    )


# ---- one natural person counts once ---------------------------------------------------------


def test_two_keys_held_by_one_person_count_as_one_person(cast, hist):
    items = [
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-OWNER"),
        approve(cast, hist, "ALICE-TOKEN", "SYNTH-OWNER", record_id="ALT-2", nonce="cd" * 16),
    ]
    result = evaluate_requirement(items, requirement(("SYNTH-OWNER",), 2), **ctx())
    assert result.satisfied is False and result.distinct_persons == ("P-ALICE",)


def test_one_person_cannot_fill_two_required_roles(cast, hist):
    items = [
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-OWNER"),
        approve(cast, hist, "ALICE-LAPTOP", "SYNTH-RESEARCH"),
    ]
    result = evaluate_requirement(items, requirement(("SYNTH-OWNER", "SYNTH-RESEARCH"), 2), **ctx())
    assert result.satisfied is False
    assert any("different persons" in r for r in result.reasons)


def test_unmapped_signer_is_refused_not_counted(cast):
    people = {k: v for k, v in PEOPLE.items() if k != "CAROL"}
    h = cast.history([cast.roster(1, persons=people)], [V1_START])
    item = approve(cast, h, "CAROL", "SYNTH-TRADING")
    assert item.person_id is None
    code = raises([item], requirement(("SYNTH-TRADING",), 1), ctx(cast, h))
    assert code == ErrorCode.NOT_AUTHORIZED


# ---- missing, revoked, compromised ----------------------------------------------------------


def test_missing_role_is_unsatisfied(cast, hist):
    result = evaluate_requirement(four(cast, hist)[:3], requirement(), **ctx())
    assert result.satisfied is False
    assert evaluate_requirement([], requirement(), **ctx()).satisfied is False


def test_revoke_record_withdraws_the_approval(cast, hist):
    items = four(cast, hist)
    withdrawn = approve(
        cast, hist, "DAVE", "SYNTH-VALIDATOR", outcome="REVOKE", record_id="REV-1", nonce="ef" * 16,
        supersedes=(items[3].record.record_id,), signed_at="2026-03-11T12:00:00Z",
    )  # fmt: skip
    result = evaluate_requirement([*items, withdrawn], requirement(), **ctx())
    assert result.satisfied is False


def test_approval_whose_key_was_compromised_later_is_excluded_and_noted(cast, hist):
    later = cast.history(
        [cast.roster(1), cast.roster(2, compromised={"DAVE": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    items = [*four(cast, hist)[:3], approve(cast, later, "DAVE", "SYNTH-VALIDATOR")]
    assert items[3].acceptable is False
    result = evaluate_requirement(items, requirement(), **ctx(cast, later))
    assert result.satisfied is False
    assert any("compromised" in r for r in result.reasons)


def test_compromised_approver_does_not_block_a_sufficient_remainder(cast, hist):
    later = cast.history(
        [cast.roster(1), cast.roster(2, compromised={"DAVE": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    items = [*four(cast, hist)[:3], approve(cast, later, "DAVE", "SYNTH-VALIDATOR")]
    result = evaluate_requirement(items, requirement(FOUR[:3], 3), **ctx(cast, later))
    assert result.satisfied is True and any("compromised" in r for r in result.reasons)


# ---- duplicates, mismatches, contradictions -------------------------------------------------


def test_duplicate_record_or_nonce_is_refused(cast, hist):
    items = four(cast, hist)
    assert raises([*items, items[0]]) == ErrorCode.REPLAY
    clone = approve(
        cast, hist, "BOB", "SYNTH-RESEARCH", record_id="OTHER-ID", nonce=items[1].record.nonce
    )
    assert raises([*items, clone]) == ErrorCode.REPLAY


def test_approval_for_another_document_scope_or_purpose_is_refused(cast, hist):
    items = four(cast, hist)
    for override in (
        {"document_id": "SYNTH-OTHER"},
        {"document_sha256": "00" * 32},
        {"spec_sha256": "00" * 32},
        {"scope": "SYNTH-OTHER"},
        {"purpose": "SYNTH-OTHER"},
    ):
        assert raises(items, requirement(**override)) == ErrorCode.DOCUMENT_MISMATCH


def test_contradictory_approvals_are_an_explicit_conflict_and_a_lone_reject_blocks(cast, hist):
    approvals = four(cast, hist)
    reject = approve(
        cast, hist, "BOB", "SYNTH-RESEARCH", outcome="REJECT", record_id="REJ-1", nonce="12" * 16
    )
    result = evaluate_requirement([*approvals, reject], requirement(), **ctx())
    assert result.satisfied is False and result.state == "CONFLICT"
    # dissent is preserved as evidence: every APPROVE is paired with the REJECT
    assert [r for _, r in result.conflicts] == ["REJ-1"] * 4
    assert {a for a, _ in result.conflicts} == {a.record.record_id for a in approvals}
    blocked = evaluate_requirement([reject], requirement(), **ctx())
    assert blocked.satisfied is False and blocked.state == "REJECTED"
    assert "REJECT" in " ".join(blocked.reasons)


def test_a_conflict_never_satisfies_even_when_the_remainder_is_sufficient(cast, hist):
    # DAVE (a different signer from every approver) rejects: dissent still blocks, and only the
    # original signer could supersede it. No quorum/veto rule decides which side wins.
    approvals = four(cast, hist)
    reject = approve(
        cast, hist, "DAVE", "SYNTH-VALIDATOR", outcome="REJECT", record_id="REJ-D", nonce="21" * 16
    )
    result = evaluate_requirement([*approvals[:3], reject], requirement(FOUR[:3], 3), **ctx())
    assert (result.satisfied, result.state) == (False, "CONFLICT")
    outsider = approve(
        cast, hist, "ALICE-LAPTOP", "SYNTH-OWNER", record_id="SUP-X", nonce="22" * 16,
        supersedes=("REJ-D",), signed_at="2026-03-11T12:00:00Z",
    )  # fmt: skip
    assert raises([*approvals[:3], reject, outsider]) == ErrorCode.SUPERSESSION


def test_a_reject_from_a_later_compromised_key_still_blocks(cast, hist):
    later = cast.history(
        [cast.roster(1), cast.roster(2, compromised={"BOB": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    reject = approve(
        cast, later, "BOB", "SYNTH-RESEARCH", outcome="REJECT", record_id="REJ-B", nonce="23" * 16
    )
    items = [*[a for a in four(cast, hist) if a.record.identity != "BOB"], reject]
    result = evaluate_requirement(items, requirement(FOUR[:1] + FOUR[2:], 3), **ctx(cast, later))
    assert (result.satisfied, result.state) == (False, "CONFLICT")
    assert any("compromised" in r for r in result.reasons)


# ---- evidence integrity: the result object is not an authority ------------------------------


def test_replaced_or_tampered_historical_approval_is_refused(cast, hist):
    items = four(cast, hist)
    first = items[0]
    for field_name, value in (
        ("person_id", "P-BOB"),
        ("later_compromise", True),
        ("roster_sha256", "00" * 32),
        ("as_of", first.as_of.replace(year=2025)),
        ("envelope_sha256", "11" * 32),
        ("history_head_sha256", "22" * 32),
        ("time_authorities_sha256", "33" * 32),
        ("key_revoked_later_at", "2026-02-01T00:00:00Z"),
    ):
        with pytest.raises(ApprovalError) as info:
            replace(first, **{field_name: value})
        assert info.value.code == ErrorCode.SCHEMA, field_name
    with pytest.raises(ApprovalError):
        replace(first, record=replace(first.record, role="SYNTH-VALIDATOR"))
    with pytest.raises(ApprovalError):
        replace(first, stamp=replace(first.stamp, attested_at="2026-03-10T12:01:00Z"))


def test_object_level_mutation_is_caught_when_the_evidence_is_consumed(cast, hist):
    items = four(cast, hist)
    object.__setattr__(items[0], "person_id", "P-FORGED")  # bypasses frozen, not the MAC
    assert raises(items) == ErrorCode.SCHEMA
    items = four(cast, hist)
    object.__setattr__(items[1], "later_compromise", True)
    assert raises(items) == ErrorCode.SCHEMA


def test_forged_identity_or_person_in_the_envelope_is_refused(cast, hist):
    # a genuine item, then the carried envelope is swapped for another signer's bytes
    items = four(cast, hist)
    other = approve(cast, hist, "BOB", "SYNTH-RESEARCH", record_id="OTHER-B", nonce="31" * 16)
    object.__setattr__(items[0], "envelope", other.envelope)
    assert raises(items) == ErrorCode.SCHEMA


def test_copied_or_pickled_evidence_is_not_a_new_instance(cast, hist):
    import copy
    import pickle

    item = four(cast, hist)[0]
    assert copy.copy(item) is item and copy.deepcopy(item) is item
    with pytest.raises(ApprovalError):
        pickle.dumps(item)


def test_missing_or_forged_time_authority_evidence_is_refused_at_consumption(cast, hist):
    items = four(cast, hist)
    wrong_tsa_pin = {**ctx(), "pinned_time_authorities_sha256": "00" * 32}
    assert raises(items, None, wrong_tsa_pin) == ErrorCode.ROSTER_UNTRUSTED
    other_cast = Cast()  # a different, unpinned time authority
    assert raises(items, None, ctx(other_cast, hist)) in (
        ErrorCode.ROSTER_UNTRUSTED,
        ErrorCode.TIME_EVIDENCE,
        ErrorCode.SIGNATURE,
    )
    # a stamp-less result cannot be built at all
    with pytest.raises(ApprovalError):
        replace(items[0], stamp=None)
    # each countersignature field is sealed, including the signature bytes themselves
    other_sig = items[1].stamp.signature_hex
    with pytest.raises(ApprovalError):
        replace(items[0], stamp=replace(items[0].stamp, signature_hex=other_sig))
    with pytest.raises(ApprovalError):
        replace(items[0], stamp=replace(items[0].stamp, authority_id="SYNTH-OTHER-TSA"))


def test_fresh_reverification_overrides_stale_carried_key_state(cast, hist):
    # Evidence produced while DAVE's key was still unflagged is re-derived against the caller's
    # newer history: the carried object says "acceptable", the fresh result says "compromised".
    items = four(cast, hist)
    assert items[3].later_compromise is False
    newer = cast.history(
        [cast.roster(1), cast.roster(2, compromised={"DAVE": "2026-08-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    result = evaluate_requirement(items, requirement(), **ctx(cast, newer))
    assert result.satisfied is False
    assert any("compromised" in r for r in result.reasons)
    assert "SYNTH-VALIDATOR" not in " ".join(result.distinct_persons)
    assert result.distinct_persons == ("P-ALICE", "P-BOB", "P-CAROL")


def test_evidence_is_reverified_against_the_callers_history_not_its_own(cast, hist):
    items = four(cast, hist)
    substituted = cast.history(
        [cast.roster(1), cast.roster(2, revoked={"BOB": "2026-07-01T00:00:00Z"})],
        [V1_START, V2_START],
    )
    # the caller pinned the substituted history's head: the evidence's roster digest must still match
    result = evaluate_requirement(items, requirement(), **ctx(cast, substituted))
    assert result.satisfied is True  # revocation after as-of does not void an earlier approval
    wrong_head = {**ctx(cast, substituted), "pinned_head_sha256": hist.head_sha256}
    assert raises(items, None, wrong_head) == ErrorCode.ROSTER_UNTRUSTED


def test_broken_roster_chain_or_changed_person_mapping_blocks_evidence(cast, hist):
    r1 = cast.roster(1)
    r2_remapped = cast.roster(2, persons={**PEOPLE, "BOB": "P-ALICE"})
    with pytest.raises(ApprovalError) as info:
        cast.history([r1, r2_remapped], [V1_START, V2_START])
    assert info.value.code == ErrorCode.HISTORY


def test_superseding_a_reject_with_an_approval_restores_consistency(cast, hist):
    reject = approve(
        cast, hist, "BOB", "SYNTH-RESEARCH", outcome="REJECT", record_id="REJ-1", nonce="12" * 16
    )
    flipped = approve(
        cast, hist, "BOB", "SYNTH-RESEARCH", record_id="APP-2", nonce="34" * 16,
        supersedes=("REJ-1",), signed_at="2026-03-11T12:00:00Z",
    )  # fmt: skip
    rest = [a for a in four(cast, hist) if a.record.identity != "BOB"]
    assert evaluate_requirement([reject, flipped, *rest], requirement(), **ctx()).satisfied is True


def test_bad_supersession_is_refused(cast, hist):
    unknown = approve(
        cast, hist, "BOB", "SYNTH-RESEARCH", record_id="X-1", nonce="56" * 16, supersedes=("NOPE",)
    )
    assert raises([unknown]) == ErrorCode.SUPERSESSION
    first = approve(cast, hist, "CAROL", "SYNTH-TRADING", record_id="C-1", nonce="78" * 16)
    other_signer = approve(
        cast, hist, "DAVE", "SYNTH-VALIDATOR", record_id="D-1", nonce="9a" * 16,
        supersedes=("C-1",), signed_at="2026-03-11T12:00:00Z",
    )  # fmt: skip
    assert raises([first, other_signer]) == ErrorCode.SUPERSESSION


def test_non_evidence_inputs_are_refused(cast, hist):
    items = four(cast, hist)
    assert raises([*items, "not evidence"]) == ErrorCode.SCHEMA
    assert raises(items, object()) == ErrorCode.SCHEMA
    forged = replace(items[0].record, role="SYNTH-OWNER")
    assert raises([forged]) == ErrorCode.SCHEMA  # an ApprovalRecord is not sealed evidence


@pytest.mark.parametrize(
    "bad",
    [
        {"required_roles": ["SYNTH-OWNER"]},
        {"required_roles": ("SYNTH-OWNER", "SYNTH-OWNER"), "min_distinct_persons": 2},
        {"required_roles": ("bad role",), "min_distinct_persons": 1},
        {"min_distinct_persons": 3},
        {"min_distinct_persons": 0},
        {"min_distinct_persons": True},
        {"document_sha256": "xyz"},
        {"scope": ""},
    ],
)
def test_requirement_validation(bad):
    with pytest.raises(ApprovalError):
        requirement(**bad)
