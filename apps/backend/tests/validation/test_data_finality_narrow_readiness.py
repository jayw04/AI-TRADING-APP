"""The NARROW, session-scoped readiness contract.

`READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS` is the outcome for a session whose
DECISION is proven valid while some corporate actions remain economically unproven. It is a distinct
verdict rather than a flag on `READY`, it never sets `adjustment_reflection_proven`, and it is reachable
only through an attestation whose every clause is re-derived from the measured evidence.

⚠ The tests here are mostly REFUSALS, on purpose. A permissive outcome tested only on its happy path is
a permissive outcome that will quietly start admitting things it should not. The two that matter most:

  * `test_the_narrow_status_is_NEVER_inherited_by_another_session` — the guard that stops this becoming
    a standing exception;
  * `test_the_narrow_status_never_reports_the_broad_claim_as_proven` — the guard that stops it being
    read as "every corporate action is reconciled".
"""

from __future__ import annotations

from datetime import date, datetime

import pandas as pd
import pytest

from app.factor_data.store import FactorDataStore
from app.validation.data_finality import (
    ConstructionSpec,
    DataReadiness,
    NarrowReadinessAttestation,
    assess_data_finality,
)

SESSION = date(2026, 7, 24)
N_SESSIONS = 300
N_TICKERS = 60
SPEC = ConstructionSpec(scoring_universe_n=20, proxy_universe_n=30)

RECON_SHA = "a" * 64
RELEVANCE_SHA = "b" * 64
QUARANTINE_SHA = "c" * 64
#: SHOP and TLN, by PERMANENT identity — the two histories this vintage withholds.
QUARANTINED = frozenset({"167284", "642054"})

#: The digest of the relevance set the READINESS construction builds. Distinct from `RELEVANCE_SHA`,
#: which is the digest of the external decision-relevance ASSESSMENT — two different artifacts that the
#: 2026-07-27 defect conflated.
RELEVANCE_SET_SHA = "5e" * 32
#: What a DIAGNOSTIC runner over a broader identity set produces. Never interchangeable with the above.
DIAGNOSTIC_SET_SHA = "d1" * 32

#: The shape of a measurement carrying the acquired-side disclosure.
JULY27_COUNTS = {
    "PROVEN_REFLECTED": 1676,
    "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 94,
    "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3,
    "UNRESOLVED_NONDECISION_MA_SEMANTICS": 18,
}
#: ★ What the DEPLOYED readiness path actually measured for 2026-07-27, over its own 670-identity
#: relevance set: the 18 adjudicated acquired-side events are not in it at all. The corpus-wide
#: adjudication still exists — it simply does not describe this session.
DEPLOYED_JULY27_COUNTS = {
    "PROVEN_REFLECTED": 1670,
    "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 91,
    "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3,
}
#: The corpus-wide size of the acquired-side adjudication, whatever any one session contains.
CORPUS_WIDE_MA_EVENTS = 18
DISCLOSURE_REASON = "ACQUIRED_SIDE_ECONOMICALLY_TERMINAL_AND_MEASURED_NON_DECISION_RELEVANT"


def _sessions(n: int, end: date) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= pd.Timedelta(days=1).to_pytimedelta()
    return sorted(out)


@pytest.fixture
def store(tmp_path):
    """A store that clears every gate BEFORE the corporate-action step, so each test isolates the one
    thing it is about: the narrow readiness contract."""
    st = FactorDataStore(db_path=str(tmp_path / "narrow.duckdb"))
    days = _sessions(N_SESSIONS, SESSION)
    tickers = [f"T{i:04d}" for i in range(N_TICKERS)]
    st.ingest_sep(pd.DataFrame([
        {"ticker": t, "date": d, "open": 100.0, "high": 100.0, "low": 100.0, "close": 100.0,
         "volume": 1_000_000 + i, "closeadj": 100.0, "closeunadj": 100.0, "lastupdated": d}
        for d in days for i, t in enumerate(tickers)]))
    st.ingest_tickers(pd.DataFrame([
        {"ticker": t, "permaticker": str(500000 + i), "name": f"{t} CORP", "exchange": "NYSE",
         "category": "Domestic Common Stock", "sector": "Technology", "industry": "Software",
         "isdelisted": False, "firstpricedate": days[0], "lastpricedate": SESSION,
         "lastupdated": SESSION}
        for i, t in enumerate(tickers)]))
    st.record_ingest_run("sep", datetime(2026, 7, 24, 22, 0), datetime(2026, 7, 24, 22, 5),
                         N_SESSIONS * N_TICKERS, "ok")
    st.record_ingest_run("actions", datetime(2026, 7, 24, 21, 5), datetime(2026, 7, 24, 21, 6),
                         0, "ok")
    yield st
    st.close()


