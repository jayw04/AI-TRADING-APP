"""The operator control path, end to end (PR S / S5.7, gate G4b operational).

S5.6 built a PAPER liquidator with no caller. This proves the whole chain from the
control an operator actually invokes:

    deactivate(liquidate=True)
        -> account mode resolves PAPER
        -> PR-S policy authorizes LOW-001
        -> ownership resolves by permanent identity
        -> quantity from the current position
        -> current broker ticker
        -> SELL submitted

and, equally, that nothing else gained the ability: a circuit-breaker trip is not a
liquidation request, another paper strategy is denied, and liquidate=False stays inert.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import select

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderStatus,
    OrderType,
    StrategyStatus,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.strategy import Strategy
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services.paper_strategy_liquidation import PaperLiquidationPolicy
from app.services.strategy_control import StrategyControlService
from app.universe.liquidation import LiquidationDisposition
from app.universe.owned_holdings import StrategyOwnedHoldingsProvider

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)
_IDENTITY = {"REG": "P-1", "XYZ": "P-2", "CONTESTED": "P-3", "GHOST": "P-4", "GAPPED": None}


class _FakeIdentity:
    def resolve(self, ticker: str, as_of: date) -> str | None:
        return _IDENTITY.get(ticker.upper())

    def current_identity_date(self) -> date:
        # Date-insensitive stand-in: a fixed frontier so the default as_of is well defined.
        # Dated/interval semantics are proven against a real store in
        # tests/universe/test_identity_asof_and_readiness.py.
        return date(2026, 8, 20)

    @property
    def ready(self) -> bool:
        return True


@pytest.fixture
async def env(session_factory):
    """LOW-001 on Account 6 PAPER (user 1); sector-rotation on Account 5 PAPER (user 2)."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(User(id=2, email="five@test", display_name="Five"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        session.add(Account(id=5, user_id=2, broker="alpaca", mode=AccountMode.paper, label="Five"))
        for i, t in enumerate(_IDENTITY, start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        for sid, uid, name in ((8, 1, "low-volatility"), (7, 2, "sector-rotation")):
            session.add(
                Strategy(
                    id=sid,
                    user_id=uid,
                    name=name,
                    version="1.0.1",
                    status=StrategyStatus.PAPER,
                    code_path=f"templates/{name}.py",
                    params_json={},
                    symbols_json=["REG"],
                    schedule="32 10 * * mon",
                    created_at=T0,
                    updated_at=T0,
                )
            )
        await session.commit()


async def _acquire(
    session_factory,
    ticker,
    oid,
    *,
    account_id=6,
    user_id=1,
    source_type=OrderSourceType.STRATEGY,
    source_id="8",
):
    async with session_factory() as session:
        sym = (
            (await session.execute(select(Symbol).where(Symbol.ticker == ticker))).scalars().first()
        )
        session.add(
            Order(
                id=oid,
                user_id=user_id,
                account_id=account_id,
                symbol_id=sym.id,
                side=OrderSide.BUY,
                qty=Decimal("10"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.FILLED,
                source_type=source_type,
                source_id=source_id,
                created_at=T0,
                updated_at=T0,
            )
        )
        session.add(
            Fill(id=oid, order_id=oid, qty=Decimal("10"), price=Decimal("100"), filled_at=T0)
        )
        await session.commit()


async def _hold(session_factory, ticker, qty="10", *, account_id=6, user_id=1):
    async with session_factory() as session:
        sym = (
            (await session.execute(select(Symbol).where(Symbol.ticker == ticker))).scalars().first()
        )
        session.add(
            Position(
                user_id=user_id,
                account_id=account_id,
                symbol_id=sym.id,
                qty=Decimal(qty),
                avg_entry_price=Decimal("100"),
                side="long",
                market_value=Decimal("1000"),
                cost_basis=Decimal("1000"),
                unrealized_pl=Decimal("0"),
                unrealized_plpc=Decimal("0"),
                updated_at=T0,
            )
        )
        await session.commit()


async def _control(session_factory, broker_positions, *, policy=None, session=None):
    submitted: list = []

    async def submit(req):
        submitted.append(req)
        return MagicMock(id=len(submitted))

    adapter = MagicMock()
    adapter.get_positions = MagicMock(
        return_value=[{"symbol": s, "qty": q} for s, q in broker_positions]
    )
    registry = MagicMock()
    registry.get = MagicMock(return_value=adapter)
    router = MagicMock()
    router.submit = AsyncMock(side_effect=submit)
    engine = MagicMock()
    engine.unregister = AsyncMock()

    svc = StrategyControlService(
        session=session,
        engine=engine,
        broker_registry=registry,
        order_router=router,
        owned_holdings_provider=StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity()),
        paper_liquidation_policy=(
            policy if policy is not None else PaperLiquidationPolicy.for_pr_s()
        ),
    )
    return svc, submitted, engine


# ---- G4b operational: the whole chain ------------------------------------------


async def test_g4b_operational_paper_stop_liquidates_an_owned_unregistered_holding(
    env, session_factory
):
    """The gate. LOW-001 owns XYZ, XYZ is not registered, operator stops with liquidate."""
    await _acquire(session_factory, "XYZ", 1)
    await _hold(session_factory, "XYZ", qty="7")

    async with session_factory() as session:
        svc, submitted, engine = await _control(session_factory, [("XYZ", "7")], session=session)
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=True)

    assert outcome.liquidation_route == "paper"
    assert outcome.stopped
    assert len(submitted) == 1
    req = submitted[0]
    assert req.symbol_ticker == "XYZ"  # current broker ticker
    assert req.side is OrderSide.SELL
    assert req.qty == Decimal("7")  # broker quantity, not a ledger sum
    assert req.account_id == 6
    assert outcome.liquidation.lines[0].disposition is LiquidationDisposition.LIQUIDATED
    engine.unregister.assert_awaited()  # and the strategy is actually stopped


