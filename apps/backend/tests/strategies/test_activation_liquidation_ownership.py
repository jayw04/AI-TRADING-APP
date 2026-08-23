"""Halt/deactivation liquidation attributes by ownership, not by registration (PR S / S5).

The second of LOW-001's two exit paths. S4 proved the normal rebalance can exit a holding
outside ``symbols_json``; this proves the *safety* path can too, and — just as importantly —
that it refuses to touch anything whose ownership is uncertain.

Everything here drives the real ``ActivationService.deactivate(liquidate=True)`` entry
point rather than calling the helper, for the same reason S3's tests used the real
``StrategyContext``: the invariant is about what the production path actually does.

    OWNED                            -> liquidation order forms
    AMBIGUOUS                        -> no order (fail closed)
    UNCLAIMED                        -> no order
    ownership_evidence_missing       -> no order (fail closed)
    registered, no acquisition       -> no order  <- registration is NOT ownership
    attribution failure              -> no orders at all

That fifth row is the one that keeps ``symbols_json == ownership`` from creeping back in
through the safety path.
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
from app.services.activation import ActivationService
from app.universe.owned_holdings import StrategyOwnedHoldingsProvider

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)

#: OWNED_UNREG is owned but was never registered. REG_NOT_ACQUIRED sits in symbols_json
#: with no acquisition at all. OLDTICK/NEWTICK share a permaticker.
_IDENTITY = {
    "REG": "P-1",
    "OWNED_UNREG": "P-2",
    "CONTESTED": "P-3",
    "FOREIGN": "P-4",
    "GHOST": "P-5",
    "REG_NOT_ACQUIRED": "P-6",
    "OLDTICK": "P-7",
    "NEWTICK": "P-7",
}


class _FakeIdentity:
    def resolve(self, ticker: str, as_of: date) -> str | None:
        # Date-insensitive stand-in: these suites exercise the classification rules, not
        # the effective-interval semantics. Dated resolution is proven end-to-end against
        # a real factor store in tests/universe/test_security_identity.py (S5.5).
        return _IDENTITY.get(ticker.upper())

    def current_identity_date(self) -> date:
        # Date-insensitive stand-in: a fixed frontier so the default as_of is well defined.
        # Dated/interval semantics are proven against a real store in
        # tests/universe/test_identity_asof_and_readiness.py.
        return date(2026, 8, 20)


@pytest.fixture
async def env(session_factory):
    """A LIVE strategy on a LIVE account.

    ``_enqueue_liquidation`` resolves ``AccountMode.live`` — the whole activation service
    is the paper->live promotion flow (ADR 0005). See the note in the PR body: LOW-001 runs
    on PAPER, where this path is currently inert for reasons unrelated to ownership.
    """
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=9, user_id=1, broker="alpaca", mode=AccountMode.live, label="Live"))
        for i, t in enumerate(_IDENTITY, start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        session.add(
            Strategy(
                id=8,
                user_id=1,
                name="low-volatility",
                version="1.0.1",
                status=StrategyStatus.LIVE,
                code_path="templates/low_volatility.py",
                params_json={},
                # Registration deliberately does NOT match ownership: it omits the owned
                # unregistered name and includes one that was never acquired.
                symbols_json=["REG", "REG_NOT_ACQUIRED"],
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
        self, ticker, *, source_type=OrderSourceType.STRATEGY, source_id="8", minutes=0
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
                    user_id=1,
                    account_id=9,
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
                Fill(id=n, order_id=n, qty=Decimal("10"), price=Decimal("100"), filled_at=T0)
            )
            await session.commit()

    async def sold_manually(self, ticker):
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
                    user_id=1,
                    account_id=9,
                    symbol_id=sym.id,
                    side=OrderSide.SELL,
                    qty=Decimal("3"),
                    type=OrderType.MARKET,
                    tif=TimeInForce.DAY,
                    status=OrderStatus.FILLED,
                    source_type=OrderSourceType.MANUAL,
                    source_id=None,
                    created_at=T0,
                    updated_at=T0,
                )
            )
            session.add(
                Fill(id=n, order_id=n, qty=Decimal("3"), price=Decimal("100"), filled_at=T0)
            )
            await session.commit()

    async def holds(self, ticker, qty="10"):
        async with self._sf() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Position(
                    user_id=1,
                    account_id=9,
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


async def _deactivate(session_factory, broker_positions, *, provider="real"):
    """Run the REAL deactivate(liquidate=True) and return the submitted OrderRequests."""
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

    if provider == "real":
        prov = StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity())
    elif provider == "broken":
        prov = MagicMock()
        prov.resolve = AsyncMock(side_effect=RuntimeError("attribution backend down"))
    else:
        prov = None

    async with session_factory() as session:
        svc = ActivationService(
            session=session,
            broker_registry=registry,
            order_router=router,
            owned_holdings_provider=prov,
        )
        await svc.deactivate(strategy_id=8, user_id=1, liquidate=True)
    return submitted


def _tickers(submitted) -> set[str]:
    return {r.symbol_ticker for r in submitted}


# ---- the owned case ------------------------------------------------------------


async def test_owned_unregistered_holding_is_liquidated(env, session_factory):
    """The S5 acceptance criterion: liquidatable after leaving symbols_json."""
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.holds("OWNED_UNREG")

    submitted = await _deactivate(session_factory, [("OWNED_UNREG", "10")])

    assert _tickers(submitted) == {"OWNED_UNREG"}
    req = submitted[0]
    assert req.side is OrderSide.SELL
    assert req.qty == Decimal("10")
    assert req.account_id == 9
    # MANUAL + confirmation so the close is not blocked by the strategy-status guard.
    assert req.source_type is OrderSourceType.MANUAL
    assert req.confirmation_text == "OWNED_UNREG"


async def test_registered_owned_holding_still_liquidates(env, session_factory):
    """Existing behaviour for the ordinary case is unchanged."""
    book = _Book(session_factory)
    await book.acquired("REG")
    await book.holds("REG")

    submitted = await _deactivate(session_factory, [("REG", "10")])
    assert _tickers(submitted) == {"REG"}


async def test_renamed_ticker_liquidates_under_the_current_ticker(env, session_factory):
    """Acquired as OLDTICK, held and closed as NEWTICK — one permaticker."""
    book = _Book(session_factory)
    await book.acquired("OLDTICK")
    await book.holds("NEWTICK")

    submitted = await _deactivate(session_factory, [("NEWTICK", "10")])
    assert _tickers(submitted) == {"NEWTICK"}


async def test_manual_sell_does_not_forfeit_liquidation(env, session_factory):
    """A partial manual sell leaves the security attributable; the remainder still closes.

    The 2026-07-07 Account-6 shape. A disposal is not a competing claim, so ownership —
    and therefore the ability to flatten what remains — survives it.
    """
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.sold_manually("OWNED_UNREG")
    await book.holds("OWNED_UNREG", qty="7")

    submitted = await _deactivate(session_factory, [("OWNED_UNREG", "7")])
    assert _tickers(submitted) == {"OWNED_UNREG"}
    assert submitted[0].qty == Decimal("7")  # broker quantity, never a ledger sum


# ---- everything uncertain is left alone ----------------------------------------


async def test_manual_buy_makes_it_unliquidatable(env, session_factory):
    """Competing acquisition -> the live quantity may not all be ours -> do not sell it."""
    book = _Book(session_factory)
    await book.acquired("CONTESTED")
    await book.acquired("CONTESTED", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("CONTESTED")

    submitted = await _deactivate(session_factory, [("CONTESTED", "10")])
    assert submitted == []


async def test_competing_strategy_makes_it_unliquidatable(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("CONTESTED")
    await book.acquired("CONTESTED", source_id="9")
    await book.holds("CONTESTED")

    submitted = await _deactivate(session_factory, [("CONTESTED", "10")])
    assert submitted == []


async def test_unclaimed_position_is_untouched(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("FOREIGN", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("FOREIGN")

    submitted = await _deactivate(session_factory, [("FOREIGN", "10")])
    assert submitted == []


async def test_position_without_ownership_evidence_is_untouched(env, session_factory):
    """Restored / transferred / externally acquired. No record, no claim, no order."""
    await _Book(session_factory).holds("GHOST")

    submitted = await _deactivate(session_factory, [("GHOST", "10")])
    assert submitted == []


async def test_registration_alone_does_not_authorise_liquidation(env, session_factory):
    """REG_NOT_ACQUIRED is in symbols_json but was never bought by this strategy.

    Pre-PR-S this would have been closed on LOW-001's behalf purely because the ticker
    appeared in the registration list. That is the ``symbols_json == ownership``
    assumption, and it must not survive on the safety path.
    """
    await _Book(session_factory).holds("REG_NOT_ACQUIRED")

    submitted = await _deactivate(session_factory, [("REG_NOT_ACQUIRED", "10")])
    assert submitted == []


async def test_unrelated_position_on_the_account_is_untouched(env, session_factory):
    """Only the owned name closes, even when the broker reports a fuller book."""
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.holds("OWNED_UNREG")
    await book.holds("GHOST")

    submitted = await _deactivate(session_factory, [("OWNED_UNREG", "10"), ("GHOST", "10")])
    assert _tickers(submitted) == {"OWNED_UNREG"}


async def test_flat_position_is_not_liquidated(env, session_factory):
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.holds("OWNED_UNREG", qty="0")

    submitted = await _deactivate(session_factory, [("OWNED_UNREG", "0")])
    assert submitted == []


async def test_attribution_failure_liquidates_nothing(env, session_factory):
    """Fail CLOSED. An attribution outage must never authorise selling unknown positions."""
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.holds("OWNED_UNREG")

    submitted = await _deactivate(session_factory, [("OWNED_UNREG", "10")], provider="broken")
    assert submitted == []


async def test_without_the_capability_pre_pr_s_behaviour_is_preserved(env, session_factory):
    """No provider wired -> registration-based liquidation, exactly as before PR S.

    Keeps existing LIVE strategies working while the concrete permaticker resolver is not
    yet wired. It still trusts registration, which is why it must not survive into the
    Dynamic PIT deployment — REG_NOT_ACQUIRED closing here is the tell.
    """
    book = _Book(session_factory)
    await book.acquired("OWNED_UNREG")
    await book.holds("OWNED_UNREG")
    await book.holds("REG_NOT_ACQUIRED")

    submitted = await _deactivate(
        session_factory,
        [("OWNED_UNREG", "10"), ("REG_NOT_ACQUIRED", "10")],
        provider=None,
    )
    assert _tickers(submitted) == {"REG_NOT_ACQUIRED"}
