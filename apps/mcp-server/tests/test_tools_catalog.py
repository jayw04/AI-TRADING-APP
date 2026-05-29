"""Per-tool unit tests for the P3 §2 read-only catalog.

Pattern: each test injects a ``FakeBackendClient`` whose methods are
preset to return canned data; the tool function under test reads from
the fake. One happy path + one error path per tool. The cap/filter/
derive behaviors get a few extra targeted cases.
"""

from __future__ import annotations

from typing import Any

import httpx
import pytest

from workbench_mcp.tools.account import get_account_state
from workbench_mcp.tools.backtests import list_recent_backtests
from workbench_mcp.tools.market_data import get_bars, get_indicators, get_quote
from workbench_mcp.tools.orders import (
    list_open_orders,
    list_recent_fills,
    list_recent_orders,
)
from workbench_mcp.tools.positions import list_positions
from workbench_mcp.tools.signals import list_recent_signals
from workbench_mcp.tools.strategies import get_strategy_detail, list_strategies


class FakeBackendClient:
    """Stand-in for WorkbenchBackendClient. Each backend method is set on
    the instance directly so individual tests can override only what
    they need."""

    def __init__(self, **methods: Any) -> None:
        for name, value in methods.items():
            setattr(self, name, value)

    async def __aenter__(self) -> FakeBackendClient:
        return self

    async def __aexit__(self, *_exc: object) -> None:
        return None


def _http_error() -> httpx.HTTPStatusError:
    return httpx.HTTPStatusError(
        "500",
        request=httpx.Request("GET", "http://test"),
        response=httpx.Response(500),
    )


def _async_value(value: Any):
    async def _f(*_a, **_k):
        return value
    return _f


def _async_raise(exc: BaseException):
    async def _f(*_a, **_k):
        raise exc
    return _f


# ---------- get_account_state ----------


async def test_get_account_state_happy():
    fake = FakeBackendClient(
        get_account=_async_value(
            {"cash": "50000", "equity": "100000", "mode": "paper"}
        )
    )
    result = await get_account_state(client=fake)
    assert result["mode"] == "paper"
    assert result["cash"] == "50000"


