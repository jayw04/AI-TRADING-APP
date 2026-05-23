"""Reproducibility: same strategy + same bars + same params → same metrics.

Locks down backtest math against accidental nondeterminism (dict iteration
order, hash randomization, floating-point reordering, etc.). If this test
flakes, do not retry — find the source. It's a real bug.

Skips if the AAPL fixture parquets aren't committed yet (run
``scripts/generate_fixture_bars.py`` to populate).
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest

from app.indicators import IndicatorComputer
from app.strategies import Backtester
from app.strategies.backtest_models import BacktestConfig
from strategies_user.examples.rsi_meanreversion import RsiMeanReversion

FIXTURE_DIR = Path(__file__).resolve().parents[1] / "fixtures" / "bars"
FIXTURE_DAYS = ["2025-11-03", "2025-11-04", "2025-11-05"]


def _load_fixture_days() -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    for d in FIXTURE_DAYS:
        path = FIXTURE_DIR / f"AAPL_{d}_1Min.parquet"
        if not path.exists():
            pytest.skip(
                f"Fixture not present: {path}. "
                "Run apps/backend/scripts/generate_fixture_bars.py AAPL "
                f"{FIXTURE_DAYS[0]} (etc.) — see P2 Session 3 §3.5."
            )
        frames.append(pd.read_parquet(path))
    df = pd.concat(frames).reset_index(drop=True)
    df["t"] = pd.to_datetime(df["t"], utc=True)
    return df.sort_values("t").reset_index(drop=True)


async def test_reference_strategy_backtest_is_reproducible():
    bars = _load_fixture_days()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)

    indicator_computer = IndicatorComputer()
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=UTC),
        end=datetime(2025, 11, 6, tzinfo=UTC),
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
        timeframe="1Min",
        seed=42,
    )

    m1, t1, e1 = await harness.run(RsiMeanReversion, ["AAPL"], config)
    m2, t2, e2 = await harness.run(RsiMeanReversion, ["AAPL"], config)

    assert m1.total_return == m2.total_return
    assert m1.sharpe_ratio == m2.sharpe_ratio
    assert m1.max_drawdown == m2.max_drawdown
    assert m1.win_rate == m2.win_rate
    assert m1.trade_count == m2.trade_count
    assert m1.starting_equity == m2.starting_equity
    assert m1.ending_equity == m2.ending_equity

    assert len(t1) == len(t2)
    for a, b in zip(t1, t2, strict=False):
        assert a.symbol == b.symbol
        assert a.entry_ts == b.entry_ts
        assert a.exit_ts == b.exit_ts
        assert abs((a.entry_price or 0) - (b.entry_price or 0)) < 1e-9
        assert abs((a.exit_price or 0) - (b.exit_price or 0)) < 1e-9
        assert abs((a.pnl or 0) - (b.pnl or 0)) < 1e-9

    assert len(e1) == len(e2)
    if e1:
        assert abs(e1[-1].equity - e2[-1].equity) < 1e-9


async def test_reference_strategy_produces_some_metrics_shape():
    """Sanity: the reference strategy produces a well-formed metrics object
    on the fixture days. We deliberately don't lock specific PnL or trade
    counts here — those depend on the exact bars and would re-fail every
    time the fixture is regenerated. The point is to catch
    "metrics dict is None" or "sharpe_ratio is NaN" regressions."""
    bars = _load_fixture_days()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=bars)

    indicator_computer = IndicatorComputer()
    harness = Backtester(bar_cache=bar_cache, indicator_computer=indicator_computer)

    config = BacktestConfig(
        start=datetime(2025, 11, 3, tzinfo=UTC),
        end=datetime(2025, 11, 6, tzinfo=UTC),
        initial_equity=Decimal("100000"),
        slippage_bps=5.0,
    )

    metrics, _trades, _equity = await harness.run(RsiMeanReversion, ["AAPL"], config)

    assert metrics.starting_equity == 100000.0
    assert metrics.ending_equity > 0
    assert metrics.trade_count >= 0
    assert isinstance(metrics.sharpe_ratio, float)
    import math
    assert not math.isnan(metrics.sharpe_ratio)
    assert metrics.max_drawdown <= 0.0
