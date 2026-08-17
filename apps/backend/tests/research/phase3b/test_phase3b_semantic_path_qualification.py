"""Semantic-path qualification for the v3.5 bridge repair.

This suite exists because three governed openings were spent on pre-research refusals, each one
triggered by a corporate-action row whose economics had no bearing on the run it aborted. Scale was
never the problem; semantic coverage was. So nothing here is about volume - every case drives the
REAL bridge (real-typed parquet -> decode -> candidate construction -> _facts() -> enrichment) and
asks one question the previous suites never asked: what does this row DO?

Frozen by MR002_Phase3B_SemanticReconciliationMatrix_v1.1 (95ae21ba...) and
MR002_Phase3B_UnitRefusalGovernance_v1.0/v1.1 (d03ae667... / 1a557a64...); section 10 by
MR002_Phase3B_LabelAdjudication_v2.0 (5647549e...) / SemanticReconciliationMatrix_v1.3 (865064f5...).
"""

from __future__ import annotations

import pytest

pa = pytest.importorskip("pyarrow")

from app.research.mr002.phase3b import candidates as CS  # noqa: E402
from app.research.mr002.phase3b import enrichment as E  # noqa: E402
from app.research.mr002.phase3b import publish as P  # noqa: E402
from app.research.mr002.phase3b.guard import VALIDATION  # noqa: E402
from app.research.mr002.phase3b.readers import FixtureReader, PinnedObject  # noqa: E402
from tests.research.phase3b import fixtures_producer as F  # noqa: E402
from tests.research.phase3b.test_phase3b_real_adapter_e2e import (  # noqa: E402
    CAL,
    REFERENCE_TABLES,
    VALIDATION_TABLES,
    _arrow_tables,
    _d,
    _manifest,
    _payload,
    _registry,
    _runner,
    _units,
)

SUBJECT = "HEALTHY"  # the fixture security that reaches SUCCESS, so a change of outcome is visible
T1 = F.SESSIONS[F.SCORE_T + 1]  # the only session a unit's actions are read from
# A row on a ticker no unit names. It keeps the ACTIONS table non-empty so the P9 date-bound
# commitment is still constructible, and it doubles as proof that an irrelevant row does nothing -
# which is the property that would have saved the third opening.
IRRELEVANT = (T1, "NOT_A_UNIT", "dividend", 0.1)


def _actions(rows: list[tuple[str, str, str, float | None]]):
    """An ACTIONS table with real DATE typing, as the sealed partition declares it."""
    return pa.table(
        {
            "date": _d([r[0] for r in rows]),
            "ticker": [r[1] for r in rows],
            "action": [r[2] for r in rows],
            "value": [r[3] for r in rows],
        }
    )


def _world(tmp_path, action_rows):
    """The real-adapter world with a substituted ACTIONS table, written as real parquet."""
    import hashlib

    tables = _arrow_tables()
    tables["actions"] = _actions(action_rows)
    root = tmp_path / "fixtures"
    objects: list[PinnedObject] = []
    for prefix, names in (("validation", VALIDATION_TABLES), ("reference", REFERENCE_TABLES)):
        for name in names:
            payload = _payload(tables[name])
            path = root / prefix / f"{name}.parquet"
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(payload)
            objects.append(
                PinnedObject(
                    "workbench-mr002-sealed-219024422756",
                    f"{prefix}/{name}.parquet",
                    f"ver-{prefix}-{name}",
                    hashlib.sha256(payload).hexdigest(),
                )
            )
    return tables, str(root), objects


def _source(tmp_path, action_rows, *, cik_by_symbol=None):
    tables, froot, objects = _world(tmp_path, action_rows)
    source = CS.ProducerCandidateSource(
        calendar=CAL,
        units=_units(),
        lineage=F.lineage_registry(),
        cik_by_symbol=dict(cik_by_symbol if cik_by_symbol is not None else F.CIK_BY_SYMBOL),
        registry=_registry(),
        observed_identities=dict(F.OBSERVED_IDENTITIES),
        spy_ticker=F.SPY,
        structural_manifest=_manifest(tables, VALIDATION_TABLES),
        reference_manifest=_manifest(tables, REFERENCE_TABLES),
        eligibility_checks_by_symbol={},
    )
    reader = FixtureReader(froot)
    payloads = {o.key: reader.read(o) for o in objects}
    return source, payloads


