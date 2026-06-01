"""Edge-case coverage for the P5 §5 risk gates — status variants, no-limits
paths, idempotent/none paths, bus publish, and buying-power/PDT/time edges.
Targets the branches the happy-path tests don't reach (risk engine ≥95% bar)."""
from datetime import UTC, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.db.enums import OrderType, RiskScopeType, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.buying_power import BuyingPowerChecker
from app.risk.circuit_breaker import CircuitBreakerService
from app.risk.pdt_analyzer import PdtAnalyzer
from app.utils.time import ensure_aware


def _now() -> datetime:
    return datetime.now(UTC)


# ---------------- ensure_aware ----------------

def test_ensure_aware_none():
    assert ensure_aware(None) is None


def test_ensure_aware_naive_becomes_utc():
    naive = datetime(2026, 1, 1, 12, 0, 0)
    out = ensure_aware(naive)
    assert out.tzinfo is UTC


def test_ensure_aware_already_aware_unchanged():
    aware = datetime(2026, 1, 1, 12, 0, 0, tzinfo=UTC)
    assert ensure_aware(aware) is aware


# ---------------- circuit breaker edges ----------------

@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                     asset_class="us_equity", name="Apple", active=True))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
                         created_at=_now(), updated_at=_now()))
        await s.commit()
    return session_factory


async def test_status_after_trip_reports_tripped(acct):
    async with acct() as s:
        await CircuitBreakerService(session=s).trip(account_id=1, reason="x", payload={})
    async with acct() as s:
        st = await CircuitBreakerService(session=s).status(1)
    assert st.tripped is True
    assert st.tripped_at is not None


async def test_status_with_unrealized_loss_headroom(acct):
    async with acct() as s:
        s.add(Position(user_id=1, account_id=1, symbol_id=1,
                       unrealized_pl=Decimal("-200"), updated_at=_now()))
        await s.commit()
    async with acct() as s:
        st = await CircuitBreakerService(session=s).status(1)
    assert st.unrealized_pnl_now == Decimal("-200")
    # net = -200, max_loss 500 → headroom = 500 - 200 = 300
    assert st.headroom == Decimal("300")


async def test_status_missing_account_raises(acct):
    async with acct() as s:
        with pytest.raises(ValueError):
            await CircuitBreakerService(session=s).status(999)


async def test_check_no_limits_returns_cleanly(session_factory):
    # User/account with NO GLOBAL limits → check() returns without tripping.
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        await s.commit()
    async with session_factory() as s:
        await CircuitBreakerService(session=s).check(1)  # no raise


async def test_check_missing_account_raises(acct):
    from app.risk.circuit_breaker import CircuitBreakerError
    async with acct() as s:
        with pytest.raises(CircuitBreakerError):
            await CircuitBreakerService(session=s).check(999)


async def test_trip_account_none_is_noop(acct):
    async with acct() as s:
        await CircuitBreakerService(session=s).trip(account_id=999, reason="x", payload={})
        # no exception, nothing created


async def test_reset_account_none_raises(acct):
    async with acct() as s:
        with pytest.raises(ValueError):
            await CircuitBreakerService(session=s).reset(
                account_id=999, user_id=1, confirmation_text="Paper"
            )


async def test_reset_when_not_tripped_is_noop(acct):
    async with acct() as s:
        await CircuitBreakerService(session=s).reset(
            account_id=1, user_id=1, confirmation_text="Paper"
        )  # not tripped → idempotent no-op


async def test_trip_publishes_to_bus(acct):
    bus = MagicMock()
    bus.publish = AsyncMock()
    async with acct() as s:
        await CircuitBreakerService(session=s, bus=bus).trip(
            account_id=1, reason="x", payload={}
        )
    bus.publish.assert_awaited()
    assert bus.publish.await_args.args[0] == "system.circuit_breaker"