class _CensusAdjustment:
    """A verifier double shaped like the real deployed measurement: NOT proven overall, every action
    classified, the per-action payload BOUNDED at the production cap, 4 unexplained movements on the
    two quarantined identities.

    ⚠ The bounded-evidence record is modelled faithfully rather than stubbed. The 2026-07-27 defect was
    invisible precisely because the old double reported `{"truncated": False}` — a shape production can
    never produce against 1,764 actions and a 200-action cap. A double that cannot reproduce the
    deployed condition cannot catch a contract that fails only there.
    """

    def __init__(self, store_identity: str, *, counts=None, disclosure=RELEVANCE_SHA,
                 unexplained=None, unexplained_total=None, reason_count=None,
                 relevance_set=RELEVANCE_SET_SHA, ma_entries=CORPUS_WIDE_MA_EVENTS,
                 serialized=None, total_actions=None, omitted=None, truncated=None, cap=200):
        self.proven = False
        self._id = store_identity
        self._counts = dict(DEPLOYED_JULY27_COUNTS if counts is None else counts)
        self._disclosure = disclosure
        self._relevance_set = relevance_set
        self._ma_entries = ma_entries
        self._unexplained = ([{"permaticker": p} for p in
                              ("167284", "167284", "642054", "642054")]
                             if unexplained is None else unexplained)
        self._total = len(self._unexplained) if unexplained_total is None else unexplained_total
        self._reason_count = (self._counts.get("UNRESOLVED_NONDECISION_MA_SEMANTICS", 0)
                              if reason_count is None else reason_count)
        # Bounding, derived to be self-consistent by default so a test that means to break ONE clause
        # does not accidentally break three.
        self._cap = cap
        self._total_actions = sum(self._counts.values()) if total_actions is None else total_actions
        self._serialized = min(self._total_actions, cap) if serialized is None else serialized
        self._omitted = (self._total_actions - self._serialized) if omitted is None else omitted
        self._truncated = (self._omitted > 0) if truncated is None else truncated

    def to_open_provenance(self) -> dict:
        return {
            "verdict": "NOT_PROVEN_UNSUPPORTED_ACTION", "proven": False,
            "detail": "the broad reflection proof does not hold",
            "store_identity_sha256": self._id,
            "relevance_set_sha256": self._relevance_set,
            "relevant_ticker_count": 670,
            "checks_by_status": self._counts,
            "checks_by_reason_code": {DISCLOSURE_REASON: self._reason_count},
            "ma_disclosure_sha256": self._disclosure,
            "ma_disclosure_entry_count": self._ma_entries,
            "checks": [{"i": i} for i in range(self._serialized)],
            "action_evidence": {
                "total_action_count": self._total_actions,
                "included_action_count": self._serialized,
                "omitted_action_count": self._omitted,
                "truncated": self._truncated,
                "max_actions": self._cap,
            },
            "unexplained_adjustment_count": self._total,
            "unexplained_examples": self._unexplained,
        }


class _ProvenAdjustment:
    def __init__(self, store_identity: str):
        self.proven = True
        self._id = store_identity

    def to_open_provenance(self) -> dict:
        return {"verdict": "PROVEN", "proven": True, "detail": "all reflected",
                "store_identity_sha256": self._id}


def _attestation(session=SESSION, **kw) -> NarrowReadinessAttestation:
    kw.setdefault("reconciliation_artifact_sha256", RECON_SHA)
    kw.setdefault("relevance_artifact_sha256", RELEVANCE_SHA)
    kw.setdefault("quarantine_artifact_sha256", QUARANTINE_SHA)
    kw.setdefault("quarantined_identities", QUARANTINED)
    kw.setdefault("relevance_set_sha256", RELEVANCE_SET_SHA)
    kw.setdefault("expected_status_counts", dict(DEPLOYED_JULY27_COUNTS))
    return NarrowReadinessAttestation(session_date=session, **kw)


def _assess(store, *, adjustment=None, attestation=..., session=SESSION):
    def verifier(window_start, session_date, tickers, store_identity):
        return (adjustment or _CensusAdjustment)(store_identity)

    return assess_data_finality(
        store, session, construction=SPEC, adjustment_verifier=verifier,
        narrow_readiness=_attestation() if attestation is ... else attestation)


def _refusals(ev) -> list[str]:
    return ev.adjustment_evidence["narrow_readiness"]["refusals"]


# ---- the claim, when it holds ------------------------------------------------------------------------

def test_the_narrow_status_is_granted_when_every_clause_holds(store):
    ev = _assess(store)
    assert ev.verdict is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS
    assert ev.ready is True, "the session may be evaluated"
    assert _refusals(ev) == []
    narrow = ev.adjustment_evidence["narrow_readiness"]
    assert narrow["full_action_semantics_proven"] is False
    assert narrow["decision_validity_proven"] is True
    # ★ The deployed July 27 shape: the session's own limitation is the QUARANTINE, and the acquired-side
    # adjudication — real, and 18 events wide corpus-wide — contributes nothing to THIS session.
    assert narrow["nondecision_limitations_present"] is False
    assert narrow["unsupported_semantics_in_readiness_relevance_set"] == 0
    assert narrow["corpus_wide_unsupported_semantics_count"] == CORPUS_WIDE_MA_EVENTS
    assert narrow["unexplained_movements_on_quarantined_identities"] == 4


