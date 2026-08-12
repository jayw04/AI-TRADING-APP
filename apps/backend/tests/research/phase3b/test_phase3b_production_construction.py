"""Production construction of the inputs the tests used to inject.

Every object here is built from a committed source column - universe, crosswalk, anchors - rather
than handed in by a fixture. That is the gap that let the real-adapter end-to-end pass while the
package could not actually run: the adapter was real, its inputs were not.
"""

from __future__ import annotations

import pytest

pa = pytest.importorskip("pyarrow")

from app.research.mr002.phase3b import candidates as CS  # noqa: E402
from app.research.mr002.phase3b.earnings_blackout import (  # noqa: E402
    BLACKOUT_RULE_ID,
    COOLING_RULE_ID,
    Calendar,
    earnings_exclusion_checks,
)
from app.research.mr002.spq1.calendar import RegisteredCalendar  # noqa: E402
from app.research.mr002.spq1.eligibility import evaluate_eligibility  # noqa: E402

SESSIONS = [
    "2013-01-02",
    "2013-01-03",
    "2013-01-04",
    "2013-01-07",
    "2013-01-08",
    "2013-02-01",
    "2013-02-04",
    "2013-02-05",
    "2013-02-06",
    "2013-02-07",
]
CAL = RegisteredCalendar(tuple(SESSIONS))


def _universe(rows):
    return pa.table(
        {
            "universe_month": [r[0] for r in rows],
            "ticker": [r[1] for r in rows],
            "permaticker": [r[2] for r in rows],
            "siccode": [3571 for _ in rows],
            "liquidity_rank": [1 for _ in rows],
            "med_dv_60": [1e9 for _ in rows],
            "in_long_universe": [r[3] for r in rows],
            "in_short_universe": [r[4] for r in rows],
        }
    )


def _crosswalk(rows):
    return pa.table(
        {
            "permaticker": [r[0] for r in rows],
            "ticker": [r[1] for r in rows],
            "cik": [r[2] for r in rows],
            "effective_from": [r[3] for r in rows],
            "effective_to": [None for _ in rows],
            "relationship_type": ["ticker_rename" for _ in rows],
            "source": ["fixture" for _ in rows],
            "source_record_id": ["x" for _ in rows],
            "confidence": ["high" for _ in rows],
            "mapping_rationale": ["fixture" for _ in rows],
            "review_status": ["auto" for _ in rows],
        }
    )


def _anchors(rows):
    return pa.table(
        {
            "ticker": [r[0] for r in rows],
            "cik": [r[1] for r in rows],
            "accession": [r[2] for r in rows],
            "session_date": [r[3] for r in rows],
            "availability_class": [r[4] for r in rows],
            "is_amendment_origin": [False for _ in rows],
            "acceptance_utc": [r[5] for r in rows],
        }
    )


# --------------------------------------------------------------------- units from the universe
def test_units_are_enumerated_per_session_and_per_side():
    table = _universe([("2013-01-01", "AAA", 1, True, True), ("2013-01-01", "BBB", 2, True, False)])
    units = CS.units_from_universe(table, CAL)
    january = [s for s in SESSIONS if s.startswith("2013-01")]
    assert len(units) == len(january) * 2 + len(january) * 1
    assert {u.side for u in units} == {"LONG", "SHORT"}
    assert {u.symbol for u in units} == {"AAA", "BBB"}
    assert all(0 <= u.t < len(SESSIONS) for u in units)


def test_a_security_on_neither_side_produces_no_unit():
    table = _universe([("2013-01-01", "AAA", 1, False, False)])
    with pytest.raises(CS.CandidateSourceRefused, match="enumerated no units"):
        CS.units_from_universe(table, CAL)


def test_membership_applies_only_to_its_reconstitution_month():
    table = _universe([("2013-02-01", "AAA", 1, True, False)])
    units = CS.units_from_universe(table, CAL)
    assert {SESSIONS[u.t][:7] for u in units} == {"2013-02"}


def test_units_are_canonically_ordered():
    table = _universe(
        [("2013-01-01", "BBB", 2, True, False), ("2013-01-01", "AAA", 1, True, False)]
    )
    units = CS.units_from_universe(table, CAL)
    assert units == sorted(units, key=lambda u: (u.symbol, u.t, u.side))


def test_a_universe_missing_a_registered_column_is_refused():
    with pytest.raises(CS.CandidateSourceRefused, match="registered columns absent"):
        CS.units_from_universe(pa.table({"ticker": ["AAA"]}), CAL)


