"""Sandboxed FactorAccessor: degrade, PIT clamp, and the sandbox surface (P9 §2 §4.5/§4.6)."""

from __future__ import annotations

from datetime import date

import pytest

from app.factor_data.accessor import FactorAccessor, FactorDataUnavailable
from app.factor_data.store import FactorDataStore

_AS_OF = date(2020, 6, 30)


def test_accessor_none_store_raises_everywhere() -> None:
    acc = FactorAccessor(None)
    with pytest.raises(FactorDataUnavailable):
        acc.momentum_scores()
    with pytest.raises(FactorDataUnavailable):
        acc.momentum_for("MOM01")
    with pytest.raises(FactorDataUnavailable):
        acc.universe()
    with pytest.raises(FactorDataUnavailable):
        acc.sectors(["MOM01"])


def test_accessor_sectors_delegates_to_store(momentum_store: FactorDataStore) -> None:
    """sectors() returns a dict keyed by every requested ticker (the synthetic
    fixture has no sector data → all None, but the mapping is complete)."""
    acc = FactorAccessor(momentum_store)
    got = acc.sectors(["MOM00", "MOM24"])
    assert set(got) == {"MOM00", "MOM24"}


def test_accessor_momentum_scores(momentum_store: FactorDataStore) -> None:
    acc = FactorAccessor(momentum_store)
    df = acc.momentum_scores(_AS_OF)
    assert len(df) == 25
    assert acc.momentum_for("MOM24", _AS_OF) > acc.momentum_for("MOM00", _AS_OF)


def test_as_of_default_is_latest_store_date(momentum_store: FactorDataStore) -> None:
    acc = FactorAccessor(momentum_store)
    _, latest = momentum_store.price_date_bounds()
    assert acc._resolve_as_of(None) == latest


def test_as_of_future_clamps_down(momentum_store: FactorDataStore) -> None:
    acc = FactorAccessor(momentum_store)
    _, latest = momentum_store.price_date_bounds()
    assert acc._resolve_as_of(date(2099, 1, 1)) == latest  # never forward
    assert acc._resolve_as_of(_AS_OF) == _AS_OF  # a past date is honored


def test_accessor_universe(momentum_store: FactorDataStore) -> None:
    acc = FactorAccessor(momentum_store)
    u = acc.universe(_AS_OF)
    assert len(u) == 25
    assert all(t.startswith("MOM") for t in u)


def test_accessor_surface_is_read_only(momentum_store: FactorDataStore) -> None:
    """The accessor must not expose the raw store, the connection, or ingest
    methods — only the three read methods. This is the sandbox boundary."""
    acc = FactorAccessor(momentum_store)
    public = {a for a in dir(acc) if not a.startswith("_")}
    assert public == {"momentum_scores", "momentum_for", "universe", "sectors"}
    # no ingest/connection handle leaks through a public attribute
    for forbidden in ("con", "store", "ingest_sep", "ingest_tickers", "path"):
        assert not hasattr(acc, forbidden)