def test_the_narrow_status_is_granted_when_the_session_DOES_carry_disclosed_events(store):
    """The other valid shape: adjudicated events that ARE inside the relevance set stay disclosed."""
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=JULY27_COUNTS),
                 attestation=_attestation(expected_status_counts=dict(JULY27_COUNTS)))
    assert ev.verdict is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS
    narrow = ev.adjustment_evidence["narrow_readiness"]
    assert narrow["nondecision_limitations_present"] is True
    assert narrow["unsupported_semantics_in_readiness_relevance_set"] == 18


def test_a_corpus_wide_adjudication_absent_from_the_session_is_not_an_active_limitation(store):
    """★ DEFECT 2, PINNED. An event the readiness relevance set never contains cannot limit a decision
    that set produced. The corpus-wide figure is REPORTED, never counted as a session finding."""
    lim = _assess(store).to_open_provenance()["disclosed_limitations"]
    assert lim["known_corpus_wide_unsupported_semantics"] == CORPUS_WIDE_MA_EVENTS
    assert lim["present_in_readiness_relevance_set"] == 0
    assert lim["limitation_count"] == 0
    assert lim["limitation_reason_codes"] == [], (
        "a reason code that fired zero times must not be listed as a finding")
    assert lim["unexplained_movements_on_quarantined_identities"] == 4, (
        "the quarantine IS the active limitation for this session and must still be disclosed")
    assert lim["readiness_relevance_set_sha256"] == RELEVANCE_SET_SHA


def test_the_flags_are_derived_from_evidence_not_forced_to_a_target_shape(store):
    """`nondecision_limitations_present` tracks the MEASUREMENT. It is not held true to preserve an
    earlier expected result, and not held false to make a session look cleaner."""
    for counts, expected in ((DEPLOYED_JULY27_COUNTS, False), (JULY27_COUNTS, True)):
        ev = _assess(store,
                     adjustment=lambda i, c=counts: _CensusAdjustment(i, counts=c),
                     attestation=_attestation(expected_status_counts=dict(counts)))
        narrow = ev.adjustment_evidence["narrow_readiness"]
        assert narrow["nondecision_limitations_present"] is expected
        assert narrow["decision_validity_proven"] is True


def test_the_narrow_status_never_reports_the_broad_claim_as_proven(store):
    """★ It is NOT a waiver. `proven` stays false everywhere it is visible."""
    ev = _assess(store)
    assert ev.adjustment_reflection_proven is False
    assert ev.adjustment_evidence["proven"] is False
    assert ev.fully_proven is False
    assert ev.has_disclosed_limitations is True
    assert str(ev.verdict) != "READY"


def test_the_narrow_status_binds_the_session_and_all_three_artifact_digests(store):
    narrow = _assess(store).adjustment_evidence["narrow_readiness"]
    assert narrow["attested_session"] == SESSION.isoformat()
    assert narrow["reconciliation_artifact_sha256"] == RECON_SHA
    assert narrow["relevance_artifact_sha256"] == RELEVANCE_SHA
    assert narrow["quarantine_artifact_sha256"] == QUARANTINE_SHA
    assert narrow["quarantined_identities"] == sorted(QUARANTINED)


# ---- the refusals ------------------------------------------------------------------------------------

def test_the_narrow_status_is_NEVER_inherited_by_another_session(store):
    """★ THE GUARD THAT STOPS THIS BECOMING A STANDING EXCEPTION.

    An attestation names ONE session. Any other observation must re-earn the status with a freshly
    computed relevance assessment, or fall back to NOT_READY_ADJUSTMENT_UNVERIFIED.
    """
    ev = _assess(store, attestation=_attestation(session=date(2026, 7, 23)))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert ev.ready is False
    assert any("session-scoped" in r for r in _refusals(ev))


def test_without_an_attestation_the_session_is_refused_exactly_as_before(store):
    ev = _assess(store, attestation=None)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert ev.ready is False
    assert ev.adjustment_evidence.get("narrow_readiness") is None


def test_an_unassessed_action_refuses_the_narrow_status(store):
    """'Every canonical action assessed' — the default-deny bucket must be EMPTY. An unassessed action
    is not a disclosed limitation; nobody has looked at it."""
    counts = {**DEPLOYED_JULY27_COUNTS, "NOT_PROVEN_UNSUPPORTED_SEMANTICS": 2}
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=counts),
                 attestation=_attestation(expected_status_counts=counts))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("never assessed" in r for r in _refusals(ev))


