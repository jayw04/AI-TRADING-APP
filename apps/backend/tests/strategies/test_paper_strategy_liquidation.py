"""Explicit PAPER liquidation, authorized for LOW-001 only (PR S / S5.6, gate G4b).

Two things are proven here, and they are equally important:

1. LOW-001 on Account 6 PAPER can have an owned holding closed automatically **even when
   that holding is absent from symbols_json** — the future failure mode PR S exists to
   prevent, and the half of the exit story S4 could not cover because
   ``ActivationService`` is LIVE-only by design (ADR 0005).
2. **No other paper strategy gains anything.** Account 5 sector-rotation and the momentum
   books are denied by an explicit default-deny policy, not merely un-called. That is the
   G1 proof: absence of a call would be evidence of nothing.

Everything runs through the real ``PaperStrategyLiquidationService`` entrypoint.
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
from app.services.paper_strategy_liquidation import (
    PaperLiquidationDenied,
    PaperLiquidationPolicy,
    PaperStrategyLiquidationService,
)
from app.universe.liquidation import LiquidationDisposition
from app.universe.owned_holdings import StrategyOwnedHoldingsProvider

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)

_IDENTITY = {
    "REG": "P-1",
    "XYZ": "P-2",  # owned, never registered — the dynamic-PIT case
    "CONTESTED": "P-3",
    "FOREIGN": "P-4",
    "GHOST": "P-5",
    "OLDTICK": "P-6",
    "NEWTICK": "P-6",
    "GAPPED": None,  # identity never resolves
}


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
    """LOW-001 (id 8, user 1) and sector-rotation (id 7, user 2), both PAPER."""
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


class _Book:
    def __init__(self, session_factory):
        self._sf = session_factory
        self._n = 0

    async def acquired(
        self,
        ticker,
        *,
        account_id=6,
        user_id=1,
        source_type=OrderSourceType.STRATEGY,
        source_id="8",
        side=OrderSide.BUY,
    ):
        self._n += 1
        n = self._n
        async with self._sf() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Order(
                    id=n,
                    user_id=user_id,
                    account_id=account_id,
                    symbol_id=sym.id,
                    side=side,
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
                Fill(id=n, order_id=n, qty=Decimal("10"), price=Decimal("100"), filled_at=T0)
            )
            await session.commit()

    async def holds(self, ticker, qty="10", account_id=6, user_id=1):
        async with self._sf() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
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


async def _liquidate(
    session_factory,
    broker_positions,
    *,
    strategy_id=8,
    policy=None,
    provider="real",
    router_raises=False,
):
    submitted: list = []

    async def submit(req):
        if router_raises:
            raise RuntimeError("router down")
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

    if provider == "real":
        prov = StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity())
    elif provider == "broken":
        prov = MagicMock()
        prov.resolve = AsyncMock(side_effect=RuntimeError("attribution down"))
    else:
        prov = None

    async with session_factory() as session:
        svc = PaperStrategyLiquidationService(
            session=session,
            owned_holdings_provider=prov,
            order_router=router,
            broker_registry=registry,
            policy=policy if policy is not None else PaperLiquidationPolicy.for_pr_s(),
        )
        result = await svc.liquidate(strategy_id=strategy_id)
    return result, submitted


def _disp(result, ticker):
    return next((x.disposition for x in result.lines if x.ticker == ticker), None)


# ---- G4b: the case PR S exists for ---------------------------------------------


async def test_g4b_owned_unregistered_paper_holding_is_liquidated(env, session_factory):
    """Week N: LOW-001 owns XYZ, which is NOT in symbols_json. Later: PAPER halt.

    XYZ must be discovered by acquisition provenance, its quantity taken from the
    position, and the close routed at the current broker ticker. This is the exact
    future failure mode the whole PR exists to prevent.
    """
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ", qty="7")

    result, submitted = await _liquidate(session_factory, [("XYZ", "7")])

    assert _disp(result, "XYZ") is LiquidationDisposition.LIQUIDATED
    assert len(submitted) == 1
    req = submitted[0]
    assert req.symbol_ticker == "XYZ"
    assert req.side is OrderSide.SELL
    assert req.qty == Decimal("7")  # broker quantity, never a ledger sum
    assert req.account_id == 6
    assert req.source_type is OrderSourceType.MANUAL


async def test_owned_registered_paper_holding_is_liquidated(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("REG")
    await book.holds("REG")

    result, submitted = await _liquidate(session_factory, [("REG", "10")])
    assert _disp(result, "REG") is LiquidationDisposition.LIQUIDATED
    assert len(submitted) == 1


async def test_renamed_ticker_closes_at_the_current_ticker(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("OLDTICK")
    await book.holds("NEWTICK")

    result, submitted = await _liquidate(session_factory, [("NEWTICK", "10")])
    assert _disp(result, "NEWTICK") is LiquidationDisposition.LIQUIDATED
    assert submitted[0].symbol_ticker == "NEWTICK"


async def test_manual_sell_leaves_the_remainder_liquidatable(env, session_factory):
    """A partial manual disposal is not a competing claim; what remains is still ours."""
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.acquired(
        "XYZ", source_type=OrderSourceType.MANUAL, source_id=None, side=OrderSide.SELL
    )
    await book.holds("XYZ", qty="4")

    result, submitted = await _liquidate(session_factory, [("XYZ", "4")])
    assert _disp(result, "XYZ") is LiquidationDisposition.LIQUIDATED
    assert submitted[0].qty == Decimal("4")


# ---- everything uncertain is reported, not sold --------------------------------


async def test_competing_strategy_is_not_liquidated(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("CONTESTED")
    await book.acquired("CONTESTED", source_id="9")
    await book.holds("CONTESTED")

    result, submitted = await _liquidate(session_factory, [("CONTESTED", "10")])
    assert submitted == []
    assert _disp(result, "CONTESTED") is LiquidationDisposition.EXCLUDED_AMBIGUOUS


async def test_manual_buy_is_not_liquidated(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("CONTESTED")
    await book.acquired("CONTESTED", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("CONTESTED")

    result, submitted = await _liquidate(session_factory, [("CONTESTED", "10")])
    assert submitted == []
    assert _disp(result, "CONTESTED") is LiquidationDisposition.EXCLUDED_AMBIGUOUS


async def test_identity_unresolved_is_its_own_disposition(env, session_factory):
    """Distinguishable from 'two owners': we cannot say what this security IS."""
    book = _Book(session_factory)
    await book.acquired("GAPPED")
    await book.holds("GAPPED")

    result, submitted = await _liquidate(session_factory, [("GAPPED", "10")])
    assert submitted == []
    assert _disp(result, "GAPPED") is LiquidationDisposition.EXCLUDED_IDENTITY_UNRESOLVED


async def test_unclaimed_is_untouched(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("FOREIGN", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("FOREIGN")

    result, submitted = await _liquidate(session_factory, [("FOREIGN", "10")])
    assert submitted == []
    assert _disp(result, "FOREIGN") is LiquidationDisposition.EXCLUDED_UNCLAIMED


async def test_missing_evidence_is_untouched(env, session_factory):
    await _Book(session_factory).holds("GHOST")

    result, submitted = await _liquidate(session_factory, [("GHOST", "10")])
    assert submitted == []
    assert _disp(result, "GHOST") is LiquidationDisposition.EXCLUDED_EVIDENCE_MISSING


async def test_flat_position_is_skipped(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ", qty="0")

    result, submitted = await _liquidate(session_factory, [("XYZ", "0")])
    assert submitted == []
    assert result.lines == ()


async def test_attribution_failure_closes_nothing(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ")

    result, submitted = await _liquidate(session_factory, [("XYZ", "10")], provider="broken")
    assert submitted == []
    assert result.lines == ()


async def test_submission_failure_is_reported_per_symbol(env, session_factory):
    """One symbol failing must not silently look like 'nothing was owned'."""
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ")

    result, _ = await _liquidate(session_factory, [("XYZ", "10")], router_raises=True)
    assert _disp(result, "XYZ") is LiquidationDisposition.ERROR
    assert result.order_ids == []


async def test_mixed_book_reports_every_position(env, session_factory):
    """No position is silently dropped — the operator sees a line for each."""
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ")
    await book.holds("GHOST")
    await book.acquired("FOREIGN", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("FOREIGN")

    result, submitted = await _liquidate(
        session_factory, [("XYZ", "10"), ("GHOST", "10"), ("FOREIGN", "10")]
    )
    assert len(submitted) == 1
    assert {x.ticker for x in result.lines} == {"XYZ", "GHOST", "FOREIGN"}
    assert len(result.liquidated) == 1
    assert len(result.excluded) == 2


# ---- G1: no other paper strategy gains anything --------------------------------


async def test_other_paper_strategy_is_denied_by_policy(env, session_factory):
    """Sector-rotation on Account 5 PAPER. Denied explicitly, not merely un-called.

    This is the G1 proof. If PAPER liquidation had been added to ActivationService, this
    strategy would have started closing positions on deactivate(liquidate=True) with no
    code change anywhere near it.
    """
    book = _Book(session_factory)
    await book.acquired("REG", account_id=5, user_id=2, source_id="7")
    await book.holds("REG", account_id=5, user_id=2)

    with pytest.raises(PaperLiquidationDenied):
        await _liquidate(session_factory, [("REG", "10")], strategy_id=7)


async def test_default_policy_denies_even_low_001(env, session_factory):
    """Default-deny by construction: a default-constructed policy authorizes nothing."""
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ")

    with pytest.raises(PaperLiquidationDenied):
        await _liquidate(session_factory, [("XYZ", "10")], policy=PaperLiquidationPolicy())


async def test_disabled_policy_denies_even_a_listed_strategy(env, session_factory):
    """Naming the strategy is not enough; the capability must also be enabled."""
    policy = PaperLiquidationPolicy(enabled=False, strategies=frozenset({"low-volatility"}))
    with pytest.raises(PaperLiquidationDenied):
        await _liquidate(session_factory, [("XYZ", "10")], policy=policy)


def test_pr_s_grant_covers_low_001_only():
    policy = PaperLiquidationPolicy.for_pr_s()
    assert policy.permits("low-volatility")
    for other in ("sector-rotation", "momentum-portfolio", "momentum-daily", "combined-book"):
        assert not policy.permits(other)


async def test_unknown_strategy_is_denied(env, session_factory):
    with pytest.raises(PaperLiquidationDenied):
        await _liquidate(session_factory, [], strategy_id=999)


async def test_missing_capability_fails_closed_without_denying(env, session_factory):
    """Authorized but unusable is not a permission error — the distinction is operational."""
    book = _Book(session_factory)
    await book.acquired("XYZ")
    await book.holds("XYZ")

    result, submitted = await _liquidate(session_factory, [("XYZ", "10")], provider=None)
    assert submitted == []
    assert result.lines == ()
