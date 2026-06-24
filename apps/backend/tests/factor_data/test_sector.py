"""SEC-001 factor engine (factors/sector.py) — sector scores + top-K baskets."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.factors.sector import sector_basket_weights, sector_scores
from app.factor_data.store import FactorDataStore

_AS_OF = date(2020, 3, 2)


def _store(tmp_path) -> FactorDataStore:
    """3 sectors × 8 names with distinct sector-level momentum: TECH fastest, ENERGY mid,
    HEALTH flat — so the top sector by mean momentum is unambiguous."""
    bdays = pd.bdate_range("2019-01-01", "2020-02-28")  # long enough for 252d-ish; use small lookback
    growth = {"TECH": 1.0015, "ENERGY": 1.0005, "HEALTH": 1.0000}
    sep, tk = [], []
    for sector, g in growth.items():
        for j in range(8):
            ticker = f"{sector[:2]}{j:02d}"
            price = 100.0
            for d in bdays:
                sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"), open=price, high=price,
                                low=price, close=price, volume=1_000_000, closeadj=price,
                                closeunadj=price, lastupdated="2026-01-01"))
                price *= g
            tk.append(dict(ticker=ticker, name=ticker, exchange="NYSE",
                           category="Domestic Common Stock", sector=sector, industry="I",
                           isdelisted="N", firstpricedate="2018-01-01", lastpricedate="2026-01-01",
                           lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "sector.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    return s


def test_sector_scores_rank_by_sector_momentum(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        df = sector_scores(s, _AS_OF, n=30, lookback_days=60, skip_days=0, min_names=20)
        # The 8 TECH names (TE..) share the highest sector score → they top the frame.
        assert all(t.startswith("TE") for t in df.index[:8])
    finally:
        s.close()


def test_sector_basket_weights_top_k_sum_to_one(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        w = sector_basket_weights(s, _AS_OF, n=30, k=1, lookback_days=60, skip_days=0, min_names=20)
        assert set(w) == {f"TE{j:02d}" for j in range(8)}   # only the top sector (TECH)
        assert abs(sum(w.values()) - 1.0) < 1e-9            # fully invested
        assert all(abs(v - 1 / 8) < 1e-9 for v in w.values())  # equal-weight within the sleeve
    finally:
        s.close()


def test_sector_basket_weights_k2_two_sectors(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        w = sector_basket_weights(s, _AS_OF, n=30, k=2, lookback_days=60, skip_days=0, min_names=20)
        sectors_held = {t[:2] for t in w}
        assert sectors_held == {"TE", "EN"}  # top-2 by mean momentum (TECH, ENERGY)
        assert abs(sum(w.values()) - 1.0) < 1e-9
        # sector-neutral: each sleeve is 1/2, so each name = (1/2)/8.
        assert all(abs(v - 0.5 / 8) < 1e-9 for v in w.values())
    finally:
        s.close()


def test_sector_scores_thin_raises(tmp_path) -> None:
    s = _store(tmp_path)
    try:
        with pytest.raises(FactorUnavailable):
            sector_scores(s, _AS_OF, n=5, lookback_days=60, skip_days=0, min_names=20)
    finally:
        s.close()
