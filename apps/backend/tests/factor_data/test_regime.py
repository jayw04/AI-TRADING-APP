"""Market-breadth regime signal (P10 §5, ADR 0022).

Breadth = the fraction of the as-of construction universe trading above its MA. Built
over controlled synthetic stores where each name is monotonically rising or falling, so
the expected fraction is exact. Pins: the extremes (all-up → 1.0, all-down → 0.0), a
known mixed fraction, fail-open (None) on a thin cross-section or below the price floor,
and determinism.
"""

from __future__ import annotations

from datetime import date

import pandas as pd

from app.factor_data.regime import market_breadth
from app.factor_data.store import FactorDataStore

_MA = 20  # small MA window so the synthetic history can be short


def _breadth_store(tmp_path, growths: list[float], *, days: int = 40, tag: str = "b"):
    """A store of ``len(growths)`` names, each a geometric path with the given daily
    growth (>1 rises above its MA, <1 falls below). Returns (store, as_of)."""
    bdays = pd.bdate_range("2020-01-02", periods=days)
    sep, tk = [], []
    for i, g in enumerate(growths):
        ticker = f"N{i:02d}"
        price = 100.0
        for d in bdays:
            sep.append(dict(ticker=ticker, date=d.strftime("%Y-%m-%d"), open=price, high=price,
                            low=price, close=price, volume=1_000_000, closeadj=price,
                            closeunadj=price, lastupdated="2026-01-01"))
            price *= g
        tk.append(dict(ticker=ticker, name=f"{ticker} Inc", exchange="NYSE",
                       category="Domestic Common Stock", isdelisted="N",
                       firstpricedate="2019-01-01", lastpricedate="2026-01-01",
                       lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / f"{tag}.duckdb"))
    s.ingest_sep(pd.DataFrame(sep))
    s.ingest_tickers(pd.DataFrame(tk))
    return s, bdays[-1].date()


def test_breadth_all_above_is_one(tmp_path) -> None:
    s, asof = _breadth_store(tmp_path, [1.01] * 25, tag="up")
    try:
        assert market_breadth(s, asof, n=25, ma_days=_MA) == 1.0
    finally:
        s.close()


def test_breadth_all_below_is_zero(tmp_path) -> None:
    s, asof = _breadth_store(tmp_path, [0.99] * 25, tag="down")
    try:
        assert market_breadth(s, asof, n=25, ma_days=_MA) == 0.0
    finally:
        s.close()


def test_breadth_mixed_fraction(tmp_path) -> None:
    """13 rising + 12 falling of 25 → breadth 13/25."""
    s, asof = _breadth_store(tmp_path, [1.01] * 13 + [0.99] * 12, tag="mix")
    try:
        assert market_breadth(s, asof, n=25, ma_days=_MA) == 13 / 25
    finally:
        s.close()


def test_breadth_none_when_thin(tmp_path) -> None:
    """Fewer valid names than min_names → None (fail open; a 5-name breadth is noise)."""
    s, asof = _breadth_store(tmp_path, [1.01] * 5, tag="thin")
    try:
        assert market_breadth(s, asof, n=25, ma_days=_MA, min_names=20) is None
    finally:
        s.close()


def test_breadth_none_below_floor(tmp_path) -> None:
    """as_of before the price-history floor → no PIT universe → None (fail open)."""
    s, _ = _breadth_store(tmp_path, [1.01] * 25, tag="floor")
    try:
        assert market_breadth(s, date(2000, 1, 1), n=25, ma_days=_MA) is None
    finally:
        s.close()


def test_breadth_none_when_history_too_short(tmp_path) -> None:
    """Names without ma_days+1 closes are not counted; if none qualify → None."""
    s, asof = _breadth_store(tmp_path, [1.01] * 25, days=10, tag="short")  # <ma_days+1
    try:
        assert market_breadth(s, asof, n=25, ma_days=_MA) is None
    finally:
        s.close()


def test_breadth_deterministic(tmp_path) -> None:
    s, asof = _breadth_store(tmp_path, [1.01] * 13 + [0.99] * 12, tag="det")
    try:
        a = market_breadth(s, asof, n=25, ma_days=_MA)
        b = market_breadth(s, asof, n=25, ma_days=_MA)
        assert a == b == 13 / 25
    finally:
        s.close()