@pytest.mark.parametrize("bad", ["PROVEN_NOT_REFLECTED", "SOURCE_CONFLICT",
                                 "NOT_PROVEN_INSUFFICIENT_DATA"])
def test_a_conflict_or_insufficiency_can_never_hide_behind_the_disclosure(store, bad):
    counts = {**DEPLOYED_JULY27_COUNTS, bad: 1}
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=counts),
                 attestation=_attestation(expected_status_counts=counts))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any(bad in r for r in _refusals(ev))


def test_a_disclosure_bound_to_a_different_assessment_is_refused(store):
    """The disclosure must point at the assessment the attestation names, or its 'measured' basis is
    somebody else's measurement."""
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=JULY27_COUNTS,
                                                        disclosure="f" * 64),
                 attestation=_attestation(expected_status_counts=dict(JULY27_COUNTS)))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("bound to assessment" in r for r in _refusals(ev))


def test_a_disclosed_action_without_its_named_relevance_reason_is_refused(store):
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=JULY27_COUNTS,
                                                        reason_count=17),
                 attestation=_attestation(expected_status_counts=dict(JULY27_COUNTS)))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("relevance reason code" in r for r in _refusals(ev))


def test_an_unexplained_movement_on_a_NON_quarantined_identity_is_refused(store):
    """Movements are tolerated only where the history is withheld from the decision entirely."""
    moves = [{"permaticker": "167284"}, {"permaticker": "999999"}]
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, unexplained=moves))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("non-quarantined" in r for r in _refusals(ev))


def test_an_uncheckable_movement_census_is_refused(store):
    """If the recorded examples are fewer than the count, a movement could exist on a non-quarantined
    name and simply not be shown, so the quarantine claim is unverifiable."""
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, unexplained_total=9))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("cannot be checked against the quarantine" in r for r in _refusals(ev))


# ---- DEFECT 1: census completeness, NOT payload completeness -----------------------------------------
#
# ★ The deployed 2026-07-27 refusal. The old clause required `truncated == False`, which the production
# MAX_EVIDENCE_ACTIONS cap makes unreachable for any real session: 1,764 relevant actions cannot fit a
# 200-action receipt. The clause was satisfiable only by a diagnostic that raised the cap in-process, so
# it gated nothing in production and blocked everything. What matters is that every action was
# CLASSIFIED — the census is computed before bounding and can prove exactly that.

def test_a_truncated_payload_alone_does_NOT_refuse_the_narrow_status(store):
    """★ THE DEFECT-1 REGRESSION. 1,764 assessed, 200 serialized, census complete → still ready."""
    counts = {"PROVEN_REFLECTED": 1670, "PROVEN_NO_PRICE_ADJUSTMENT_APPLICABLE": 91,
              "PROVEN_LINEAGE_EVENT_NO_ADDITIONAL_PRICE_ADJUSTMENT": 3}
    assert sum(counts.values()) == 1764
    ev = _assess(store,
                 adjustment=lambda i: _CensusAdjustment(i, counts=counts),
                 attestation=_attestation(expected_status_counts=dict(counts)))
    ae = ev.adjustment_evidence["action_evidence"]
    assert (ae["total_action_count"], ae["included_action_count"], ae["truncated"]) == (1764, 200, True)
    assert _refusals(ev) == [], "truncation of the bounded receipt is not incompleteness of the census"
    assert ev.verdict is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS


def test_a_census_that_does_not_sum_to_the_assessed_total_is_refused(store):
    """The property that actually matters: every action classified."""
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, total_actions=1800))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("every action classified" in r for r in _refusals(ev))


def test_inconsistent_omitted_count_arithmetic_is_refused(store):
    """`omitted == total - serialized`, checked against the list actually carried."""
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, omitted=3))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("bounded-evidence arithmetic is inconsistent" in r for r in _refusals(ev))


def test_a_truncated_flag_contradicting_the_omitted_count_is_refused(store):
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, truncated=False))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("contradicts" in r for r in _refusals(ev))


def test_evidence_bounded_at_a_RAISED_cap_is_refused_as_diagnostic(store):
    """⛔ A diagnostic that lifts the production cap must never satisfy a production contract — that is
    how the 2026-07-27 attestation was produced in the first place."""
    from app.validation.data_finality import MAX_EVIDENCE_ACTIONS

    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, cap=MAX_EVIDENCE_ACTIONS + 1))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("diagnostic record" in r for r in _refusals(ev))


def test_more_actions_serialized_than_the_cap_allows_is_refused(store):
    """A record carrying more detail than its own declared bound is not a record of that bound."""
    ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, cap=50, serialized=60))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("against a cap of 50" in r for r in _refusals(ev))


def test_missing_bounded_evidence_is_refused(store):
    class _NoBounds(_CensusAdjustment):
        def to_open_provenance(self):
            return {**super().to_open_provenance(), "action_evidence": {}}

    ev = _assess(store, adjustment=_NoBounds)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("no bounded-evidence record" in r for r in _refusals(ev))


