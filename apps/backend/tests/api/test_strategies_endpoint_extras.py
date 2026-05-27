"""Branch-coverage backfill for ``/api/v1/strategies``.

The base ``test_strategies_endpoint.py`` covers create/list/get/update/start/
stop happy paths and ownership 404. This file targets branches the base file
misses: omit-symbols-fallback, start-from-ERROR recovery, the read-only
sub-resource endpoints (runs / signals / backtests), risk_limits_id update.
Per P2 Session 6 §6.2.

The new async submit_backtest endpoint is exercised in
``test_backtest_jobs_endpoint.py``; we don't duplicate it here.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.signal import Signal
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_run import StrategyRun
from app.db.models.symbol import Symbol
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed(factory: async_sessionmaker) -> None:
    async with factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            Symbol(
                id=1,
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple",
                active=True,
            )
        )
        await session.commit()


@pytest_asyncio.fixture
async def client_and_factory() -> (
    AsyncIterator[tuple[AsyncClient, async_sessionmaker]]
):
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.events.bus import get_event_bus
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()

    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = get_sessionmaker()
    await _seed(factory)

    app = create_app()
    app.state.strategy_engine = MagicMock()
    app.state.strategy_engine.register = AsyncMock()
    app.state.strategy_engine.unregister = AsyncMock()
    # Default to "no schema" so the params_schema injection path doesn't try
    # to serialize a MagicMock — individual tests override when they need
    # a real dict.
    app.state.strategy_engine.get_params_schema = lambda _sid: None
    app.state.bar_cache = MagicMock()
    app.state.bar_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(columns=["t", "o", "h", "l", "c", "v"])
    )
    app.state.indicator_computer = MagicMock()

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac, factory

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    get_event_bus.cache_clear()


@pytest_asyncio.fixture
async def client(client_and_factory) -> AsyncClient:
    return client_and_factory[0]


@pytest_asyncio.fixture
async def factory(client_and_factory) -> async_sessionmaker:
    return client_and_factory[1]


async def _make_strategy(
    factory: async_sessionmaker,
    *,
    status: StrategyStatus = StrategyStatus.IDLE,
    user_id: int = 1,
    symbols: list[str] | None = None,
) -> int:
    async with factory() as session:
        row = StrategyRow(
            user_id=user_id,
            name="t",
            version="0.1.0",
            type=StrategyType.PYTHON,
            status=status,
            code_path="examples/rsi_meanreversion.py",
            params_json={},
            symbols_json=symbols if symbols is not None else ["AAPL"],
            schedule="*/1 * * * *",
            risk_limits_id=None,
            created_at=_now(),
            updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


# ---------- create: symbol fallback ----------


async def test_create_falls_back_to_class_symbols_when_request_omits(client) -> None:
    """If the create request has no ``symbols`` field, fall back to the
    strategy class's declared symbols. The reference RSI strategy declares
    ``["AAPL", "MSFT", "SPY"]`` so the persisted row should contain AAPL."""
    resp = await client.post(
        "/api/v1/strategies",
        json={
            "name": "default-symbols",
            "code_path": "examples/rsi_meanreversion.py",
            "type": "python",
        },
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # RsiMeanReversion declares ["AAPL","MSFT","SPY"] as the class default.
    assert "AAPL" in body["symbols"]


# ---------- start: recovers from ERROR ----------


async def test_start_recovers_from_error_state(client, factory) -> None:
    """A strategy in ERROR is eligible to restart — ACTIVE_STRATEGY_STATUSES
    doesn't include ERROR, so engine.register fires and the row transitions
    to PAPER."""
    sid = await _make_strategy(factory, status=StrategyStatus.ERROR)

    async def fake_register(strategy_id: int):
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            r.error_text = None
            await s.commit()
        result = MagicMock()
        result.run_id = 7
        return result

    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["new_status"] == "paper"
    assert body["run_id"] == 7


# ---------- start: engine raises StrategyLoadError -> 400 ----------


async def test_start_returns_400_on_loader_failure(client, factory) -> None:
    from app.strategies.loader import StrategyLoadError

    sid = await _make_strategy(factory)

    async def fake_register(_strategy_id: int):
        raise StrategyLoadError("file went missing")

    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/start")
    assert resp.status_code == 400
    assert "file went missing" in resp.json()["detail"]


# ---------- update: risk_limits_id path ----------


async def test_update_risk_limits_id_field(client, factory) -> None:
    """Covers the PUT branch where ``body.risk_limits_id`` is set; the
    base test covers params/symbols but not this one."""
    sid = await _make_strategy(factory, status=StrategyStatus.IDLE)

    resp = await client.put(
        f"/api/v1/strategies/{sid}",
        json={"risk_limits_id": 42, "version": "0.2.0"},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["risk_limits_id"] == 42
    assert body["version"] == "0.2.0"


# ---------- sub-resources: 404 when strategy missing ----------


async def test_list_runs_returns_404_for_unknown_strategy(client) -> None:
    resp = await client.get("/api/v1/strategies/9999/runs")
    assert resp.status_code == 404


async def test_list_signals_returns_404_for_unknown_strategy(client) -> None:
    resp = await client.get("/api/v1/strategies/9999/signals")
    assert resp.status_code == 404


async def test_list_backtests_returns_404_for_unknown_strategy(client) -> None:
    resp = await client.get("/api/v1/strategies/9999/backtests")
    assert resp.status_code == 404


async def test_get_backtest_returns_404_when_result_does_not_belong(
    client, factory
) -> None:
    """A backtest result owned by another strategy must not leak across
    strategy ids."""
    sid_a = await _make_strategy(factory)
    sid_b = await _make_strategy(factory)

    async with factory() as session:
        result = BacktestResult(
            strategy_id=sid_b,
            label="x",
            params_json={},
            metrics_json={
                "total_return": 0.0,
                "annualized_return": 0.0,
                "sharpe_ratio": 0.0,
                "max_drawdown": 0.0,
                "win_rate": 0.0,
                "profit_factor": 0.0,
                "trade_count": 0,
                "avg_win": 0.0,
                "avg_loss": 0.0,
                "avg_trade_duration_seconds": 0.0,
                "starting_equity": 100000.0,
                "ending_equity": 100000.0,
            },
            equity_curve_json=[],
            trades_json=[],
            range_start=_now(),
            range_end=_now(),
            created_at=_now(),
        )
        session.add(result)
        await session.commit()
        await session.refresh(result)
        rid = result.id

    # Request the result via strategy A — must 404, not return strategy B's row.
    resp = await client.get(f"/api/v1/strategies/{sid_a}/backtests/{rid}")
    assert resp.status_code == 404


# ---------- sub-resources: populated reads ----------


async def test_list_runs_returns_recent_runs(client, factory) -> None:
    sid = await _make_strategy(factory)
    async with factory() as session:
        session.add(
            StrategyRun(
                strategy_id=sid,
                started_at=_now(),
                ended_at=None,
                status=StrategyStatus.PAPER,
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/strategies/{sid}/runs")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1


async def test_list_signals_returns_recent_signals(client, factory) -> None:
    from app.db.enums import SignalType

    sid = await _make_strategy(factory)
    async with factory() as session:
        session.add(
            Signal(
                user_id=1,
                strategy_id=sid,
                symbol_id=1,
                type=SignalType.ENTRY,
                payload_json={"rsi": 28.0},
                received_at=_now(),
                processed_at=None,
            )
        )
        await session.commit()

    resp = await client.get(f"/api/v1/strategies/{sid}/signals")
    assert resp.status_code == 200
    body = resp.json()
    assert body["count"] == 1
    assert body["items"][0]["symbol"] == "AAPL"


# ---------- P4 §7: params_schema on the detail endpoint ----------


async def test_detail_injects_schema_from_engine(client, factory) -> None:
    """When the engine has a schema for the registered strategy, the
    detail endpoint surfaces it on ``params_schema``."""
    sid = await _make_strategy(factory)

    fake_schema = {
        "rsi_period": {
            "type": "integer", "min": 2, "max": 100, "default": 14,
        }
    }
    client._transport.app.state.strategy_engine.get_params_schema = (
        lambda strategy_id: fake_schema if strategy_id == sid else None
    )

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["params_schema"] is not None
    assert body["params_schema"]["rsi_period"]["default"] == 14


async def test_detail_returns_null_schema_when_engine_has_none(
    client, factory
) -> None:
    """If the engine doesn't know about this strategy (not registered, or
    the class doesn't declare a schema), ``params_schema`` is ``None``."""
    sid = await _make_strategy(factory)
    client._transport.app.state.strategy_engine.get_params_schema = (
        lambda strategy_id: None
    )

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    assert resp.json()["params_schema"] is None


