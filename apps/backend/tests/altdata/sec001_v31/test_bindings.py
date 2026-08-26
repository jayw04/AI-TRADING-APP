"""The full evidence chain: permanent security -> class identity -> SEC tuple -> CIK.

The point of these tests is the FIRST hop. A declared class tuple bound to a CIK is not a
security->CIK binding, and treating it as one is the V3 failure shape.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.altdata.sec001_v31.bindings import (
    COMPETING,
    FIRST_HOP_TICKER_ONLY,
    NO_BINDING,
    NO_FIRST_HOP,
    UNIQUE,
    BindingReport,
    ClassIdentityLink,
    build_declared_class_episodes,
    build_security_cik_bindings,
    declared_class,
    detect_competing_bindings,
    security_cik_binding_covers_week,
)
from app.altdata.sec001_v31.clock import accepted_at_utc
from app.altdata.sec001_v31.layers import Observation

CLASS_A = ("Class A Common Stock, $0.001 par value", "GOOGL", "Nasdaq Global Select Market")
CLASS_C = ("Class C Capital Stock, $0.001 par value", "GOOG", "Nasdaq Global Select Market")
GOOGL_PT, GOOG_PT = 195146, 119496

APPROVED = "O9_APPROVED_EFFECTIVE_DATED_SECURITY_MASTER"


def obs(cik: int, when: str, dc, accession: str) -> Observation:
    title, symbol, exch = dc
    return Observation(
        accepted_at=when,
        cik=cik,
        trading_symbol=symbol,
        security_12b_title=title,
        security_exchange_name=exch,
        form="10-Q",
        accession=accession,
    )


def t(d: str) -> datetime:
    return accepted_at_utc(f"{d}T12:00:00.000Z")


def link(pt: int, dc, a: str, b: str, basis: str = APPROVED) -> ClassIdentityLink:
    return ClassIdentityLink(pt, dc, t(a), t(b), basis)


# =============================================== the first hop is required
def test_declared_class_episodes_are_not_bindings():
    """They prove class-tuple -> CIK. That is the last two hops only."""
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    assert len(eps) == 1
    assert type(eps[0]).__name__ == "DeclaredClassCikEpisode"
    # with NO class-identity link there is no binding at all
    assert build_security_cik_bindings(eps, []) == []


def test_without_a_first_hop_the_week_is_disputed_not_bound():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    covered, status = security_cik_binding_covers_week(
        build_security_cik_bindings(eps, []), [], GOOGL_PT, t("2024-01-01")
    )
    assert covered is False and status == NO_FIRST_HOP


@pytest.mark.parametrize(
    "basis", ["TICKER_EQUALITY", "TICKER_EQUALITY_ONLY", "CURRENT_TICKER_MAP", "SYMBOL_MATCH", ""]
)
def test_a_ticker_equality_first_hop_is_inadmissible(basis):
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31", basis)]
    bindings = build_security_cik_bindings(eps, links)

    assert bindings == [], "ticker equality cannot close the first hop"
    covered, status = security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2024-01-01"))
    assert covered is False and status == FIRST_HOP_TICKER_ONLY


def test_an_approved_first_hop_produces_a_binding():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31")]
    bindings = build_security_cik_bindings(eps, links)

    assert len(bindings) == 1 and bindings[0].permaticker == GOOGL_PT and bindings[0].cik == 1652044
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2024-01-01")) == (
        True,
        UNIQUE,
    )


def test_a_reused_class_tuple_across_unrelated_issuers_does_not_merge():
    """Two unrelated issuers reusing one symbol/title/exchange at non-overlapping dates.

    The old class-tuple-keyed model stitched these into successive episodes of one
    'security'. With the first hop required, each binds only to its own permanent identity.
    """
    observations = [
        obs(111111, "2005-01-01T12:00:00.000Z", CLASS_A, "old1"),
        obs(111111, "2007-01-01T12:00:00.000Z", CLASS_A, "old2"),
        obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "new1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "new2"),
    ]
    eps = build_declared_class_episodes(observations, to_utc=accepted_at_utc)
    assert len(eps) == 2, "two CIKs -> two declared-class episodes"

    # only the modern permanent security is linked to the modern interval
    links = [link(GOOGL_PT, CLASS_A, "2015-01-01", "2026-12-31")]
    bindings = build_security_cik_bindings(eps, links)

    assert len(bindings) == 1 and bindings[0].cik == 1652044
    assert detect_competing_bindings(bindings) == []
    # the 2005-2007 window belongs to no permanent security we can prove
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2006-01-01"))[0] is False


# =============================================== multi-class still separates
def test_one_cik_two_classes_binds_to_two_permanent_securities():
    observations = [
        obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_C, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_C, "a2"),
    ]
    eps = build_declared_class_episodes(observations, to_utc=accepted_at_utc)
    links = [
        link(GOOGL_PT, CLASS_A, "2015-01-01", "2026-12-31"),
        link(GOOG_PT, CLASS_C, "2015-01-01", "2026-12-31"),
    ]
    bindings = build_security_cik_bindings(eps, links)

    assert {b.permaticker for b in bindings} == {GOOGL_PT, GOOG_PT}
    assert all(b.cik == 1652044 for b in bindings)
    assert detect_competing_bindings(bindings) == []


def test_declared_class_key_is_the_class_tuple_not_the_ticker():
    a = obs(1652044, "2024-01-01T12:00:00.000Z", CLASS_A, "x")
    c = obs(1652044, "2024-01-01T12:00:00.000Z", CLASS_C, "x")
    assert declared_class(a) != declared_class(c)


# =============================================== the competing conjunct
def test_two_admissible_bindings_overlapping_one_permanent_security_are_competing():
    observations = [
        obs(1652044, "2022-01-01T12:00:00.000Z", CLASS_A, "a1"),
        obs(1652044, "2024-01-01T12:00:00.000Z", CLASS_A, "a2"),
        obs(1288776, "2023-01-01T12:00:00.000Z", CLASS_A, "b1"),
        obs(1288776, "2025-01-01T12:00:00.000Z", CLASS_A, "b2"),
    ]
    eps = build_declared_class_episodes(observations, to_utc=accepted_at_utc)
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31")]
    bindings = build_security_cik_bindings(eps, links)

    conflicts = detect_competing_bindings(bindings)
    assert len(conflicts) == 1
    assert {conflicts[0].left.cik, conflicts[0].right.cik} == {1652044, 1288776}
    assert str(GOOGL_PT) in conflicts[0].describe()

    covered, status = security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2023-06-01"))
    assert covered is False and status == COMPETING


def test_non_overlapping_successive_ciks_are_not_competing():
    observations = [
        obs(1288776, "2015-01-01T12:00:00.000Z", CLASS_A, "b1"),
        obs(1288776, "2015-06-01T12:00:00.000Z", CLASS_A, "b2"),
        obs(1652044, "2016-01-01T12:00:00.000Z", CLASS_A, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
    ]
    eps = build_declared_class_episodes(observations, to_utc=accepted_at_utc)
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31")]
    assert detect_competing_bindings(build_security_cik_bindings(eps, links)) == []


# =============================================== inward bounding
def test_binding_interval_is_the_intersection_of_both_hops():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2024-01-01", "2025-01-01")]
    b = build_security_cik_bindings(eps, links)[0]

    assert b.valid_from == t("2024-01-01") and b.valid_to == t("2025-01-01")
    assert b.covers(t("2024-06-01"))
    # neither hop may extend the other
    assert not b.covers(t("2023-01-01")) and not b.covers(t("2026-01-01"))


def test_no_outward_extrapolation_past_observed_evidence():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2030-12-31")]
    bindings = build_security_cik_bindings(eps, links)

    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2021-02-08"))[0] is False
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2026-08-01"))[0] is False
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2024-01-01")) == (
        True,
        UNIQUE,
    )


def test_a_week_outside_every_binding_but_with_an_admissible_link_reports_no_binding():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2022-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2030-12-31")]
    bindings = build_security_cik_bindings(eps, links)
    covered, status = security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2025-01-01"))
    assert covered is False and status == NO_BINDING


# =============================================== report
def test_binding_report_surfaces_inadmissible_first_hops():
    observations = [
        obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
    ]
    links = [
        link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31", "TICKER_EQUALITY"),
        link(GOOG_PT, CLASS_C, "2000-01-01", "2026-12-31"),
    ]
    rep = BindingReport.build(observations, links, to_utc=accepted_at_utc)
    assert len(rep.inadmissible_first_hops) == 1
    assert rep.inadmissible_first_hops[0].basis == "TICKER_EQUALITY"
    assert rep.bindings == [] and rep.conflicts == []
    assert len(rep.episodes) == 1