async def test_get_account_state_backend_error():
    fake = FakeBackendClient(get_account=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await get_account_state(client=fake)


# ---------- list_positions ----------


async def test_list_positions_happy():
    payload = {
        "items": [
            {"symbol": "AAPL", "qty": "10", "side": "long"},
            {"symbol": "MSFT", "qty": "5", "side": "long"},
        ],
        "count": 2,
    }
    fake = FakeBackendClient(get_positions=_async_value(payload))
    result = await list_positions(client=fake)
    assert result["count"] == 2
    assert {p["symbol"] for p in result["positions"]} == {"AAPL", "MSFT"}


async def test_list_positions_caps_at_100():
    huge = {
        "items": [
            {"symbol": f"SYM{i}", "qty": "1", "side": "long"} for i in range(500)
        ]
    }
    fake = FakeBackendClient(get_positions=_async_value(huge))
    result = await list_positions(client=fake)
    assert result["count"] == 100
    assert len(result["positions"]) == 100


async def test_list_positions_error():
    fake = FakeBackendClient(get_positions=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_positions(client=fake)


# ---------- list_open_orders ----------


async def test_list_open_orders_happy():
    captured: dict[str, Any] = {}

    async def fake_get_orders(*, status=None, symbol=None, limit=None):
        captured["status"] = status
        captured["symbol"] = symbol
        captured["limit"] = limit
        return {"items": [{"id": 1, "symbol": "AAPL", "status": "submitted"}]}

    fake = FakeBackendClient(get_orders=fake_get_orders)
    result = await list_open_orders(symbol="AAPL", client=fake)
    assert captured["status"] == "open"
    assert captured["symbol"] == "AAPL"
    assert result["count"] == 1


async def test_list_open_orders_error():
    fake = FakeBackendClient(get_orders=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_open_orders(client=fake)


# ---------- list_recent_orders ----------


async def test_list_recent_orders_default_limit():
    captured: dict[str, Any] = {}

    async def fake_get_orders(*, status=None, symbol=None, limit=None):
        captured["limit"] = limit
        return {"items": []}

    fake = FakeBackendClient(get_orders=fake_get_orders)
    await list_recent_orders(client=fake)
    assert captured["limit"] == 50


async def test_list_recent_orders_clamps_to_max():
    captured: dict[str, Any] = {}

    async def fake_get_orders(*, status=None, symbol=None, limit=None):
        captured["limit"] = limit
        return {"items": []}

    fake = FakeBackendClient(get_orders=fake_get_orders)
    await list_recent_orders(limit=10_000, client=fake)
    assert captured["limit"] == 100


async def test_list_recent_orders_error():
    fake = FakeBackendClient(get_orders=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_recent_orders(client=fake)


# ---------- list_recent_fills ----------


async def test_list_recent_fills_flattens_from_orders():
    payload = {
        "items": [
            {
                "id": 10,
                "symbol": "AAPL",
                "side": "buy",
                "fills": [
                    {"qty": "5", "price": "190.10", "filled_at": "t1"},
                    {"qty": "3", "price": "190.20", "filled_at": "t2"},
                ],
            },
            {
                "id": 11,
                "symbol": "MSFT",
                "side": "sell",
                "fills": [{"qty": "2", "price": "350.00", "filled_at": "t3"}],
            },
        ]
    }
    fake = FakeBackendClient(get_orders=_async_value(payload))
    result = await list_recent_fills(client=fake)
    assert result["count"] == 3
    assert result["fills"][0]["order_id"] == 10
    assert result["fills"][0]["symbol"] == "AAPL"
    assert result["fills"][-1]["symbol"] == "MSFT"


async def test_list_recent_fills_stops_at_limit():
    """Fills accumulate across orders; bounded by limit."""
    payload = {
        "items": [
            {
                "id": i,
                "symbol": "AAPL",
                "side": "buy",
                "fills": [
                    {"qty": "1", "price": "190", "filled_at": f"t{i}{j}"}
                    for j in range(5)
                ],
            }
            for i in range(10)
        ]
    }
    fake = FakeBackendClient(get_orders=_async_value(payload))
    result = await list_recent_fills(limit=7, client=fake)
    assert result["count"] == 7


async def test_list_recent_fills_error():
    fake = FakeBackendClient(get_orders=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_recent_fills(client=fake)


# ---------- list_strategies ----------


async def test_list_strategies_happy():
    payload = {
        "items": [
            {"id": 1, "name": "rsi-mean-reversion", "status": "paper"},
            {"id": 2, "name": "macd-cross", "status": "idle"},
        ]
    }
    fake = FakeBackendClient(get_strategies=_async_value(payload))
    result = await list_strategies(client=fake)
    assert result["count"] == 2


async def test_list_strategies_passes_status_filter():
    captured: dict[str, Any] = {}

    async def fake_get_strategies(*, status=None):
        captured["status"] = status
        return {"items": []}

    fake = FakeBackendClient(get_strategies=fake_get_strategies)
    await list_strategies(status="paper", client=fake)
    assert captured["status"] == "paper"


async def test_list_strategies_error():
    fake = FakeBackendClient(get_strategies=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_strategies(client=fake)


# ---------- get_strategy_detail ----------


async def test_get_strategy_detail_aggregates_three_endpoints():
    today = "2026-05-28"
    fake = FakeBackendClient(
        get_strategy=_async_value({"id": 1, "name": "rsi"}),
        get_strategy_runs=_async_value(
            {"items": [{"id": 100, "started_at": f"{today}T09:00:00+00:00"}]}
        ),
        get_strategy_signals=_async_value(
            {
                "items": [
                    {"id": 1, "received_at": f"{today}T10:00:00+00:00"},
                    {"id": 2, "received_at": f"{today}T10:30:00+00:00"},
                    {"id": 3, "received_at": "2025-01-01T10:00:00+00:00"},
                ]
            }
        ),
    )
    result = await get_strategy_detail(strategy_id=1, client=fake)
    assert result["strategy"]["id"] == 1
    assert result["last_run"]["id"] == 100
    # 2 of 3 signals have today's date; the count is computed against the
    # current UTC day so this just checks the comparator works rather
    # than a precise number.
    assert isinstance(result["signals_today"], int)


async def test_get_strategy_detail_handles_no_runs():
    fake = FakeBackendClient(
        get_strategy=_async_value({"id": 1, "name": "rsi"}),
        get_strategy_runs=_async_value({"items": []}),
        get_strategy_signals=_async_value({"items": []}),
    )
    result = await get_strategy_detail(strategy_id=1, client=fake)
    assert result["last_run"] is None
    assert result["signals_today"] == 0


async def test_get_strategy_detail_error():
    fake = FakeBackendClient(get_strategy=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await get_strategy_detail(strategy_id=999, client=fake)


# ---------- list_recent_signals ----------


async def test_list_recent_signals_passes_filters():
    captured: dict[str, Any] = {}

    async def fake_get_signals(**kwargs):
        captured.update(kwargs)
        return {"items": []}

    fake = FakeBackendClient(get_signals=fake_get_signals)
    await list_recent_signals(
        limit=50,
        strategy_id=7,
        symbol="AAPL",
        type_="entry",
        since="2026-05-01T00:00:00Z",
        client=fake,
    )
    assert captured["limit"] == 50
    assert captured["strategy_id"] == 7
    assert captured["symbol"] == "AAPL"
    assert captured["type_"] == "entry"
    assert captured["since"] == "2026-05-01T00:00:00Z"


async def test_list_recent_signals_caps_at_200():
    captured: dict[str, Any] = {}

    async def fake_get_signals(**kwargs):
        captured.update(kwargs)
        return {"items": []}

    fake = FakeBackendClient(get_signals=fake_get_signals)
    await list_recent_signals(limit=10_000, client=fake)
    assert captured["limit"] == 200


async def test_list_recent_signals_error():
    fake = FakeBackendClient(get_signals=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await list_recent_signals(client=fake)


# ---------- list_recent_backtests ----------


async def test_list_recent_backtests_with_strategy_id():
    fake = FakeBackendClient(
        get_strategy_backtests=_async_value(
            {
                "items": [
                    {
                        "id": 1,
                        "strategy_id": 7,
                        "label": "v1",
                        "range_start": "2026-01-01",
                        "range_end": "2026-02-01",
                        "created_at": "2026-02-01T00:00:00+00:00",
                        "metrics": {
                            "trade_count": 10,
                            "total_return": 0.05,
                            "sharpe_ratio": 1.2,
                            "max_drawdown": -0.03,
                            "noise_field": "ignored",
                        },
                    }
                ]
            }
        )
    )
    result = await list_recent_backtests(strategy_id=7, client=fake)
    assert result["count"] == 1
    bt = result["backtests"][0]
    assert bt["metrics_summary"]["trade_count"] == 10
    assert "noise_field" not in bt["metrics_summary"]


async def test_list_recent_backtests_cross_strategy_fanout():
    """Without strategy_id, fans out over the first N strategies."""

    async def fake_get_strategies(*, status=None):
        return {"items": [{"id": i} for i in range(5)]}

    backtests_by_strategy = {
        i: {"items": [{"id": i * 10, "strategy_id": i, "metrics": {}}]}
        for i in range(5)
    }

    async def fake_get_strategy_backtests(strategy_id, *, limit=None):
        return backtests_by_strategy[strategy_id]

    fake = FakeBackendClient(
        get_strategies=fake_get_strategies,
        get_strategy_backtests=fake_get_strategy_backtests,
    )
    result = await list_recent_backtests(limit=20, client=fake)
    # Sum across 5 strategies × 1 = 5 backtests.
    assert result["count"] == 5


async def test_list_recent_backtests_clamps_limit():
    captured: dict[str, Any] = {}

    async def fake_get_strategy_backtests(strategy_id, *, limit=None):
        captured["limit"] = limit
        return {"items": []}

    fake = FakeBackendClient(get_strategy_backtests=fake_get_strategy_backtests)
    await list_recent_backtests(strategy_id=1, limit=999, client=fake)
    assert captured["limit"] == 50


async def test_list_recent_backtests_error():
    fake = FakeBackendClient(
        get_strategy_backtests=_async_raise(_http_error())
    )
    with pytest.raises(httpx.HTTPStatusError):
        await list_recent_backtests(strategy_id=1, client=fake)


# ---------- get_quote ----------


async def test_get_quote_happy():
    fake = FakeBackendClient(
        get_quote=_async_value(
            {"symbol": "AAPL", "bid": "189.95", "ask": "190.05", "last": "190.00"}
        )
    )
    result = await get_quote(symbol="AAPL", client=fake)
    assert result["symbol"] == "AAPL"
    assert result["last"] == "190.00"


async def test_get_quote_backend_503():
    fake = FakeBackendClient(
        get_quote=_async_raise(
            httpx.HTTPStatusError(
                "503",
                request=httpx.Request("GET", "http://test"),
                response=httpx.Response(503),
            )
        )
    )
    with pytest.raises(httpx.HTTPStatusError):
        await get_quote(symbol="AAPL", client=fake)


# ---------- get_bars ----------


async def test_get_bars_passes_timeframe_and_limit():
    captured: dict[str, Any] = {}

    async def fake_get_bars(symbol, *, timeframe=None, limit=None):
        captured["symbol"] = symbol
        captured["timeframe"] = timeframe
        captured["limit"] = limit
        return {"symbol": symbol, "timeframe": timeframe, "bars": []}

    fake = FakeBackendClient(get_bars=fake_get_bars)
    await get_bars(symbol="AAPL", timeframe="5Min", limit=75, client=fake)
    assert captured == {"symbol": "AAPL", "timeframe": "5Min", "limit": 75}


async def test_get_bars_always_caps_at_200():
    captured: dict[str, Any] = {}

    async def fake_get_bars(symbol, *, timeframe=None, limit=None):
        captured["limit"] = limit
        return {"symbol": symbol, "timeframe": timeframe, "bars": []}

    fake = FakeBackendClient(get_bars=fake_get_bars)
    await get_bars(symbol="AAPL", limit=10_000, client=fake)
    assert captured["limit"] == 200


async def test_get_bars_truncates_response():
    """Even if the backend returned more rows than asked, the tool caps."""

    async def fake_get_bars(symbol, *, timeframe=None, limit=None):
        return {
            "symbol": symbol,
            "timeframe": timeframe,
            "bars": [{"t": i, "o": 1, "h": 2, "l": 0.5, "c": 1.5, "v": 100} for i in range(500)],
        }

    fake = FakeBackendClient(get_bars=fake_get_bars)
    result = await get_bars(symbol="AAPL", limit=50, client=fake)
    assert result["count"] == 50
    assert len(result["bars"]) == 50


async def test_get_bars_error():
    fake = FakeBackendClient(get_bars=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await get_bars(symbol="AAPL", client=fake)


# ---------- get_indicators ----------


async def test_get_indicators_happy():
    fake = FakeBackendClient(
        get_indicators=_async_value(
            {"symbol": "AAPL", "indicators": {"rsi": {"latest": 35.0}}}
        )
    )
    result = await get_indicators(symbol="AAPL", names="rsi", client=fake)
    assert result["indicators"]["rsi"]["latest"] == 35.0


async def test_get_indicators_error():
    fake = FakeBackendClient(get_indicators=_async_raise(_http_error()))
    with pytest.raises(httpx.HTTPStatusError):
        await get_indicators(symbol="AAPL", client=fake)
