"""Identity map and monthly PIT universe on SYNTHETIC rename / reuse / delisting fixtures.

No vendor data is read and nothing here says anything about real coverage. These tests establish
the logic's structural properties only: temporal classification (never "repeated id => legit"),
no look-ahead, identity-keyed membership, delisted-later names retained, exclusions reported
against the original population, and determinism.
"""

from __future__ import annotations

import copy
from datetime import date, timedelta

import pytest

from app.research.range002.data.identity_map import (
    AMBIGUOUS_OVERLAP,
    NO_MAPPING,
    RESOLVED,
    IdentityDataError,
    IdentityRecord,
    audit_identity,
    build_identity_map,
    permaticker_on,
    ticker_on,
)
from app.research.range002.data.pit_universe import (
    AMBIGUOUS_IDENTITY,
    BASIS_SPLIT_ADJUSTED,
    INSUFFICIENT_HISTORY,
    NO_DECISION_DAY_PRINT,
    NO_IDENTITY_MAPPING,
    NOT_COMMON_STOCK,
    PRICE_NOT_ABOVE_MIN,
    DailyObs,
    Listing,
    PitUniverseError,
    UniverseParams,
    build_universe_month,
)

D = date
MONTH = D(2018, 3, 1)
DECISION = D(2018, 2, 28)
PARAMS = UniverseParams(
    n=3, adv_window=3, min_price=10.0, basis=BASIS_SPLIT_ADJUSTED,
    category_map=("Domestic Common Stock",), intraday_basis="raw",
)  # fmt: skip


def rec(p: str, t: str, a: date, b: date | None) -> IdentityRecord:
    return IdentityRecord(p, t, a, b)


def days(end: date, k: int) -> list[date]:
    out, d = [], end
    while len(out) < k:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


def series(p: str, close: float, vol: float, end: date = DECISION, k: int = 3) -> list[DailyObs]:
    return [DailyObs(p, d, close, close, vol, BASIS_SPLIT_ADJUSTED) for d in days(end, k)]


# --- identity map ---------------------------------------------------------------------------


def test_rename_is_a_candidate_only_when_intervals_do_not_overlap() -> None:
    m = build_identity_map(
        [rec("P1", "OLD", D(2010, 1, 1), D(2017, 6, 30)), rec("P1", "NEW", D(2017, 7, 1), None)]
    )
    a = audit_identity(m)
    assert a.rename_candidates == (("P1", ("OLD", "NEW")),)
    assert a.permaticker_overlaps == ()
    assert ticker_on(m, "P1", D(2016, 1, 4)).value == "OLD"
    assert ticker_on(m, "P1", D(2018, 1, 4)).value == "NEW"
    assert ticker_on(m, "P1", D(2009, 1, 4)).status == NO_MAPPING


def test_overlapping_tickers_for_one_issuer_is_a_conflict_not_a_rename() -> None:
    m = build_identity_map(
        [rec("P1", "OLD", D(2010, 1, 1), D(2017, 12, 31)), rec("P1", "NEW", D(2017, 7, 1), None)]
    )
    a = audit_identity(m)
    assert a.rename_candidates == () and a.permaticker_overlaps == (("P1", ("OLD", "NEW")),)
    assert ticker_on(m, "P1", D(2017, 8, 1)).status == AMBIGUOUS_OVERLAP
    assert ticker_on(m, "P1", D(2016, 8, 1)).status == RESOLVED


def test_ticker_reuse_resolves_by_date_and_simultaneous_reuse_is_ambiguous() -> None:
    seq = build_identity_map(
        [rec("P1", "XYZ", D(2010, 1, 1), D(2014, 5, 1)), rec("P2", "XYZ", D(2016, 1, 1), None)]
    )
    assert audit_identity(seq).reuse_candidates == (("XYZ", ("P1", "P2")),)
    assert permaticker_on(seq, "XYZ", D(2012, 1, 4)).value == "P1"
    assert permaticker_on(seq, "XYZ", D(2017, 1, 4)).value == "P2"
    assert permaticker_on(seq, "XYZ", D(2015, 1, 5)).status == NO_MAPPING  # the gap

    clash = build_identity_map(
        [rec("P1", "XYZ", D(2010, 1, 1), None), rec("P2", "XYZ", D(2016, 1, 1), None)]
    )
    assert audit_identity(clash).ticker_overlaps == (("XYZ", ("P1", "P2")),)
    assert permaticker_on(clash, "XYZ", D(2017, 1, 4)).status == AMBIGUOUS_OVERLAP


def test_defective_records_are_refused() -> None:
    with pytest.raises(IdentityDataError):
        build_identity_map([rec("P1", "A", D(2018, 2, 1), D(2018, 1, 1))])
    with pytest.raises(IdentityDataError):
        build_identity_map([rec(" ", "A", D(2018, 1, 1), None)])
    with pytest.raises(IdentityDataError):
        build_identity_map([rec("P1", "A", D(2018, 1, 1), None)] * 2)


# --- PIT universe ---------------------------------------------------------------------------


