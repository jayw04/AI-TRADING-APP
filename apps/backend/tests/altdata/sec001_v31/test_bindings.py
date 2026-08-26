"""The genuine NO_COMPETING_SECURITY_CIK_BINDING conjunct — between two ADMISSIBLE bindings.

Deliberately separate from ``INDEX_COVER_CIK_MISMATCH``: an index CIK is acquisition
metadata and is not an admissible security->CIK binding, so it can never be one side of a
competing-binding finding.
"""

from __future__ import annotations

from datetime import datetime

from app.altdata.sec001_v31.acquire import accepted_at_utc
from app.altdata.sec001_v31.bindings import (
    COMPETING,
    UNIQUE,
    binding_covers_week,
    build_binding_episodes,
    detect_competing_bindings,
    security_key,
)
from app.altdata.sec001_v31.layers import Observation

CLASS_A = ("Class A Common Stock, $0.001 par value", "GOOGL", "Nasdaq Global Select Market")
CLASS_C = ("Class C Capital Stock, $0.001 par value", "GOOG", "Nasdaq Global Select Market")


def obs(cik: int, when: str, title: str, symbol: str, exch: str, accession: str) -> Observation:
    return Observation(
        accepted_at=when,
        cik=cik,
        trading_symbol=symbol,
        security_12b_title=title,
        security_exchange_name=exch,
        form="10-Q",
        accession=accession,
    )


def week(d: str) -> datetime:
    return accepted_at_utc(f"{d}T12:00:00.000Z")


def test_security_key_is_the_class_tuple_not_the_ticker():
    a = obs(1652044, "2024-01-01T12:00:00.000Z", *CLASS_A, "acc-1")
    c = obs(1652044, "2024-01-01T12:00:00.000Z", *CLASS_C, "acc-1")
    assert security_key(a) != security_key(c), "two classes of one registrant are two securities"


def test_one_cik_two_classes_is_not_competing():
    observations = [
        obs(1652044, "2022-05-01T12:00:00.000Z", *CLASS_A, "a1"),
        obs(1652044, "2026-06-01T12:00:00.000Z", *CLASS_A, "a2"),
        obs(1652044, "2022-05-01T12:00:00.000Z", *CLASS_C, "a1"),
        obs(1652044, "2026-06-01T12:00:00.000Z", *CLASS_C, "a2"),
    ]
    eps = build_binding_episodes(observations, to_utc=accepted_at_utc)
    assert len(eps) == 2
    assert detect_competing_bindings(eps) == []


def test_two_admissible_bindings_overlapping_the_same_security_are_competing():
    """The real conjunct: CIK A and CIK B both claiming one security over overlapping time."""
    observations = [
        obs(1652044, "2022-01-01T12:00:00.000Z", *CLASS_A, "a1"),
        obs(1652044, "2024-01-01T12:00:00.000Z", *CLASS_A, "a2"),
        obs(1288776, "2023-01-01T12:00:00.000Z", *CLASS_A, "b1"),
        obs(1288776, "2025-01-01T12:00:00.000Z", *CLASS_A, "b2"),
    ]
    eps = build_binding_episodes(observations, to_utc=accepted_at_utc)
    conflicts = detect_competing_bindings(eps)

    assert len(conflicts) == 1
    assert {conflicts[0].left.cik, conflicts[0].right.cik} == {1652044, 1288776}
    assert "1652044" in conflicts[0].describe()

    covered, status = binding_covers_week(eps, security_key(observations[0]), week("2023-06-01"))
    assert covered is False and status == COMPETING


def test_non_overlapping_successive_ciks_are_not_competing():
    observations = [
        obs(1288776, "2015-01-01T12:00:00.000Z", *CLASS_A, "b1"),
        obs(1288776, "2015-06-01T12:00:00.000Z", *CLASS_A, "b2"),
        obs(1652044, "2016-01-01T12:00:00.000Z", *CLASS_A, "a1"),
        obs(1652044, "2026-06-01T12:00:00.000Z", *CLASS_A, "a2"),
    ]
    eps = build_binding_episodes(observations, to_utc=accepted_at_utc)
    assert detect_competing_bindings(eps) == []


def test_inward_bounding_qualifies_only_inside_observed_evidence():
    observations = [
        obs(1652044, "2022-05-16T12:00:00.000Z", *CLASS_A, "a1"),
        obs(1652044, "2026-06-08T12:00:00.000Z", *CLASS_A, "a2"),
    ]
    eps = build_binding_episodes(observations, to_utc=accepted_at_utc)
    sec = security_key(observations[0])

    assert binding_covers_week(eps, sec, week("2024-01-01")) == (True, UNIQUE)
    # no outward extrapolation: before the first and after the last observation
    assert binding_covers_week(eps, sec, week("2021-02-08"))[0] is False
    assert binding_covers_week(eps, sec, week("2026-08-01"))[0] is False


def test_a_security_with_no_binding_at_all_is_not_covered():
    eps = build_binding_episodes([], to_utc=accepted_at_utc)
    assert binding_covers_week(eps, CLASS_A, week("2024-01-01")) == (
        False,
        "NO_BINDING_COVERS_WEEK",
    )
