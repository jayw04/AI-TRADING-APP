"""Golden test for IndicatorComputer.

Locks down structural properties of each indicator on a fixed bar file. Real
exact-value assertions are brittle across pandas-ta versions (floating-point
determinism is finicky); instead we assert invariants that any correct
implementation has to satisfy. Together they catch any garbage output from
a version upgrade.

The fixture parquet lives at ``tests/fixtures/bars/AAPL_2025-11-03_1Min.parquet``.
If it's missing, every test in this module skips with a clear hint to run
``scripts/generate_fixture_bars.py`` (which hits real Alpaca paper).
"""

from __future__ import annotations

from pathlib import Path

import pandas as pd
import pytest

from app.indicators import IndicatorComputer

FIXTURE = (
    Path(__file__).resolve().parents[1] / "fixtures" / "bars" / "AAPL_2025-11-03_1Min.parquet"
)


@pytest.fixture
def bars() -> pd.DataFrame:
    if not FIXTURE.exists():
        pytest.skip(
            f"Fixture not present: {FIXTURE}. "
            "Run apps/backend/scripts/generate_fixture_bars.py once with Alpaca creds "
            "and commit the parquet — see P2 Session 1 §1.5.1."
        )
    df = pd.read_parquet(FIXTURE)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df


def _synthetic_uptrend(n: int = 60) -> pd.DataFrame:
    """Self-contained ascending-close bars (no fixture needed)."""
    t = pd.date_range("2025-01-01", periods=n, freq="D", tz="UTC")
    c = pd.Series(range(100, 100 + n), dtype="float64")
    return pd.DataFrame(
        {"t": t, "o": c, "h": c + 1.0, "l": c - 1.0, "c": c, "v": [1000.0] * n}
    )


def test_ema20_and_ema50_computed() -> None:
    """P5.5 §2 added EMA20/EMA50 so the morning brief can honor a user's
    'ema_relationship: 20>50' threshold. In a clean uptrend the shorter EMA
    tracks recent (higher) prices, so EMA20 > EMA50."""
    bars = _synthetic_uptrend(60)
    out = IndicatorComputer().compute(
        bars, names=["EMA20", "EMA50"], symbol="X", timeframe="1Day"
    )
    ema20 = out["EMA20"].dropna().iloc[-1]
    ema50 = out["EMA50"].dropna().iloc[-1]
    assert ema20 == ema20 and ema50 == ema50  # finite (not NaN)
    assert ema20 > ema50


def test_ema20_ema50_in_core_indicators() -> None:
    from app.indicators import CORE_INDICATORS

    assert "EMA20" in CORE_INDICATORS
    assert "EMA50" in CORE_INDICATORS


def test_rsi_latest_in_range(bars: pd.DataFrame) -> None:
    out = IndicatorComputer().compute(
        bars, names=["RSI14"], symbol="AAPL", timeframe="1Min"
    )
    last = out["RSI14"].dropna().iloc[-1]
    # RSI is mathematically in [0, 100]; anything outside is broken.
    assert 0.0 <= last <= 100.0


def test_sma200_equals_simple_mean_of_last_200_closes(bars: pd.DataFrame) -> None:
    if len(bars) < 200:
        pytest.skip("Need at least 200 bars for SMA200")
    out = IndicatorComputer().compute(
        bars, names=["SMA200"], symbol="AAPL", timeframe="1Min"
    )
    expected = bars["c"].tail(200).mean()
    actual = out["SMA200"].dropna().iloc[-1]
    assert abs(actual - expected) < 1e-6


def test_macd_returns_three_named_series(bars: pd.DataFrame) -> None:
    out = IndicatorComputer().compute(
        bars, names=["MACD"], symbol="AAPL", timeframe="1Min"
    )
    macd = out["MACD"]
    assert isinstance(macd, dict)
    assert set(macd.keys()) == {"macd", "signal", "hist"}
    for series in macd.values():
        assert isinstance(series, pd.Series)