def test_the_production_evidence_cap_is_unchanged_at_200():
    """⛔ The fix was to the GUARD, never to the cap. Pinned so a future 'make it pass' cannot raise it."""
    from app.validation.adjustment_verifier import MAX_EVIDENCE_ACTIONS

    assert MAX_EVIDENCE_ACTIONS == 200


def test_the_narrow_clause_pins_the_SAME_cap_the_verifier_enforces():
    """One source of truth. A second copy of the number is a pin that drifts silently."""
    from app.validation import adjustment_verifier, data_finality

    assert data_finality.MAX_EVIDENCE_ACTIONS == adjustment_verifier.MAX_EVIDENCE_ACTIONS == 200


def test_a_diagnostic_that_REBINDS_the_verifier_cap_cannot_relax_the_readiness_clause(store):
    """★ `layer2_adjustment_reconciliation` legitimately rebinds `av.MAX_EVIDENCE_ACTIONS` in its own
    process to serialize every action. The readiness clause imported the value at import time, so a
    diagnostic monkeypatch cannot widen what production will accept."""
    from app.validation import adjustment_verifier, data_finality

    original = adjustment_verifier.MAX_EVIDENCE_ACTIONS
    try:
        adjustment_verifier.MAX_EVIDENCE_ACTIONS = 100_000
        assert data_finality.MAX_EVIDENCE_ACTIONS == 200, "the readiness clause must not follow"
        ev = _assess(store, adjustment=lambda i: _CensusAdjustment(i, cap=100_000))
        assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
        assert any("diagnostic record" in r for r in _refusals(ev))
    finally:
        adjustment_verifier.MAX_EVIDENCE_ACTIONS = original


# ---- DEFECT 2: the census must describe THIS session's relevance set ----------------------------------

def test_a_census_measured_over_a_DIFFERENT_relevance_set_is_refused(store):
    """★ THE DEFECT-2 REGRESSION. The 2026-07-27 attestation's counts came from a diagnostic runner
    whose relevance set held 689 identities; the readiness path builds 670. Both were internally
    consistent; only one described the session."""
    ev = _assess(store, attestation=_attestation(relevance_set_sha256=DIAGNOSTIC_SET_SHA))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("different set of securities" in r for r in _refusals(ev))


def test_an_attestation_with_no_relevance_set_binding_is_refused(store):
    """Unattributed counts are not evidence about anything."""
    ev = _assess(store, attestation=_attestation(relevance_set_sha256=""))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("names no relevance set" in r for r in _refusals(ev))


def test_an_attestation_with_no_expected_census_is_refused(store):
    ev = _assess(store, attestation=_attestation(expected_status_counts={}))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("no expected census" in r for r in _refusals(ev))


def test_a_stale_attestation_is_refused_rather_than_reinterpreted(store):
    """The measurement moved after the attestation was written."""
    ev = _assess(store, attestation=_attestation(
        expected_status_counts={**DEPLOYED_JULY27_COUNTS, "PROVEN_REFLECTED": 1669}))
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("stale" in r for r in _refusals(ev))


def test_the_narrow_path_never_shadows_a_fully_proven_session(store):
    """When the broad proof holds, the ordinary READY verdict is returned and the narrow machinery is
    not consulted at all."""
    ev = _assess(store, adjustment=_ProvenAdjustment)
    assert ev.verdict is DataReadiness.READY
    assert ev.fully_proven is True
    assert ev.has_disclosed_limitations is False


def test_the_disclosed_status_is_not_in_the_general_readiness_set():
    """⛔ The per-action status must never be admitted to the verifier's general readiness set — that
    would relax the gate for EVERY session rather than making a bounded, session-scoped claim."""
    from app.validation.adjustment_verifier import SATISFIES_READINESS, ActionStatus

    assert ActionStatus.UNRESOLVED_NONDECISION_MA_SEMANTICS not in SATISFIES_READINESS


# ---- the readiness TRUTH TABLE ----------------------------------------------------------------------
#
# `ready` no longer means "fully proven" now that a second ready verdict exists, so the three
# properties are pinned EXHAUSTIVELY over every DataReadiness member rather than only on the two paths
# the other tests exercise. A future verdict added without a decision about these three will fail here.

def _vary(base, verdict, proven):
    from dataclasses import replace

    return replace(base, verdict=verdict, adjustment_reflection_proven=proven)


@pytest.mark.parametrize("verdict", list(DataReadiness))
@pytest.mark.parametrize("proven", [True, False])
def test_the_three_readiness_invariants_hold_for_every_verdict(store, verdict, proven):
    """fully_proven => ready · has_disclosed_limitations => ready · never both at once."""
    ev = _vary(_assess(store), verdict, proven)
    if ev.fully_proven:
        assert ev.ready, "fully_proven must imply ready"
    if ev.has_disclosed_limitations:
        assert ev.ready, "has_disclosed_limitations must imply ready"
    assert not (ev.fully_proven and ev.has_disclosed_limitations), (
        "a session cannot be both fully proven and limited")


