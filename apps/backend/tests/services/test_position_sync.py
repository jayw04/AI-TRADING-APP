"""PositionSyncService tests — verifies upsert + delete-stale behavior."""

from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.events.bus import EventBus
from app.services.position_sync import PositionSyncService


@pytest.fixture
async def seeded_for_positions(session_factory):
    async with session_factory() as session:
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
                name="Apple Inc.",
                active=True,
            )
        )
        session.add(
            Symbol(
                id=2,
                ticker="MSFT",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Microsoft",
                active=True,
            )
        )
        await session.commit()
    yield


@pytest.fixture
def mock_adapter_paper() -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.get_positions.return_value = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "190.50",
            "side": "long",
            "market_value": "1950.00",
            "cost_basis": "1905.00",
            "unrealized_pl": "45.00",
            "unrealized_plpc": "0.024",
        },
    ]
    return a


async def test_position_sync_upserts_new(
    session_factory, seeded_for_positions, mock_adapter_paper
) -> None:
    bus = EventBus()
    svc = PositionSyncService(mock_adapter_paper, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1
        assert rows[0].symbol_id == 1
        assert rows[0].qty == Decimal("10")
        assert rows[0].avg_entry_price == Decimal("190.5000")


async def test_position_sync_updates_on_replay(
    session_factory, seeded_for_positions, mock_adapter_paper
) -> None:
    """Two consecutive syncs must end with one row (unique constraint + upsert)."""
    bus = EventBus()
    svc = PositionSyncService(mock_adapter_paper, session_factory, bus)
    await svc.sync_once()
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1


async def test_position_sync_deletes_stale(session_factory, seeded_for_positions) -> None:
    """A position previously in our DB but no longer in Alpaca's response → deleted."""
    async with session_factory() as session:
        session.add(
            Position(
                user_id=1,
                account_id=1,
                symbol_id=2,  # MSFT
                qty=Decimal("5"),
                avg_entry_price=Decimal("400"),
                side="long",
                market_value=Decimal("2000"),
                cost_basis=Decimal("2000"),
                unrealized_pl=Decimal("0"),
                unrealized_plpc=Decimal("0"),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    adapter = MagicMock()
    adapter.is_paper = True
    # Alpaca now reports only AAPL — MSFT closed.
    adapter.get_positions.return_value = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "190.50",
            "side": "long",
            "market_value": "1950.00",
            "cost_basis": "1905.00",
            "unrealized_pl": "45.00",
            "unrealized_plpc": "0.024",
        },
    ]

    bus = EventBus()
    svc = PositionSyncService(adapter, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        symbol_ids = (await session.execute(select(Position.symbol_id))).scalars().all()
        assert 1 in symbol_ids  # AAPL persisted
        assert 2 not in symbol_ids  # MSFT removed


async def test_position_sync_skips_unknown_symbol(
    session_factory, seeded_for_positions
) -> None:
    """A position for a symbol not in our `symbols` table is skipped, not crashed."""
    adapter = MagicMock()
    adapter.is_paper = True
    adapter.get_positions.return_value = [
        {
            "symbol": "AAPL",
            "qty": "10",
            "avg_entry_price": "190.50",
            "side": "long",
            "market_value": "1950.00",
            "cost_basis": "1905.00",
            "unrealized_pl": "45.00",
            "unrealized_plpc": "0.024",
        },
        # NVDA not in our seeded symbols — must be skipped silently.
        {
            "symbol": "NVDA",
            "qty": "1",
            "avg_entry_price": "1000",
            "side": "long",
            "market_value": "1000",
            "cost_basis": "1000",
            "unrealized_pl": "0",
            "unrealized_plpc": "0",
        },
    ]

    bus = EventBus()
    svc = PositionSyncService(adapter, session_factory, bus)
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        assert len(rows) == 1  # only AAPL persisted
        assert rows[0].symbol_id == 1


async def test_position_sync_no_account_row_still_publishes(session_factory) -> None:
    """If our local accounts row is missing, the snapshot still goes out (no crash)."""
    adapter = MagicMock()
    adapter.is_paper = True
    adapter.get_positions.return_value = []
    bus = EventBus()
    svc = PositionSyncService(adapter, session_factory, bus)
    result = await svc.sync_once()
    assert result == []
