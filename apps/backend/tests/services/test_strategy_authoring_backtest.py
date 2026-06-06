"""P7 §3 — backtest_generated_code: validate → temp-file load → backtest → outcome."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock

import pandas as pd

from app.services.strategy_authoring.backtest import backtest_generated_code

NOW = datetime(2025, 11, 10, tzinfo=UTC)

_HEADER = """
from __future__ import annotations
from decimal import Decimal
from typing import Any, ClassVar
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Strategy
"""


def _strategy(body_on_bar: str) -> str:
    return _HEADER + f'''
class Gen(Strategy):
    name: ClassVar[str] = "gen"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["TEST"]
    schedule: ClassVar[str] = "event"
    default_params: ClassVar[dict[str, Any]] = {{"timeframe": "1Min"}}

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        self.n = 0

    async def on_bar(self, bar) -> None:
{body_on_bar}
'''


def _submit(side: str) -> str:
    return (
        'await self.ctx.submit_order(OrderRequest('
        f'user_id=0, account_id=0, symbol_ticker="TEST", side=OrderSide.{side}, '
        'qty=Decimal("10"), type=OrderType.MARKET, tif=TimeInForce.DAY, '
        'source_type=OrderSourceType.STRATEGY))'
    )


TRADING = _strategy(
    "        self.n += 1\n"
    "        if self.n == 2:\n"
    "            " + _submit("BUY") + "\n"
    "        elif self.n == 5:\n"
    "            " + _submit("SELL")
)
DO_NOTHING = _strategy("        self.n += 1")
RAISES = _strategy('        raise RuntimeError("boom")')


def _bars(count=10, start_price=100.0) -> pd.DataFrame:
    start = datetime(2025, 11, 3, 14, 30, tzinfo=UTC)
    rows = [{
        "t": start + timedelta(minutes=i), "o": start_price + i * 0.1,
        "h": start_price + i * 0.1 + 0.05, "l": start_price + i * 0.1 - 0.05,
        "c": start_price + i * 0.1 + 0.02, "v": 1000 + i,
    } for i in range(count)]
    return pd.DataFrame(rows)


def _harness():
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=_bars(10))
    return bar_cache, MagicMock()


async def test_valid_strategy_backtests_ok():
    bar_cache, ind = _harness()
    out = await backtest_generated_code(code=TRADING, bar_cache=bar_cache, indicator_computer=ind, now=NOW)
    assert out.status == "ok"
    assert out.trade_count >= 1
    assert out.metrics is not None
    assert "sharpe_ratio" in out.metrics


async def test_do_nothing_strategy_is_no_trades():
    bar_cache, ind = _harness()
    out = await backtest_generated_code(code=DO_NOTHING, bar_cache=bar_cache, indicator_computer=ind, now=NOW)
    assert out.status == "no_trades"
    assert out.trade_count == 0


async def test_runtime_error_surfaced():
    bar_cache, ind = _harness()
    out = await backtest_generated_code(code=RAISES, bar_cache=bar_cache, indicator_computer=ind, now=NOW)
    assert out.status == "runtime_error"
    assert "boom" in (out.error or "")


async def test_syntax_error():
    bar_cache, ind = _harness()
    out = await backtest_generated_code(code="def oops(:\n  pass", bar_cache=bar_cache, indicator_computer=ind, now=NOW)
    assert out.status == "syntax_error"


async def test_unsafe_code_blocked_before_load():
    bar_cache, ind = _harness()
    out = await backtest_generated_code(
        code="import os\nos.system('echo hi')", bar_cache=bar_cache, indicator_computer=ind, now=NOW
    )
    assert out.status == "unsafe_code"
    assert "os" in (out.error or "")


async def test_unavailable_when_no_bar_cache():
    out = await backtest_generated_code(code=TRADING, bar_cache=None, indicator_computer=None, now=NOW)
    assert out.status == "unavailable"