def fixture() -> tuple[list[Listing], list[DailyObs], list[IdentityRecord]]:
    listings = [
        Listing("BIG", True, None),
        Listing("MID", True, None),
        Listing("DEAD", True, D(2018, 6, 15)),  # delisted AFTER the decision day: must stay
        Listing("PENNY", True, None),
        Listing("ETF", False, None),
        Listing("SHORT", True, None),
        Listing("GONE", True, D(2018, 1, 10)),  # delisted BEFORE the decision day
        Listing("UNMAPPED", True, None),
        Listing("CLASH", True, None),
        Listing("LOW", True, None),
    ]
    obs: list[DailyObs] = []
    for p, close, vol in [
        ("BIG", 100.0, 1_000_000),
        ("MID", 50.0, 400_000),
        ("DEAD", 20.0, 900_000),
        ("PENNY", 5.0, 9_000_000),
        ("ETF", 200.0, 5_000_000),
        ("UNMAPPED", 30.0, 800_000),
        ("CLASH", 30.0, 700_000),
        ("LOW", 12.0, 100_000),
    ]:
        obs += series(p, close, vol)
    obs += series("SHORT", 40.0, 500_000, k=2)  # only two usable days
    obs += series("GONE", 40.0, 500_000, end=D(2018, 1, 9))  # no print on the decision day
    ids = [
        rec(p, p, D(2005, 1, 1), None)
        for p in ("BIG", "MID", "DEAD", "PENNY", "ETF", "SHORT", "GONE", "LOW")
    ]
    ids += [rec("CLASH", "CLASH", D(2005, 1, 1), None), rec("CLASH", "CLASH2", D(2010, 1, 1), None)]
    return listings, obs, ids


def build(listings: list[Listing], obs: list[DailyObs], ids: list[IdentityRecord], params=PARAMS):  # type: ignore[no-untyped-def]
    return build_universe_month(MONTH, DECISION, listings, obs, build_identity_map(ids), params)


def test_membership_ranks_by_adv_keeps_delisted_later_and_reports_every_exclusion() -> None:
    u = build(*fixture())
    # ADV: BIG 100M, DEAD 18M, MID 20M; LOW 1.2M ranks 4th -> cut
    assert [m.permaticker for m in u.members] == ["BIG", "MID", "DEAD"]
    assert [m.rank for m in u.members] == [1, 2, 3]
    assert u.members[2].last_price_date == D(2018, 6, 15)  # delisted-later name retained
    reasons = {e.permaticker: e.reason for e in u.excluded}
    assert reasons == {
        "PENNY": PRICE_NOT_ABOVE_MIN,
        "ETF": NOT_COMMON_STOCK,
        "SHORT": INSUFFICIENT_HISTORY,
        "GONE": NO_DECISION_DAY_PRINT,
        "UNMAPPED": NO_IDENTITY_MAPPING,
        "CLASH": AMBIGUOUS_IDENTITY,
    }
    assert u.below_cut == 1 and u.population == 10
    assert u.population == len(u.members) + u.below_cut + len(u.excluded)


def test_no_lookahead_future_rows_and_labels_change_nothing() -> None:
    listings, obs, ids = fixture()
    base = build(listings, obs, ids)
    future = copy.deepcopy(obs) + [
        DailyObs(
            "LOW", D(2018, 3, 5), 999.0, 999.0, 9e12, BASIS_SPLIT_ADJUSTED
        ),  # would top the ranking if it leaked
        DailyObs("BIG", D(2018, 3, 6), 0.01, 0.01, 1.0, BASIS_SPLIT_ADJUSTED),
    ]
    relabelled = [Listing(li.permaticker, li.common_stock, D(2030, 1, 1)) for li in listings]
    again = build(relabelled, future, ids)
    assert [m.permaticker for m in again.members] == [m.permaticker for m in base.members]
    assert [(m.adv, m.prior_close) for m in again.members] == [
        (m.adv, m.prior_close) for m in base.members
    ]
    assert again.excluded == base.excluded


def test_identity_is_keyed_to_the_issuer_not_the_ticker_string() -> None:
    listings, obs, ids = fixture()
    ids = [r for r in ids if r.permaticker != "BIG"] + [
        rec("BIG", "OLDBIG", D(2005, 1, 1), D(2018, 1, 31)),
        rec("BIG", "NEWBIG", D(2018, 2, 1), None),
        rec("OTHER", "OLDBIG", D(2018, 3, 1), None),  # the old string reused later by someone else
    ]
    big = next(m for m in build(listings, obs, ids).members if m.permaticker == "BIG")
    assert big.vendor_ticker == "NEWBIG"


def test_deterministic_and_input_order_irrelevant() -> None:
    listings, obs, ids = fixture()
    a = build(listings, obs, ids)
    b = build(list(reversed(listings)), list(reversed(obs)), list(reversed(ids)))
    assert a == b


def test_defective_inputs_refuse_rather_than_guess() -> None:
    listings, obs, ids = fixture()
    with pytest.raises(PitUniverseError):
        build_universe_month(
            DECISION, DECISION, listings, obs, build_identity_map(ids), PARAMS
        )  # decision day not before the month
    with pytest.raises(PitUniverseError):
        build(listings, obs + [obs[0]], ids)  # duplicate observation
    with pytest.raises(PitUniverseError):
        build(
            listings, obs + [DailyObs("BIG", D(2018, 1, 2), 1.0, 1.0, 1.0, "adj")], ids
        )  # mixed basis
    with pytest.raises(PitUniverseError):
        build(
            listings,
            obs,
            ids,
            UniverseParams(0, 3, 10.0, BASIS_SPLIT_ADJUSTED, ("Domestic Common Stock",), "raw"),
        )