# ---- negative paths ------------------------------------------------------------


async def test_liquidate_false_stops_without_orders(env, session_factory):
    """A stop is still just a stop. Nothing here makes disposal the default."""
    await _acquire(session_factory, "XYZ", 1)
    await _hold(session_factory, "XYZ")

    async with session_factory() as session:
        svc, submitted, engine = await _control(session_factory, [("XYZ", "10")], session=session)
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=False)

    assert submitted == []
    assert outcome.liquidation_requested is False
    assert outcome.liquidation_route is None
    engine.unregister.assert_awaited()


async def test_other_paper_strategy_is_denied_but_still_stops(env, session_factory):
    """G1. Sector-rotation gets no liquidation — and is told, rather than silently stopped."""
    await _acquire(session_factory, "REG", 1, account_id=5, user_id=2, source_id="7")
    await _hold(session_factory, "REG", account_id=5, user_id=2)

    async with session_factory() as session:
        svc, submitted, engine = await _control(session_factory, [("REG", "10")], session=session)
        outcome = await svc.deactivate(strategy_id=7, user_id=2, liquidate=True)

    assert submitted == []
    assert outcome.liquidation_route is None
    assert outcome.denied_reason is not None
    assert outcome.stopped
    engine.unregister.assert_awaited()


async def test_disabled_policy_denies_low_001(env, session_factory):
    """Mode PAPER is not sufficient; the explicit grant must be present."""
    await _acquire(session_factory, "XYZ", 1)
    await _hold(session_factory, "XYZ")

    async with session_factory() as session:
        svc, submitted, _ = await _control(
            session_factory,
            [("XYZ", "10")],
            policy=PaperLiquidationPolicy(),
            session=session,
        )
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=True)

    assert submitted == []
    assert outcome.denied_reason is not None


@pytest.mark.parametrize(
    ("ticker", "setup"),
    [("CONTESTED", "competing"), ("GAPPED", "unresolved"), ("GHOST", "no_evidence")],
)
async def test_uncertain_ownership_produces_no_order(env, session_factory, ticker, setup):
    """Authorized, PAPER, requested — and still refused, because ownership is uncertain."""
    if setup == "competing":
        await _acquire(session_factory, ticker, 1)
        await _acquire(session_factory, ticker, 2, source_id="9")
    elif setup == "unresolved":
        await _acquire(session_factory, ticker, 1)
    await _hold(session_factory, ticker)

    async with session_factory() as session:
        svc, submitted, _ = await _control(session_factory, [(ticker, "10")], session=session)
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=True)

    assert submitted == []
    assert outcome.liquidation_route == "paper"
    assert outcome.liquidation.order_ids == []


async def test_breaker_trip_alone_does_not_liquidate(env, session_factory):
    """A trip is not a liquidation request.

    The breaker stops NEW risk and preserves risk-reducing activity. Nothing in the
    breaker path reaches this service, and a HALTED strategy stopped without an explicit
    liquidate flag submits no orders. Redefining a trip as "flatten the book" would be a
    change to platform risk semantics, not a bug fix.
    """
    await _acquire(session_factory, "XYZ", 1)
    await _hold(session_factory, "XYZ")
    async with session_factory() as session:
        strat = await session.get(Strategy, 8)
        strat.status = StrategyStatus.HALTED  # as the breaker would leave it
        await session.commit()

    async with session_factory() as session:
        svc, submitted, _ = await _control(session_factory, [("XYZ", "10")], session=session)
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=False)

    assert submitted == []
    assert outcome.liquidation_requested is False


async def test_mode_routing_lives_in_one_place(env, session_factory):
    """A LIVE account routes to ActivationService, not the paper service.

    Also asserted structurally: the seam is the only place that asks the account its mode,
    so a later caller cannot reach the liquidator while skipping the policy.
    """
    import inspect

    from app.services import strategy_control

    src = inspect.getsource(strategy_control.StrategyControlService)
    # Exactly one query of the account's mode, and exactly one branch on it. A second of
    # either is how a caller ends up reaching the liquidator without the policy.
    assert src.count("Account.mode") == 1, "more than one place asks the account its mode"
    assert src.count("mode is AccountMode.live") == 1, "mode routing is branched twice"

    async with session_factory() as session:
        session.add(Account(id=9, user_id=1, broker="alpaca", mode=AccountMode.live, label="Live"))
        strat = await session.get(Strategy, 8)
        strat.status = StrategyStatus.LIVE
        await session.commit()

    async with session_factory() as session:
        svc, _submitted, _ = await _control(session_factory, [], session=session)
        outcome = await svc.deactivate(strategy_id=8, user_id=1, liquidate=True)

    assert outcome.liquidation_route == "live"


async def test_wrong_user_is_refused(env, session_factory):
    async with session_factory() as session:
        svc, _, _ = await _control(session_factory, [], session=session)
        with pytest.raises(PermissionError):
            await svc.deactivate(strategy_id=8, user_id=99, liquidate=True)