def test_the_readiness_truth_table_is_exact(store):
    base = _assess(store)
    narrow = DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS
    for verdict in DataReadiness:
        proven = verdict is DataReadiness.READY
        ev = _vary(base, verdict, proven)
        if verdict is DataReadiness.READY:
            expected = (True, True, False)
        elif verdict is narrow:
            expected = (True, False, True)
        else:
            expected = (False, False, False)
        assert (ev.ready, ev.fully_proven, ev.has_disclosed_limitations) == expected, (
            f"{verdict} produced the wrong readiness triple")


def test_every_not_ready_or_integrity_stop_verdict_is_false_on_all_three(store):
    base = _assess(store)
    blocked = [v for v in DataReadiness
               if str(v).startswith(("NOT_READY", "INTEGRITY_STOP"))]
    assert blocked, "the enum must still carry blocking verdicts"
    for verdict in blocked:
        for proven in (True, False):
            ev = _vary(base, verdict, proven)
            assert (ev.ready, ev.fully_proven, ev.has_disclosed_limitations) == (False, False, False)


# ---- what a downstream receipt must carry -----------------------------------------------------------

def test_the_narrow_status_never_appears_downstream_as_merely_ready(store):
    """★ A receipt saying only `ready: true` would read IDENTICALLY for a fully proven session and one
    carrying disclosed limitations. The provenance must state the claim, not just the permission."""
    d = _assess(store).to_open_provenance()
    assert d["readiness_verdict"] == str(
        DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)
    assert d["fully_proven"] is False
    assert d["has_disclosed_limitations"] is True
    lim = d["disclosed_limitations"]
    assert lim is not None
    assert lim["session_date"] == SESSION.isoformat()
    assert lim["limitation_count"] == 0, "no adjudicated event lies in this relevance set"
    assert lim["known_corpus_wide_unsupported_semantics"] == CORPUS_WIDE_MA_EVENTS
    assert lim["limitation_reason_codes"] == []
    assert lim["reconciliation_artifact_sha256"] == RECON_SHA
    assert lim["relevance_artifact_sha256"] == RELEVANCE_SHA
    assert lim["quarantine_artifact_sha256"] == QUARANTINE_SHA
    assert lim["quarantined_identities"] == sorted(QUARANTINED)
    assert lim["full_action_semantics_proven"] is False


def test_a_fully_proven_session_carries_no_limitation_block(store):
    d = _assess(store, adjustment=_ProvenAdjustment).to_open_provenance()
    assert d["readiness_verdict"] == "READY"
    assert d["fully_proven"] is True
    assert d["has_disclosed_limitations"] is False
    assert d["disclosed_limitations"] is None


def test_a_refused_session_carries_no_limitation_block(store):
    d = _assess(store, attestation=None).to_open_provenance()
    assert d["fully_proven"] is False
    assert d["has_disclosed_limitations"] is False
    assert d["disclosed_limitations"] is None


# ---- the runner must not FLATTEN the narrow status ---------------------------------------------------
#
# The readiness CLI previously reported a hard-coded "READY" for any evaluable session and derived its
# exit code from `verdict == "READY"`. Both are wrong once a second ready verdict exists: the narrow
# result would print as a plain READY (erasing the limitation at exactly the point an operator reads
# it), and reporting the true verdict without fixing the exit code would call a governed outcome a
# failure. Pinned here because it is a one-line regression in an easy-to-overlook place.

def _load_cli():
    import importlib.util
    import sys
    from pathlib import Path

    backend = Path(__file__).resolve().parents[2]
    spec = importlib.util.spec_from_file_location(
        "forward_cli_narrow", backend / "scripts" / "run_forward_validation_session.py")
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules["forward_cli_narrow"] = module
    spec.loader.exec_module(module)
    return module


def test_the_readiness_cli_exits_zero_for_both_evaluable_verdicts():
    from app.validation.data_finality import READINESS_PERMITS_EVALUATION

    cli = _load_cli()
    for verdict in READINESS_PERMITS_EVALUATION:
        report = cli._ReadinessReport("2026-07-24", str(verdict), "d", {})
        assert report.emit() == 0, f"{verdict} is evaluable and must not exit non-zero"


def test_the_readiness_cli_exits_nonzero_for_every_blocking_verdict():
    cli = _load_cli()
    from app.validation.data_finality import READINESS_PERMITS_EVALUATION

    for verdict in DataReadiness:
        if verdict in READINESS_PERMITS_EVALUATION:
            continue
        assert cli._ReadinessReport("2026-07-24", str(verdict), "d", {}).emit() == 1


