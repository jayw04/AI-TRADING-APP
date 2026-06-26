"""LOW-001 factor engine — `low_vol_scores` cross-section.

Builds a small, deterministic store whose tickers have *different realized
volatilities* (the conftest stores use constant-growth paths → zero return
variance, so they can't exercise this), and asserts the engine ranks the calmest
names highest and refuses a degenerate cross-section.
"""

from __future__ import annotations

import random
from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.factors.low_vol import low_vol_scores
from app.factor_data.store import FactorDataStore

_START = pd.Timestamp("2019-01-01")
_END = pd.Timestamp("2020-12-31")
_N = 24  # ≥ engine min_names (20)
_AS_OF = date(2020, 12, 1)


def _build_volatile_frames() -> tuple[pd.DataFrame, pd.DataFrame]:
    """`_N` random-walk names with monotonically increasing daily-return σ.

    Ticker ``VOL{i}`` has per-day return σ = 0.004 + 0.002·i, so VOL00 is the
    calmest and VOL{N-1} the most volatile. Seeded → deterministic ranking."""
    bdays = pd.bdate_range(_START, _END)
    rng = random.Random(17)
    sep_rows, tk_rows = [], []
    for i in range(_N):
        ticker = f"VOL{i:02d}"
        sigma = 0.004 + 0.002 * i
        price = 100.0
        for d in bdays:
            price *= 1.0 + rng.gauss(0.0, sigma)
            price = max(price, 1.0)  # keep strictly positive
            sep_rows.append(
                dict(
                    ticker=ticker, date=d.strftime("%Y-%m-%d"),
                    open=price, high=price, low=price, close=price,
                    volume=2_000_000, closeadj=price, closeunadj=price,
                    lastupdated="2026-01-01",
                )
            )
        tk_rows.append(
            dict(
                ticker=ticker, name=f"{ticker} Inc", exchange="NYSE",
                category="Domestic Common Stock", isdelisted="N",
                firstpricedate="2018-01-01", lastpricedate="2026-01-01",
                lastupdated="2026-01-01",
            )
        )
    return pd.DataFrame(sep_rows), pd.DataFrame(tk_rows)


@pytest.fixture
def volatile_store(tmp_path) -> FactorDataStore:
    sep, tickers = _build_volatile_frames()
    s = FactorDataStore(db_path=str(tmp_path / "lowvol.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tickers)
    yield s
    s.close()


def test_low_vol_scores_ranks_calmest_first(volatile_store: FactorDataStore) -> None:
    df = low_vol_scores(volatile_store, _AS_OF, n=50)
    # Shape: indexed by ticker, [volatility, score], score = −volatility.
    assert list(df.columns) == ["volatility", "score"]
    assert (df["volatility"] > 0).all()
    assert (df["score"] == -df["volatility"]).all()
    # Sorted by score descending == volatility ascending (calmest first).
    assert df["score"].is_monotonic_decreasing
    # The constructed σ ordering survives: the calmest name leads, the wildest trails.
    assert df.index[0] == "VOL00"
    assert df.index[-1] == f"VOL{_N - 1:02d}"


def test_low_vol_scores_deterministic(volatile_store: FactorDataStore) -> None:
    a = low_vol_scores(volatile_store, _AS_OF, n=50)
    b = low_vol_scores(volatile_store, _AS_OF, n=50)
    pd.testing.assert_frame_equal(a, b)


def test_low_vol_scores_raises_on_thin_cross_section(volatile_store: FactorDataStore) -> None:
    """Fewer than min_names valid vols → FactorUnavailable (don't rank noise)."""
    with pytest.raises(FactorUnavailable):
        low_vol_scores(volatile_store, _AS_OF, n=5)
