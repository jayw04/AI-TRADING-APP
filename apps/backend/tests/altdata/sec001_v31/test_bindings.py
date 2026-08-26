"""The full evidence chain: permanent security -> class identity -> SEC tuple -> CIK.

The point of these tests is the FIRST hop. A declared class tuple bound to a CIK is not a
security->CIK binding, and treating it as one is the V3 failure shape.
"""

from __future__ import annotations

from datetime import datetime

import pytest

from app.altdata.sec001_v31.bindings import (
    COMPETING,
    FIRST_HOP_ARTIFACT_UNVERIFIED,
    FIRST_HOP_IDENTITY_NOT_INDEPENDENT,
    FIRST_HOP_INTERVAL_UNSUPPORTED,
    FIRST_HOP_SOURCE_CLASS_NOT_APPROVED,
    NO_BINDING,
    NO_FIRST_HOP,
    O9_APPROVED_SOURCE_CLASSES,
    UNIQUE,
    BindingReport,
    ClassIdentityLink,
    FirstHopAdmissionPolicy,
    FirstHopSource,
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

APPROVED_CLASS = "TEST_O9_EFFECTIVE_DATED_SECURITY_MASTER"
#: The production policy admits NOTHING; tests must opt a class in explicitly.
POLICY = FirstHopAdmissionPolicy(frozenset({APPROVED_CLASS}))


def governed_source(**kw) -> FirstHopSource:
    base = dict(
        source_class=APPROVED_CLASS,
        artifact_sha256="a" * 64,
        artifact_verified=True,
        identity_match_method="GOVERNED_SECURITY_MASTER_KEY",
        covers_from=t("1990-01-01"),
        covers_to=t("2030-12-31"),
    )
    base.update(kw)
    return FirstHopSource(**base)


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


def link(pt: int, dc, a: str, b: str, source: FirstHopSource | None = None) -> ClassIdentityLink:
    return ClassIdentityLink(
        pt, dc, t(a), t(b), source if source is not None else governed_source()
    )


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
    assert build_security_cik_bindings(eps, [], POLICY) == []


def test_without_a_first_hop_the_week_is_disputed_not_bound():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    covered, status = security_cik_binding_covers_week(
        build_security_cik_bindings(eps, [], POLICY), [], GOOGL_PT, t("2024-01-01"), POLICY
    )
    assert covered is False and status == NO_FIRST_HOP


def _eps():
    return build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )


