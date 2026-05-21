"""Asset sync tests with mocked adapter + an in-memory SQLite session."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy import select

from app.db.models.symbol import Symbol
from app.events.bus import EventBus
from app.services.asset_sync import AssetSyncService


@pytest.fixture
def mock_adapter() -> MagicMock:
    a = MagicMock()
    a.list_assets.return_value = [
        {"symbol": "AAPL", "exchange": "NASDAQ", "asset_class": "us_equity", "name": "Apple Inc."},
        {"symbol": "MSFT", "exchange": "NASDAQ", "asset_class": "us_equity", "name": "Microsoft"},
        {"symbol": "SPY", "exchange": "ARCA", "asset_class": "us_equity", "name": "SPDR S&P 500"},
    ]
    return a


async def test_asset_sync_inserts_new_symbols(session_factory, mock_adapter) -> None:
    bus = EventBus()
    svc = AssetSyncService(mock_adapter, session_factory, bus)
    counts = await svc.sync_once()

    assert counts["count_total"] == 3
    assert counts["count_added"] == 3
    assert counts["count_deactivated"] == 0

    async with session_factory() as session:
        rows = (await session.execute(select(Symbol).order_by(Symbol.ticker))).scalars().all()
        tickers = [r.ticker for r in rows]
        assert "AAPL" in tickers
        assert "MSFT" in tickers
        assert "SPY" in tickers
        assert all(r.active for r in rows)


async def test_asset_sync_deactivates_missing(session_factory, mock_adapter) -> None:
    # Seed a symbol that's NOT in the mock Alpaca response.
    async with session_factory() as session:
        session.add(
            Symbol(
                ticker="STALE",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Stale Co",
                active=True,
            )
        )
        await session.commit()

    bus = EventBus()
    svc = AssetSyncService(mock_adapter, session_factory, bus)
    counts = await svc.sync_once()

    assert counts["count_deactivated"] == 1

    async with session_factory() as session:
        stale = (
            await session.execute(select(Symbol).where(Symbol.ticker == "STALE"))
        ).scalars().first()
        assert stale is not None
        assert stale.active is False


async def test_asset_sync_reactivates_returning_symbol(session_factory, mock_adapter) -> None:
    # AAPL is in the Alpaca mock and was previously deactivated locally.
    async with session_factory() as session:
        session.add(
            Symbol(
                ticker="AAPL",
                exchange="NASDAQ",
                asset_class="us_equity",
                name="Apple Inc.",
                active=False,
            )
        )
        await session.commit()

    bus = EventBus()
    svc = AssetSyncService(mock_adapter, session_factory, bus)
    counts = await svc.sync_once()

    # AAPL is "updated" (it existed before), not "added".
    assert counts["count_updated"] >= 1

    async with session_factory() as session:
        aapl = (
            await session.execute(select(Symbol).where(Symbol.ticker == "AAPL"))
        ).scalars().first()
        assert aapl is not None
        assert aapl.active is True