def test_bb_mid_lies_between_lower_and_upper(bars: pd.DataFrame) -> None:
    out = IndicatorComputer().compute(
        bars, names=["BB"], symbol="AAPL", timeframe="1Min"
    )
    bb = out["BB"]
    assert set(bb.keys()) == {"bb_lower", "bb_mid", "bb_upper"}
    df = pd.DataFrame(bb).dropna()
    assert (df["bb_lower"] <= df["bb_mid"]).all()
    assert (df["bb_mid"] <= df["bb_upper"]).all()


def test_relvol20_is_positive(bars: pd.DataFrame) -> None:
    out = IndicatorComputer().compute(
        bars, names=["RELVOL20"], symbol="AAPL", timeframe="1Min"
    )
    rv = out["RELVOL20"].dropna()
    assert (rv > 0).all()


def test_unknown_indicator_raises() -> None:
    bars = pd.DataFrame(
        [
            {
                "t": pd.Timestamp("2025-11-03 14:30:00", tz="UTC"),
                "o": 100, "h": 100.5, "l": 99.5, "c": 100, "v": 1000,
            }
        ]
    )
    with pytest.raises(KeyError, match="Unknown indicator"):
        IndicatorComputer().compute(
            bars, names=["FNORD"], symbol="X", timeframe="1Min"
        )


def test_empty_bars_yields_empty_series() -> None:
    out = IndicatorComputer().compute(
        pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"]),
        names=["RSI14"],
        symbol="X",
        timeframe="1Min",
    )
    assert out["RSI14"].empty


def test_short_window_normalizes_pandas_ta_none(monkeypatch) -> None:
    """Regression: on some pandas-ta/numpy builds (the CI-resolved versions, not
    local) a window longer than the bar count makes ``ta.rsi``/``atr``/``sma``/
    ``ema``/``macd``/``bbands``/``vwap`` return ``None`` rather than an all-NaN
    series. The computer must normalize that to a *full-length* NaN series, not
    crash on ``.rename`` — the crash otherwise wedged the backtest worker job in
    'running'. Forcing the pandas-ta calls to ``None`` reproduces the CI build
    locally and pins the fix.

    The full-length (not empty) shape matters: it matches the warmup region of a
    real series so downstream ``.iloc[-1]`` behaves identically with or without
    enough data — which is exactly what the local pandas-ta build already does."""
    import pandas_ta as ta

    bars = _synthetic_uptrend(5)  # fewer rows than any indicator's window
    for fn in ("sma", "ema", "rsi", "atr", "macd", "bbands", "vwap"):
        monkeypatch.setattr(ta, fn, lambda *a, **k: None)

    names = ["SMA20", "EMA20", "RSI14", "ATR14", "MACD", "BB", "VWAP"]
    out = IndicatorComputer().compute(bars, names=names, symbol="X", timeframe="1Min")

    # Single-output → a full-length, all-NaN series (NOT the empty series the old
    # except-branch produced after the crash).
    for n in ("SMA20", "EMA20", "RSI14", "ATR14", "VWAP"):
        assert isinstance(out[n], pd.Series), n
        assert len(out[n]) == len(bars), n
        assert out[n].isna().all(), n

    # Multi-output → dict of full-length NaN series for each output.
    for n, keys in (
        ("MACD", {"macd", "signal", "hist"}),
        ("BB", {"bb_lower", "bb_mid", "bb_upper"}),
    ):
        assert set(out[n].keys()) == keys, n
        for s in out[n].values():
            assert len(s) == len(bars) and s.isna().all(), n


def test_memoization_returns_same_series_object(bars: pd.DataFrame) -> None:
    """Identity check: same call within the 60s TTL returns the cached
    series, not a recomputed one. This is how strategies pick up the same
    snapshot multiple times in the same tick without recomputing."""
    computer = IndicatorComputer()
    out1 = computer.compute(
        bars, names=["RSI14"], symbol="AAPL", timeframe="1Min"
    )
    out2 = computer.compute(
        bars, names=["RSI14"], symbol="AAPL", timeframe="1Min"
    )
    assert out1["RSI14"] is out2["RSI14"]
