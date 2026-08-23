"""Dated identity resolution against a REAL factor store (PR S / S5.5).

S2 and S3 proved the ownership *rules* against a fake resolver. This file proves the
concrete wiring: a real DuckDB ``FactorDataStore``, a real ``tickers`` slice with real
effective intervals, and the adapter that turns ``(ticker, date)`` into a permaticker.

The property under test is the one the fake could not express — that identity is an
identifier **plus an interval**, so the same ticker resolves differently (or not at all)
depending on when you ask:

    2026-04-01  BUY OLDTICK        -> permaticker P
    2026-08-22  position NEWTICK   -> permaticker P
    => same security, attributable, exits under NEWTICK

and the refusals:

    different permaticker     -> not the same security
    date outside the interval -> None  (the symbol denoted something else then)
    missing permaticker       -> None  (unrefreshed store)
    duplicate ticker rows     -> None  (ambiguous lineage claim)

None of these may ever degrade to ticker equality.
"""

from __future__ import annotations

from datetime import UTC, date, datetime
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
from app.factor_data.store import FactorDataStore
from app.universe.owned_holdings import HoldingExclusionReason, StrategyOwnedHoldingsProvider
from app.universe.security_identity import FactorStoreSecurityIdentityResolver

D_ACQUIRE = date(2026, 4, 1)
D_NOW = date(2026, 8, 22)
T_ACQUIRE = datetime(2026, 4, 1, 17, 31, tzinfo=UTC)


@pytest.fixture
def store(tmp_path):
    """A real store whose `tickers` slice encodes one rename and several refusals.

    OLDTICK/NEWTICK are one lineage (P-100) that renamed mid-interval, so both rows carry
    the same permaticker with windows covering their own eras. REUSED's window ENDS before
    D_NOW: the bare ticker belongs to a later lineage now, so asking about it today is
    answerable but asking about D_ACQUIRE is not, and vice versa.
    """
    s = FactorDataStore(str(tmp_path / "f.duckdb"))
    s.con.execute(
        """
        INSERT INTO tickers
            (ticker, permaticker, name, exchange, category, sector, industry,
             isdelisted, firstpricedate, lastpricedate, lastupdated)
        VALUES
            ('OLDTICK','P-100','Old Co','NYSE','Domestic Common Stock',NULL,NULL,
             TRUE,  DATE '2020-01-01', DATE '2026-06-30', DATE '2026-08-22'),
            ('NEWTICK','P-100','New Co','NYSE','Domestic Common Stock',NULL,NULL,
             FALSE, DATE '2026-07-01', DATE '2026-12-31', DATE '2026-08-22'),
            ('OTHER',  'P-200','Other Co','NYSE','Domestic Common Stock',NULL,NULL,
             FALSE, DATE '2020-01-01', DATE '2026-12-31', DATE '2026-08-22'),
            ('REUSED', 'P-300','Reused Co','NYSE','Domestic Common Stock',NULL,NULL,
             TRUE,  DATE '2019-01-01', DATE '2026-05-01', DATE '2026-08-22'),
            ('NOPERMA', NULL,  'No Perma','NYSE','Domestic Common Stock',NULL,NULL,
             FALSE, DATE '2020-01-01', DATE '2026-12-31', DATE '2026-08-22')
        """
    )
    yield s
    s.close()


def _resolver(store) -> FactorStoreSecurityIdentityResolver:
    return FactorStoreSecurityIdentityResolver(store)


# ---- the adapter itself --------------------------------------------------------


def test_rename_within_one_lineage_resolves_to_one_identity(store):
    """The headline case: two tickers, two eras, one security."""
    r = _resolver(store)
    assert r.resolve("OLDTICK", D_ACQUIRE) == "P-100"
    assert r.resolve("NEWTICK", D_NOW) == "P-100"


def test_distinct_lineages_do_not_collide(store):
    r = _resolver(store)
    assert r.resolve("OTHER", D_NOW) == "P-200"
    assert r.resolve("OTHER", D_NOW) != r.resolve("NEWTICK", D_NOW)


def test_date_outside_the_effective_interval_is_unresolved(store):
    """REUSED stopped denoting P-300 on 2026-05-01. Today the bare symbol is someone
    else's, and the honest answer is None — not the stale lineage."""
    r = _resolver(store)
    assert r.resolve("REUSED", date(2026, 3, 1)) == "P-300"
    assert r.resolve("REUSED", D_NOW) is None


def test_ticker_before_its_lineage_began_is_unresolved(store):
    assert _resolver(store).resolve("NEWTICK", D_ACQUIRE) is None


def test_missing_permaticker_is_unresolved(store):
    """An unrefreshed store. The column is deliberately not backfilled from ticker
    equality, so it must fail closed rather than invent the identity."""
    assert _resolver(store).resolve("NOPERMA", D_NOW) is None


def test_unknown_ticker_is_unresolved(store):
    assert _resolver(store).resolve("NEVERHEARDOF", D_NOW) is None


