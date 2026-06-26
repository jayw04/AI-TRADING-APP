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


# ---- multi-account sync (mirrors AccountSyncService.sync_all) ------------------


def _pos(symbol: str, qty: str = "10") -> dict:
    return {
        "symbol": symbol, "qty": qty, "avg_entry_price": "100", "side": "long",
        "market_value": "1000", "cost_basis": "1000", "unrealized_pl": "0",
        "unrealized_plpc": "0",
    }


def _mock_pos_adapter(positions: list, *, fail: bool = False) -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    if fail:
        a.get_positions.side_effect = RuntimeError("broker down")
    else:
        a.get_positions.return_value = positions
    return a


class _FakeRegistry:
    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def get(self, account_id: int):
        return self._m.get(account_id)


async def _seed_multi(session_factory, n: int) -> None:
    """n users/paper-accounts + the AAPL(1)/MSFT(2) symbols (shared)."""
    async with session_factory() as session:
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        session.add(Symbol(id=2, ticker="MSFT", exchange="NASDAQ",
                           asset_class="us_equity", name="Microsoft", active=True))
        for i in range(1, n + 1):
            session.add(User(id=i, email=f"u{i}@test", display_name=f"U{i}"))
            await session.flush()
            session.add(Account(id=i, user_id=i, broker="alpaca",
                                mode=AccountMode.paper, label=f"P{i}"))
        await session.commit()


async def test_sync_all_syncs_positions_for_every_account(session_factory) -> None:
    """Each account's own adapter is used → positions land scoped to that account."""
    await _seed_multi(session_factory, 2)
    reg = _FakeRegistry({1: _mock_pos_adapter([_pos("AAPL")]),
                         2: _mock_pos_adapter([_pos("MSFT")])})
    svc = PositionSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert sorted(result["synced"]) == [1, 2]
    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
        pairs = {(r.account_id, r.symbol_id) for r in rows}
    assert pairs == {(1, 1), (2, 2)}  # acct1→AAPL, acct2→MSFT — NOT just account 1


async def test_sync_all_skips_account_without_adapter(session_factory) -> None:
    await _seed_multi(session_factory, 2)
    reg = _FakeRegistry({1: _mock_pos_adapter([_pos("AAPL")]), 2: None})  # acct2 has no creds
    svc = PositionSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert result["synced"] == [1] and result["skipped"] == [2]


async def test_sync_all_one_failure_does_not_abort_others(session_factory) -> None:
    await _seed_multi(session_factory, 2)
    reg = _FakeRegistry({1: _mock_pos_adapter([_pos("AAPL")]),
                         2: _mock_pos_adapter([], fail=True)})
    svc = PositionSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert result["synced"] == [1] and result["errors"] == [2]
    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
    assert [r.account_id for r in rows] == [1]  # the good account still synced


async def test_sync_all_without_registry_falls_back_to_primary(
    session_factory, seeded_for_positions, mock_adapter_paper
) -> None:
    svc = PositionSyncService(mock_adapter_paper, session_factory, EventBus())  # no registry
    result = await svc.sync_all()
    assert result == {"synced": [], "skipped": [], "errors": []}
    async with session_factory() as session:
        rows = (await session.execute(select(Position))).scalars().all()
    assert len(rows) == 1  # sync_once ran for the primary account (AAPL)