def _outcome_for(source, payloads, symbol=SUBJECT):
    """Drive the real path and return the enrichment code for one symbol, or None if refused."""
    pairs = source.candidates(payloads)
    for decision, facts in pairs:
        if facts.official_open_source_identity and f":{symbol}:" in (
            facts.official_open_source_identity
        ):
            return E.enrich(decision, facts).ExecutionEnrichmentCode, facts
    return None, None


def _bridge_refusals(source, symbol=SUBJECT):
    return [r for r in source.refusals if r[0] == symbol and r[2] in CS.BRIDGE_REFUSAL_CODES]


# --------------------------------------------------------------- 1. ticker-rename continuity
def test_a_ticker_change_pair_no_longer_refuses_and_has_no_economic_effect(tmp_path):
    """The exact shape that spent the third opening: two ticker-change rows on one session.

    Both are upstream lineage metadata, consumed by the crosswalk before a candidate exists. They
    must not reach the economic scalar, must not be published as an audit identity, and must not
    refuse anything.
    """
    source, payloads = _source(
        tmp_path,
        [(T1, SUBJECT, "tickerchangefrom", None), (T1, SUBJECT, "tickerchangeto", None)],
    )
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind is None
    assert facts.corporate_action_identity is None
    assert not _bridge_refusals(source)


# --------------------------------------------------------------- 2-3. governed delisting
def test_a_delisting_on_t_plus_1_stops_the_record(tmp_path):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "delisted", None)])
    code, facts = _outcome_for(source, payloads)
    assert code == E.STOP_DELISTING
    assert facts.delisted_at_or_before_t_plus_1 is True
    # Channel 2 is exclusive - a delisting never becomes the economic scalar.
    assert facts.corporate_action_kind is None
    # ...but it stays audit-visible, and names the action that actually drove the disposition.
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:delisted"


def test_the_delisting_rule_is_at_or_before_not_equality(tmp_path):
    """`dataset.py:303` applies ``ad <= d``. A delisting BEFORE t+1 still governs t+1."""
    earlier = F.SESSIONS[F.SCORE_T - 1]
    source, payloads = _source(tmp_path, [(earlier, SUBJECT, "delisted", None)])
    code, facts = _outcome_for(source, payloads)
    assert facts.delisted_at_or_before_t_plus_1 is True
    assert code == E.STOP_DELISTING


def test_a_delisting_after_t_plus_1_does_not_reach_back(tmp_path):
    later = F.SESSIONS[F.SCORE_T + 2]
    source, payloads = _source(tmp_path, [(later, SUBJECT, "delisted", None)])
    code, facts = _outcome_for(source, payloads)
    assert facts.delisted_at_or_before_t_plus_1 is False
    assert code == E.SUCCESS


def test_acquisitionby_plus_delisted_no_longer_conflicts(tmp_path):
    """77 development sessions carry this pair. It used to abort the whole run.

    Each kind now goes to its own channel, so there is nothing to compose and nothing to refuse.
    """
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "acquisitionby", None), (T1, SUBJECT, "delisted", None)]
    )
    code, facts = _outcome_for(source, payloads)
    assert not _bridge_refusals(source)
    assert code == E.STOP_DELISTING  # delisting outranks corporate action in the frozen precedence
    assert facts.corporate_action_kind == "acquisitionby"  # still the economic scalar
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:delisted"


# --------------------------------------------------------------- 4. inert: visible, effectless
@pytest.mark.parametrize("kind", sorted(CS.EXPLICITLY_INERT))
def test_an_inert_kind_is_audit_visible_but_has_no_economic_effect(tmp_path, kind):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, kind, None)])
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS, f"{kind} must not change the outcome"
    assert facts.corporate_action_kind is None, f"{kind} must not become the economic scalar"
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:{kind}"
    assert not _bridge_refusals(source)


def test_an_inert_kind_beside_an_economic_one_creates_no_conflict(tmp_path):
    """'Inert' cannot mean 'no economic effect but still causes economic conflict'."""
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "spunofffrom", None), (T1, SUBJECT, "dividend", 0.40)]
    )
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind == "dividend"
    assert not _bridge_refusals(source)


