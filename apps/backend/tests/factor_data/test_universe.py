"""Point-in-time, survivorship-free universe correctness (P9 §1 §4.6 ★)."""

from __future__ import annotations

from datetime import date

import pytest

from app.factor_data.store import FactorDataStore
from app.factor_data.universe import UniverseUnavailable, universe_asof


def test_universe_excludes_names_added_later(store: FactorDataStore) -> None:
    # NEW1 is first priced 2010-06-01; at 2005 it must be absent.
    u = universe_asof(store, date(2005, 1, 3), n=5, lookback_days=63)
    assert "NEW1" not in u
    # ...and present once it exists and is liquid.
    later = universe_asof(store, date(2015, 1, 2), n=5, lookback_days=63)
    assert "NEW1" in later


def test_universe_includes_then_excludes_delisted_name(store: FactorDataStore) -> None:
    """A name present *then* but since delisted is included as of a date while it
    was trading, and excluded after its delisting — the survivorship-free hinge."""
    while_alive = universe_asof(store, date(2005, 1, 3), n=5, lookback_days=63)
    assert "DEAD1" in while_alive  # DEAD1 was the 2nd-most-liquid name in 2005

    after_delisting = universe_asof(store, date(2015, 1, 2), n=5, lookback_days=63)
    assert "DEAD1" not in after_delisting  # delisted 2008-09-15


def test_universe_ranking_is_by_dollar_volume(store: FactorDataStore) -> None:
    # 2005: per-day dollar volume DEAD1 1.5e9 > BIGA 1.0e9 > BIGB 4e8 > MIDC 9e7.
    u = universe_asof(store, date(2005, 6, 30), n=3, lookback_days=63)
    assert u == ["DEAD1", "BIGA", "BIGB"]


def test_universe_size_is_capped(store: FactorDataStore) -> None:
    assert len(universe_asof(store, date(2015, 6, 30), n=2, lookback_days=63)) == 2
    # only 4 names are eligible in 2015 (DEAD1 gone) — n larger than eligible set
    assert len(universe_asof(store, date(2015, 6, 30), n=100, lookback_days=63)) == 4


def test_universe_below_floor_raises(store: FactorDataStore) -> None:
    floor, _ = store.price_date_bounds()
    assert floor is not None
    with pytest.raises(UniverseUnavailable):
        universe_asof(store, date(floor.year - 1, 1, 1))


def test_universe_empty_store_raises(tmp_path) -> None:
    s = FactorDataStore(db_path=str(tmp_path / "empty.duckdb"))
    try:
        with pytest.raises(UniverseUnavailable):
            universe_asof(s, date(2015, 1, 2))
    finally:
        s.close()


def test_universe_reproducible(store: FactorDataStore) -> None:
    a = universe_asof(store, date(2012, 3, 30), n=4, lookback_days=63)
    b = universe_asof(store, date(2012, 3, 30), n=4, lookback_days=63)
    assert a == b  # identical ordered list


def test_universe_rejects_nonpositive_n(store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        universe_asof(store, date(2015, 1, 2), n=0)