def test_the_readiness_cli_reports_the_narrow_verdict_verbatim_not_READY(store):
    """★ THE FLATTENING GUARD. `ready: true` must never be the whole story."""
    cli = _load_cli()
    ev = _assess(store)
    assert ev.ready is True
    # what the CLI would report for this evidence
    assert ev.has_disclosed_limitations is True
    verdict = str(ev.verdict)
    assert verdict != "READY"
    assert cli._ReadinessReport("2026-07-24", verdict, "d", {}).emit() == 0


# ---- the FIVE required top-level receipt fields ------------------------------------------------------
#
# ⚠ `ready`, `fully_proven` and `has_disclosed_limitations` are all @property, so `asdict()` silently
# drops every one of them. Two were caught only because the receipt contract named them explicitly;
# `ready` — the field a downstream reader is most likely to look for — was missing after that. Pinned
# exhaustively so a future property can never go missing the same way.

RECEIPT_REQUIRED = ("readiness_verdict", "ready", "fully_proven", "has_disclosed_limitations",
                    "full_action_semantics_proven")


@pytest.mark.parametrize("field_name", RECEIPT_REQUIRED)
def test_every_required_receipt_field_is_present_on_the_narrow_path(store, field_name):
    assert field_name in _assess(store).to_open_provenance()


@pytest.mark.parametrize("field_name", RECEIPT_REQUIRED)
def test_every_required_receipt_field_is_present_on_the_fully_proven_path(store, field_name):
    assert field_name in _assess(store, adjustment=_ProvenAdjustment).to_open_provenance()


@pytest.mark.parametrize("field_name", RECEIPT_REQUIRED)
def test_every_required_receipt_field_is_present_on_a_refused_path(store, field_name):
    assert field_name in _assess(store, attestation=None).to_open_provenance()


def test_the_narrow_receipt_states_exactly_the_governed_values(store):
    d = _assess(store).to_open_provenance()
    assert d["readiness_verdict"] == str(
        DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS)
    assert d["ready"] is True
    assert d["fully_proven"] is False
    assert d["has_disclosed_limitations"] is True
    assert d["full_action_semantics_proven"] is False


def test_the_fully_proven_receipt_states_exactly_the_governed_values(store):
    d = _assess(store, adjustment=_ProvenAdjustment).to_open_provenance()
    assert d["readiness_verdict"] == "READY"
    assert d["ready"] is True
    assert d["fully_proven"] is True
    assert d["has_disclosed_limitations"] is False
    assert d["full_action_semantics_proven"] is True


def test_a_refused_receipt_states_exactly_the_governed_values(store):
    d = _assess(store, attestation=None).to_open_provenance()
    assert d["ready"] is False
    assert d["fully_proven"] is False
    assert d["has_disclosed_limitations"] is False
    assert d["full_action_semantics_proven"] is False
    assert d["disclosed_limitations"] is None


def test_no_property_on_the_evidence_is_silently_dropped_from_provenance(store):
    """The root cause, pinned generically: a computed property that never reaches the serialized record
    is invisible to every downstream reader."""
    ev = _assess(store)
    d = ev.to_open_provenance()
    props = [n for n in dir(type(ev))
             if isinstance(getattr(type(ev), n, None), property) and not n.startswith("_")]
    missing = sorted(n for n in props if n not in d)
    assert not missing, f"computed properties absent from the receipt: {missing}"


# ---- the attestation must be DERIVED from the readiness construction ---------------------------------
#
# ★ DEFECT 2's root cause. The 2026-07-27 attestation's census was hand-carried from a diagnostic runner
# that built its own relevance set. `build_narrow_readiness_attestation` removes the opportunity: it runs
# the IDENTICAL production assessment, captures the relevance set at the one boundary it crosses, and
# derives both the digest and the census from that single run. Nothing about it may be hand-entered.

class _SetSensitiveAdjustment(_CensusAdjustment):
    """A verifier whose census and relevance digest DEPEND on the identities it was handed — which is
    what makes 'two different sets, two different censuses' observable in a test at all."""

    def __init__(self, store_identity, tickers, **kw):
        super().__init__(store_identity, **kw)
        self._names = sorted(tickers)
        self._counts = {"PROVEN_REFLECTED": len(self._names)}
        self._total_actions = len(self._names)
        self._serialized = min(self._total_actions, self._cap)
        self._omitted = self._total_actions - self._serialized
        self._truncated = self._omitted > 0
        self._relevance_set = "%064x" % (len(self._names) * 7919)


def _derive(store, session=SESSION):
    from app.validation.data_finality import build_narrow_readiness_attestation

    def verifier(window_start, session_date, tickers, store_identity):
        return _SetSensitiveAdjustment(store_identity, tickers)

    return build_narrow_readiness_attestation(
        store, session, construction=SPEC, adjustment_verifier=verifier,
        reconciliation_artifact_sha256=RECON_SHA, relevance_artifact_sha256=RELEVANCE_SHA,
        quarantine_artifact_sha256=QUARANTINE_SHA, quarantined_identities=QUARANTINED)