def test_schema_forbids_duplicate_ticker_rows(store):
    """The ambiguous-lineage guard in the adapter is belt-and-braces, and this says why.

    ``tickers.ticker`` is a PRIMARY KEY, so two rows claiming one symbol cannot exist. The
    resolver still refuses on ``len(rows) != 1`` rather than taking ``rows[0]``: the guard
    costs nothing, also covers the zero-row case, and would hold if the constraint were
    ever relaxed. Asserting the constraint here documents that the branch is unreachable
    today by design, not by luck.
    """
    import duckdb

    with pytest.raises(duckdb.ConstraintException):
        store.con.execute(
            """
            INSERT INTO tickers
                (ticker, permaticker, name, exchange, category, sector, industry,
                 isdelisted, firstpricedate, lastpricedate, lastupdated)
            VALUES ('OTHER','P-999','Dup','NYSE','Domestic Common Stock',NULL,NULL,
                    FALSE, DATE '2020-01-01', DATE '2026-12-31', DATE '2026-08-22')
            """
        )


def test_no_store_fails_closed(store):
    r = FactorStoreSecurityIdentityResolver(None)
    assert not r.ready
    assert r.resolve("NEWTICK", D_NOW) is None


def test_ready_reports_provisioning(store):
    assert _resolver(store).ready is True


def test_lookup_is_memoised(store):
    """A 200-symbol dispatch resolves the same handful of names repeatedly."""
    calls = {"n": 0}
    real = store.permaticker_asof

    def counting(ticker, as_of):
        calls["n"] += 1
        return real(ticker, as_of)

    store.permaticker_asof = counting  # type: ignore[method-assign]
    r = _resolver(store)
    for _ in range(5):
        r.resolve("NEWTICK", D_NOW)
    assert calls["n"] == 1


# ---- end to end: acquisition date vs current session ---------------------------


@pytest.fixture
async def book(session_factory):
    """Acquired as OLDTICK in April; held as NEWTICK today."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        for i, t in enumerate(["OLDTICK", "NEWTICK", "OTHER", "REUSED"], start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()

    async def acquire(ticker, oid, when):
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
                    source_type=OrderSourceType.STRATEGY,
                    source_id="8",
                    created_at=when,
                    updated_at=when,
                )
            )
            session.add(
                Fill(id=oid, order_id=oid, qty=Decimal("10"), price=Decimal("100"), filled_at=when)
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
                    updated_at=datetime(2026, 8, 22, tzinfo=UTC),
                )
            )
            await session.commit()

    return acquire, hold


async def test_renamed_security_is_owned_and_readable_under_the_new_ticker(
    store, book, session_factory
):
    """The S5.5 acceptance case, end to end through the real store.

    The acquisition resolves on ITS fill date (April, when the symbol was OLDTICK); the
    position resolves on TODAY (when it is NEWTICK). Both land on P-100, so the holding is
    attributable and exits under the current ticker. Resolving both on one date would fail:
    NEWTICK did not exist in April, and OLDTICK is out of interval today.
    """
    acquire, hold = book
    await acquire("OLDTICK", 1, T_ACQUIRE)
    await hold("NEWTICK")

    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8, as_of=D_NOW)

    assert res.tickers == frozenset({"NEWTICK"})
    assert res.holdings[0].security_id == "P-100"
    assert res.excluded == ()


async def test_different_lineage_is_not_the_same_security(store, book, session_factory):
    """Acquired OTHER (P-200), holding NEWTICK (P-100). No claim, no order."""
    acquire, hold = book
    await acquire("OTHER", 1, T_ACQUIRE)
    await hold("NEWTICK")

    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8, as_of=D_NOW)

    assert res.tickers == frozenset()
    assert res.excluded[0].ticker == "NEWTICK"
    assert res.excluded[0].reason is HoldingExclusionReason.OWNERSHIP_EVIDENCE_MISSING


async def test_holding_outside_its_effective_interval_fails_closed(store, book, session_factory):
    """REUSED's lineage ended in May; today's identity is unresolvable, so no claim.

    This is precisely where ticker equality would have quietly attributed a position in
    one company to an acquisition in another.
    """
    acquire, hold = book
    await acquire("REUSED", 1, datetime(2026, 3, 1, 17, 31, tzinfo=UTC))
    await hold("REUSED")

    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8, as_of=D_NOW)

    assert res.tickers == frozenset()
    ex = res.excluded[0]
    assert ex.ticker == "REUSED"
    assert ex.detail == "identity_unresolved"


async def test_unprovisioned_store_yields_no_ownership(store, book, session_factory):
    """No factor store -> no identities -> nothing attributable. Fail closed, not open."""
    acquire, hold = book
    await acquire("OLDTICK", 1, T_ACQUIRE)
    await hold("NEWTICK")

    provider = StrategyOwnedHoldingsProvider(
        session_factory, FactorStoreSecurityIdentityResolver(None)
    )
    res = await provider.resolve(account_id=6, strategy_id=8, as_of=D_NOW)
    assert res.tickers == frozenset()