# --------------------------------------------------------------------- identity from crosswalk
def test_an_ambiguous_symbol_is_left_unresolved_not_arbitrated():
    table = _crosswalk([(1, "AAA", 111, "2013-01-02"), (2, "AAA", 222, "2013-01-03")])
    resolved = CS.cik_by_symbol_from(table)
    assert "AAA" not in resolved.by_symbol, "an ambiguous symbol must never be silently picked"
    assert resolved.ambiguous == ("AAA",)


def test_an_unambiguous_symbol_resolves():
    table = _crosswalk([(1, "AAA", 111, "2013-01-02"), (1, "AAA", 111, "2013-01-03")])
    resolved = CS.cik_by_symbol_from(table)
    assert resolved.by_symbol == {"AAA": 111} and resolved.ambiguous == ()


def test_lineage_admits_an_interval_opening_inside_the_window():
    """The first implementation dropped these silently; the ordinal must be found by search."""
    table = _crosswalk([(7, "AAA", 111, "2013-02-04")])
    lineage = CS.lineage_from(table, CAL)
    record = lineage.lineage["AAA"][0]
    assert record.effective_session_ordinal == SESSIONS.index("2013-02-04")
    assert lineage.resolve_permanent_id("AAA", SESSIONS.index("2013-02-05")) == "PSEC-7"


def test_lineage_interval_opening_before_the_window_starts_at_ordinal_zero():
    table = _crosswalk([(7, "AAA", 111, "2002-07-22")])
    lineage = CS.lineage_from(table, CAL)
    assert lineage.lineage["AAA"][0].effective_session_ordinal == 0


def test_lineage_interval_opening_after_the_window_is_dropped():
    table = _crosswalk([(7, "AAA", 111, "2099-01-01")])
    with pytest.raises(CS.CandidateSourceRefused, match="no lineage records"):
        CS.lineage_from(table, CAL)


# --------------------------------------------------------------------- anchors to eligibility
def test_anchors_are_grouped_with_their_availability_timestamps():
    table = _anchors([("AAA", 111, "acc1", "2013-01-03", "PRE_OPEN", "2013-01-03T12:00:00Z")])
    by_symbol, availability = CS.anchors_by_symbol(table)
    assert [a.accession for a in by_symbol["AAA"]] == ["acc1"]
    assert availability["acc1"] == "2013-01-03T12:00:00Z"


def test_an_anchor_without_an_acceptance_timestamp_is_refused():
    table = _anchors([("AAA", 111, "acc1", "2013-01-03", "PRE_OPEN", None)])
    with pytest.raises(CS.CandidateSourceRefused, match="no acceptance timestamp"):
        CS.anchors_by_symbol(table)


def test_the_constructed_checks_actually_make_a_unit_ineligible():
    """End of the chain: anchors table -> checks -> evaluate_eligibility says INELIGIBLE."""
    table = _anchors([("AAA", 111, "acc1", "2013-01-04", "PRE_OPEN", "2013-01-04T12:00:00Z")])
    by_symbol, availability = CS.anchors_by_symbol(table)
    cal = Calendar(tuple(SESSIONS))
    cutoff = "2013-12-31T20:00:00Z"

    blocked_t = SESSIONS.index("2013-01-04") - 1  # decision t whose t+1 open is prohibited
    checks = earnings_exclusion_checks(by_symbol["AAA"], cal, blocked_t, availability)
    assert {c.rule_id for c in checks} == {COOLING_RULE_ID, BLACKOUT_RULE_ID}
    assert evaluate_eligibility(checks, cutoff).status != "ELIGIBLE"

    clear_t = SESSIONS.index("2013-01-08")
    clear = earnings_exclusion_checks(by_symbol["AAA"], cal, clear_t, availability)
    assert evaluate_eligibility(clear, cutoff).status == "ELIGIBLE"


def test_the_two_controls_remain_separately_attributable_through_the_checks():
    table = _anchors([("AAA", 111, "acc1", "2013-01-04", "PRE_OPEN", "2013-01-04T12:00:00Z")])
    by_symbol, availability = CS.anchors_by_symbol(table)
    cal = Calendar(tuple(SESSIONS))
    # t=2 -> execution open ordinal 3, inside the PRE_OPEN cooling window (opens 2 and 3).
    # The 70-day blackout starts 2013-03-15, beyond this fixture calendar, so it cannot fire.
    checks = earnings_exclusion_checks(by_symbol["AAA"], cal, 2, availability)
    by_rule = {c.rule_id: c for c in checks}
    assert by_rule[COOLING_RULE_ID].excludes is True
    assert by_rule[BLACKOUT_RULE_ID].excludes is False
    assert by_rule[COOLING_RULE_ID].precedence_category == "event_blackout"
    assert by_rule[BLACKOUT_RULE_ID].precedence_category == "event_blackout"