def test_a_derived_attestation_is_accepted_by_the_assessment_it_was_derived_from(store):
    """The whole point: one production construction, one relevance set, one census."""
    attestation, record = _derive(store)
    assert attestation.relevance_set_sha256, "the derivation must bind the relevance set"
    assert attestation.expected_status_counts, "the derivation must bind a census"

    def verifier(window_start, session_date, tickers, store_identity):
        return _SetSensitiveAdjustment(store_identity, tickers)

    ev = assess_data_finality(store, SESSION, construction=SPEC, adjustment_verifier=verifier,
                              narrow_readiness=attestation)
    assert _refusals(ev) == []
    assert ev.verdict is DataReadiness.READY_DECISION_VALID_WITH_DISCLOSED_NONDECISION_LIMITATIONS


def test_the_derivation_record_names_everything_the_ruling_requires(store):
    _, record = _derive(store)
    for key in ("session_date", "scoring_universe_n", "proxy_universe_n", "relevance_set_sha256",
                "relevant_identities", "relevant_ticker_count", "expected_status_counts",
                "quarantine_artifact_sha256", "relevance_artifact_sha256",
                "reconciliation_artifact_sha256", "quarantined_identities", "store_identity_sha256"):
        assert key in record, f"the construction record must name {key}"
    assert record["session_date"] == SESSION.isoformat()
    assert record["relevant_ticker_count"] == len(record["relevant_identities"])
    assert record["quarantined_identities"] == sorted(QUARANTINED)


def test_the_derived_census_is_measured_over_the_captured_relevance_set(store):
    """The census and the identity list describe the SAME set — the property whose absence was the
    2026-07-27 defect."""
    attestation, record = _derive(store)
    assert sum(attestation.expected_status_counts.values()) == record["relevant_ticker_count"]
    assert attestation.relevance_set_sha256 == record["relevance_set_sha256"]


def test_an_attestation_derived_over_a_BROADER_set_is_refused_by_the_readiness_run(store):
    """★ THE EXACT 2026-07-27 FAILURE, reproduced. A diagnostic sees more identities, so it measures a
    different census; the readiness path refuses it instead of adopting it."""
    attestation, record = _derive(store)
    # 19 extra identities — the same shape as the real 689-vs-670 divergence.
    broader = record["relevant_ticker_count"] + 19
    diagnostic = NarrowReadinessAttestation(
        session_date=SESSION, reconciliation_artifact_sha256=RECON_SHA,
        relevance_artifact_sha256=RELEVANCE_SHA, quarantine_artifact_sha256=QUARANTINE_SHA,
        relevance_set_sha256="%064x" % (broader * 7919),
        quarantined_identities=QUARANTINED,
        expected_status_counts={"PROVEN_REFLECTED": broader})
    assert diagnostic.relevance_set_sha256 != attestation.relevance_set_sha256

    def verifier(window_start, session_date, tickers, store_identity):
        return _SetSensitiveAdjustment(store_identity, tickers)

    ev = assess_data_finality(store, SESSION, construction=SPEC, adjustment_verifier=verifier,
                              narrow_readiness=diagnostic)
    assert ev.verdict is DataReadiness.NOT_READY_ADJUSTMENT_UNVERIFIED
    assert any("different set of securities" in r for r in _refusals(ev))


def test_the_builder_refuses_when_the_assessment_never_reached_verification(store):
    """No relevance set exists to attest to, so nothing may be emitted."""
    from app.validation.data_finality import DataFinalityError, build_narrow_readiness_attestation

    with pytest.raises(DataFinalityError, match="no relevance set or census"):
        build_narrow_readiness_attestation(
            store, date(2030, 1, 2), construction=SPEC,
            adjustment_verifier=lambda *a: _CensusAdjustment(a[3]),
            reconciliation_artifact_sha256=RECON_SHA, relevance_artifact_sha256=RELEVANCE_SHA,
            quarantine_artifact_sha256=QUARANTINE_SHA)


def test_the_readiness_path_NEVER_derives_its_own_expected_counts():
    """⛔ THE HONESTY CONTROL. An assessment that learned its own expectations would agree with itself
    by construction and clause (8) would prove nothing. The derivation lives in a separate function
    whose output is an artifact, and `assess_data_finality` must never call it."""
    import inspect

    from app.validation import data_finality

    src = inspect.getsource(data_finality.assess_data_finality)
    assert "build_narrow_readiness_attestation" not in src
    assert "NarrowReadinessAttestation(" not in src, (
        "the readiness path must only ever READ the caller's attestation, never construct one")
    assert "expected_status_counts" not in src, (
        "the readiness path must not touch expected counts outside the refusal clauses")