def test_the_production_policy_admits_nothing_by_construction():
    """No O-9-approved source class exists in custody; that absence IS the finding."""
    assert frozenset() == O9_APPROVED_SOURCE_CLASSES
    default = FirstHopAdmissionPolicy()
    ok, reason = default.admit(link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31"))
    assert ok is False and reason == FIRST_HOP_SOURCE_CLASS_NOT_APPROVED
    assert (
        build_security_cik_bindings(_eps(), [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31")])
        == []
    )


def test_a_link_with_no_source_at_all_is_inadmissible():
    bare = ClassIdentityLink(GOOGL_PT, CLASS_A, t("2000-01-01"), t("2026-12-31"), None)
    ok, reason = POLICY.admit(bare)
    assert ok is False and reason == FIRST_HOP_SOURCE_CLASS_NOT_APPROVED


@pytest.mark.parametrize(
    "kw,expected",
    [
        ({"source_class": "SOMETHING_PLAUSIBLE"}, FIRST_HOP_SOURCE_CLASS_NOT_APPROVED),
        ({"artifact_verified": False}, FIRST_HOP_ARTIFACT_UNVERIFIED),
        ({"artifact_sha256": "short"}, FIRST_HOP_ARTIFACT_UNVERIFIED),
        ({"identity_match_method": "TICKER_EQUALITY"}, FIRST_HOP_IDENTITY_NOT_INDEPENDENT),
        ({"identity_match_method": "CURRENT_TICKER_MAP"}, FIRST_HOP_IDENTITY_NOT_INDEPENDENT),
        ({"identity_match_method": ""}, FIRST_HOP_IDENTITY_NOT_INDEPENDENT),
        ({"covers_from": t("2024-01-01")}, FIRST_HOP_INTERVAL_UNSUPPORTED),
        ({"covers_to": t("2010-01-01")}, FIRST_HOP_INTERVAL_UNSUPPORTED),
    ],
)
def test_each_positive_admission_condition_is_required(kw, expected):
    """A well-chosen label proves nothing; every condition is checked independently."""
    bad = link(GOOGL_PT, CLASS_A, "2020-01-01", "2026-12-31", governed_source(**kw))
    ok, reason = POLICY.admit(bad)
    assert ok is False and reason == expected
    assert build_security_cik_bindings(_eps(), [bad], POLICY) == []
    covered, status = security_cik_binding_covers_week([], [bad], GOOGL_PT, t("2024-01-01"), POLICY)
    assert covered is False and status.startswith("DISPUTED_FIRST_HOP_")


def test_an_approved_first_hop_produces_a_binding():
    eps = build_declared_class_episodes(
        [
            obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
            obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
        ],
        to_utc=accepted_at_utc,
    )
    links = [link(GOOGL_PT, CLASS_A, "2000-01-01", "2026-12-31")]
    bindings = build_security_cik_bindings(eps, links, POLICY)

    assert len(bindings) == 1 and bindings[0].permaticker == GOOGL_PT and bindings[0].cik == 1652044
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2024-01-01"), POLICY) == (
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
    bindings = build_security_cik_bindings(eps, links, POLICY)

    assert len(bindings) == 1 and bindings[0].cik == 1652044
    assert detect_competing_bindings(bindings) == []
    # the 2005-2007 window belongs to no permanent security we can prove
    assert (
        security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2006-01-01"), POLICY)[0]
        is False
    )


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
    bindings = build_security_cik_bindings(eps, links, POLICY)

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
    bindings = build_security_cik_bindings(eps, links, POLICY)

    conflicts = detect_competing_bindings(bindings)
    assert len(conflicts) == 1
    assert {conflicts[0].left.cik, conflicts[0].right.cik} == {1652044, 1288776}
    assert str(GOOGL_PT) in conflicts[0].describe()

    covered, status = security_cik_binding_covers_week(
        bindings, links, GOOGL_PT, t("2023-06-01"), POLICY
    )
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
    assert detect_competing_bindings(build_security_cik_bindings(eps, links, POLICY)) == []


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
    b = build_security_cik_bindings(eps, links, POLICY)[0]

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
    bindings = build_security_cik_bindings(eps, links, POLICY)

    assert (
        security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2021-02-08"), POLICY)[0]
        is False
    )
    assert (
        security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2026-08-01"), POLICY)[0]
        is False
    )
    assert security_cik_binding_covers_week(bindings, links, GOOGL_PT, t("2024-01-01"), POLICY) == (
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
    bindings = build_security_cik_bindings(eps, links, POLICY)
    covered, status = security_cik_binding_covers_week(
        bindings, links, GOOGL_PT, t("2025-01-01"), POLICY
    )
    assert covered is False and status == NO_BINDING


# =============================================== report
def test_binding_report_surfaces_inadmissible_first_hops():
    observations = [
        obs(1652044, "2022-05-16T12:00:00.000Z", CLASS_A, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", CLASS_A, "a2"),
    ]
    links = [
        link(
            GOOGL_PT,
            CLASS_A,
            "2000-01-01",
            "2026-12-31",
            governed_source(identity_match_method="TICKER_EQUALITY"),
        ),
        link(GOOG_PT, CLASS_C, "2000-01-01", "2026-12-31"),
    ]
    rep = BindingReport.build(observations, links, to_utc=accepted_at_utc, policy=POLICY)
    assert len(rep.inadmissible_first_hops) == 1
    assert rep.inadmissible_first_hops[0][1] == FIRST_HOP_IDENTITY_NOT_INDEPENDENT
    assert rep.bindings == [] and rep.conflicts == []
    assert len(rep.episodes) == 1
