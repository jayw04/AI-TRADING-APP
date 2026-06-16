"""CircuitBreakerService tests (P5 §5).

Adapted to the live schema: strategies have no account_id (mapped via
user_id + status↔mode); Fill has no signed_direction (realized PnL joins
Order.side); unrealized PnL is read from the local positions table.
"""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    RiskScopeType,
    StrategyStatus,
    StrategyType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.circuit_breaker import CircuitBreakerError, CircuitBreakerService


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                label="Paper", created_at=_now(),
            )
        )
        session.add(
            RiskLimits(
                id=1, user_id=1, broker_mode=AccountMode.paper,
                scope_type=RiskScopeType.GLOBAL,
                max_daily_loss=Decimal("500"),
                created_at=_now(), updated_at=_now(),
            )
        )
        session.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ",
                           asset_class="us_equity", name="Apple", active=True))
        for sid in (10, 11):
            session.add(
                StrategyRow(
                    id=sid, user_id=1, name=f"s{sid}", version="0.1.0",
                    type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
                    code_path="x.py", params_json={}, symbols_json=[],
                    schedule="event", created_at=_now(), updated_at=_now(),
                )
            )
        await session.commit()
    return session_factory


async def test_status_not_tripped_initially(seeded):
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        status = await cb.status(1)
    assert status.tripped is False
    assert status.tripped_at is None


async def test_check_passes_when_no_loss(seeded):
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        await cb.check(1)  # no fills/positions → net 0 → no trip


async def test_trip_halts_active_strategies_for_account_mode(seeded):
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        await cb.trip(account_id=1, reason="test", payload={"x": "y"})
    async with seeded() as session:
        account = await session.get(Account, 1)
        s10 = await session.get(StrategyRow, 10)
        s11 = await session.get(StrategyRow, 11)
    assert account.circuit_breaker_tripped_at is not None
    assert s10.status == StrategyStatus.HALTED
    assert s11.status == StrategyStatus.HALTED


async def test_trip_does_not_halt_other_users_or_modes(seeded):
    # A LIVE-status strategy and another user's strategy must NOT be halted
    # when a paper account trips.
    async with seeded() as session:
        session.add(User(id=2, email="u2@local"))
        session.add(StrategyRow(
            id=20, user_id=1, name="live-strat", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.LIVE,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=21, user_id=2, name="other-user", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        await cb.trip(account_id=1, reason="test", payload={})
    async with seeded() as session:
        live = await session.get(StrategyRow, 20)
        other = await session.get(StrategyRow, 21)
    assert live.status == StrategyStatus.LIVE  # different mode → untouched
    assert other.status == StrategyStatus.PAPER  # different user → untouched


async def test_check_when_tripped_raises(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        with pytest.raises(CircuitBreakerError) as exc:
            await CircuitBreakerService(session=session).check(1)
    assert "tripped" in str(exc.value).lower()


async def test_check_trips_on_unrealized_loss(seeded):
    # A position with unrealized loss beyond max_daily_loss trips the breaker.
    async with seeded() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,
            unrealized_pl=Decimal("-600"), updated_at=_now(),
        ))
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        with pytest.raises(CircuitBreakerError):
            await cb.check(1)
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is not None


async def test_check_trips_on_realized_loss(seeded):
    # BUY 10@100 then SELL 10@90 today → realized loss 100. max_daily_loss=500,
    # so tighten to 50 to trip. Verifies the Fill→Order sign logic.
    async with seeded() as session:
        rl = await session.get(RiskLimits, 1)
        rl.max_daily_loss = Decimal("50")
        buy = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        sell = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.SELL,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add_all([buy, sell])
        await session.flush()
        session.add_all([
            Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"),
                 filled_at=_now()),
            Fill(order_id=sell.id, qty=Decimal("10"), price=Decimal("90"),
                 filled_at=_now()),
        ])
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        realized = await cb._compute_realized_pnl_today(1)
        assert realized == Decimal("-100")  # lost $100
        with pytest.raises(CircuitBreakerError):
            await cb.check(1)


async def test_realized_pnl_zero_on_buys_only(seeded):
    """★ Regression: opening a book must NOT count as realized loss. A BUY with
    notional far above max_daily_loss (1000 > 500) realizes 0 and never trips —
    the old signed-cash-flow calc booked -1000 and halted on capital deployment."""
    async with seeded() as session:
        buy = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add(buy)
        await session.flush()
        session.add(Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"),
                         filled_at=_now()))
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        assert await cb._compute_realized_pnl_today(1) == Decimal("0")
        await cb.check(1)  # must NOT raise
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is None


