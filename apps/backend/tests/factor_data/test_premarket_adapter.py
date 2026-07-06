"""SCAN-001 premarket-data gate — increment (A) adapter tests.

Covers the premarket-gapper → engine feature-panel mapping: real gap pass-through, the
premarket-vs-daily RVOL proxy, store-coverage joins, the drop rules for uncoverable names,
and that the produced rows flow correctly through the frozen engine's gates.
"""

from __future__ import annotations

from app.factor_data import candidate_engine as ce
from app.factor_data import premarket_adapter as pa


def _gapper(**kw: object) -> dict[str, object]:
    base = {"symbol": "AAA", "price": 50.0, "gap_pct": 8.0, "premarket_volume": 4_000_000}
    base.update(kw)
    return base


def _store(**kw: object) -> dict[str, object]:
    base = {"atr_pct": 4.0, "avg_volume": 1_000_000.0, "prev_dollar_vol": 100_000_000.0}
    base.update(kw)
    return base


def test_feature_row_uses_real_gap_and_rvol_proxy() -> None:
    row = pa.premarket_feature_row(_gapper(), _store())
    assert row is not None
    assert row["symbol"] == "AAA"
    assert row["gap_pct"] == 8.0                      # real premarket gap, passed through
    assert row["rvol"] == 4.0                         # 4,000,000 / 1,000,000 avg daily (proxy)
    assert row["atr_pct"] == 4.0                      # from the store
    assert row["price"] == 50.0
    assert row["dollar_vol"] == 100_000_000.0


def test_feature_row_gap_is_absolute() -> None:
    # a down-gap reads the same magnitude (matches the engine's |open − prev_close| convention)
    row = pa.premarket_feature_row(_gapper(gap_pct=-6.0), _store())
    assert row is not None and row["gap_pct"] == 6.0


def test_feature_row_drops_when_no_store_coverage() -> None:
    assert pa.premarket_feature_row(_gapper(), None) is None


def test_feature_row_drops_when_no_atr_or_price() -> None:
    assert pa.premarket_feature_row(_gapper(), _store(atr_pct=0.0)) is None   # no store ATR
    assert pa.premarket_feature_row(_gapper(price=0.0), _store()) is None     # no premarket price


def test_feature_row_missing_symbol_is_dropped() -> None:
    assert pa.premarket_feature_row({"price": 50.0}, _store()) is None


def test_feature_row_malformed_values_fail_soft() -> None:
    # non-numeric premarket fields degrade to 0 rather than raising into a live scan
    row = pa.premarket_feature_row(
        _gapper(gap_pct="n/a", premarket_volume=None), _store()
    )
    assert row is not None
    assert row["gap_pct"] == 0.0 and row["rvol"] == 0.0


def test_feature_row_passes_earnings_flag_through() -> None:
    row = pa.premarket_feature_row(_gapper(), _store(earnings_today=True))
    assert row is not None and row["earnings_today"] is True
    assert ce.is_eligible(row) is False   # the engine's safety exclusion still fires


def test_panel_joins_and_drops_uncovered_symbols() -> None:
    gappers = [
        _gapper(symbol="AAA"),
        _gapper(symbol="BBB", price=200.0),
        _gapper(symbol="ZZZ"),               # no store entry → dropped
    ]
    store_features = {
        "AAA": _store(),
        "BBB": _store(atr_pct=3.0),
        # ZZZ deliberately absent
    }
    panel = pa.premarket_panel(gappers, store_features)
    assert [r["symbol"] for r in panel] == ["AAA", "BBB"]


def test_panel_rows_flow_through_the_frozen_engine() -> None:
    # the adapter's output is exactly what select_candidates consumes
    gappers = [
        _gapper(symbol="STRONG", gap_pct=8.0, premarket_volume=4_000_000),   # Gap+RVOL+ATR
        _gapper(symbol="PENNY", price=4.0),                                  # ineligible (<$10)
        _gapper(symbol="QUIET", gap_pct=1.0, premarket_volume=500_000),      # no signal fires
    ]
    store_features = {
        "STRONG": _store(),
        "PENNY": _store(),
        "QUIET": _store(atr_pct=1.5),   # ATR below the 2% threshold → no opportunity signal fires
    }
    panel = pa.premarket_panel(gappers, store_features)
    out = ce.select_candidates(panel, top_n=10)
    assert [c.symbol for c in out] == ["STRONG"]      # only the real gapper is selected
    assert out[0].reason == "Gap + RVOL + ATR"


def test_panel_empty_inputs() -> None:
    assert pa.premarket_panel([], {}) == []


# ---- features_from_bars (the pure core of the historical store join, increment B) ----


def _bars(n: int, *, high: float = 102.0, low: float = 98.0, close: float = 100.0,
          volume: float = 1_000_000.0) -> list[dict[str, float]]:
    return [{"high": high, "low": low, "close": close, "volume": volume} for _ in range(n)]


def test_features_from_bars_computes_store_features() -> None:
    feat = pa.features_from_bars(_bars(21))
    assert feat is not None
    assert feat["atr_pct"] == 4.0                       # $4 range on a $100 close → 4%
    assert feat["avg_volume"] == 1_000_000.0
    assert feat["prev_dollar_vol"] == 100_000_000.0     # 100 close × 1,000,000 volume


def test_features_from_bars_needs_enough_history() -> None:
    assert pa.features_from_bars(_bars(10)) is None      # < ATR_N + 1 bars


def test_features_from_bars_zero_prev_close_is_safe() -> None:
    bars = _bars(21)
    bars[-1]["close"] = 0.0
    assert pa.features_from_bars(bars) is None


def test_features_from_bars_avg_volume_is_trailing_window() -> None:
    bars = _bars(25, volume=2_000_000.0)
    for b in bars[:5]:
        b["volume"] = 99_000_000.0   # old bars outside the 20-day window must not skew the avg
    feat = pa.features_from_bars(bars)
    assert feat is not None and feat["avg_volume"] == 2_000_000.0


def test_features_then_adapter_end_to_end() -> None:
    # the historical join (features_from_bars) feeds the gapper adapter cleanly
    store_feat = pa.features_from_bars(_bars(21))
    row = pa.premarket_feature_row(_gapper(), store_feat)
    assert row is not None and row["atr_pct"] == 4.0 and row["rvol"] == 4.0
