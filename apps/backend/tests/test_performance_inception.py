"""Per-account performance inception marker — account total-return window + benchmark window
both start from `accounts.performance_inception_at` when set (dashboard comparison stays aligned
for a book that started live after its account row)."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.benchmark_snapshot import BenchmarkSnapshot
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user import User

D7 = datetime(2026, 7, 7, 16, 10, tzinfo=UTC)
D17 = datetime(2026, 7, 17, 16, 10, tzinfo=UTC)


@pytest.fixture
async def app_inception(session_factory, monkeypatch):
    """user 1 + paper account 1 with performance_inception_at=D17; equity + benchmark snapshots
    that straddle the marker (so pre-marker rows must be excluded)."""
    from app.db import session as db_session
    from app.main import create_app

    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: session_factory)

    async with session_factory() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
                      label="Paper", performance_inception_at=D17))
        s.add(AccountState(
            account_id=1, cash=Decimal("5000"), equity=Decimal("110000"),
            last_equity=Decimal("110000"), buying_power=Decimal("150000"),
            portfolio_value=Decimal("110000"), daytrade_count=0, day_change=Decimal("0"),
            day_change_pct=Decimal("0"), status="ACTIVE", pattern_day_trader=False,
            trading_blocked=False, account_blocked=False, raw_payload={},
            updated_at=datetime.now(UTC),
        ))
        # equity: pre-marker 100k (must be EXCLUDED), at-marker 105k (the true starting point)
        s.add(EquitySnapshot(account_id=1, ts=D7, equity=Decimal("100000"),
                             cash=Decimal("5000"), portfolio_value=Decimal("100000"),
                             day_change_pct=Decimal("0")))
        s.add(EquitySnapshot(account_id=1, ts=D17, equity=Decimal("105000"),
                             cash=Decimal("5000"), portfolio_value=Decimal("105000"),
                             day_change_pct=Decimal("0")))
        # benchmark: pre-marker 100 (must be EXCLUDED), at-marker 110, current 121
        for ts, px in ((D7, "100"), (D17, "110"), (datetime(2026, 7, 18, 16, 10, tzinfo=UTC), "121")):
            s.add(BenchmarkSnapshot(symbol="SPY", ts=ts, close=Decimal(px)))
        await s.commit()

    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


async def test_account_starting_equity_uses_marker(app_inception: AsyncClient) -> None:
    resp = await app_inception.get("/api/v1/account")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    # starting_equity is the 105k snapshot AT the marker, not the 100k pre-marker one.
    assert Decimal(body["starting_equity"]) == Decimal("105000")
    # total return measured from the marker: 110k / 105k - 1 ~= +4.76%
    assert abs(float(body["total_return_pct"]) - (110000 / 105000 - 1)) < 1e-9


async def test_benchmarks_window_to_marker(app_inception: AsyncClient) -> None:
    resp = await app_inception.get("/api/v1/benchmarks")
    assert resp.status_code == 200, resp.text
    spy = next(r for r in resp.json()["items"] if r["symbol"] == "SPY")
    # inception moved to the marker date; the pre-marker 100 close is excluded.
    assert spy["inception_date"] == "2026-07-17"
    assert float(spy["inception_price"]) == 110.0
    # window return 110 -> 121 = +10%, NOT the global 100 -> 121 = +21%.
    assert spy["return_pct"] == 0.1
