from decimal import Decimal
from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.user import User
from app.events.bus import EventBus
from app.services.account_sync import AccountSyncService


@pytest.fixture
def mock_adapter_paper() -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.get_account.return_value = {
        "status": "ACTIVE",
        "cash": "50000.00",
        "equity": "98750.42",
        "last_equity": "100000.00",
        "buying_power": "150000.00",
        "portfolio_value": "98750.42",
        "daytrade_count": 0,
        "pattern_day_trader": False,
        "trading_blocked": False,
        "account_blocked": False,
    }
    return a


async def _seed_paper_account(session_factory) -> None:
    async with session_factory() as session:
        session.add(User(id=1, email="test@example.com", display_name="Test"))
        await session.flush()
        session.add(
            Account(
                id=1,
                user_id=1,
                broker="alpaca",
                mode=AccountMode.paper,
                label="Paper",
            )
        )
        await session.commit()


async def test_account_sync_upserts_state(session_factory, mock_adapter_paper) -> None:
    await _seed_paper_account(session_factory)

    bus = EventBus()
    svc = AccountSyncService(mock_adapter_paper, session_factory, bus)
    payload = await svc.sync_once()

    assert payload["status"] == "ACTIVE"
    assert payload["equity"] == Decimal("98750.42")
    assert payload["day_change"] == Decimal("-1249.58")

    async with session_factory() as session:
        state = (await session.execute(select(AccountState))).scalars().first()
        assert state is not None
        assert state.account_id == 1
        assert state.status == "ACTIVE"
        assert state.equity == Decimal("98750.42")


async def test_account_sync_idempotent(session_factory, mock_adapter_paper) -> None:
    await _seed_paper_account(session_factory)

    bus = EventBus()
    svc = AccountSyncService(mock_adapter_paper, session_factory, bus)
    await svc.sync_once()
    await svc.sync_once()
    await svc.sync_once()

    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
        assert len(rows) == 1  # unique constraint on account_id


async def test_account_sync_no_account_row_warns(session_factory, mock_adapter_paper) -> None:
    # No accounts seeded — should log warning and not crash.
    bus = EventBus()
    svc = AccountSyncService(mock_adapter_paper, session_factory, bus)
    payload = await svc.sync_once()
    # Payload returned even when no row to upsert.
    assert payload["status"] == "ACTIVE"

    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
        assert len(rows) == 0
