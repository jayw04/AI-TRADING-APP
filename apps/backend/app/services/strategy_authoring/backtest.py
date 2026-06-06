"""Auto-backtest of generated strategy code (P7 §3).

Direction Decision 2: never present generated code without a backtest. This
safety-validates the code (AST gate, BEFORE any execution), loads it through the
production ``StrategyLoader`` (from a temp file), runs a backtest on cached bars
over the strategy's own timeframe and a ~6-month window, and returns the metrics —
or, on syntax / safety / load / runtime / zero-trade failure, the failure. The
backtest uses the in-memory ``BacktestContext`` simulator, never a broker.
"""
from __future__ import annotations

import ast
import tempfile
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

import structlog

from app.services.strategy_authoring.code_safety import (
    UnsafeCodeError,
    validate_generated_code_tree,
)
from app.strategies import (
    BacktestConfig,
    Backtester,
    StrategyLoader,
    StrategyLoadError,
)
from app.strategies.backtest_models import BacktestMetrics

logger = structlog.get_logger(__name__)

BACKTEST_WINDOW_DAYS = 183  # ~6 months (owner pick — responsive over the interactive loop)


@dataclass(frozen=True)
class BacktestOutcome:
    status: str  # ok | no_trades | syntax_error | unsafe_code | load_error | runtime_error | unavailable
    metrics: dict[str, Any] | None
    trade_count: int
    error: str | None


def _outcome(status: str, *, error: str | None = None) -> BacktestOutcome:
    return BacktestOutcome(status=status, metrics=None, trade_count=0, error=error)


def _metrics_to_dict(m: BacktestMetrics) -> dict[str, Any]:
    return {
        "total_return": m.total_return,
        "annualized_return": m.annualized_return,
        "sharpe_ratio": m.sharpe_ratio,
        "max_drawdown": m.max_drawdown,
        "win_rate": m.win_rate,
        "profit_factor": m.profit_factor,
        "trade_count": m.trade_count,
        "starting_equity": m.starting_equity,
        "ending_equity": m.ending_equity,
    }


async def backtest_generated_code(
    *,
    code: str,
    bar_cache: Any,
    indicator_computer: Any,
    now: datetime | None = None,
) -> BacktestOutcome:
    """Validate + load + backtest generated code. Never raises — every failure is
    a status on the returned outcome."""
    if bar_cache is None or indicator_computer is None:
        return _outcome("unavailable", error="backtest data is not available")

    now = now or datetime.now(UTC)

    # 1. Parse (syntax) — distinct from the safety failure below.
    try:
        tree = ast.parse(code)
    except SyntaxError as exc:
        return _outcome("syntax_error", error=str(exc))

    # 2. Safety gate — runs BEFORE the loader exec's the module.
    try:
        validate_generated_code_tree(tree)
    except UnsafeCodeError as exc:
        logger.warning("generated_code_unsafe", reason=str(exc))
        return _outcome("unsafe_code", error=str(exc))

    # 3. Load through the production path (temp file → StrategyLoader).
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "gen_strategy.py"
        path.write_text(code, encoding="utf-8")
        try:
            cls = StrategyLoader(Path(tmp)).load("gen_strategy.py")
        except StrategyLoadError as exc:
            return _outcome("load_error", error=str(exc))

        symbols = list(cls.symbols or [])
        if not symbols:
            return _outcome("load_error", error="strategy declares no symbols")

        params = dict(cls.default_params or {})
        timeframe = str(params.get("timeframe", "1Min"))
        config = BacktestConfig(
            start=now - timedelta(days=BACKTEST_WINDOW_DAYS),
            end=now,
            initial_equity=Decimal("100000"),
            timeframe=timeframe,
            params=params,
        )

        # 4. Run (in-memory simulator; never a broker).
        try:
            metrics, _trades, _equity = await Backtester(
                bar_cache=bar_cache, indicator_computer=indicator_computer
            ).run(cls, symbols, config)
        except Exception as exc:  # noqa: BLE001 - any strategy bug → surface it
            logger.warning("generated_code_backtest_failed", error=str(exc))
            return _outcome("runtime_error", error=str(exc))

    status = "ok" if metrics.trade_count > 0 else "no_trades"
    return BacktestOutcome(
        status=status,
        metrics=_metrics_to_dict(metrics),
        trade_count=metrics.trade_count,
        error=None,
    )
