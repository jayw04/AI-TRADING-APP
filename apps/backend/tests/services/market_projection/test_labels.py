"""MKT-PROJ-001 labeler tests (pre-registration §2): threshold math, PIT, targets."""

from __future__ import annotations

from datetime import date, timedelta

import pandas as pd
import pytest

from app.services.market_projection import labels as lb
from app.services.market_projection.schemas import Label


def _daily(n: int = 40, close: float = 100.0, rng: float = 1.0) -> pd.DataFrame:
    """n flat sessions ending 2026-07-01: close=100, high/low = ±rng/2."""
    days = [date(2026, 7, 1) - timedelta(days=i) for i in range(n * 2)]
    days = sorted(d for d in days if d.weekday() < 5)[-n:]
    return pd.DataFrame(
        {"open": close, "high": close + rng / 2, "low": close - rng / 2,
         "close": close, "volume": 1_000_000.0},
        index=days,
    )


def test_atr_pct_flat_series() -> None:
    df = _daily(rng=1.0)  # TR = 1.0 on a 100 close → ATR20_pct = 1.0
    assert lb.atr_pct_through(df, df.index[-1]) == pytest.approx(1.0)


def test_threshold_floor_binds_when_atr_small() -> None:
    df = _daily(rng=0.4)  # ATR 0.4% → 0.5×ATR = 0.2% < 0.60% floor
    assert lb.threshold_pct_for(df, df.index[-1]) == pytest.approx(0.60)


def test_threshold_scales_with_atr() -> None:
    df = _daily(rng=3.0)  # ATR 3% → threshold 1.5%
    assert lb.threshold_pct_for(df, df.index[-1] + timedelta(days=1)) == pytest.approx(1.5)


def test_threshold_is_pit_day_t_bar_cannot_move_it() -> None:
    """The frozen PIT rule: day t's own (even absurd) bar never enters day t's threshold."""
    df = _daily(rng=1.0)
    day = df.index[-1]
    base = lb.threshold_pct_for(df, day)
    poisoned = df.copy()
    poisoned.loc[day, ["high", "low"]] = [200.0, 50.0]  # massive day-t range
    assert lb.threshold_pct_for(poisoned, day) == base


def test_labels_at_boundaries() -> None:
    assert lb.label_for(0.75, 0.75) is Label.UP        # >= threshold → UP
    assert lb.label_for(-0.75, 0.75) is Label.DOWN
    assert lb.label_for(0.7499, 0.75) is Label.NEUTRAL
    assert lb.label_for(-0.7499, 0.75) is Label.NEUTRAL


def test_preopen_target_is_open_to_close() -> None:
    """The v0.2 leakage fix: the pre-open target must ignore the overnight gap."""
    df = _daily()
    day = df.index[-1]
    df.loc[day, "open"] = 102.0   # +2% gap...
    df.loc[day, "close"] = 101.0  # ...but intraday open→close = −0.98%
    assert lb.preopen_realized_return(df, day) == pytest.approx(-0.9804, abs=1e-3)


def test_preclose_target_is_next_session_close_vs_close() -> None:
    df = _daily()
    t, t1 = df.index[-2], df.index[-1]
    df.loc[t1, "close"] = 102.0
    assert lb.preclose_realized_return(df, t) == pytest.approx(2.0)
    # the most recent session has no t+1 yet → label not matured
    assert lb.preclose_realized_return(df, t1) is None


def test_insufficient_history_returns_none() -> None:
    df = _daily(n=10)
    assert lb.threshold_pct_for(df, df.index[-1]) is None