# --------------------------------------------------------------- 5-6. the two vocabulary states
def test_an_unknown_kind_refuses_the_unit_and_not_the_run(tmp_path):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "no_such_vendor_action", None)])
    pairs = source.candidates(payloads)
    refusals = _bridge_refusals(source)
    assert refusals, "the unit must refuse"
    assert {r[2] for r in refusals} == {CS.REFUSED_ACTION_KIND}
    assert {r[3] for r in refusals} == {CS.VOCAB_UNKNOWN}
    # The decisive property: OTHER securities still produced candidates.
    assert pairs, "an unknown kind on one symbol must not abort independent units"
    assert not any(f":{SUBJECT}:" in (f.official_open_source_identity or "") for _d, f in pairs)


@pytest.mark.parametrize("kind", sorted(CS.KNOWN_UNADJUDICATED))
def test_a_known_unadjudicated_kind_refuses_the_unit_with_its_own_state(tmp_path, kind):
    """listed / bankruptcyliquidation are feed-present and unadjudicated.

    They are NOT aliased to their look-alikes: bankruptcyliquidation is not bankruptcy. Name
    similarity is not adjudication. (`relation` and `spinoff` left this set under
    LabelAdjudication v2.0 - section 10 below covers their adjudicated behaviour.)
    """
    source, payloads = _source(tmp_path, [(T1, SUBJECT, kind, None)])
    source.candidates(payloads)
    refusals = _bridge_refusals(source)
    assert {r[3] for r in refusals} == {CS.VOCAB_KNOWN_UNADJUDICATED}


def test_the_two_vocabulary_states_are_distinguishable_in_the_census(tmp_path):
    """The gates treat these two irreconcilably, so the census must key them apart.

    One unit is inspected per security here, so the two states are driven through separate runs -
    which is also the honest shape: what must differ is the census KEY, not one run's tally.
    """
    keys = []
    for i, kind in enumerate(["listed", "no_such_vendor_action"]):
        source, payloads = _source(tmp_path / f"case{i}", [(T1, SUBJECT, kind, None)])
        source.candidates(payloads)
        census = source.refusal_census()
        keys.append(sorted(census["units_bridge_refused_by_code_and_vocabulary_state"]))
    assert keys[0] == [f"{CS.REFUSED_ACTION_KIND}|{CS.VOCAB_KNOWN_UNADJUDICATED}"]
    assert keys[1] == [CS.UNKNOWN_VOCABULARY_REASON]
    assert keys[0] != keys[1]


# --------------------------------------------------------------- 7. no composition
def test_two_differing_economic_kinds_refuse_the_unit(tmp_path):
    """dividend+split occurs in the development window. No ordering or combined return is invented."""
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "dividend", 0.40), (T1, SUBJECT, "split", None)]
    )
    pairs = source.candidates(payloads)
    assert {r[2] for r in _bridge_refusals(source)} == {CS.REFUSED_ACTION_COMPOSITION}
    assert pairs, "independent units continue"


def test_the_same_economic_kind_twice_is_not_a_conflict(tmp_path):
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "dividend", 0.25), (T1, SUBJECT, "dividend", 0.15)]
    )
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS
    assert facts.cash_distribution == pytest.approx(0.40), "two distributions are two distributions"


# --------------------------------------------------------------- 10. adjudicated 2026-08-17
# LabelAdjudication v2.0 (5647549e...) / SemanticReconciliationMatrix v1.3 (865064f5...): `relation`
# is informational linkage (channel 3 only), and spinoff+spinoffdividend are ONE composite event.
def test_relation_alone_is_audit_visible_but_has_no_effect(tmp_path):
    """Informational issuer/security linkage: no scalar, no refusal, channel-3 identity only."""
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "relation", None)])
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind is None
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:relation"
    assert not _bridge_refusals(source)


def test_relation_contributes_no_identity_precedence(tmp_path):
    """A linkage beside an economic action neither conflicts nor displaces its identity."""
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "relation", None), (T1, SUBJECT, "dividend", 0.40)]
    )
    code, facts = _outcome_for(source, payloads)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind == "dividend"
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:dividend"
    assert not _bridge_refusals(source)


