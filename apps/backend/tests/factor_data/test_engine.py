"""Cross-sectional momentum engine: ordering, PIT no-look-ahead, guards (P9 §2 §4.4)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.engine import FactorUnavailable, momentum_scores
from app.factor_data.store import FactorDataStore

from .conftest import build_momentum_frames

_AS_OF = date(2020, 6, 30)


def test_momentum_scores_shape_and_order(momentum_store: FactorDataStore) -> None:
    df = momentum_scores(momentum_store, _AS_OF, n=500)
    assert list(df.columns) == ["momentum", "winsorized", "zscore", "rank", "score"]
    assert len(df) == 25
    # score == winsorized z-score; sorted descending
    assert list(df["score"]) == sorted(df["score"], reverse=True)
    # MOM24 has the highest growth → highest momentum → top of the frame
    assert df.index[0] == "MOM24"
    assert df.index[-1] == "MOM00"
    # zscore of the winsorized cross-section is ~mean 0
    assert df["zscore"].mean() == pytest.approx(0.0, abs=1e-9)


def test_momentum_scores_below_min_names_raises(store: FactorDataStore) -> None:
    # the §1 `store` fixture has only 5 names < min_names=20
    with pytest.raises(FactorUnavailable):
        momentum_scores(store, date(2015, 6, 30))


def test_momentum_scores_reproducible(momentum_store: FactorDataStore) -> None:
    a = momentum_scores(momentum_store, _AS_OF)
    b = momentum_scores(momentum_store, _AS_OF)
    pd.testing.assert_frame_equal(a, b)


def test_no_lookahead_future_prices_do_not_change_past_scores(tmp_path) -> None:
    """★ The §2 honesty hinge: a score as of D is identical whether or not the
    store also contains prices dated after D."""
    sep_full, tickers = build_momentum_frames(price_end=pd.Timestamp("2020-12-31"))
    sep_trunc, _ = build_momentum_frames(price_end=pd.Timestamp(_AS_OF))

    full = FactorDataStore(db_path=str(tmp_path / "full.duckdb"))
    trunc = FactorDataStore(db_path=str(tmp_path / "trunc.duckdb"))
    try:
        full.ingest_sep(sep_full)
        full.ingest_tickers(tickers)
        trunc.ingest_sep(sep_trunc)
        trunc.ingest_tickers(tickers)

        scores_full = momentum_scores(full, _AS_OF)
        scores_trunc = momentum_scores(trunc, _AS_OF)
        pd.testing.assert_frame_equal(scores_full, scores_trunc)
    finally:
        full.close()
        trunc.close()
