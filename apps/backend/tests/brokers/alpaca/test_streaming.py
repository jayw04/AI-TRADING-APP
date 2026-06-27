"""Tests for TradeUpdatesStream lifecycle and event-bus forwarding."""

import asyncio
from unittest.mock import MagicMock, patch

import pytest

from app.brokers.alpaca.credentials import AlpacaCredentials
from app.brokers.alpaca.streaming import (
    TradeUpdatesStream,
    _normalize_trade_update,
)
from app.events.bus import EventBus


@pytest.fixture
def creds() -> AlpacaCredentials:
    return AlpacaCredentials(api_key="PK_TEST", api_secret="SECRET_TEST", paper=True)


# ---- _normalize_trade_update ----


def test_normalize_handles_dict_payload() -> None:
    data = {
        "event": "fill",
        "order": {
            "id": "abc-123",
            "symbol": "AAPL",
            "side": "buy",
            "status": "filled",
            "client_order_id": "co-1",
        },
        "execution_id": "exec-1",
        "qty": "1",
        "price": "190.50",
        "position_qty": "1",
        "timestamp": "2026-05-19T10:00:00Z",
    }
    out = _normalize_trade_update(data)
    assert out["event"] == "fill"
    assert out["broker_order_id"] == "abc-123"
    assert out["symbol"] == "AAPL"
    assert out["side"] == "buy"
    assert out["order_status"] == "filled"
    assert out["client_order_id"] == "co-1"
    assert out["qty"] == "1"
    assert out["price"] == "190.50"
    assert out["raw"] == data


def test_normalize_handles_object_with_model_dump() -> None:
    obj = MagicMock()
    obj.model_dump = MagicMock(
        return_value={
            "event": "new",
            "order": {"id": "x-1", "symbol": "MSFT", "side": "sell", "status": "new"},
        }
    )
    out = _normalize_trade_update(obj)
    assert out["event"] == "new"
    assert out["broker_order_id"] == "x-1"
    assert out["symbol"] == "MSFT"


def test_normalize_handles_missing_order() -> None:
    data = {"event": "trade_update_lol", "execution_id": "e", "qty": None}
    out = _normalize_trade_update(data)
    assert out["event"] == "trade_update_lol"
    assert out["broker_order_id"] is None
    assert out["symbol"] is None


# ---- lifecycle ----


async def test_start_is_idempotent(creds: AlpacaCredentials) -> None:
    bus = EventBus()
    stream = TradeUpdatesStream(creds, bus)

    with patch("alpaca.trading.stream.TradingStream") as MockTS:
        instance = MagicMock()

        async def _ok() -> None:
            return None

        async def _hang() -> None:
            await asyncio.sleep(3600)

        instance._start_ws = _ok
        instance._consume = _hang  # connected; receive loop blocks until cancelled
        instance.close = _ok
        MockTS.return_value = instance

        await stream.start()
        assert stream.is_started is True
        await stream.start()  # second call is a no-op
        # subscribe_trade_updates should have been called exactly once
        assert instance.subscribe_trade_updates.call_count == 1

        await stream.stop()
        assert stream.is_started is False


async def test_handle_update_publishes_to_bus(creds: AlpacaCredentials) -> None:
    bus = EventBus()
    received: list[dict] = []

    async def consumer() -> None:
        async for event in bus.subscribe("alpaca.trade_update"):
            received.append(event)
            break

    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0)  # let the subscriber register

    stream = TradeUpdatesStream(creds, bus)
    fake_payload = {
        "event": "fill",
        "order": {"id": "ord-99", "symbol": "F", "side": "buy", "status": "filled"},
        "execution_id": "e-1",
        "qty": "1",
        "price": "12.34",
    }
    await stream._handle_update(fake_payload)
    await asyncio.wait_for(consumer_task, timeout=2.0)

    assert len(received) == 1
    assert received[0]["event"] == "fill"
    assert received[0]["broker_order_id"] == "ord-99"
    assert received[0]["symbol"] == "F"
    assert stream.last_message_at is not None


async def test_status_event_published_on_start_stop(creds: AlpacaCredentials) -> None:
    bus = EventBus()
    statuses: list[str] = []

    async def consumer() -> None:
        async for event in bus.subscribe("alpaca.stream_status"):
            statuses.append(event["status"])
            if len(statuses) >= 2:
                break

    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    with patch("alpaca.trading.stream.TradingStream") as MockTS:
        instance = MagicMock()

        async def _ok() -> None:
            return None

        async def _hang() -> None:
            await asyncio.sleep(3600)

        instance._start_ws = _ok
        instance._consume = _hang  # connected; receive loop blocks until cancelled
        instance.close = _ok
        MockTS.return_value = instance

        stream = TradeUpdatesStream(creds, bus)
        await stream.start()
        await stream.stop()

    await asyncio.wait_for(consumer_task, timeout=2.0)
    assert "started" in statuses
    assert "stopped" in statuses


async def test_stop_without_start_is_noop(creds: AlpacaCredentials) -> None:
    bus = EventBus()
    stream = TradeUpdatesStream(creds, bus)
    await stream.stop()  # should not raise
    assert stream.is_started is False


async def test_reconnect_backs_off_and_auto_disables(
    creds: AlpacaCredentials, monkeypatch
) -> None:
    """A socket that keeps breaking (Norton MITM) must NOT spin: after
    _MAX_CONSECUTIVE_FAILURES rapid failures the stream auto-disables instead of
    reconnecting forever (fills then come from the polling sync)."""
    import app.brokers.alpaca.streaming as smod

    # Make backoff instant and the cap small so the test is fast + deterministic.
    monkeypatch.setattr(smod, "_RECONNECT_BASE_BACKOFF_S", 0.0)
    monkeypatch.setattr(smod, "_RECONNECT_MAX_BACKOFF_S", 0.0)
    monkeypatch.setattr(smod, "_MAX_CONSECUTIVE_FAILURES", 3)

    bus = EventBus()
    statuses: list[str] = []

    async def consumer() -> None:
        async for event in bus.subscribe("alpaca.stream_status"):
            statuses.append(event["status"])
            if "disabled" in statuses:
                break

    consumer_task = asyncio.create_task(consumer())
    await asyncio.sleep(0)

    with patch("alpaca.trading.stream.TradingStream") as MockTS:
        instance = MagicMock()
        consume_calls = {"n": 0}

        async def _ok() -> None:
            return None

        async def _consume_fail() -> None:
            consume_calls["n"] += 1
            raise RuntimeError("websocket torn (simulated Norton MITM)")

        instance._start_ws = _ok
        instance._consume = _consume_fail
        instance.close = _ok
        MockTS.return_value = instance

        stream = TradeUpdatesStream(creds, bus)
        await stream.start()
        await asyncio.wait_for(stream._task, timeout=2.0)  # task ends when it disables

    assert stream.is_disabled is True
    assert consume_calls["n"] == 3  # tried exactly the cap, then stopped (no spin)
    await asyncio.wait_for(consumer_task, timeout=2.0)
    assert "disabled" in statuses