async def test_publish_swallows_bus_error(acct):
    bus = MagicMock()
    bus.publish = AsyncMock(side_effect=RuntimeError("bus down"))
    async with acct() as s:
        # Must not raise even though publish fails.
        await CircuitBreakerService(session=s, bus=bus).trip(
            account_id=1, reason="x", payload={}
        )
    async with acct() as s:
        acc = await s.get(Account, 1)
    assert acc.circuit_breaker_tripped_at is not None  # trip still durable


async def test_trip_halts_strategy_then_idempotent_publish(acct):
    # Cover the HALT loop with an actual strategy present.
    async with acct() as s:
        s.add(StrategyRow(id=5, user_id=1, name="s", version="0.1.0",
                          type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
                          code_path="x.py", params_json={}, symbols_json=[],
                          schedule="event", created_at=_now(), updated_at=_now()))
        await s.commit()
    async with acct() as s:
        await CircuitBreakerService(session=s).trip(account_id=1, reason="x", payload={})
    async with acct() as s:
        assert (await s.get(StrategyRow, 5)).status == StrategyStatus.HALTED


# ---------------- buying power edges ----------------

def _req(type, qty="10", limit=None, stop=None):
    from app.db.enums import OrderSide
    r = MagicMock()
    r.side = OrderSide.BUY
    r.type = type
    r.qty = Decimal(qty)
    r.limit_price = Decimal(limit) if limit else None
    r.stop_price = Decimal(stop) if stop else None
    r.symbol_ticker = "AAPL"
    return r


async def test_buying_power_stop_limit_uses_limit_price():
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(return_value={"buying_power": "100000"}))
    checker = BuyingPowerChecker(broker_registry=reg)
    d = await checker.check(MagicMock(id=1), _req(OrderType.STOP_LIMIT, limit="50", qty="10"))
    assert d.required_notional == Decimal("500")


async def test_buying_power_market_no_bar_cache_fails_open():
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(return_value={"buying_power": "1"}))
    checker = BuyingPowerChecker(broker_registry=reg)  # no bar_cache
    d = await checker.check(MagicMock(id=1), _req(OrderType.MARKET, qty="10"))
    assert d.required_notional == Decimal("0")  # no price → 0 → sufficient
    assert d.sufficient is True


async def test_buying_power_market_bar_none_fails_open():
    bar_cache = MagicMock()
    bar_cache.get_latest_bar = AsyncMock(return_value=None)
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(return_value={"buying_power": "1"}))
    checker = BuyingPowerChecker(broker_registry=reg, bar_cache=bar_cache)
    d = await checker.check(MagicMock(id=1), _req(OrderType.MARKET, qty="10"))
    assert d.required_notional == Decimal("0")


async def test_buying_power_bar_cache_raises_returns_none():
    bar_cache = MagicMock()
    bar_cache.get_latest_bar = AsyncMock(side_effect=RuntimeError("boom"))
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(return_value={"buying_power": "1"}))
    checker = BuyingPowerChecker(broker_registry=reg, bar_cache=bar_cache)
    d = await checker.check(MagicMock(id=1), _req(OrderType.MARKET, qty="10"))
    assert d.required_notional == Decimal("0")


# ---------------- PDT edges ----------------

async def test_pdt_missing_account_raises(session_factory):
    async with session_factory() as s:
        with pytest.raises(ValueError):
            await PdtAnalyzer(session=s).compute(999)


async def test_pdt_equity_missing_key_is_none(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        await s.commit()
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(return_value={"cash": "1"}))
    async with session_factory() as s:
        st = await PdtAnalyzer(session=s, broker_registry=reg).compute(1)
    assert st.account_equity is None


async def test_pdt_adapter_raises_equity_none(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", created_at=_now()))
        await s.commit()
    reg = MagicMock()
    reg.get.return_value = MagicMock(get_account=MagicMock(side_effect=RuntimeError("x")))
    async with session_factory() as s:
        st = await PdtAnalyzer(session=s, broker_registry=reg).compute(1)
    assert st.account_equity is None
