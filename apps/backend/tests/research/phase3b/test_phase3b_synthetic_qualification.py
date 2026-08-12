"""Synthetic qualification of the mounted Phase 3B execution layer.

Exercises the S0..S11 path through PRE_ACCESS_READY and never crosses into sealed access: every
object here is synthetic and the guard is driven directly.

Non-vacuity is enforced rather than assumed. Every census assertion checks the number of records
EXAMINED alongside the counts, and the edge-case sweep asserts that all fourteen registered cases
were actually exercised. A green run over zero candidates is a harness failure, not a pass.
"""

from __future__ import annotations

import hashlib
import json

import pytest

from app.research.mr002.phase3b import admissibility as A
from app.research.mr002.phase3b import enrichment as E
from app.research.mr002.phase3b import guard as G
from app.research.mr002.phase3b import roster as R
from app.research.mr002.phase3b import states as S
from app.research.mr002.phase3b.gap import GAP_THRESHOLD, GapInputInvalid, economic_gap, gap_cancels


class FakeDecision:
    """The frozen SignalDecisionRecord surface the enricher is allowed to consult."""

    def __init__(self, session: int = 100, payload: dict | None = None):
        self.decision_session = session
        self._payload = payload or {"z": -2.1, "side": "long", "configuration_id": "B"}

    def canonical(self) -> dict:
        return dict(self._payload)

    @property
    def record_identity(self) -> str:
        return hashlib.sha256(json.dumps(self.canonical(), sort_keys=True).encode()).hexdigest()

    def mutate(self) -> None:
        self._payload["z"] = -9.9


def facts(**kw):
    base = dict(requested_execution_session=101, official_open=100.0, close_t=100.0)
    base.update(kw)
    return E.ExecutionFacts(**base)


# --------------------------------------------------------------------------- the gap formula
def test_gap_is_the_registered_construction_not_the_legacy_one():
    """(open + D)/close - 1, never open/adjusted_close - 1."""
    assert economic_gap(99.0, 100.0, 1.0) == pytest.approx(0.0, abs=1e-12)
    # The legacy behaviour would report a 1% gap on the same ex-dividend bar.
    legacy = 99.0 / 100.0 - 1.0
    assert legacy == pytest.approx(-0.01)
    assert economic_gap(99.0, 100.0, 1.0) != pytest.approx(legacy)


def test_ex_dividend_drop_is_not_a_gap_at_the_threshold():
    """A 7% price fall that is entirely a distribution must NOT cancel."""
    gap = economic_gap(93.0, 100.0, 7.0)
    assert gap == pytest.approx(0.0, abs=1e-12)
    assert not gap_cancels(gap)
    # the same fall with no distribution DOES cancel
    assert gap_cancels(economic_gap(93.0, 100.0, 0.0))


def test_gap_threshold_is_frozen_at_six_percent():
    assert GAP_THRESHOLD == 0.06
    assert gap_cancels(economic_gap(106.0, 100.0))
    assert not gap_cancels(economic_gap(105.99, 100.0))


@pytest.mark.parametrize("o,c,d", [(0.0, 100.0, 0.0), (100.0, 0.0, 0.0), (100.0, 100.0, -1.0)])
def test_gap_fails_closed_on_invalid_inputs(o, c, d):
    with pytest.raises(GapInputInvalid):
        economic_gap(o, c, d)


def test_non_finite_gap_cancels_rather_than_passing():
    assert gap_cancels(float("nan"))


