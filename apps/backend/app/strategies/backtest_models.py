"""Dataclasses used by the backtest harness.

These are the on-the-wire and in-DB shapes for metrics, trades, and equity
curves. The shape is deliberately conservative: scalars where possible,
ISO timestamp strings rather than datetimes for trivial JSON round-trip
into the ``BacktestResult`` JSON columns.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any


@dataclass
class BacktestConfig:
    """Parameters that drive a backtest run."""

    start: datetime
    end: datetime
    initial_equity: Decimal = Decimal("100000")
    slippage_bps: float = 5.0  # 0.05% of fill price
    commission_per_share: float = 0.0  # Alpaca paper has no commissions
    timeframe: str = "1Min"
    # Strategy-side params override (merged over the strategy's defaults).
    params: dict[str, Any] = field(default_factory=dict)
    seed: int = 42  # for any RNG inside the strategy or harness


@dataclass
class BacktestTrade:
    """One round-trip: entry fill → exit fill, with realized P&L."""

    symbol: str
    side: str  # 'long' | 'short'
    entry_ts: str
    entry_price: float
    exit_ts: str | None
    exit_price: float | None
    qty: float
    pnl: float | None
    duration_seconds: int | None  # wall-clock; includes non-trading gaps
    exit_reason: str | None  # 'exit_signal' | 'stop' | 'eod' | 'backtest_end'
    # Bars the position was open (master-symbol bars between entry and exit).
    # Skips overnight/weekend gaps, so it's the right "intraday vs swing" metric
    # where wall-clock duration over-counts (an EOD exit that fills next-open is
    # ~1 session of bars, not ~17h).
    bar_count_held: int | None = None
    # Phase 0A research instrumentation. MAE/MFE = worst/best price excursion DURING the hold,
    # as a signed fraction of entry (mae <= 0 adverse, mfe >= 0 favorable). time_to_entry_seconds
    # = seconds from the 09:30 ET session open to the entry fill. (META's stop-then-target shows
    # exactly why MAE/MFE matter — owner review, 2026-06-30.)
    mae: float | None = None
    mfe: float | None = None
    time_to_entry_seconds: int | None = None


@dataclass
class BacktestMetrics:
    """Standard performance metrics."""

    total_return: float  # final_equity / initial_equity - 1
    annualized_return: float
    sharpe_ratio: float  # daily returns × √252
    max_drawdown: float  # negative fraction, e.g. -0.123
    win_rate: float  # fraction of closed trades with pnl > 0
    profit_factor: float  # gross_profit / gross_loss; inf if no losses
    trade_count: int  # closed trades
    avg_win: float
    avg_loss: float
    avg_trade_duration_seconds: float
    starting_equity: float
    ending_equity: float
    # Phase 0A aggregates (means over closed trades; 0.0 when no trades).
    avg_mae: float = 0.0
    avg_mfe: float = 0.0
    avg_time_to_entry_seconds: float = 0.0
    # Phase 0B: Opportunity Funnel — distinct symbol-days reaching each stage
    # (universe -> qualified -> touched -> entered -> stopped / exited). Answers
    # "why did only 1 of N trade?" — a permanent research/dashboard KPI (owner review).
    opportunity_funnel: dict[str, int] = field(default_factory=dict)


@dataclass
class EquityPoint:
    t: str  # ISO timestamp
    equity: float


def metrics_to_dict(m: BacktestMetrics) -> dict[str, Any]:
    return asdict(m)


def trades_to_list(trades: list[BacktestTrade]) -> list[dict[str, Any]]:
    return [asdict(t) for t in trades]


def equity_to_list(points: list[EquityPoint]) -> list[dict[str, Any]]:
    return [asdict(p) for p in points]
