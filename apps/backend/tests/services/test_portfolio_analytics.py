"""Tests for the Portfolio Analytics Engine (correlation / overlap / diversification)."""

from __future__ import annotations

from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
import pytest_asyncio
from sqlalchemy.ext.asyncio import async_sessionmaker

from app.db.models.account import Account, AccountMode
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.position import Position
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.services import portfolio_analytics as pae

# ---- pure stats ---------------------------------------------------------------

def test_pearson_perfect_and_anti() -> None:
    assert pae.pearson([1, 2, 3, 4], [2, 4, 6, 8]) == pytest.approx(1.0)
    assert pae.pearson([1, 2, 3, 4], [8, 6, 4, 2]) == pytest.approx(-1.0)


def test_pearson_none_when_too_few_or_constant() -> None:
    assert pae.pearson([1, 2], [1, 2]) is None            # < 3 points
    assert pae.pearson([1, 1, 1], [1, 2, 3]) is None       # constant series


def test_jaccard() -> None:
    assert pae.jaccard({"A", "B"}, {"A", "B"}) == 1.0
    assert pae.jaccard({"A", "B"}, {"C", "D"}) == 0.0
    assert pae.jaccard({"A", "B", "C"}, {"A"}) == pytest.approx(1 / 3)


def test_diversification_score() -> None:
    assert pae.diversification_score([0.99, 0.99]) < 10     # highly correlated → low
    assert pae.diversification_score([0.0, -0.2]) == 100    # uncorrelated/negative → 100
    assert pae.diversification_score([]) == 100


# ---- engine integration -------------------------------------------------------

@pytest_asyncio.fixture
async def factory() -> AsyncIterator[async_sessionmaker]:
    from app.config import get_settings
    from app.db import models  # noqa: F401
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield get_sessionmaker()
    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


async def test_compute_flags_lockstep_pair(factory) -> None:
    base = datetime(2026, 6, 25, 16, 10, tzinfo=UTC)
    async with factory() as s:
        for aid in (1, 2, 3):
            s.add(User(id=aid, email=f"u{aid}@t"))
            s.add(Account(id=aid, user_id=aid, broker="alpaca", mode=AccountMode.paper, label=f"acct{aid}"))
        s.add(Symbol(id=1, ticker="AAOI", exchange="X", asset_class="us_equity", name="", active=True))
        s.add(Symbol(id=2, ticker="KO", exchange="X", asset_class="us_equity", name="", active=True))
        # acct1 & acct2 move in lockstep (same equity path); acct3 moves opposite.
        path12 = [100.0, 101, 99, 103, 97, 105]
        path3 = [100.0, 99, 101, 97, 103, 95]
        for i, (e12, e3) in enumerate(zip(path12, path3, strict=True)):
            ts = base + timedelta(days=i)
            for aid, eq in ((1, e12), (2, e12), (3, e3)):
                s.add(EquitySnapshot(account_id=aid, ts=ts, equity=Decimal(str(eq * 1000)),
                                     cash=Decimal(0), portfolio_value=Decimal(0), day_change_pct=Decimal(0)))
        # acct1 & acct2 hold the same name; acct3 holds a different one.
        s.add(Position(user_id=1, account_id=1, symbol_id=1, qty=Decimal("10"), updated_at=base))
        s.add(Position(user_id=2, account_id=2, symbol_id=1, qty=Decimal("10"), updated_at=base))
        s.add(Position(user_id=3, account_id=3, symbol_id=2, qty=Decimal("10"), updated_at=base))
        await s.commit()

    async with factory() as s:
        pa = await pae.compute(s, [(1, "acct1"), (2, "acct2"), (3, "acct3")], window_days=30)

    by_pair = {(p.a, p.b): p for p in pa.pairs}
    assert by_pair[(1, 2)].correlation == pytest.approx(1.0)   # lockstep
    assert by_pair[(1, 2)].overlap_pct == 100.0                # identical holdings
    assert by_pair[(1, 3)].correlation < 0                     # opposite
    assert by_pair[(1, 3)].overlap_pct == 0.0
    assert pa.highest_corr is not None and (pa.highest_corr.a, pa.highest_corr.b) == (1, 2)
    assert pa.correlation_status == "High"