async def test_realized_pnl_uses_prior_day_cost_basis(seeded):
    """A position OPENED on a prior day and SOLD today realizes today's loss
    against the prior-day cost basis; the prior buy itself counts toward neither
    today's realized P&L nor (it is closed) the unrealized term."""
    prior = _now() - timedelta(days=2)
    async with seeded() as session:
        rl = await session.get(RiskLimits, 1)
        rl.max_daily_loss = Decimal("50")
        buy = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=prior, updated_at=prior,
        )
        sell = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.SELL,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add_all([buy, sell])
        await session.flush()
        session.add_all([
            Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"), filled_at=prior),
            Fill(order_id=sell.id, qty=Decimal("10"), price=Decimal("90"), filled_at=_now()),
        ])
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        assert await cb._compute_realized_pnl_today(1) == Decimal("-100")
        with pytest.raises(CircuitBreakerError):
            await cb.check(1)


async def test_realized_pnl_partial_sell_gain(seeded):
    """A partial sell realizes only the sold qty against average cost:
    BUY 10@100, SELL 4@110 → +40 realized (open 6 remain, unrealized)."""
    async with seeded() as session:
        buy = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        sell = Order(
            user_id=1, account_id=1, symbol_id=1, side=OrderSide.SELL,
            type=OrderType.MARKET, qty=Decimal("4"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, source_type=OrderSourceType.MANUAL,
            created_at=_now(), updated_at=_now(),
        )
        session.add_all([buy, sell])
        await session.flush()
        session.add_all([
            Fill(order_id=buy.id, qty=Decimal("10"), price=Decimal("100"), filled_at=_now()),
            Fill(order_id=sell.id, qty=Decimal("4"), price=Decimal("110"), filled_at=_now()),
        ])
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        assert await cb._compute_realized_pnl_today(1) == Decimal("40")


async def test_reset_clears_tripped_state(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        await CircuitBreakerService(session=session).reset(
            account_id=1, user_id=1, confirmation_text="Paper"
        )
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is None


async def test_reset_rejects_wrong_confirmation(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        with pytest.raises(ValueError) as exc:
            await CircuitBreakerService(session=session).reset(
                account_id=1, user_id=1, confirmation_text="wrong"
            )
    assert "label" in str(exc.value).lower()


async def test_reset_does_not_restart_halted_strategies(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        await CircuitBreakerService(session=session).reset(
            account_id=1, user_id=1, confirmation_text="Paper"
        )
    async with seeded() as session:
        s10 = await session.get(StrategyRow, 10)
        s11 = await session.get(StrategyRow, 11)
    assert s10.status == StrategyStatus.HALTED
    assert s11.status == StrategyStatus.HALTED


async def test_reset_rejects_wrong_user(seeded):
    async with seeded() as session:
        session.add(User(id=2, email="other@local"))
        await session.commit()
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        with pytest.raises(PermissionError):
            await CircuitBreakerService(session=session).reset(
                account_id=1, user_id=2, confirmation_text="Paper"
            )


async def test_trip_is_idempotent(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        first = (await session.get(Account, 1)).circuit_breaker_tripped_at
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="again", payload={}
        )
        after = (await session.get(Account, 1)).circuit_breaker_tripped_at
    assert after == first


# ---- evaluate() — continuous-monitor path (P10 §6, trips without raising) -------

async def test_evaluate_trips_on_breach_without_raising(seeded):
    async with seeded() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,
            unrealized_pl=Decimal("-600"), updated_at=_now(),
        ))
        await session.commit()
    async with seeded() as session:
        cb = CircuitBreakerService(session=session)
        tripped = await cb.evaluate(1)  # must NOT raise (unlike check())
        assert tripped is True
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is not None


async def test_evaluate_noop_within_limit(seeded):
    async with seeded() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,
            unrealized_pl=Decimal("-100"), updated_at=_now(),  # within the 500 limit
        ))
        await session.commit()
    async with seeded() as session:
        assert await CircuitBreakerService(session=session).evaluate(1) is False
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is None


async def test_evaluate_true_when_already_tripped(seeded):
    async with seeded() as session:
        await CircuitBreakerService(session=session).trip(
            account_id=1, reason="test", payload={}
        )
    async with seeded() as session:
        assert await CircuitBreakerService(session=session).evaluate(1) is True


async def test_evaluate_noop_when_no_limit(seeded):
    async with seeded() as session:
        rl = await session.get(RiskLimits, 1)
        rl.max_daily_loss = None
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1,
            unrealized_pl=Decimal("-9999"), updated_at=_now(),
        ))
        await session.commit()
    async with seeded() as session:
        assert await CircuitBreakerService(session=session).evaluate(1) is False


async def test_breaker_monitor_job_trips_account_with_open_position(seeded):
    from app.jobs.breaker_monitor import run_breaker_monitor

    async with seeded() as session:
        session.add(Position(
            user_id=1, account_id=1, symbol_id=1, qty=Decimal("10"),
            unrealized_pl=Decimal("-600"), updated_at=_now(),
        ))
        await session.commit()
    await run_breaker_monitor(seeded)  # `seeded` is the session_factory
    async with seeded() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is not None
