"""ADR 0043 §D3 — the account-sync SHADOW wiring.

Proves the integration contract: flag gating, called-once-with-the-RECONCILED-equity, exception
isolation (sync still completes + publishes), and NO authority leakage (a fail-closed shadow result
changes nothing about account state, the breaker, or the published snapshot). Plus one end-to-end
capture through the live path. The module's own logic is covered separately.
"""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy import func, select

import app.services.account_sync as account_sync_mod
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.user import User
from app.risk.loss_control.session_baseline import (
    SHADOW_MISSING_AFTER_ACTIVITY,
    ShadowResult,
)
from app.services.account_sync import AccountSyncService
from app.services.day_change_basis import BROKER_LAST_EQUITY

D = Decimal
TRADING_NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)  # Monday 11:00 ET — a real session


def _paper_adapter(equity: str = "123456.78") -> MagicMock:
    a = MagicMock()
    a.is_paper = True
    a.get_account.return_value = {
        "status": "ACTIVE", "cash": "1000.00", "equity": equity, "last_equity": "100000.00",
        "buying_power": "2000.00", "portfolio_value": equity, "daytrade_count": 0,
        "pattern_day_trader": False, "trading_blocked": False, "account_blocked": False,
    }
    a.list_orders.return_value = []  # no external broker activity (real-capture path)
    return a


async def _seed_paper_account(session_factory) -> None:
    async with session_factory() as s:
        s.add(User(id=1, email="test@example.com", display_name="Test"))
        await s.flush()
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"))
        await s.commit()


def _set_flag(monkeypatch, enabled: bool) -> None:
    monkeypatch.setattr(
        account_sync_mod,
        "get_settings",
        lambda: SimpleNamespace(session_baseline_shadow_enabled=enabled),
    )


def _patch_shadow(monkeypatch, *, capture: AsyncMock) -> MagicMock:
    """Replace SessionBaselineShadow with a spy; return the class mock (instance is .return_value)."""
    instance = MagicMock()
    instance.capture = capture
    cls = MagicMock(return_value=instance)
    monkeypatch.setattr(account_sync_mod, "SessionBaselineShadow", cls)
    return cls


# --------------------------------------------------------------- flag gating


async def test_flag_disabled_no_shadow_call(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    _set_flag(monkeypatch, enabled=False)
    cls = _patch_shadow(monkeypatch, capture=AsyncMock())
    svc = AccountSyncService(_paper_adapter(), session_factory, MagicMock(publish=AsyncMock()))
    await svc.sync_once()
    cls.assert_not_called()  # shadow never even constructed when the flag is off


async def test_flag_enabled_calls_capture_once_with_reconciled_equity(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    _set_flag(monkeypatch, enabled=True)
    capture = AsyncMock()
    adapter = _paper_adapter(equity="123456.78")
    cls = _patch_shadow(monkeypatch, capture=capture)
    svc = AccountSyncService(adapter, session_factory, MagicMock(publish=AsyncMock()))
    await svc.sync_once()

    cls.assert_called_once()
    assert cls.call_args.kwargs["adapter"] is adapter  # the account's OWN adapter
    capture.assert_awaited_once()
    kw = capture.await_args.kwargs
    assert kw["account_id"] == 1
    assert kw["reconciled_equity"] == D("123456.78")  # the just-reconciled broker equity


# --------------------------------------------------------------- exception isolation


async def test_shadow_exception_does_not_break_sync(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    _set_flag(monkeypatch, enabled=True)
    _patch_shadow(monkeypatch, capture=AsyncMock(side_effect=RuntimeError("shadow boom")))
    bus = MagicMock(publish=AsyncMock())
    svc = AccountSyncService(_paper_adapter(), session_factory, bus)

    payload = await svc.sync_once()  # must NOT raise

    assert payload["status"] == "ACTIVE"
    bus.publish.assert_awaited()  # sync completed and published despite the shadow failure
    async with session_factory() as s:
        state = (await s.execute(select(AccountState))).scalars().first()
    assert state is not None and state.equity == D("123456.78")  # AccountState upserted normally


# --------------------------------------------------------------- no authority leakage


async def test_fail_closed_shadow_result_changes_no_authority(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    _set_flag(monkeypatch, enabled=True)
    # The shadow returns a FAIL-CLOSED outcome — the wiring must treat it as pure telemetry.
    missing = ShadowResult(
        outcome=SHADOW_MISSING_AFTER_ACTIVITY, account_id=1, market_session_date="2026-07-20",
        activity_detected=True,
    )
    _patch_shadow(monkeypatch, capture=AsyncMock(return_value=missing))
    bus = MagicMock(publish=AsyncMock())
    svc = AccountSyncService(_paper_adapter(), session_factory, bus)
    await svc.sync_once()

    bus.publish.assert_awaited()  # a normal account snapshot — not a risk decision
    async with session_factory() as s:
        acct = await s.get(Account, 1)
        events = await s.scalar(select(func.count()).select_from(RiskControlEvent))
        states = await s.scalar(select(func.count()).select_from(RiskLossControlState))
        state = (await s.execute(select(AccountState))).scalars().first()
    assert acct.circuit_breaker_tripped_at is None  # no breaker trip
    assert events == 0 and states == 0  # no state-machine transition
    assert state.equity == D("123456.78")  # account sync itself unaffected


# --------------------------------------------------------------- reconciled (not stale) equity


async def test_capture_receives_current_broker_equity_not_stale_persisted(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    # A stale AccountState already holds an OLD equity...
    async with session_factory() as s:
        s.add(AccountState(day_change_basis=BROKER_LAST_EQUITY, account_id=1, cash=D("1"), equity=D("1.00"), last_equity=D("1.00"),
                           buying_power=D("1"), portfolio_value=D("1"), daytrade_count=0,
                           day_change=D("0"), day_change_pct=D("0"), status="ACTIVE",
                           pattern_day_trader=False, trading_blocked=False, account_blocked=False,
                           updated_at=TRADING_NOW))
        await s.commit()
    _set_flag(monkeypatch, enabled=True)
    capture = AsyncMock()
    _patch_shadow(monkeypatch, capture=capture)
    svc = AccountSyncService(_paper_adapter(equity="200000.00"), session_factory,
                             MagicMock(publish=AsyncMock()))
    await svc.sync_once()
    # The shadow gets the FRESH broker-reconciled equity, not the stale persisted 1.00.
    assert capture.await_args.kwargs["reconciled_equity"] == D("200000.00")


# --------------------------------------------------------------- end-to-end (real capture)


async def test_end_to_end_shadow_writes_a_real_baseline(session_factory, monkeypatch):
    await _seed_paper_account(session_factory)
    _set_flag(monkeypatch, enabled=True)
    # Pin the account-sync clock to a real trading session so the capture is deterministic.
    monkeypatch.setattr(account_sync_mod, "datetime", _FixedClock)
    svc = AccountSyncService(_paper_adapter(equity="150000.00"), session_factory,
                             MagicMock(publish=AsyncMock()))
    await svc.sync_once()  # real SessionBaselineShadow runs

    async with session_factory() as s:
        row = (await s.execute(select(RiskSessionBaseline))).scalars().first()
    assert row is not None
    assert row.market_session_date == "2026-07-20"
    assert row.baseline_equity == D("150000.00")  # captured from the reconciled equity


class _FixedClock:
    @staticmethod
    def now(tz=None):  # type: ignore[no-untyped-def]
        return TRADING_NOW
