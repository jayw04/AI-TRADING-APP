"""GET /api/v1/account — real AccountState-backed handler."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest
from httpx import ASGITransport, AsyncClient

from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.user import User
from app.services.day_change_basis import (
    BROKER_LAST_EQUITY,
    PRIOR_SESSION_CLOSE_PROXY,
    UNAVAILABLE,
)


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
                day_change_basis=BROKER_LAST_EQUITY,
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


async def _client_for_state(session_factory, monkeypatch, **state_kwargs):
    """One account + one AccountState row, served by the real app."""
    from app.db import session as db_session
    from app.main import create_app

    monkeypatch.setattr(db_session, "get_sessionmaker", lambda: session_factory)
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper")
        )
        session.add(
            AccountState(
                account_id=1,
                cash=Decimal("50000"),
                buying_power=Decimal("150000"),
                daytrade_count=0,
                status="ACTIVE",
                pattern_day_trader=False,
                trading_blocked=False,
                account_blocked=False,
                raw_payload={},
                updated_at=datetime.now(UTC),
                **state_kwargs,
            )
        )
        await session.commit()
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


async def test_account_reports_no_day_change_when_the_basis_is_unavailable(
    session_factory, monkeypatch
) -> None:
    """`null`, not `0.00`. A zero here renders as a measured flat day in the dashboard, which is
    exactly the false claim this basis label exists to prevent."""
    client = await _client_for_state(
        session_factory,
        monkeypatch,
        equity=Decimal("102177.42"),
        last_equity=Decimal(0),
        portfolio_value=Decimal("102177.42"),
        day_change=Decimal(0),  # placeholder held for legacy consumers
        day_change_pct=Decimal(0),
        day_change_basis=UNAVAILABLE,
    )
    async with client as ac:
        resp = await ac.get("/api/v1/account")
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["day_change"] is None
    assert body["day_change_pct"] is None
    assert body["day_change_basis"] == UNAVAILABLE


async def test_account_serves_the_persisted_proxy_figures_verbatim(
    session_factory, monkeypatch
) -> None:
    """The endpoint re-derives nothing: whatever the sync decided is what the dashboard shows, so
    the display and the persisted risk-path input cannot drift apart."""
    client = await _client_for_state(
        session_factory,
        monkeypatch,
        equity=Decimal("80000"),
        last_equity=Decimal(0),
        portfolio_value=Decimal("80000"),
        day_change=Decimal("-4000"),
        day_change_pct=Decimal("-0.047619"),
        day_change_basis=PRIOR_SESSION_CLOSE_PROXY,
    )
    async with client as ac:
        resp = await ac.get("/api/v1/account")
    body = resp.json()
    assert Decimal(body["day_change"]) == Decimal("-4000")
    assert body["day_change_basis"] == PRIOR_SESSION_CLOSE_PROXY
