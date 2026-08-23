"""READ authority vs BUY authority in the REAL StrategyContext (PR S / S3, PIT-T16).

These run against the actual ``StrategyContext`` and a real DB session, not the template's
synthetic double. That is deliberate: the invariant under test is *what the real object
hides*, and a mock cannot discharge it — the mock is the thing S1 had to repair.

LOW-PIT v0.3 §4.7 splits the two scopes::

    READ AUTHORITY                          BUY AUTHORITY
    = registered                            = existing v1.0.1 rules only
    ∪ strategy-owned currently-held         (unchanged by PR S)

The whole file exists to prove the widening on the left did not leak into the right.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

import pandas as pd
import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.strategies.context import StrategyContext
from app.universe.owned_holdings import StrategyOwnedHoldingsProvider

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)

#: REG is registered. OWNED_UNREG is held with Strategy-8 provenance but never registered.
#: FOREIGN is held on the account by someone else. GHOST is held with no provenance at all.
_IDENTITY = {"REG": "P-1", "OWNED_UNREG": "P-2", "FOREIGN": "P-3", "GHOST": "P-4"}


class _FakeIdentity:
    def resolve(self, ticker: str, as_of: date) -> str | None:
        # Date-insensitive stand-in: these suites exercise the classification rules, not
        # the effective-interval semantics. Dated resolution is proven end-to-end against
        # a real factor store in tests/universe/test_security_identity.py (S5.5).
        return _IDENTITY.get(ticker.upper())


@pytest.fixture
async def book(session_factory):
    """One registered symbol, one owned-but-unregistered holding, and two decoys."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        for i, t in enumerate(_IDENTITY, start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()

    async def acquire(ticker, oid, source_type=OrderSourceType.STRATEGY, source_id="8"):
        async with session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Order(
                    id=oid,
                    user_id=1,
                    account_id=6,
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

    async def hold(ticker, qty="10"):
        async with session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Position(
                    user_id=1,
                    account_id=6,
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

    await acquire("REG", 1)
    await hold("REG")
    await acquire("OWNED_UNREG", 2)
    await hold("OWNED_UNREG")
    await acquire("FOREIGN", 3, source_type=OrderSourceType.MANUAL, source_id=None)
    await hold("FOREIGN")
    await hold("GHOST")


def _ctx(session_factory, *, widened: bool) -> tuple[StrategyContext, list]:
    """A real StrategyContext registered for REG only.

    ``widened=False`` is the v1.0.1 control: no capability injected, so the ownership scope
    must be empty and every assertion below must flip.
    """
    submitted: list = []

    async def fake_submit(req):
        submitted.append(req)
        return MagicMock(id=1, rejection_reason=None)

    bar_cache = MagicMock()
    # Returns bars for ANY ticker, so the only gate under test is the context's own.
    bar_cache.get_bars = AsyncMock(
        return_value=pd.DataFrame(
            {"t": [T0], "o": [1.0], "h": [1.0], "l": [1.0], "c": [100.0], "v": [1]}
        )
    )

    owned_fn = None
    if widened:
        provider = StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity())

        async def owned_fn(scope_id=None):  # noqa: F811 - deliberate rebinding
            return await provider.readable_tickers(account_id=6, strategy_id=8)

    return (
        StrategyContext(
            strategy_id=8,
            user_id=1,
            account_id=6,
            symbols=["REG"],
            session_factory=session_factory,
            bar_cache=bar_cache,
            indicator_computer=MagicMock(),
            submit_order_fn=fake_submit,
            owned_holdings_fn=owned_fn,
        ),
        submitted,
    )


# ---- READ authority widens, and only for the right symbol ----------------------


async def test_registered_symbol_behaviour_is_unchanged(book, session_factory):
    ctx, _ = _ctx(session_factory, widened=True)
    assert (await ctx.get_position_for("REG")).qty == Decimal("10")
    assert not (await ctx.get_recent_bars("REG", "1Day", 1)).empty


async def test_owned_unregistered_holding_becomes_readable(book, session_factory):
    """The core S3 result: position and price both reachable for an exit."""
    ctx, _ = _ctx(session_factory, widened=True)

    pos = await ctx.get_position_for("OWNED_UNREG")
    assert pos is not None and pos.qty == Decimal("10")
    assert not (await ctx.get_recent_bars("OWNED_UNREG", "1Day", 1)).empty

    tickers = {p.symbol_id for p in await ctx.get_positions()}
    assert len(tickers) == 2  # REG + OWNED_UNREG, not FOREIGN or GHOST


async def test_without_the_capability_nothing_widens(book, session_factory):
    """v1.0.1 control. The default is unchanged behaviour, not opt-out behaviour."""
    ctx, _ = _ctx(session_factory, widened=False)

    assert await ctx.get_position_for("OWNED_UNREG") is None
    assert (await ctx.get_recent_bars("OWNED_UNREG", "1Day", 1)).empty
    assert await ctx.read_scope() == frozenset({"REG"})


async def test_ambiguous_and_evidence_free_holdings_stay_invisible(book, session_factory):
    """Fail-closed cases are not readable merely because they are held on the account."""
    ctx, _ = _ctx(session_factory, widened=True)

    assert await ctx.get_position_for("FOREIGN") is None
    assert await ctx.get_position_for("GHOST") is None
    assert (await ctx.get_recent_bars("GHOST", "1Day", 1)).empty
    assert await ctx.read_scope() == frozenset({"REG", "OWNED_UNREG"})


# ---- PIT-T16: READ authority is NOT buy authority ------------------------------


async def test_pit_t16_read_widening_does_not_widen_buy_authority(book, session_factory):
    """PIT-T16 — the invariant that keeps the widening honest.

    A symbol readable purely by ownership must remain outside every mechanism that could
    turn it into a purchase: it is not in ``ctx.symbols`` (which drives dispatch iteration
    and target-selection membership), and it is not netted by ``pending_buy_qty`` (which is
    buy planning). Visibility exists so the holding can be *exited*.
    """
    ctx, _ = _ctx(session_factory, widened=True)

    # Readable...
    assert await ctx.get_position_for("OWNED_UNREG") is not None
    assert "OWNED_UNREG" in await ctx.read_scope()

    # ...but absent from the registered universe, which is what planning consumes.
    assert ctx.symbols == ["REG"]
    assert "OWNED_UNREG" not in ctx.symbols

    # ...and absent from buy-side netting, which was deliberately NOT widened.
    async with session_factory() as session:
        sym = (
            (await session.execute(select(Symbol).where(Symbol.ticker == "OWNED_UNREG")))
            .scalars()
            .first()
        )
        session.add(
            Order(
                id=99,
                user_id=1,
                account_id=6,
                symbol_id=sym.id,
                side=OrderSide.BUY,
                qty=Decimal("5"),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                status=OrderStatus.SUBMITTED,
                source_type=OrderSourceType.STRATEGY,
                source_id="8",
                created_at=T0,
                updated_at=T0,
            )
        )
        await session.commit()

    assert "OWNED_UNREG" not in await ctx.pending_buy_qty()


async def test_read_scope_is_not_a_registration_mutation(book, session_factory):
    """Resolving the scope must not write anything back into ``symbols``."""
    ctx, _ = _ctx(session_factory, widened=True)
    before = list(ctx.symbols)
    await ctx.read_scope()
    await ctx.get_position_for("OWNED_UNREG")
    assert ctx.symbols == before


# ---- operational properties ----------------------------------------------------


async def test_scope_is_cached_per_dispatch_and_refreshed_across_dispatches(book, session_factory):
    """The engine calls on_bar once per symbol; the scope cannot be recomputed each time.

    It also must not be cached *forever* — a new dispatch is a new slot and may have a new
    book.
    """
    calls = {"n": 0}
    provider = StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity())

    async def counting(scope_id=None):
        calls["n"] += 1
        return await provider.readable_tickers(account_id=6, strategy_id=8)

    ctx = StrategyContext(
        strategy_id=8,
        user_id=1,
        account_id=6,
        symbols=["REG"],
        session_factory=session_factory,
        bar_cache=MagicMock(),
        indicator_computer=MagicMock(),
        submit_order_fn=AsyncMock(),
        owned_holdings_fn=counting,
    )

    ctx.dispatch_seq = 1
    for _ in range(5):
        await ctx.get_position_for("OWNED_UNREG")
    assert calls["n"] == 1

    ctx.dispatch_seq = 2
    await ctx.get_position_for("OWNED_UNREG")
    assert calls["n"] == 2