async def test_list_endpoint_omits_schema(client, factory) -> None:
    """The list endpoint intentionally skips the engine call to keep the
    list payload small. Schema is detail-endpoint only."""
    await _make_strategy(factory)
    called = {"n": 0}

    def maybe_called(_sid: int) -> dict | None:
        called["n"] += 1
        return {"rsi_period": {"type": "integer", "default": 14}}

    client._transport.app.state.strategy_engine.get_params_schema = maybe_called

    resp = await client.get("/api/v1/strategies")
    assert resp.status_code == 200
    body = resp.json()
    for item in body["items"]:
        # Field is absent OR null — both mean "schema not surfaced."
        assert item.get("params_schema") is None
    assert called["n"] == 0


# ---------- P4 §4: POST /reload ----------


async def test_reload_active_strategy_calls_unregister_then_register(
    client, factory,
) -> None:
    """Reload of an active strategy: unregister → clear flag → register."""
    sid = await _make_strategy(factory, status=StrategyStatus.PAPER)
    async with factory() as session:
        row = await session.get(StrategyRow, sid)
        row.has_pending_reload = True
        row.pending_reload_at = _now()
        await session.commit()

    unregister_calls: list[tuple[int, str | None]] = []
    register_calls: list[int] = []

    async def fake_unregister(strategy_id: int, *, reason: str | None = None):
        unregister_calls.append((strategy_id, reason))
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.IDLE
            await s.commit()

    async def fake_register(strategy_id: int):
        register_calls.append(strategy_id)
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.PAPER
            await s.commit()
        result = MagicMock()
        result.run_id = 99
        return result

    client._transport.app.state.strategy_engine.unregister = fake_unregister
    client._transport.app.state.strategy_engine.register = fake_register

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["action"] == "reload"
    assert body["new_status"] == "paper"
    assert body["run_id"] == 99

    assert unregister_calls == [(sid, "reload")]
    assert register_calls == [sid]

    async with factory() as session:
        r = await session.get(StrategyRow, sid)
    assert r.has_pending_reload is False
    assert r.pending_reload_at is None


