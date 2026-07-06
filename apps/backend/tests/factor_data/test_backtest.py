"""Weekly cross-sectional momentum backtest: mark-to-market, delisting, PIT (P9 §3 §4.5)."""

from __future__ import annotations

from datetime import date

import pandas as pd
import pytest

from app.factor_data.backtest import (
    _iso_week_last_trading_days,
    _simulate,
    _vol_target_overlay,
    run_momentum_backtest,
)
from app.factor_data.store import FactorDataStore

from .conftest import build_momentum_frames

_START = date(2018, 7, 1)
_END = date(2020, 12, 31)


# ---- _simulate: hand-checked daily mark-to-market + final-price→cash -------------

def _two_name_store(tmp_path) -> tuple[FactorDataStore, list[date]]:
    """AAA flat at 100 for 5 days; DEAD rises 100→110→121 then delists after day 3."""
    days = [d.date() for d in pd.bdate_range("2020-01-06", periods=5)]
    rows = []
    for d in days:
        rows.append(dict(ticker="AAA", date=d.strftime("%Y-%m-%d"), open=100, high=100,
                         low=100, close=100, volume=1_000_000, closeadj=100.0,
                         closeunadj=100.0, lastupdated="2026-01-01"))
    dead_px = {days[0]: 100.0, days[1]: 110.0, days[2]: 121.0}  # delists after day 3
    for d, px in dead_px.items():
        rows.append(dict(ticker="DEAD", date=d.strftime("%Y-%m-%d"), open=px, high=px,
                         low=px, close=px, volume=1_000_000, closeadj=px,
                         closeunadj=px, lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "sim.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    return s, days


def test_simulate_marks_daily_and_freezes_delisted_to_cash(tmp_path) -> None:
    """★ Final price → cash: DEAD earns to its last price (day 3) then its sleeve
    freezes as cash; it is NOT dropped and NOT taken to zero."""
    store, days = _two_name_store(tmp_path)
    try:
        # rebalance at day0; segment = days 1..4. 50/50 AAA/DEAD, no costs.
        curve, holdings = _simulate(
            store, [days[0]], days, lambda d: {"AAA": 0.5, "DEAD": 0.5},
            initial_equity=100.0, turnover_cost_bps=0.0,
        )
        equities = [round(e, 4) for _, e in curve]
        # day1: 50 + 55 = 105; day2: 50 + 60.5 = 110.5; day3,4: DEAD frozen at 60.5
        assert equities == [105.0, 110.5, 110.5, 110.5]
        assert "DEAD" in holdings[0].tickers  # held, not excluded for delisting
        assert holdings[0].realized_return == pytest.approx(0.105)
    finally:
        store.close()


def test_simulate_delisting_realizes_decline(tmp_path) -> None:
    """★ The other sign of final-price→cash: a name that DECLINES into its last
    print realizes the negative return, then freezes as cash (Finding 9 — the
    bankruptcy/decline direction, not just the acquisition gap-up)."""
    days = [d.date() for d in pd.bdate_range("2020-01-06", periods=5)]
    rows = []
    for d in days:
        rows.append(dict(ticker="AAA", date=d.strftime("%Y-%m-%d"), open=100, high=100,
                         low=100, close=100, volume=1_000_000, closeadj=100.0,
                         closeunadj=100.0, lastupdated="2026-01-01"))
    drop_px = {days[0]: 100.0, days[1]: 90.0, days[2]: 81.0}  # declines, delists after day 3
    for d, px in drop_px.items():
        rows.append(dict(ticker="DROP", date=d.strftime("%Y-%m-%d"), open=px, high=px,
                         low=px, close=px, volume=1_000_000, closeadj=px,
                         closeunadj=px, lastupdated="2026-01-01"))
    s = FactorDataStore(db_path=str(tmp_path / "drop.duckdb"))
    s.ingest_sep(pd.DataFrame(rows))
    try:
        curve, holdings = _simulate(
            s, [days[0]], days, lambda d: {"AAA": 0.5, "DROP": 0.5},
            initial_equity=100.0, turnover_cost_bps=0.0,
        )
        equities = [round(e, 4) for _, e in curve]
        # day1: 50 + 45 = 95; day2: 50 + 40.5 = 90.5; day3,4: DROP frozen at 40.5
        assert equities == [95.0, 90.5, 90.5, 90.5]
        assert holdings[0].realized_return == pytest.approx(-0.095)  # negative — realized the decline
    finally:
        s.close()


def test_simulate_turnover_cost_charged(tmp_path) -> None:
    store, days = _two_name_store(tmp_path)
    try:
        # 100 bps one-way turnover on full deploy (prev book empty → turnover 0.5)
        curve, _ = _simulate(
            store, [days[0]], days, lambda d: {"AAA": 1.0},
            initial_equity=100.0, turnover_cost_bps=100.0,
        )
        # AAA is flat, so equity == post-cost equity = 100 * (1 - 0.01*0.5) = 99.5
        assert curve[-1][1] == pytest.approx(99.5)
    finally:
        store.close()


# ---- rebalance-date math --------------------------------------------------------

def test_iso_week_last_trading_days() -> None:
    days = [d.date() for d in pd.bdate_range("2020-01-01", "2020-01-31")]
    rebal = _iso_week_last_trading_days(days)
    # each rebalance is the last trading day of its ISO week (Fridays here)
    for d in rebal:
        assert d.weekday() == 4  # Friday — last bday of these full weeks
    assert rebal == sorted(rebal)


# ---- end-to-end over the synthetic momentum cohort ------------------------------

@pytest.fixture
def bt_store(tmp_path) -> FactorDataStore:
    sep, tk = build_momentum_frames()
    s = FactorDataStore(db_path=str(tmp_path / "bt.duckdb"))
    s.ingest_sep(sep)
    s.ingest_tickers(tk)
    yield s
    s.close()


def test_backtest_runs_top_quintile(bt_store: FactorDataStore) -> None:
    r = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    assert len(r.rebalances) > 50
    assert len(r.equity_curve) == len(r.baseline_curve) > 0
    # top quintile of 25 names = 5; the highest-growth names lead
    assert len(r.holdings[0].tickers) == 5
    assert "MOM24" in r.holdings[0].tickers
    # momentum book (longs the winners) beats the symmetric equal-weight baseline
    assert r.metrics.total_return > r.baseline_metrics.total_return


def test_backtest_top_n_absolute_count(bt_store: FactorDataStore) -> None:
    """MOM-002: top_n selects an ABSOLUTE book size, overriding top_quantile.
    top_quantile=0.2 on 25 names would pick 5; top_n=3 pins it to 3 regardless."""
    r = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2, top_n=3)
    assert all(len(h.tickers) == 3 for h in r.holdings)
    assert r.config.top_n == 3
    # the top-3 are the strongest momentum names (subset of the top quintile)
    assert "MOM24" in r.holdings[0].tickers


def test_backtest_top_n_caps_at_universe(bt_store: FactorDataStore) -> None:
    """top_n larger than the scored cross-section is clamped to what exists —
    never raises, never pads with phantom names."""
    r = run_momentum_backtest(bt_store, _START, _END, top_n=1000)
    assert all(1 <= len(h.tickers) <= 25 for h in r.holdings)


def test_backtest_rejects_bad_top_n(bt_store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        run_momentum_backtest(bt_store, _START, _END, top_n=0)


def test_backtest_deterministic(bt_store: FactorDataStore) -> None:
    a = run_momentum_backtest(bt_store, _START, _END)
    b = run_momentum_backtest(bt_store, _START, _END)
    assert a.equity_curve == b.equity_curve
    assert a.metrics == b.metrics
    assert a.baseline_curve == b.baseline_curve


def test_backtest_no_lookahead_prefix_matches(bt_store: FactorDataStore) -> None:
    """★ A backtest to an earlier end == the prefix of one run to a later end:
    extending the store with later data never moves a historical equity point."""
    early = run_momentum_backtest(bt_store, _START, date(2019, 12, 31))
    late = run_momentum_backtest(bt_store, _START, _END)
    cutoff = date(2019, 12, 31)
    late_prefix = [(d, e) for d, e in late.equity_curve if d <= cutoff]
    assert early.equity_curve == late_prefix


def test_backtest_survivorship_winner_delists_is_held(tmp_path) -> None:
    """★ A top-quintile winner that delists mid-backtest is held while alive and
    realizes final-price→cash — not silently dropped (the §1/§2 bias, on the
    holding side)."""
    sep, tk = build_momentum_frames()
    # Truncate MOM24 (the top winner): delist it after 2019-06-28.
    cut = pd.Timestamp("2019-06-28")
    sep = sep[~((sep["ticker"] == "MOM24") & (pd.to_datetime(sep["date"]) > cut))]
    tk.loc[tk["ticker"] == "MOM24", "lastpricedate"] = "2019-06-28"
    tk.loc[tk["ticker"] == "MOM24", "isdelisted"] = "Y"

    s = FactorDataStore(db_path=str(tmp_path / "surv.duckdb"))
    try:
        s.ingest_sep(sep)
        s.ingest_tickers(tk)
        r = run_momentum_backtest(s, _START, _END, top_quantile=0.2)
        # MOM24 was a top winner and tradeable early → it MUST appear in an early
        # holding (a survivorship-biased backtest using only end-of-data listings
        # would never include it).
        early_held = any("MOM24" in h.tickers for h in r.holdings if h.rebalance_date <= cut.date())
        assert early_held
        # ...and after its delisting it drops out of later holdings.
        late_held = any("MOM24" in h.tickers for h in r.holdings if h.rebalance_date > date(2019, 9, 1))
        assert not late_held
        assert r.metrics.total_return > 0  # the book still completes coherently
    finally:
        s.close()


def test_backtest_rejects_bad_params(bt_store: FactorDataStore) -> None:
    with pytest.raises(ValueError):
        run_momentum_backtest(bt_store, _START, _END, delisting="haircut")
    with pytest.raises(ValueError):
        run_momentum_backtest(bt_store, _START, _END, top_quantile=0.0)


def test_backtest_empty_window_returns_empty(bt_store: FactorDataStore) -> None:
    r = run_momentum_backtest(bt_store, date(2030, 1, 1), date(2030, 12, 31))
    assert r.equity_curve == []
    assert r.metrics.total_return == 0.0


# ---- vol-target overlay (review Priority 1) ------------------------------------

def test_vol_target_overlay_dampens_high_vol() -> None:
    """★ The overlay shrinks day-over-day swings of a high-vol curve once the EWMA
    warms up (a low target vs. big ±swings → small gross exposure)."""
    days = [d.date() for d in pd.bdate_range("2020-01-06", periods=60)]
    eq, curve = 100.0, []
    for i, d in enumerate(days):
        eq *= 1.08 if i % 2 == 0 else 0.93  # violent alternating returns
        curve.append((d, eq))
    scaled = _vol_target_overlay(curve, vol_target_annual=0.05, span=10, initial_equity=100.0)
    assert len(scaled) == len(curve)

    def _abs_rets(c: list[tuple[date, float]]) -> list[float]:
        v = [e for _, e in c]
        return [abs(v[i] / v[i - 1] - 1.0) for i in range(1, len(v))]

    half = len(curve) // 2  # compare the post-warm-up tail
    assert sum(_abs_rets(scaled)[half:]) < sum(_abs_rets(curve)[half:])


def test_vol_target_overlay_no_lookahead() -> None:
    """The scale for day t uses returns strictly before t, so the overlay on a
    prefix equals the prefix of the overlay on the full curve."""
    days = [d.date() for d in pd.bdate_range("2020-01-06", periods=40)]
    eq, curve = 100.0, []
    for i, d in enumerate(days):
        eq *= 1.05 if i % 3 else 0.97
        curve.append((d, eq))
    full = _vol_target_overlay(curve, vol_target_annual=0.10, span=10, initial_equity=100.0)
    prefix = _vol_target_overlay(curve[:25], vol_target_annual=0.10, span=10, initial_equity=100.0)
    assert [round(e, 8) for _, e in prefix] == [round(e, 8) for _, e in full[:25]]


def test_backtest_vol_overlay_optional_and_additive(bt_store: FactorDataStore) -> None:
    base = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2)
    assert base.vol_scaled_curve == [] and base.vol_scaled_metrics is None

    scaled = run_momentum_backtest(bt_store, _START, _END, top_quantile=0.2,
                                   vol_target_annual=0.10, vol_ewma_span=20)
    assert len(scaled.vol_scaled_curve) == len(scaled.equity_curve) > 0
    assert scaled.vol_scaled_metrics is not None
    # the overlay is purely additive — the core book curve is byte-identical.
    assert scaled.equity_curve == base.equity_curve
