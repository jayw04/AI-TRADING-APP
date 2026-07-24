"""GET /api/v1/account — real AccountState-backed handler."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.equity_snapshot import EquitySnapshot
from app.db.models.user import User


@pytest.fixture
async def app_with_seeded_account(session_factory, monkeypatch):
    """Build an app whose sessionmaker points at the test DB, then seed
    a user + paper account + account_state row."""
    from app.db import session as db_session
    from app.main import create_app

    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: session_factory)

    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            AccountState(
                account_id=1,
                cash=Decimal("50000"),
                equity=Decimal("98750.42"),
                last_equity=Decimal("100000"),
                buying_power=Decimal("150000"),
                portfolio_value=Decimal("98750.42"),
                daytrade_count=0,
                day_change=Decimal("-1249.58"),
                day_change_pct=Decimal("-0.012496"),
                status="ACTIVE",
                pattern_day_trader=False,
                trading_blocked=False,
                account_blocked=False,
                raw_payload={},
                updated_at=datetime.now(UTC),
            )
        )
        await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac


async def test_account_returns_real_state(app_with_seeded_account: AsyncClient) -> None:
    resp = await app_with_seeded_account.get("/api/v1/account")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["account_id"] == 1
    assert body["mode"] == "paper"
    assert body["status"] == "ACTIVE"
    assert Decimal(body["equity"]) == Decimal("98750.42")
    assert Decimal(body["day_change"]) == Decimal("-1249.58")


async def test_account_404_when_no_account_row(client: AsyncClient) -> None:
    """Default test fixture has no seeded account → 404."""
    resp = await client.get("/api/v1/account")
    assert resp.status_code == 404


async def test_account_day_change_falls_back_to_equity_snapshot(
    session_factory, monkeypatch
) -> None:
    """When broker last_equity is 0, today's change uses the prior snapshot baseline."""
    from app.db import session as db_session
    from app.main import create_app

    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: session_factory)

    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper"
            )
        )
        session.add(
            AccountState(
                account_id=1,
                cash=Decimal("50000"),
                equity=Decimal("102177.42"),
                last_equity=Decimal(0),
                buying_power=Decimal("150000"),
                portfolio_value=Decimal("102177.42"),
                daytrade_count=0,
                day_change=Decimal("102177.42"),
                day_change_pct=Decimal(0),
                status="ACTIVE",
                pattern_day_trader=False,
                trading_blocked=False,
                account_blocked=False,
                raw_payload={},
                updated_at=datetime.now(UTC),
            )
        )
        session.add(
            EquitySnapshot(
                account_id=1,
                ts=datetime(2026, 7, 22, 20, 0, tzinfo=UTC),
                equity=Decimal("101500"),
                cash=Decimal("50000"),
                portfolio_value=Decimal("101500"),
                day_change_pct=Decimal("0.005"),
            )
        )
        await session.commit()

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        resp = await ac.get("/api/v1/account")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert Decimal(body["day_change"]) == Decimal("677.42")
    assert Decimal(body["day_change_pct"]).quantize(Decimal("0.0001")) == Decimal("0.0067")
