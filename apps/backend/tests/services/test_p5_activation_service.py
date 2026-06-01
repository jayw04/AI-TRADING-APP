"""ActivationService unit tests (P5 §7).

Adapted to live schema: no `Backtest` model (uses backtest_results); strategies
have no account_id (mapped via user_id+mode → 6 prereqs incl. live_account_exists);
get_positions() is sync list[dict]; submit(req)->Order; liquidation uses MANUAL
source (works for LIVE + HALTED).
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import MagicMock

import pyotp
import pytest

from app.db.enums import RiskScopeType, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.services.activation import (
    ACTIVATION_COOLDOWN_HOURS,
    ActivationError,
    ActivationService,
)


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_full(session_factory) -> str:
    """Seed everything for all prereqs satisfied. Returns the TOTP secret."""
    async with session_factory() as session:
        session.add(User(id=1, email="t@local", display_name="T", totp_verified_at=_now()))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
                            label="MyLive", created_at=_now()))
        session.add(RiskLimits(user_id=1, broker_mode=AccountMode.live,
                               scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
                               created_at=_now(), updated_at=_now()))
        session.add(StrategyRow(id=10, user_id=1, name="momentum_v1", version="0.1.0",
                                type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
                                code_path="x.py", params_json={}, symbols_json=["AAPL", "MSFT"],
                                schedule="event", created_at=_now(), updated_at=_now()))
        session.add(BacktestResult(strategy_id=10, label="bt", params_json={},
                                   metrics_json={}, equity_curve_json=[], trades_json=[],
                                   range_start=_now() - timedelta(days=30), range_end=_now(),
                                   created_at=_now() - timedelta(days=1)))
        await session.commit()
        store = CredentialStore(session)
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "PKLIVE")
        await store.set(1, CredentialKind.ALPACA_LIVE_SECRET, "secret")
        secret = pyotp.random_base32()
        await store.set(1, CredentialKind.TOTP_SECRET, secret)
    return secret


async def test_all_prereqs_satisfied(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        prereqs = await ActivationService(session=session).check_prerequisites(10)
    assert all(p.satisfied for p in prereqs)
    assert {p.name for p in prereqs} == {
        "live_account_exists", "live_broker_credentials", "totp_enrolled",
        "recent_backtest", "live_risk_limits", "circuit_breaker_clear",
    }


async def test_missing_live_account(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        acc = await session.get(Account, 1)
        await session.delete(acc)
        await session.commit()
    async with session_factory() as session:
        prereqs = {p.name: p for p in await ActivationService(session=session).check_prerequisites(10)}
    assert prereqs["live_account_exists"].satisfied is False


async def test_missing_broker_credentials(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        await CredentialStore(session).revoke(1, CredentialKind.ALPACA_LIVE_KEY)
    async with session_factory() as session:
        prereqs = {p.name: p for p in await ActivationService(session=session).check_prerequisites(10)}
    assert prereqs["live_broker_credentials"].satisfied is False


async def test_missing_totp(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        user = await session.get(User, 1)
        user.totp_verified_at = None
        await session.commit()
    async with session_factory() as session:
        prereqs = {p.name: p for p in await ActivationService(session=session).check_prerequisites(10)}
    assert prereqs["totp_enrolled"].satisfied is False


async def test_old_backtest_not_recent(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(BacktestResult).where(BacktestResult.strategy_id == 10)
            .values(created_at=_now() - timedelta(days=10))
        )
        await session.commit()
    async with session_factory() as session:
        prereqs = {p.name: p for p in await ActivationService(session=session).check_prerequisites(10)}
    assert prereqs["recent_backtest"].satisfied is False


async def test_circuit_breaker_tripped(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        account = await session.get(Account, 1)
        account.circuit_breaker_tripped_at = _now()
        await session.commit()
    async with session_factory() as session:
        prereqs = {p.name: p for p in await ActivationService(session=session).check_prerequisites(10)}
    assert prereqs["circuit_breaker_clear"].satisfied is False


async def test_initiate_success_sets_pending_live(session_factory):
    secret = await _seed_full(session_factory)
    code = pyotp.TOTP(secret).now()
    async with session_factory() as session:
        result = await ActivationService(session=session).initiate(
            strategy_id=10, user_id=1, confirmation_name="momentum_v1", totp_code=code,
        )
    assert result.status == StrategyStatus.PENDING_LIVE
    assert result.initiated_at is not None
    assert 23 * 3600 < result.seconds_remaining <= ACTIVATION_COOLDOWN_HOURS * 3600


async def test_initiate_wrong_confirmation_name(session_factory):
    secret = await _seed_full(session_factory)
    code = pyotp.TOTP(secret).now()
    async with session_factory() as session:
        with pytest.raises(ActivationError, match="Confirmation name"):
            await ActivationService(session=session).initiate(
                strategy_id=10, user_id=1, confirmation_name="WRONG", totp_code=code,
            )


async def test_initiate_wrong_totp(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        with pytest.raises(ActivationError, match="TOTP"):
            await ActivationService(session=session).initiate(
                strategy_id=10, user_id=1, confirmation_name="momentum_v1", totp_code="000000",
            )


async def test_initiate_unsatisfied_prereqs_rejected(session_factory):
    secret = await _seed_full(session_factory)
    code = pyotp.TOTP(secret).now()
    async with session_factory() as session:
        account = await session.get(Account, 1)
        account.circuit_breaker_tripped_at = _now()
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(ActivationError, match="circuit_breaker_clear"):
            await ActivationService(session=session).initiate(
                strategy_id=10, user_id=1, confirmation_name="momentum_v1", totp_code=code,
            )


async def test_initiate_wrong_status_rejected(session_factory):
    secret = await _seed_full(session_factory)
    code = pyotp.TOTP(secret).now()
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.LIVE
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(ActivationError, match="IDLE or PAPER"):
            await ActivationService(session=session).initiate(
                strategy_id=10, user_id=1, confirmation_name="momentum_v1", totp_code=code,
            )


async def test_cancel_reverts_to_idle(session_factory):
    secret = await _seed_full(session_factory)
    code = pyotp.TOTP(secret).now()
    async with session_factory() as session:
        await ActivationService(session=session).initiate(
            strategy_id=10, user_id=1, confirmation_name="momentum_v1", totp_code=code,
        )
    async with session_factory() as session:
        await ActivationService(session=session).cancel(strategy_id=10, user_id=1)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
    assert s.status == StrategyStatus.IDLE
    assert s.live_activation_initiated_at is None


async def test_cancel_when_not_pending_raises(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        with pytest.raises(ActivationError, match="PENDING_LIVE"):
            await ActivationService(session=session).cancel(strategy_id=10, user_id=1)


async def test_cancel_other_user_raises_permission(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        session.add(User(id=2, email="other@local"))
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.PENDING_LIVE
        s.live_activation_initiated_at = _now()
        await session.commit()
    async with session_factory() as session:
        with pytest.raises(PermissionError):
            await ActivationService(session=session).cancel(strategy_id=10, user_id=2)


async def test_complete_pending_before_24h_no_transition(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.PENDING_LIVE
        s.live_activation_initiated_at = _now() - timedelta(hours=23)
        await session.commit()
    async with session_factory() as session:
        assert await ActivationService(session=session).complete_pending(10) is False
    async with session_factory() as session:
        assert (await session.get(StrategyRow, 10)).status == StrategyStatus.PENDING_LIVE


async def test_complete_pending_after_24h_transitions(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.PENDING_LIVE
        s.live_activation_initiated_at = _now() - timedelta(hours=25)
        await session.commit()
    async with session_factory() as session:
        assert await ActivationService(session=session).complete_pending(10) is True
    async with session_factory() as session:
        assert (await session.get(StrategyRow, 10)).status == StrategyStatus.LIVE


async def test_complete_pending_idempotent_when_live(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.LIVE
        await session.commit()
    async with session_factory() as session:
        assert await ActivationService(session=session).complete_pending(10) is False


async def test_deactivate_without_liquidation(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.LIVE
        await session.commit()
    async with session_factory() as session:
        result = await ActivationService(session=session).deactivate(
            strategy_id=10, user_id=1, liquidate=False,
        )
    assert result["new_status"] == "idle"
    assert result["liquidation_orders"] == []


async def test_deactivate_with_liquidation_submits_matching_symbols(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.LIVE
        await session.commit()

    # get_positions is sync, returns list[dict]. NVDA is not in symbols_json.
    broker_reg = MagicMock()
    adapter = MagicMock()
    adapter.get_positions = MagicMock(return_value=[
        {"symbol": "AAPL", "qty": "10"},
        {"symbol": "NVDA", "qty": "5"},
    ])
    broker_reg.get.return_value = adapter

    submitted: list = []

    async def fake_submit(req):
        submitted.append(req)
        return MagicMock(id=len(submitted) + 100)

    order_router = MagicMock()
    order_router.submit = fake_submit

    async with session_factory() as session:
        result = await ActivationService(
            session=session, broker_registry=broker_reg, order_router=order_router,
        ).deactivate(strategy_id=10, user_id=1, liquidate=True)

    assert len(result["liquidation_orders"]) == 1
    assert len(submitted) == 1
    req = submitted[0]
    assert req.symbol_ticker == "AAPL"
    assert req.side.value == "sell"
    assert req.qty == Decimal("10")
    assert req.confirmation_text == "AAPL"  # MANUAL+LIVE auto-confirmation
