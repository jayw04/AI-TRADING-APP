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


# ---- multi-account sync (P13.5) -----------------------------------------------

def _mock_adapter(equity: str, *, fail: bool = False) -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    if fail:
        a.get_account.side_effect = RuntimeError("broker down")
    else:
        a.get_account.return_value = {
            "status": "ACTIVE", "cash": "1000.00", "equity": equity, "last_equity": equity,
            "buying_power": "2000.00", "portfolio_value": equity, "daytrade_count": 0,
            "pattern_day_trader": False, "trading_blocked": False, "account_blocked": False,
        }
    return a


class _FakeRegistry:
    def __init__(self, mapping: dict) -> None:
        self._m = mapping

    def get(self, account_id: int):
        return self._m.get(account_id)


async def _seed_accounts(session_factory, n: int) -> None:
    async with session_factory() as session:
        for i in range(1, n + 1):
            session.add(User(id=i, email=f"u{i}@example.com", display_name=f"U{i}"))
            await session.flush()
            session.add(Account(id=i, user_id=i, broker="alpaca",
                                mode=AccountMode.paper, label=f"Paper{i}"))
        await session.commit()


async def test_sync_all_syncs_every_account_via_registry(session_factory) -> None:
    await _seed_accounts(session_factory, 3)
    reg = _FakeRegistry({1: _mock_adapter("10000.00"), 2: _mock_adapter("20000.00"),
                         3: _mock_adapter("30000.00")})
    svc = AccountSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert sorted(result["synced"]) == [1, 2, 3]
    async with session_factory() as session:
        states = {s.account_id: s.equity
                  for s in (await session.execute(select(AccountState))).scalars().all()}
    assert states == {1: Decimal("10000.00"), 2: Decimal("20000.00"), 3: Decimal("30000.00")}


async def test_sync_all_skips_account_without_adapter(session_factory) -> None:
    await _seed_accounts(session_factory, 2)
    reg = _FakeRegistry({1: _mock_adapter("10000.00"), 2: None})  # acct 2 has no creds/adapter
    svc = AccountSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert result["synced"] == [1] and result["skipped"] == [2]
    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
    assert [r.account_id for r in rows] == [1]


async def test_sync_all_one_failure_does_not_abort_others(session_factory) -> None:
    await _seed_accounts(session_factory, 2)
    reg = _FakeRegistry({1: _mock_adapter("10000.00"), 2: _mock_adapter("0", fail=True)})
    svc = AccountSyncService(MagicMock(), session_factory, EventBus(), broker_registry=reg)
    result = await svc.sync_all()
    assert result["synced"] == [1] and result["errors"] == [2]
    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
    assert [r.account_id for r in rows] == [1]  # the good account still synced


async def test_sync_all_without_registry_falls_back_to_primary(
    session_factory, mock_adapter_paper
) -> None:
    await _seed_paper_account(session_factory)
    svc = AccountSyncService(mock_adapter_paper, session_factory, EventBus())  # no registry
    result = await svc.sync_all()
    assert result == {"synced": [], "skipped": [], "errors": []}
    async with session_factory() as session:
        rows = (await session.execute(select(AccountState))).scalars().all()
    assert len(rows) == 1  # sync_once ran for the primary account