# --------------------------------------------------------------------------- edge-case sweep
EDGE_CASES = {
    "no_official_open": (dict(official_open=None), E.STOP_NO_OFFICIAL_OPEN),
    "trading_halt": (dict(halted=True), E.STOP_TRADING_HALT),
    "delisting": (dict(delisted_at_or_before_t_plus_1=True), E.STOP_DELISTING),
    "symbol_or_permsec_transition": (dict(identity_transition=True), E.STOP_IDENTITY_CONFLICT),
    "future_information": (dict(future_information=True), E.FUTURE_INFORMATION),
    "adjusted_vs_unadjusted_open_identity": (dict(open_basis_conflict=True), E.STOP_PRICE_CONFLICT),
    "execution_session_ne_registered_next": (
        dict(actual_source_session=102),
        E.STOP_PRICE_CONFLICT,
    ),
    "calendar_mismatch": (dict(requested_execution_session=105), E.STOP_PRICE_CONFLICT),
    "missing_or_conflicting_open": (dict(close_t=None), E.STOP_PRICE_CONFLICT),
    "merger_consideration": (
        dict(corporate_action_kind="merger", adjusted_open_constructible=False),
        E.STOP_CORPORATE_ACTION,
    ),
    "cash_only_acquisition": (
        dict(corporate_action_kind="cash_only_acquisition", adjusted_open_constructible=False),
        E.STOP_CORPORATE_ACTION,
    ),
    "stock_and_cash_acquisition": (
        dict(corporate_action_kind="stock_and_cash_acquisition", adjusted_open_constructible=False),
        E.STOP_CORPORATE_ACTION,
    ),
    # the two CONDITIONAL cases, false branch
    "dividend_or_distribution__unresolvable": (
        dict(corporate_action_kind="dividend", adjusted_open_constructible=False),
        E.STOP_CORPORATE_ACTION,
    ),
    "split_close_t_to_open_t1__unresolvable": (
        dict(corporate_action_kind="split", adjusted_open_constructible=False),
        E.STOP_CORPORATE_ACTION,
    ),
    # the two CONDITIONAL cases, true branch
    "dividend_or_distribution__resolvable": (
        dict(
            corporate_action_kind="dividend",
            adjusted_open_constructible=True,
            official_open=99.0,
            cash_distribution=1.0,
        ),
        E.SUCCESS,
    ),
    "split_close_t_to_open_t1__resolvable": (
        dict(corporate_action_kind="split", adjusted_open_constructible=True),
        E.SUCCESS,
    ),
}


@pytest.mark.parametrize("name", sorted(EDGE_CASES))
def test_every_registered_edge_case_maps_to_its_frozen_code(name):
    kw, expected = EDGE_CASES[name]
    rec = E.enrich(FakeDecision(), facts(**kw))
    assert rec.ExecutionEnrichmentCode == expected, name
    assert E.CENSUS_CATEGORY[rec.ExecutionEnrichmentCode] == E.CENSUS_CATEGORY[expected]
    assert rec.terminal_treatment == E.TERMINAL_TREATMENT[expected]


def test_edge_case_sweep_is_not_vacuous():
    """The sweep must exercise every registered code that has a frozen trigger."""
    produced = {
        E.enrich(FakeDecision(), facts(**kw)).ExecutionEnrichmentCode
        for kw, _ in EDGE_CASES.values()
    }
    triggerable = set(E.REGISTERED_CODES) - set(E.RESERVED_CODES)
    assert produced == triggerable, f"unexercised: {sorted(triggerable - produced)}"
    assert len(EDGE_CASES) >= 14


def test_source_missing_is_reserved_and_unreachable():
    """R-A2: registered, reserved, expected count zero, and no synthetic input can raise it."""
    assert E.STOP_SOURCE_MISSING in E.REGISTERED_CODES
    assert E.STOP_SOURCE_MISSING in E.RESERVED_CODES
    produced = {
        E.enrich(FakeDecision(), facts(**kw)).ExecutionEnrichmentCode
        for kw, _ in EDGE_CASES.values()
    }
    assert E.STOP_SOURCE_MISSING not in produced


def test_price_conflict_has_its_own_census_category():
    """R-A3: not buried in the catch-all."""
    assert E.CENSUS_CATEGORY[E.STOP_PRICE_CONFLICT] == "price conflict"
    assert E.CENSUS_CATEGORY[E.STOP_PRICE_CONFLICT] != "other registered disposition"


def test_published_surface_is_exactly_the_frozen_ten_fields():
    rec = E.enrich(FakeDecision(), facts())
    assert sorted(rec.schema_surface()) == sorted(
        [
            "decision_record_sha256",
            "decision_session_t",
            "execution_session_t_plus_1",
            "official_open_source_identity",
            "official_open_price_ref",
            "realization_horizon",
            "ExecutionEnrichmentDisposition",
            "ExecutionEnrichmentCode",
            "corporate_action_identity",
            "conservative_short_flag",
        ]
    )
    assert rec.realization_horizon == 6


