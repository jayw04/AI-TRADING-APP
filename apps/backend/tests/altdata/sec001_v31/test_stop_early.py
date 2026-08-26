"""Stop-early: the sealed rule is not "fetch 452 then look"."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.altdata.sec001_v31.bindings import (
    ClassIdentityLink,
    FirstHopAdmissionPolicy,
    FirstHopSource,
)
from app.altdata.sec001_v31.clock import accepted_at_utc
from app.altdata.sec001_v31.layers import Observation
from app.altdata.sec001_v31.stop_early import (
    AdmissibleSpan,
    GovernedGrid,
    StopEarlyController,
)


def cls_for(pt: int):
    """One declared class per permanent security.

    A single shared class tuple would let every link pair with every CIK's episode, which
    is a COMPETING binding, not a qualified one -- correct behaviour, wrong fixture.
    """
    return (f"Class {pt} Common Stock", f"AA{pt}", "Nasdaq")


CLASS = cls_for(0)
APPROVED_CLASS = "TEST_O9_SOURCE"
POLICY = FirstHopAdmissionPolicy(frozenset({APPROVED_CLASS}))


def wk(i: int) -> datetime:
    return datetime(2022, 5, 16, tzinfo=UTC) + timedelta(weeks=i)


def source() -> FirstHopSource:
    return FirstHopSource(
        source_class=APPROVED_CLASS,
        artifact_sha256="a" * 64,
        artifact_verified=True,
        identity_match_method="GOVERNED_SECURITY_MASTER_KEY",
        covers_from=wk(-500),
        covers_to=wk(500),
    )


def obs(cik: int, when: datetime, accession: str, dc=None) -> Observation:
    title, symbol, exch = dc or CLASS
    return Observation(
        accepted_at=when.strftime("%Y-%m-%dT%H:%M:%S.000Z"),
        cik=cik,
        trading_symbol=symbol,
        security_12b_title=title,
        security_exchange_name=exch,
        form="10-Q",
        accession=accession,
    )


def grid(n_weeks: int, budget: int, permatickers_per_week: int, max_failing: int) -> GovernedGrid:
    weeks = tuple(wk(i) for i in range(n_weeks))
    return GovernedGrid(
        spans=(
            AdmissibleSpan("20.0y", n_weeks, max_failing, weeks),
            AdmissibleSpan("26.4y", n_weeks, max_failing, weeks),
        ),
        excluded_low={w: frozenset(range(permatickers_per_week)) for w in weeks},
        weekly_unresolved_budget=budget,
    )


def controller(g: GovernedGrid, links: list[ClassIdentityLink]) -> StopEarlyController:
    return StopEarlyController(grid=g, links=links, to_utc=accepted_at_utc, policy=POLICY)


def test_with_no_evidence_nothing_is_qualified_and_acquisition_may_proceed():
    """Optimistic credit: everything unproven counts as RESOLVED, so a fresh run continues."""
    c = controller(grid(10, budget=2, permatickers_per_week=20, max_failing=1), [])
    assert c.qualified_unresolved(wk(0)) == 0
    assert c.stop_is_invariant() is False
    assert c.may_spend_next_request() == (True, "CONTINUE")


def test_stop_becomes_invariant_once_enough_cells_are_PROVEN_unresolved():
    g = grid(10, budget=2, permatickers_per_week=5, max_failing=1)
    links = [ClassIdentityLink(pt, cls_for(pt), wk(-1), wk(11), source()) for pt in range(5)]
    c = controller(g, links)
    assert c.stop_is_invariant() is False

    # three securities proven lineage-stable in every week => 3 > budget of 2 => every week
    # fails => both spans exceed max_failing=1
    for pt in range(3):
        c.admit(
            [
                obs(1000 + pt, wk(0), f"a{pt}", cls_for(pt)),
                obs(1000 + pt, wk(9), f"b{pt}", cls_for(pt)),
            ]
        )

    assert c.qualified_unresolved(wk(5)) == 3
    assert c.week_fails(wk(5)) is True
    assert c.stop_is_invariant() is True
    assert c.may_spend_next_request() == (False, "G0A_STOP_INVARIANT_UNDER_OPTIMISTIC_CREDIT")


def test_stop_requires_EVERY_admissible_span_to_fail():
    weeks_a = tuple(wk(i) for i in range(10))
    weeks_b = tuple(wk(i) for i in range(10, 20))
    g = GovernedGrid(
        spans=(
            AdmissibleSpan("A", 10, 0, weeks_a),
            AdmissibleSpan("B", 10, 0, weeks_b),
        ),
        excluded_low={w: frozenset({1}) for w in weeks_a + weeks_b},
        weekly_unresolved_budget=0,
    )
    # evidence only covers span A's weeks
    links = [ClassIdentityLink(1, cls_for(1), wk(0), wk(9), source())]
    c = controller(g, links)
    c.admit([obs(1, wk(0), "a", cls_for(1)), obs(1, wk(9), "b", cls_for(1))])

    report = c.report()
    assert report["spans"][0]["fails_o2"] is True
    assert report["spans"][1]["fails_o2"] is False
    assert c.stop_is_invariant() is False, "one surviving span means acquisition continues"


def test_the_qualified_set_is_monotone_so_stopping_is_sound():
    """Once a span fails it cannot be rescued: evidence only ever adds unresolved cells."""
    g = grid(6, budget=0, permatickers_per_week=3, max_failing=0)
    links = [ClassIdentityLink(pt, cls_for(pt), wk(-1), wk(7), source()) for pt in range(3)]
    c = controller(g, links)

    counts = []
    for pt in range(3):
        c.admit(
            [
                obs(500 + pt, wk(0), f"x{pt}", cls_for(pt)),
                obs(500 + pt, wk(5), f"y{pt}", cls_for(pt)),
            ]
        )
        counts.append(c.qualified_unresolved(wk(3)))
    assert counts == sorted(counts), "qualified-unresolved must never shrink"
    assert c.stop_is_invariant() is True


def test_an_inadmissible_first_hop_qualifies_nothing():
    """No governed first hop => no binding => no cell PROVEN unresolved => keep going."""
    g = grid(6, budget=0, permatickers_per_week=3, max_failing=0)
    ungoverned = [
        ClassIdentityLink(
            pt,
            cls_for(pt),
            wk(-1),
            wk(7),
            FirstHopSource("NOT_APPROVED", "b" * 64, True, "TICKER_EQUALITY", wk(-9), wk(9)),
        )
        for pt in range(3)
    ]
    c = controller(g, ungoverned)
    for pt in range(3):
        c.admit(
            [
                obs(500 + pt, wk(0), f"x{pt}", cls_for(pt)),
                obs(500 + pt, wk(5), f"y{pt}", cls_for(pt)),
            ]
        )

    assert c.qualified_unresolved(wk(3)) == 0
    assert c.stop_is_invariant() is False


def test_the_gate_is_consulted_before_each_request_not_after():
    """The integration contract: check, then spend -- so the verdict cannot be overrun."""
    g = grid(6, budget=0, permatickers_per_week=2, max_failing=0)
    links = [ClassIdentityLink(pt, cls_for(pt), wk(-1), wk(7), source()) for pt in range(2)]
    c = controller(g, links)

    spent = 0
    for pt in range(10):
        allowed, _reason = c.may_spend_next_request()
        if not allowed:
            break
        spent += 1
        if pt < 2:
            c.admit(
                [
                    obs(700 + pt, wk(0), f"p{pt}", cls_for(pt)),
                    obs(700 + pt, wk(5), f"q{pt}", cls_for(pt)),
                ]
            )

    assert c.stop_is_invariant() is True
    assert spent < 10, "acquisition must stop before exhausting the envelope"


def test_an_empty_span_set_never_reports_stop():
    c = controller(GovernedGrid(spans=(), excluded_low={}), [])
    assert c.stop_is_invariant() is False


@pytest.mark.parametrize("budget", [0, 1, 5])
def test_week_failure_is_strictly_greater_than_the_budget(budget):
    g = grid(3, budget=budget, permatickers_per_week=budget, max_failing=0)
    links = [ClassIdentityLink(pt, cls_for(pt), wk(-1), wk(4), source()) for pt in range(budget)]
    c = controller(g, links)
    for pt in range(budget):
        c.admit(
            [
                obs(800 + pt, wk(0), f"m{pt}", cls_for(pt)),
                obs(800 + pt, wk(2), f"n{pt}", cls_for(pt)),
            ]
        )
    assert c.qualified_unresolved(wk(1)) == budget
    assert c.week_fails(wk(1)) is False, "equal to the budget is not a breach"
