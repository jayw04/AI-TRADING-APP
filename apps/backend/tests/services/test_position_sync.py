import asyncio
from unittest.mock import MagicMock

import pytest

from app.events.bus import EventBus
from app.services.position_sync import PositionSyncService


@pytest.fixture
def mock_adapter() -> MagicMock:
    a = MagicMock()
    a.get_positions.return_value = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "190.50",
            "side": "long",
            "market_value": "1950.00",
            "cost_basis": "1905.00",
            "unrealized_pl": "45.00",
            "unrealized_plpc": "0.0236",
            "current_price": "195.00",
            "lastday_price": "194.00",
            "change_today": "0.005",
            "asset_class": "us_equity",
        },
    ]
    return a


async def test_position_sync_returns_normalized(mock_adapter) -> None:
    bus = EventBus()
    svc = PositionSyncService(mock_adapter, bus)
    result = await svc.sync_once()

    assert len(result) == 1
    assert result[0]["symbol"] == "AAPL"
    assert result[0]["qty"] == "10"  # preserved as string
    assert result[0]["asset_class"] == "us_equity"


async def test_position_sync_publishes_snapshot(mock_adapter) -> None:
    bus = EventBus()
    received: list[dict] = []

    async def consumer() -> None:
        async for event in bus.subscribe("positions.snapshot"):
            received.append(event)
            break  # one message is enough

    consumer_task = asyncio.create_task(consumer())
    # Give the subscriber a tick to register on the bus before publishing.
    await asyncio.sleep(0)

    svc = PositionSyncService(mock_adapter, bus)
    await svc.sync_once()

    await asyncio.wait_for(consumer_task, timeout=2.0)
    assert len(received) == 1
    assert received[0]["count"] == 1


async def test_position_sync_empty(mock_adapter) -> None:
    mock_adapter.get_positions.return_value = []
    bus = EventBus()
    svc = PositionSyncService(mock_adapter, bus)
    result = await svc.sync_once()
    assert result == []