async def test_registered_symbols_never_pay_for_an_ownership_lookup(book, session_factory):
    """Registration is checked first, so the common path costs nothing new."""
    calls = {"n": 0}

    async def counting(scope_id=None):
        calls["n"] += 1
        return frozenset()

    ctx = StrategyContext(
        strategy_id=8,
        user_id=1,
        account_id=6,
        symbols=["REG"],
        session_factory=session_factory,
        bar_cache=MagicMock(),
        indicator_computer=MagicMock(),
        submit_order_fn=AsyncMock(),
        owned_holdings_fn=counting,
    )
    await ctx.get_position_for("REG")
    assert calls["n"] == 0


async def test_capability_failure_fails_closed(book, session_factory):
    """A broken ownership lookup degrades to registered-only, never to open visibility."""

    async def boom(scope_id=None):
        raise RuntimeError("ownership backend down")

    ctx = StrategyContext(
        strategy_id=8,
        user_id=1,
        account_id=6,
        symbols=["REG"],
        session_factory=session_factory,
        bar_cache=MagicMock(),
        indicator_computer=MagicMock(),
        submit_order_fn=AsyncMock(),
        owned_holdings_fn=boom,
    )
    assert await ctx.get_position_for("OWNED_UNREG") is None
    assert await ctx.read_scope() == frozenset({"REG"})