def test_a_populated_relation_value_reverts_the_unit_to_unadjudicated(tmp_path):
    """RELATION-VALUE-PREMISE: 0/98 in the bounded evidence; a populated value is outside the
    adjudicated premise and must fail closed rather than be silently reinterpreted."""
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "relation", 1.0)])
    pairs = source.candidates(payloads)
    refusals = _bridge_refusals(source)
    assert {r[2] for r in refusals} == {CS.REFUSED_ACTION_KIND}
    assert {r[3] for r in refusals} == {CS.VOCAB_KNOWN_UNADJUDICATED}
    assert pairs, "independent units continue"


def test_the_spinoff_pair_is_one_composite_event_not_a_conflict(tmp_path):
    """65/75 bounded spinoffs carry both records: one event in two denominations, not a conflict.

    The structural kind is the scalar and the identity. The dollar value does NOT enter the
    registered distribution term - owner correction 2026-08-17 (Corrigendum v1.0): whether it is
    cash actually received or a valuation of distributed stock is the OPEN SPINOFF-GAP-SEMANTICS
    finding, and the frozen gap economics do not change on an implementation inference.
    """
    source, payloads = _source(
        tmp_path, [(T1, SUBJECT, "spinoff", 0.25), (T1, SUBJECT, "spinoffdividend", 3.81)]
    )
    code, facts = _outcome_for(source, payloads)
    assert not _bridge_refusals(source)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind == "spinoff"
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:spinoff"
    assert facts.cash_distribution == 0.0, "spinoffdividend value must NOT reach the gap term"


def test_a_spinoff_without_a_dollar_value_is_valid_and_unadjusted(tmp_path):
    """10/75 bounded spinoffs publish no dollar value: 'value unavailable', never 'event invalid'.
    The ratio is NEVER summed into the distribution term."""
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "spinoff", 0.25)])
    code, facts = _outcome_for(source, payloads)
    assert not _bridge_refusals(source)
    assert code == E.SUCCESS
    assert facts.corporate_action_kind == "spinoff"
    assert facts.cash_distribution == 0.0


def test_spinoffdividend_alone_is_unresolved_composition(tmp_path):
    """A value component without its structural event - zero observed in the bounded window -
    refuses the unit rather than being consumed as a free-standing action."""
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "spinoffdividend", 3.81)])
    pairs = source.candidates(payloads)
    assert {r[2] for r in _bridge_refusals(source)} == {CS.REFUSED_ACTION_COMPOSITION}
    assert pairs, "independent units continue"


def test_the_spinoff_composite_beside_another_economic_kind_still_refuses(tmp_path):
    """The composite is the ONLY authorized composition - spinoff+split (dev census x4) still
    refuses. No general composition rule exists."""
    source, payloads = _source(
        tmp_path,
        [
            (T1, SUBJECT, "spinoff", 0.25),
            (T1, SUBJECT, "spinoffdividend", 3.81),
            (T1, SUBJECT, "split", 2.0),
        ],
    )
    source.candidates(payloads)
    assert {r[2] for r in _bridge_refusals(source)} == {CS.REFUSED_ACTION_COMPOSITION}


def test_delisting_still_outranks_the_spinoff_composite(tmp_path):
    """AUDIT-IDENTITY-PRECEDENCE is unchanged for the first three classes."""
    source, payloads = _source(
        tmp_path,
        [
            (T1, SUBJECT, "spinoff", 0.25),
            (T1, SUBJECT, "spinoffdividend", 3.81),
            (T1, SUBJECT, "delisted", None),
        ],
    )
    code, facts = _outcome_for(source, payloads)
    assert code == E.STOP_DELISTING
    assert facts.corporate_action_kind == "spinoff"
    assert facts.corporate_action_identity == f"actions:{SUBJECT}:{T1}:delisted"


# --------------------------------------------------------------- 8. identity at unit scope
def test_an_unresolved_cik_refuses_the_unit_and_not_the_run(tmp_path):
    """The latent whole-run abort found while freezing v1.1, now frozen as a unit condition."""
    partial = {k: v for k, v in F.CIK_BY_SYMBOL.items() if k != SUBJECT}
    source, payloads = _source(tmp_path, [IRRELEVANT], cik_by_symbol=partial)
    pairs = source.candidates(payloads)
    assert {r[2] for r in _bridge_refusals(source)} == {CS.REFUSED_IDENTITY}
    assert pairs, "one unresolvable symbol must not abort the run"


