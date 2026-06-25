"""Conviction-buy signal construction (§3) — the faithful filter over insider-buy events."""

from __future__ import annotations

from datetime import UTC, date, datetime

from app.altdata.events.store import CorporateEvent
from app.altdata.signal import conviction_hits


def _buy(ticker, txn: date, *, value: float, officer=True, owner="Jane Exec",
         filed: date | None = None, director=False, amendment=False) -> CorporateEvent:
    filed = filed or txn
    return CorporateEvent(
        cik=1, ticker=ticker, event_type="insider_buy", source="sec_edgar_form4",
        accession=f"{ticker}-{txn.isoformat()}-{owner}",
        filed_at=datetime(filed.year, filed.month, filed.day, 18, 30, tzinfo=UTC),
        event_date=txn,
        payload={"buy_value": value, "is_officer": officer, "is_director": director,
                 "owner_name": owner, "is_amendment": amendment},
    )


def test_big_solo_qualifies_alone():
    hits = conviction_hits([_buy("AAA", date(2026, 3, 2), value=150_000)])
    assert len(hits) == 1
    h = hits[0]
    assert h.is_big_solo and not h.is_cluster and h.value == 150_000


def test_below_min_value_is_filtered():
    assert conviction_hits([_buy("AAA", date(2026, 3, 2), value=20_000)]) == []


def test_non_officer_is_filtered():
    # a $30k buy by a non-officer (director/10%-owner) is excluded from the exec/officer subset
    assert conviction_hits([_buy("AAA", date(2026, 3, 2), value=30_000, officer=False)]) == []


def test_cluster_fires_when_second_insider_makes_it_visible():
    # two different officers each buy $30k (each < big-solo) within 30d. The cluster is only
    # KNOWABLE when the 2nd files (3/20); the 1st buy (3/2) sees only itself -> not yet a cluster.
    # Forward-only trailing window = PIT-honest: exactly one hit, on the date the cluster appears.
    evs = [
        _buy("BBB", date(2026, 3, 2), value=30_000, owner="Officer A"),
        _buy("BBB", date(2026, 3, 20), value=30_000, owner="Officer B"),
    ]
    hits = conviction_hits(evs)
    assert len(hits) == 1
    assert hits[0].event_date == date(2026, 3, 20)
    assert hits[0].is_cluster and not hits[0].is_big_solo and hits[0].n_cluster_insiders == 2


def test_same_insider_twice_is_not_a_cluster():
    # one officer buying twice is one distinct insider -> not clustered; neither is big-solo -> no hit
    evs = [
        _buy("CCC", date(2026, 3, 2), value=30_000, owner="Officer A"),
        _buy("CCC", date(2026, 3, 10), value=30_000, owner="Officer A"),
    ]
    assert conviction_hits(evs) == []


def test_cluster_window_excludes_old_buys():
    evs = [
        _buy("DDD", date(2026, 1, 1), value=30_000, owner="Officer A"),
        _buy("DDD", date(2026, 3, 1), value=30_000, owner="Officer B"),  # 59d later -> not clustered
    ]
    assert conviction_hits(evs) == []


def test_amendments_excluded_from_signal():
    # a 4/A correction is not a new conviction event
    assert conviction_hits([_buy("EEE", date(2026, 3, 2), value=150_000, amendment=True)]) == []


def test_entry_anchor_is_filing_date_not_transaction():
    h = conviction_hits([_buy("FFF", date(2026, 3, 2), value=150_000,
                              filed=date(2026, 3, 4))])[0]
    assert h.event_date == date(2026, 3, 2)
    assert h.entry_date == date(2026, 3, 4)  # PIT: enter when knowable, not on the transaction