def test_no_legacy_label_is_ever_published():
    for kw, _ in EDGE_CASES.values():
        rec = E.enrich(FakeDecision(), facts(**kw))
        surface = json.dumps(rec.schema_surface())
        for legacy in ("ADMISSIBLE", "CANCELLED_GAP", "CANCELLED_MISSING_OPEN"):
            assert legacy not in surface


def test_decision_record_mutation_is_detected():
    d = FakeDecision()
    original = E.enrich(d, facts())
    assert original.decision_record_sha256 == d.record_identity

    class Mutating(FakeDecision):
        def __init__(self):
            super().__init__()
            self._n = 0

        @property
        def record_identity(self):
            self._n += 1
            return "before" if self._n <= 1 else "after"

    with pytest.raises(E.DecisionRecordMutated):
        E.enrich(Mutating(), facts())


# --------------------------------------------------------------------------- the guard
def _guard(ready=False):
    return G.ValidationGuard(
        registered_objects={
            G.VALIDATION: {"validation/prices.parquet"},
            G.REFERENCE: {"reference/crosswalk.parquet"},
        },
        pre_access_ready=ready,
    )


def test_oos_is_refused_unconditionally_even_when_ready():
    g = _guard(ready=True)
    with pytest.raises(G.ValidationAccessRefused):
        g.open_object(G.OOS, "oos/prices.parquet", version_id="v")
    assert g.counts()["oos_reads"] == 0
    assert not g.opening_consumed


def test_validation_read_is_refused_before_the_gate():
    g = _guard(ready=False)
    with pytest.raises(G.ValidationAccessRefused):
        g.open_object(G.VALIDATION, "validation/prices.parquet", version_id="v")
    assert not g.opening_consumed
    assert g.counts()["sealed_reads"] == 0


def test_unpinned_validation_read_is_refused():
    g = _guard(ready=True)
    with pytest.raises(G.ValidationAccessRefused):
        g.open_object(G.VALIDATION, "validation/prices.parquet")
    assert not g.opening_consumed


def test_unregistered_object_is_refused():
    g = _guard(ready=True)
    with pytest.raises(G.ValidationAccessRefused):
        g.open_object(G.VALIDATION, "validation/not_registered.parquet", version_id="v")


def test_first_permitted_validation_read_consumes_the_opening_and_chains():
    g = _guard(ready=True)
    assert not g.opening_consumed
    g.open_object(G.VALIDATION, "validation/prices.parquet", version_id="v1")
    assert g.opening_consumed
    assert g.counts()["validation_reads"] == 1
    assert g.chain_verifies()


def test_refused_attempts_are_evidence_not_openings():
    g = _guard(ready=True)
    for _ in range(3):
        with pytest.raises(G.ValidationAccessRefused):
            g.open_object(G.OOS, "oos/prices.parquet", version_id="v")
    c = g.counts()
    assert c["attempts"] == 3 and c["blocked"] == 3 and c["sealed_reads"] == 0
    assert not g.opening_consumed
    assert g.chain_verifies()


# --------------------------------------------------------------------------- the sequence
def _advance_to(seq, target):
    """Advance from wherever the sequence currently is, so repeated calls compose."""
    start = S.SEQUENCE.index(seq.state) + 1
    for st in S.SEQUENCE[start : S.SEQUENCE.index(target) + 1]:
        seq.advance(st)


def test_sequence_refuses_to_skip_states():
    seq = S.LaunchSequence()
    with pytest.raises(S.SequenceViolation):
        seq.advance(S.S7_PRE_ACCESS_READY)


def test_reader_may_be_assumed_only_from_the_gate():
    seq = S.LaunchSequence()
    _advance_to(seq, S.S6_OUTPUTS_PREPARED)
    with pytest.raises(S.SequenceViolation):
        seq.assert_may_assume_reader()
    seq.advance(S.S7_PRE_ACCESS_READY)
    seq.assert_may_assume_reader()