# --------------------------------------------------------------- 9. upstream controls still live
def test_future_information_mutation_still_raises(tmp_path):
    """Unchanged and must stay so: the protection operates BY EXCEPTION, not via a boolean."""

    class Mutating:
        record_identity = "a" * 64
        decision_session = F.SCORE_T

        def canonical(self):
            self.record_identity = "b" * 64
            return {"n": self.record_identity}

    with pytest.raises(E.DecisionRecordMutated, match="FUTURE_INFORMATION"):
        E.enrich(Mutating(), E.ExecutionFacts(requested_execution_session=F.SCORE_T + 1))


def test_a_missing_registered_column_still_refuses_the_whole_run(tmp_path):
    """Global integrity is unchanged: schema corruption is not a per-unit condition."""
    with pytest.raises(CS.CandidateSourceRefused, match="registered columns absent"):
        CS.cash_distributions(pa.table({"date": ["2013-01-02"]}))


# --------------------------------------------------------------- census + materiality gates
def test_the_reconciliation_identity_balances_and_counts_both_kinds_of_refusal(tmp_path):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "listed", None)])
    source.candidates(payloads)
    census = source.refusal_census()
    assert census["reconciliation"]["balances"] is True
    assert (
        census["units_enumerated"]
        == census["units_producer_refused"]
        + census["units_bridge_refused"]
        + census["units_accepted"]
    )
    assert census["eligible_candidate_units"] == (
        census["units_enumerated"] - census["units_producer_refused"]
    )
    assert census["units_bridge_refused"] >= 1
    assert census["observed_action_vocabulary"] == ["listed"]


def test_an_unregistered_kind_breaches_its_gate_at_incidence_one(tmp_path):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "no_such_vendor_action", None)])
    source.candidates(payloads)
    census = source.refusal_census()
    gate = census["materiality_gate_results_by_reason"][CS.UNKNOWN_VOCABULARY_REASON]
    assert gate["breached"] is True
    assert gate["max_incidence"] == 0
    assert gate["unregistered_kinds_observed"] == ["no_such_vendor_action"]
    assert census["any_materiality_gate_breached"] is True
    assert census["unregistered_action_kinds_observed"] == ["no_such_vendor_action"]


def test_a_clean_run_breaches_nothing(tmp_path):
    source, payloads = _source(tmp_path, [(T1, SUBJECT, "dividend", 0.40)])
    source.candidates(payloads)
    census = source.refusal_census()
    assert census["any_materiality_gate_breached"] is False
    assert census["unregistered_action_kinds_observed"] == []


def test_the_gate_is_a_disjunction_of_fraction_and_symbol_count():
    """Either condition alone breaches. Frozen: >1% OR >5 symbols for the 1%/5 reasons."""
    reason = CS.REFUSED_ACTION_COMPOSITION

    # Symbol count alone: 6 symbols out of a large population is far under 1%.
    by_reason = {reason: 6}
    symbols = {reason: {f"SYM{i}" for i in range(6)}}
    gates = CS.ProducerCandidateSource._evaluate_gates(10_000, by_reason, symbols, [])
    assert gates[reason]["fraction"] < 0.01 and gates[reason]["breached"] is True

    # Fraction alone: 2 units of 100 is 2%, but only 2 symbols.
    by_reason = {reason: 2}
    symbols = {reason: {"A", "B"}}
    gates = CS.ProducerCandidateSource._evaluate_gates(100, by_reason, symbols, [])
    assert gates[reason]["unique_symbols"] <= 5 and gates[reason]["breached"] is True

    # Neither: at the boundary, which is NOT a breach - the predicate is strictly greater-than.
    by_reason = {reason: 1}
    symbols = {reason: {"A"}}
    gates = CS.ProducerCandidateSource._evaluate_gates(100, by_reason, symbols, [])
    assert gates[reason]["fraction"] == pytest.approx(0.01) and gates[reason]["breached"] is False


