"""The S8.6 production failure, pinned (PR S-R).

On 2026-08-23 the deployed v1.0.2 runtime had a healthy factor store — 22,104 tickers,
21,988 with a permaticker, identity coverage through 2026-08-20 — and resolved **nothing**:

    resolve("AAPL", today = 2026-08-23)  ->  None
    resolve("AAPL", 2026-08-20)          ->  199059

All 39 Account-6 holdings classified ``identity_unresolved`` and failed closed. Two
defects, both reproduced here:

1. ``owned_holdings.resolve()`` defaulted ``as_of`` to the **wall clock**. The vendor
   TICKERS slice always lags, so on a Sunday — or any morning before ingest — every
   effective interval has already closed and the whole book becomes unattributable. The
   wall clock is not a fact about the data.

2. ``ready`` tested ``store is not None``. A provisioned-but-unusable identity source
   answers ``None`` to everything, ownership silently becomes "nothing is ours", and the
   deployment reads as healthy. It did: ``ready`` was True throughout the failure.

The raw interval semantics are NOT changed — asking about a date outside coverage still
returns ``None``, correctly. What changed is which date gets asked by default.
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

#: The production shape: "today" is a Sunday, coverage ended the previous Thursday.
PROD_TODAY = date(2026, 8, 23)
PROD_COVERAGE = date(2026, 8, 20)
T_ACQUIRE = datetime(2026, 7, 7, 17, 31, tzinfo=UTC)


def _rows(con, rows):
    con.executemany(
        """
        INSERT INTO tickers
            (ticker, permaticker, name, exchange, category, sector, industry,
             isdelisted, firstpricedate, lastpricedate, lastupdated)
        VALUES (?, ?, ?, 'NYSE', 'Domestic Common Stock', NULL, NULL, FALSE, ?, ?, ?)
        """,
        rows,
    )


@pytest.fixture
def store(tmp_path):
    """A store shaped exactly like production on 2026-08-23: coverage ends 08-20."""
    s = FactorDataStore(str(tmp_path / "f.duckdb"))
    _rows(
        s.con,
        [
            ("AAPL", "199059", "Apple", date(1986, 1, 1), PROD_COVERAGE, PROD_COVERAGE),
            ("HON", "198566", "Honeywell", date(1986, 1, 1), PROD_COVERAGE, PROD_COVERAGE),
            ("BRK.B", "196523", "Berkshire", date(1996, 5, 9), PROD_COVERAGE, PROD_COVERAGE),
            # A renamed lineage: same permaticker, two eras.
            ("OLDTICK", "P-900", "Old", date(2020, 1, 1), date(2026, 6, 30), PROD_COVERAGE),
            ("NEWTICK", "P-900", "New", date(2026, 7, 1), PROD_COVERAGE, PROD_COVERAGE),
            # A lineage that ENDED: the bare symbol belongs to someone else now.
            ("REUSED", "P-800", "Reused", date(2019, 1, 1), date(2026, 5, 1), PROD_COVERAGE),
        ],
    )
    yield s
    s.close()


def _resolver(store):
    return FactorStoreSecurityIdentityResolver(store)


# ---- defect 1: the as_of default ------------------------------------------------


def test_identity_coverage_date_is_the_data_frontier_not_the_calendar(store):
    assert store.identity_coverage_date() == PROD_COVERAGE
    assert store.identity_coverage_date() != PROD_TODAY


def test_the_exact_production_failure(store):
    """Reproduces and fixes S8.6 check 8.

    The raw interval question at today's date still answers None — that is correct and
    unchanged. What must now work is the DEFAULT.
    """
    r = _resolver(store)
    assert r.resolve("AAPL", PROD_COVERAGE) == "199059"  # explicit, in coverage
    assert r.resolve("AAPL", PROD_TODAY) is None  # explicit, outside — still None
    assert r.current_identity_date() == PROD_COVERAGE  # the default the caller will use


async def test_holdings_resolve_by_default_on_a_day_with_no_coverage(store, session_factory, book):
    """The whole book was unattributable in production. It must attribute now.

    No ``as_of`` passed — exactly how the engine and the liquidation paths call it.
    """
    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8)

    assert res.tickers == frozenset({"AAPL", "HON", "BRK.B"})
    assert res.excluded == ()
    assert {h.security_id for h in res.holdings} == {"199059", "198566", "196523"}


async def test_explicit_as_of_is_still_honoured(store, session_factory, book):
    """Historical questions must stay answerable at the date the caller asked about."""
    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8, as_of=PROD_TODAY)
    assert res.tickers == frozenset()
    assert {e.detail for e in res.excluded} == {"identity_unresolved"}


async def test_no_identity_coverage_fails_closed(session_factory, book, tmp_path):
    """An empty identity slice must not silently claim the book."""
    empty = FactorDataStore(str(tmp_path / "empty.duckdb"))
    try:
        provider = StrategyOwnedHoldingsProvider(
            session_factory, FactorStoreSecurityIdentityResolver(empty)
        )
        res = await provider.resolve(account_id=6, strategy_id=8)
        assert res.tickers == frozenset()
        assert len(res.excluded) == 3
        assert {e.reason for e in res.excluded} == {HoldingExclusionReason.OWNERSHIP_AMBIGUOUS}
    finally:
        empty.close()


# ---- defect 2: readiness --------------------------------------------------------


def test_ready_is_true_only_when_the_resolver_actually_answers(store):
    assert _resolver(store).ready is True


def test_ready_false_without_a_store():
    assert FactorStoreSecurityIdentityResolver(None).ready is False


def test_ready_false_for_an_empty_identity_slice(tmp_path):
    """The production shape of the failure: a store exists and answers nothing."""
    s = FactorDataStore(str(tmp_path / "empty.duckdb"))
    try:
        assert FactorStoreSecurityIdentityResolver(s).ready is False
    finally:
        s.close()


def test_ready_false_when_every_permaticker_is_null(tmp_path):
    """An unrefreshed store — the column exists but was never backfilled."""
    s = FactorDataStore(str(tmp_path / "null.duckdb"))
    try:
        _rows(s.con, [("AAPL", None, "Apple", date(1986, 1, 1), PROD_COVERAGE, PROD_COVERAGE)])
        r = FactorStoreSecurityIdentityResolver(s)
        assert r.current_identity_date() is None
        assert r.ready is False
    finally:
        s.close()


def test_ready_false_when_no_identity_covers_the_frontier(tmp_path):
    """Coverage date exists but nothing resolves on it — still not ready."""
    s = FactorDataStore(str(tmp_path / "gap.duckdb"))
    try:
        # lastpricedate present (sets the frontier) but firstpricedate is AFTER it, so no
        # interval contains the frontier.
        _rows(s.con, [("X", "P-1", "X", date(2027, 1, 1), PROD_COVERAGE, PROD_COVERAGE)])
        assert FactorStoreSecurityIdentityResolver(s).ready is False
    finally:
        s.close()


def test_old_readiness_test_would_have_passed(store, tmp_path):
    """Why the previous gate missed it: `store is not None` is true for a useless store."""
    empty = FactorDataStore(str(tmp_path / "e2.duckdb"))
    try:
        r = FactorStoreSecurityIdentityResolver(empty)
        assert r._store is not None  # the OLD readiness condition — passes
        assert r.ready is False  # the NEW one — correctly fails
    finally:
        empty.close()


# ---- retained invariants --------------------------------------------------------


async def test_renamed_ticker_still_resolves_to_one_identity(store, session_factory):
    r = _resolver(store)
    assert r.resolve("OLDTICK", date(2026, 4, 1)) == "P-900"
    assert r.resolve("NEWTICK", PROD_COVERAGE) == "P-900"


def test_expired_lineage_still_fails_closed(store):
    """REUSED stopped denoting P-800 in May; at the frontier it must not resolve."""
    r = _resolver(store)
    assert r.resolve("REUSED", date(2026, 3, 1)) == "P-800"
    assert r.resolve("REUSED", PROD_COVERAGE) is None


async def test_no_ticker_equality_fallback_survives(store, session_factory):
    """A held symbol whose current identity is unresolvable stays unattributable."""
    async with session_factory() as session:
        session.add(User(id=1, email="j@t", display_name="J"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        session.add(Symbol(id=1, ticker="REUSED", asset_class="us_equity", active=True))
        await session.commit()
    async with session_factory() as session:
        sym = (
            (await session.execute(select(Symbol).where(Symbol.ticker == "REUSED")))
            .scalars()
            .first()
        )
        session.add(
            Order(
                id=1,
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
                created_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
                updated_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
            )
        )
        session.add(
            Fill(
                id=1,
                order_id=1,
                qty=Decimal("10"),
                price=Decimal("100"),
                filled_at=datetime(2026, 3, 1, 17, 0, tzinfo=UTC),
            )
        )
        session.add(
            Position(
                user_id=1,
                account_id=6,
                symbol_id=sym.id,
                qty=Decimal("10"),
                avg_entry_price=Decimal("100"),
                side="long",
                market_value=Decimal("1000"),
                cost_basis=Decimal("1000"),
                unrealized_pl=Decimal("0"),
                unrealized_plpc=Decimal("0"),
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    provider = StrategyOwnedHoldingsProvider(session_factory, _resolver(store))
    res = await provider.resolve(account_id=6, strategy_id=8)
    assert res.tickers == frozenset()
    assert res.excluded[0].detail == "identity_unresolved"


# ---- shared Account-6-like fixture ---------------------------------------------


@pytest.fixture
async def book(session_factory):
    """Three Strategy-8-acquired holdings, as on the live account."""
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=6, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Six"))
        for i, t in enumerate(["AAPL", "HON", "BRK.B"], start=1):
            session.add(Symbol(id=i, ticker=t, asset_class="us_equity", name=t, active=True))
        await session.commit()

    for oid, t in enumerate(["AAPL", "HON", "BRK.B"], start=1):
        async with session_factory() as session:
            sym = (
                (await session.execute(select(Symbol).where(Symbol.ticker == t))).scalars().first()
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
                    created_at=T_ACQUIRE,
                    updated_at=T_ACQUIRE,
                )
            )
            session.add(
                Fill(
                    id=oid,
                    order_id=oid,
                    qty=Decimal("10"),
                    price=Decimal("100"),
                    filled_at=T_ACQUIRE,
                )
            )
            session.add(
                Position(
                    user_id=1,
                    account_id=6,
                    symbol_id=sym.id,
                    qty=Decimal("10"),
                    avg_entry_price=Decimal("100"),
                    side="long",
                    market_value=Decimal("1000"),
                    cost_basis=Decimal("1000"),
                    unrealized_pl=Decimal("0"),
                    unrealized_plpc=Decimal("0"),
                    updated_at=datetime.now(UTC),
                )
            )
            await session.commit()