def test_restart_is_free_before_consumption_and_prohibited_after():
    seq = S.LaunchSequence()
    _advance_to(seq, S.S7_PRE_ACCESS_READY)
    seq.assert_may_restart()
    assert seq.restart_disposition() == "PERMITTED_FREE"
    _advance_to(seq, S.S9_OPENING_CONSUMED)
    assert seq.opening_consumed
    with pytest.raises(S.SequenceViolation):
        seq.assert_may_restart()
    assert seq.restart_disposition() == "PROHIBITED_WITHOUT_ADJUDICATION"


def test_everything_that_can_fail_without_cost_precedes_the_gate():
    assert S.SEQUENCE.index(S.GATE) < S.SEQUENCE.index(S.IRREVERSIBLE)
    for st in (
        S.S1_CODE_IDENTITY_VERIFIED,
        S.S2_CONTRACT_IDENTITY_VERIFIED,
        S.S3_CONFIG_BOUND,
        S.S4_RUNTIME_VERIFIED,
        S.S5_INPUTS_STAGED,
        S.S6_OUTPUTS_PREPARED,
    ):
        assert S.SEQUENCE.index(st) < S.SEQUENCE.index(S.GATE)


# --------------------------------------------------------------------------- the roster
def test_roster_enumerates_and_verifies_itself():
    bound = R.current_roster()
    detail = R.verify(bound)
    assert detail["layer_modules"] >= 6
    assert detail["producer_modules"] == 15
    assert detail["drift"] == 0


def test_roster_refuses_digest_drift():
    bound = R.current_roster()
    bound["producer"]["producer.py"] = "0" * 64
    with pytest.raises(R.RosterRefused, match="drift"):
        R.verify(bound)


def test_roster_refuses_a_missing_module():
    bound = R.current_roster()
    bound["layer"]["invented_module.py"] = "0" * 64
    with pytest.raises(R.RosterRefused, match="missing"):
        R.verify(bound)


def test_roster_refuses_an_unbound_module_present():
    bound = R.current_roster()
    bound["layer"].pop("gap.py")
    with pytest.raises(R.RosterRefused, match="unbound module present"):
        R.verify(bound)


def test_producer_roster_is_the_fifteen_bound_modules():
    assert len(R.PRODUCER_MODULES) == 15
    assert "models.py" in R.PRODUCER_MODULES


# --------------------------------------------------------------------------- entry adjudication
def test_gap_cancellation_is_success_plus_not_admissible_never_an_enrichment_stop():
    """Owner ruling: a well-formed over-threshold gap is an ENTRY outcome, not enrichment failure."""
    f = facts(official_open=108.0, close_t=100.0)
    rec = E.enrich(FakeDecision(), f)
    adj = A.adjudicate_entry(rec, f)
    assert rec.ExecutionEnrichmentCode == E.SUCCESS
    assert adj.entry_admissible is False
    assert adj.outcome == A.NOT_ADMITTED_GAP
    assert adj.economic_gap == pytest.approx(0.08)


def test_admissibility_fields_are_not_on_the_frozen_record():
    """R-U1: the ten-field surface gains no eleventh or twelfth field."""
    rec = E.enrich(FakeDecision(), facts())
    assert not hasattr(rec, "entry_admissible")
    assert not hasattr(rec, "economic_gap")
    assert len(rec.schema_surface()) == 10


def test_ex_dividend_candidate_remains_admissible():
    f = facts(official_open=93.0, close_t=100.0, cash_distribution=7.0)
    rec = E.enrich(FakeDecision(), f)
    adj = A.adjudicate_entry(rec, f)
    assert rec.ExecutionEnrichmentCode == E.SUCCESS
    assert adj.entry_admissible is True and adj.outcome == A.ADMITTED


def test_failed_enrichment_is_not_adjudicated_rather_than_defaulted_false():
    f = facts(halted=True)
    rec = E.enrich(FakeDecision(), f)
    adj = A.adjudicate_entry(rec, f)
    assert adj.entry_admissible is None
    assert adj.outcome == A.NOT_ADJUDICATED
