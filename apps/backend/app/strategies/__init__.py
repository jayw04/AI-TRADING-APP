"""Strategy framework.

User strategies subclass :class:`Strategy` and are loaded from
``apps/backend/strategies_user/``. They get a :class:`StrategyContext`
with safe accessors for market data, positions, order submission, and
signal logging.

ADR 0002 alignment: :meth:`StrategyContext.submit_order` dispatches
through :class:`app.orders.router.OrderRouter` — strategies have no
direct path to the broker adapter.

The backtest harness (:class:`Backtester` + :class:`BacktestContext`)
runs the same ``Strategy`` subclass against cached bars in a
deterministic in-memory simulation. Strategies don't know whether
they're running on paper or in backtest.
"""

from .backtest_models import (
    BacktestConfig,
    BacktestMetrics,
    BacktestTrade,
    EquityPoint,
)
from .backtester import Backtester, persist_backtest_result
from .base import Strategy
from .context import Bar, FillEvent, SignalEvent, StrategyContext
from .engine import StrategyEngine
from .loader import StrategyLoader, StrategyLoadError

__all__ = [
    "BacktestConfig",
    "BacktestMetrics",
    "BacktestTrade",
    "Backtester",
    "Bar",
    "EquityPoint",
    "FillEvent",
    "SignalEvent",
    "Strategy",
    "StrategyContext",
    "StrategyEngine",
    "StrategyLoader",
    "StrategyLoadError",
    "persist_backtest_result",
]