def test_identity_carries_the_larger_frozen_ceiling():
    gates = CS.ProducerCandidateSource._evaluate_gates(
        1000, {CS.REFUSED_IDENTITY: 15}, {CS.REFUSED_IDENTITY: {f"S{i}" for i in range(8)}}, []
    )
    result = gates[CS.REFUSED_IDENTITY]
    assert result["max_fraction"] == 0.02 and result["max_unique_symbols"] == 10
    assert result["breached"] is False, "1.5% over 8 symbols is inside the identity ceiling"


# --------------------------------------------------------------- evidence admissibility
def test_a_gate_breach_completes_the_run_but_makes_the_evidence_inadmissible(tmp_path):
    """COMPLETED + FAIL + inadmissible is the legitimate combination, not a contradiction.

    The opening is spent either way. What the gate decides is whether the population it bought may
    be read as a research result.
    """
    # Build the runner FIRST: its own `_world` writes the default fixtures to the same root, so
    # substituting the ACTIONS table before that would simply be overwritten.
    runner = _runner(tmp_path, out_name="out-breach")
    tables, froot, objects = _world(tmp_path, [(T1, SUBJECT, "no_such_vendor_action", None)])
    runner.reader = FixtureReader(froot)
    # The pinned checksums must follow the substituted bytes, or the reader refuses before the
    # gate is ever reached - which would prove the pin works, not the gate.
    runner.inputs = objects
    runner.registered_objects = {VALIDATION: {o.key for o in objects}}
    runner.candidate_source = CS.ProducerCandidateSource(
        calendar=CAL,
        units=_units(),
        lineage=F.lineage_registry(),
        cik_by_symbol=dict(F.CIK_BY_SYMBOL),
        registry=_registry(),
        observed_identities=dict(F.OBSERVED_IDENTITIES),
        spy_ticker=F.SPY,
        structural_manifest=_manifest(tables, VALIDATION_TABLES),
        reference_manifest=_manifest(tables, REFERENCE_TABLES),
        eligibility_checks_by_symbol={},
    )
    outcome = runner.run()
    assert outcome.execution_status == "COMPLETED"
    assert outcome.qualification_status == P.FAIL
    assert outcome.evidence_admissible is False
    assert outcome.disposition == P.FAIL
    assert outcome.exit_code == P.EXIT_BY_DISPOSITION[P.FAIL]
    assert outcome.opening_consumed, "a breach does not un-spend the opening"
    assert outcome.refusal_census["any_materiality_gate_breached"] is True


def test_a_clean_run_is_admissible_and_publishes_the_census(tmp_path):
    runner = _runner(tmp_path, out_name="out-clean")
    outcome = runner.run()
    assert outcome.disposition == P.PASS, outcome.error
    assert outcome.execution_status == "COMPLETED"
    assert outcome.qualification_status == P.PASS
    assert outcome.evidence_admissible is True
    assert "ValidationUnitRefusalCensus_v1.0.json" in outcome.deliverable_hashes


def test_a_source_without_the_census_is_refused(tmp_path):
    """An absent accounting would publish as 'nothing was refused'. Fail closed instead."""

    class NoCensus:
        def candidates(self, payloads):  # noqa: ANN001
            return []

    runner = _runner(tmp_path, out_name="out-nocensus")
    runner.candidate_source = NoCensus()
    outcome = runner.run()
    assert outcome.disposition == P.REFUSED
    assert "mandatory unit-refusal census" in (outcome.error or "")


def test_every_bridge_refusal_code_is_reachable(tmp_path):
    """No registered code may be unreachable - an unreachable refusal proves nothing."""
    reached = set()
    cases = [
        ([(T1, SUBJECT, "no_such_vendor_action", None)], None),
        ([(T1, SUBJECT, "dividend", 0.4), (T1, SUBJECT, "split", None)], None),
        ([IRRELEVANT], {k: v for k, v in F.CIK_BY_SYMBOL.items() if k != SUBJECT}),
    ]
    for rows, ciks in cases:
        source, payloads = _source(tmp_path / str(len(reached)), rows, cik_by_symbol=ciks)
        source.candidates(payloads)
        reached.update(r[2] for r in source.refusals if r[2] in CS.BRIDGE_REFUSAL_CODES)
    assert reached == set(CS.BRIDGE_REFUSAL_CODES)
