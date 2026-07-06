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

from app.factor_data.regime import market_breadth, vix_percentile
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


# ---- VIX percentile (P10 §5, ADR 0022) -----------------------------------------

_VLB = 20  # small VIX lookback so test series stay short


def _vix_store(tmp_path, closes: list[float], *, tag: str = "v", symbol: str = "^VIX"):
    """A store with an ^VIX series of the given daily closes. Returns (store, as_of)."""
    bdays = pd.bdate_range("2020-01-02", periods=len(closes))
    df = pd.DataFrame({
        "symbol": symbol,
        "date": [d.strftime("%Y-%m-%d") for d in bdays],
        "close": closes,
        "lastupdated": "2026-01-01",
    })
    s = FactorDataStore(db_path=str(tmp_path / f"{tag}.duckdb"))
    s.ingest_index_prices(df)
    return s, bdays[-1].date()


def test_index_prices_roundtrip(tmp_path) -> None:
    """ingest_index_prices → get_index_series returns the closes ascending by date."""
    s, asof = _vix_store(tmp_path, [10.0, 11.0, 12.0], tag="rt")
    try:
        df = s.get_index_series("^VIX", date(2020, 1, 1), asof)
        assert list(df["close"]) == [10.0, 11.0, 12.0]
        assert s.row_count("index_prices") == 3
    finally:
        s.close()


def test_vix_percentile_latest_high_is_one(tmp_path) -> None:
    """Latest close is a fresh high → the whole prior window is below → percentile 1.0."""
    s, asof = _vix_store(tmp_path, [float(x) for x in range(1, 26)], tag="hi")
    try:
        assert vix_percentile(s, asof, lookback_days=_VLB) == 1.0
    finally:
        s.close()


def test_vix_percentile_latest_low_is_zero(tmp_path) -> None:
    """Latest close is the minimum → nothing below it → percentile 0.0."""
    s, asof = _vix_store(tmp_path, [float(x) for x in range(25, 0, -1)], tag="lo")
    try:
        assert vix_percentile(s, asof, lookback_days=_VLB) == 0.0
    finally:
        s.close()


def test_vix_percentile_mid(tmp_path) -> None:
    """Window 1..20, latest 10.5 → 10 of 20 prior closes below → 0.5."""
    s, asof = _vix_store(tmp_path, [float(x) for x in range(1, 21)] + [10.5], tag="mid")
    try:
        assert vix_percentile(s, asof, lookback_days=_VLB) == 0.5
    finally:
        s.close()


def test_vix_percentile_none_when_short(tmp_path) -> None:
    """Fewer than lookback_days+1 closes → None (fail open; e.g. pre-FMP-depth dates)."""
    s, asof = _vix_store(tmp_path, [10.0] * 10, tag="short")
    try:
        assert vix_percentile(s, asof, lookback_days=_VLB) is None
    finally:
        s.close()


def test_vix_percentile_none_when_absent(tmp_path) -> None:
    """No series for the symbol → None (fail open)."""
    s, asof = _vix_store(tmp_path, [float(x) for x in range(1, 26)], tag="absent")
    try:
        assert vix_percentile(s, asof, symbol="^NOPE", lookback_days=_VLB) is None
    finally:
        s.close()


def test_vix_percentile_is_point_in_time(tmp_path) -> None:
    """A future spike must not leak: flat 10s through as_of, big spikes AFTER it →
    evaluated at the pre-spike date, percentile sees only the flat history (0.0)."""
    closes = [10.0] * 21 + [100.0, 100.0, 100.0, 100.0]
    bdays = pd.bdate_range("2020-01-02", periods=len(closes))
    df = pd.DataFrame({"symbol": "^VIX", "date": [d.strftime("%Y-%m-%d") for d in bdays],
                       "close": closes, "lastupdated": "2026-01-01"})
    s = FactorDataStore(db_path=str(tmp_path / "pit.duckdb"))
    s.ingest_index_prices(df)
    try:
        asof = bdays[20].date()  # the last flat day, before the spikes
        assert vix_percentile(s, asof, lookback_days=_VLB) == 0.0
    finally:
        s.close()
