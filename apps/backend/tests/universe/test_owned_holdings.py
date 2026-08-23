"""StrategyOwnedHoldingsProvider — S2 ownership intersected with the live position book.

The provider decides which currently-held securities a strategy may READ. Every current
position must land in exactly one bucket, and only one of them widens anything:

    OWNED              -> admitted
    AMBIGUOUS          -> excluded, ownership_ambiguous
    UNCLAIMED          -> excluded, ownership_unclaimed
    no classification  -> excluded, ownership_evidence_missing

The fourth bucket is the point of this file. S2's UNCLAIMED is a positive statement, so a
position simply missing from S2's output must not be read as "probably ours". Account 6
happens to have Strategy-8 provenance for all 39 of its holdings today; that is a fact
about Account 6, not a rule (LOW-PIT v0.3 §5.4.2).
"""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account, AccountMode
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.universe.owned_holdings import (
    HoldingExclusionReason,
    StrategyOwnedHoldingsProvider,
)

T0 = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)

_IDENTITY = {
    "AAA": "P-1001",
    "BBB": "P-1002",
    "CCC": "P-1003",
    "DDD": "P-1004",
    "EEE": "P-1005",
    "OLDTICK": "P-2001",
    "NEWTICK": "P-2001",
}
_TICKERS = [*_IDENTITY, "GAPPED"]


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
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        for i, t in enumerate(_TICKERS, start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()


class _Book:
    """Writes acquisitions and positions. Deliberately separate operations: provenance
    and the live book are different facts and the provider must combine them itself."""

    def __init__(self, session_factory):
        self._sf = session_factory
        self._oid = 0
        self._fid = 0

    async def acquired(
        self,
        ticker: str,
        *,
        source_type: OrderSourceType = OrderSourceType.STRATEGY,
        source_id: str | None = "8",
        minutes: int = 0,
    ) -> None:
        self._oid += 1
        self._fid += 1
        async with self._sf() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == ticker)))
                .scalars()
                .first()
            )
            session.add(
                Order(
                    id=self._oid,
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
                    created_at=T0 + timedelta(minutes=minutes),
                    updated_at=T0 + timedelta(minutes=minutes),
                )
            )
            session.add(
                Fill(
                    id=self._fid,
                    order_id=self._oid,
                    qty=Decimal("10"),
                    price=Decimal("100"),
                    filled_at=T0 + timedelta(minutes=minutes),
                )
            )
            await session.commit()

    async def holds(self, ticker: str, qty: str = "10") -> None:
        async with self._sf() as session:
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


def _provider(session_factory) -> StrategyOwnedHoldingsProvider:
    return StrategyOwnedHoldingsProvider(session_factory, _FakeIdentity())


def _excluded(res, ticker: str):
    return next((e for e in res.excluded if e.ticker == ticker), None)


# ---- the four buckets ----------------------------------------------------------


async def test_owned_and_held_is_admitted(seeded, session_factory):
    book = _Book(session_factory)
    await book.acquired("AAA")
    await book.holds("AAA")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset({"AAA"})
    assert res.holdings[0].security_id == "P-1001"
    assert res.excluded == ()


async def test_ambiguous_holding_is_excluded_fail_closed(seeded, session_factory):
    book = _Book(session_factory)
    await book.acquired("BBB")
    await book.acquired("BBB", source_type=OrderSourceType.MANUAL, source_id=None, minutes=5)
    await book.holds("BBB")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    ex = _excluded(res, "BBB")
    assert ex.reason is HoldingExclusionReason.OWNERSHIP_AMBIGUOUS
    assert ex.detail == "non_strategy_acquisition"


async def test_unclaimed_holding_is_excluded(seeded, session_factory):
    book = _Book(session_factory)
    await book.acquired("CCC", source_type=OrderSourceType.MANUAL, source_id=None)
    await book.holds("CCC")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    assert _excluded(res, "CCC").reason is HoldingExclusionReason.OWNERSHIP_UNCLAIMED


async def test_position_with_no_acquisition_evidence_is_excluded(seeded, session_factory):
    """A restored / transferred / externally acquired position.

    No acquisition row exists at all, so S2 does not mention it. Absence must produce an
    explicit missing-evidence outcome, never a claim. This is the case Account-6
    exclusivity would otherwise paper over.
    """
    await _Book(session_factory).holds("DDD")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    ex = _excluded(res, "DDD")
    assert ex.reason is HoldingExclusionReason.OWNERSHIP_EVIDENCE_MISSING
    assert ex.detail is None


async def test_held_ticker_with_unresolvable_identity_is_excluded(seeded, session_factory):
    """Cannot establish the security -> cannot pose the ownership question -> fail closed."""
    book = _Book(session_factory)
    await book.acquired("GAPPED")
    await book.holds("GAPPED")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    ex = _excluded(res, "GAPPED")
    # S2 classified it AMBIGUOUS/identity_unresolved; the provider surfaces that, having
    # matched on ticker because neither side could resolve an identity.
    assert ex.reason is HoldingExclusionReason.OWNERSHIP_AMBIGUOUS
    assert ex.detail == "identity_unresolved"


# ---- the ownership/holding boundary --------------------------------------------


async def test_owned_but_flat_does_not_enter_the_read_set(seeded, session_factory):
    """Provenance is not a holding.

    A Strategy-8 BUY months ago whose position has since gone to zero must not re-enter
    the read scope — the read scope exists to manage holdings the strategy *has*.
    """
    book = _Book(session_factory)
    await book.acquired("EEE")
    await book.holds("EEE", qty="0")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    assert res.excluded == ()  # not held at all, so not a holding to explain


async def test_owned_with_no_position_row_at_all_is_absent(seeded, session_factory):
    await _Book(session_factory).acquired("EEE")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.holdings == ()
    assert res.excluded == ()


async def test_renamed_ticker_is_readable_under_its_current_ticker(seeded, session_factory):
    """Acquired as OLDTICK, held today as NEWTICK, one permaticker.

    Matching on identity rather than on the acquisition ticker is what makes the CURRENT
    broker ticker readable. A ticker-keyed match would exclude the very position it needs
    to exit.
    """
    book = _Book(session_factory)
    await book.acquired("OLDTICK")
    await book.holds("NEWTICK")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset({"NEWTICK"})
    assert res.holdings[0].security_id == "P-2001"


async def test_mixed_book_classifies_every_holding(seeded, session_factory):
    """No position is silently dropped: admitted + excluded covers the whole book."""
    book = _Book(session_factory)
    await book.acquired("AAA")
    await book.holds("AAA")
    await book.acquired("BBB")
    await book.acquired("BBB", source_id="9", minutes=5)
    await book.holds("BBB")
    await book.holds("DDD")

    res = await _provider(session_factory).resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset({"AAA"})
    assert {e.ticker for e in res.excluded} == {"BBB", "DDD"}
    assert len(res.holdings) + len(res.excluded) == 3