async def test_reload_idle_strategy_skips_engine_calls(client, factory) -> None:
    """Reload on an IDLE strategy clears the flag without touching the engine
    — the next /start will pick up the new code."""
    sid = await _make_strategy(factory, status=StrategyStatus.IDLE)
    async with factory() as session:
        row = await session.get(StrategyRow, sid)
        row.has_pending_reload = True
        row.pending_reload_at = _now()
        await session.commit()

    unregister_mock = AsyncMock()
    register_mock = AsyncMock()
    client._transport.app.state.strategy_engine.unregister = unregister_mock
    client._transport.app.state.strategy_engine.register = register_mock

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 200
    body = resp.json()
    assert body["action"] == "reload"
    assert body["new_status"] == "idle"
    assert body["run_id"] is None

    unregister_mock.assert_not_awaited()
    register_mock.assert_not_awaited()

    async with factory() as session:
        r = await session.get(StrategyRow, sid)
    assert r.has_pending_reload is False


async def test_reload_returns_404_for_other_user(client, factory) -> None:
    """User #1 can't reload user #2's strategy."""
    async with factory() as session:
        session.add(User(id=2, email="other@test", display_name="Other"))
        await session.commit()
    sid = await _make_strategy(factory, user_id=2)

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 404


async def test_reload_rejects_non_python_strategy(client, factory) -> None:
    """PINE/AGENT strategies aren't reloadable in P2/P4."""
    from app.db.enums import StrategyType as ST

    async with factory() as session:
        row = StrategyRow(
            user_id=1, name="pine-x", version="0.1.0",
            type=ST.PINE, status=StrategyStatus.IDLE,
            code_path=None,
            params_json={}, symbols_json=["AAPL"], schedule="event",
            risk_limits_id=None,
            has_pending_reload=False, pending_reload_at=None,
            created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        sid = row.id

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 400


async def test_strategy_response_exposes_pending_reload_fields(
    client, factory,
) -> None:
    """The detail response surfaces has_pending_reload + pending_reload_at."""
    sid = await _make_strategy(factory)
    detected = _now()
    async with factory() as session:
        row = await session.get(StrategyRow, sid)
        row.has_pending_reload = True
        row.pending_reload_at = detected
        await session.commit()

    resp = await client.get(f"/api/v1/strategies/{sid}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["has_pending_reload"] is True
    assert body["pending_reload_at"] is not None


async def test_reload_clears_flag_even_if_register_fails(client, factory) -> None:
    """The pending flag clears as part of the reload call. If re-register
    fails (e.g. syntax error in the new file), the user fixing the file
    produces a new pending event — leaving the flag set after a failed
    reload would confuse the UI."""
    from app.strategies.loader import StrategyLoadError

    sid = await _make_strategy(factory, status=StrategyStatus.PAPER)
    async with factory() as session:
        row = await session.get(StrategyRow, sid)
        row.has_pending_reload = True
        row.pending_reload_at = _now()
        await session.commit()

    async def fake_unregister(strategy_id: int, *, reason: str | None = None):
        async with factory() as s:
            r = await s.get(StrategyRow, strategy_id)
            r.status = StrategyStatus.IDLE
            await s.commit()

    async def failing_register(_strategy_id: int):
        raise StrategyLoadError("SyntaxError on line 17")

    client._transport.app.state.strategy_engine.unregister = fake_unregister
    client._transport.app.state.strategy_engine.register = failing_register

    resp = await client.post(f"/api/v1/strategies/{sid}/reload")
    assert resp.status_code == 400
    assert "SyntaxError" in resp.json()["detail"]

    # Flag still clears even though re-register raised.
    async with factory() as session:
        r = await session.get(StrategyRow, sid)
    assert r.has_pending_reload is False
    assert r.pending_reload_at is None
