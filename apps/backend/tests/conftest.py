import os
from collections.abc import AsyncIterator

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

# In-memory SQLite for tests: no filesystem dependency (`./data/` is gitignored
# and absent in a fresh CI checkout). None of the P0 tests need persistent
# tables — they exercise routing, auth, WS heartbeats, and the SELECT-1
# healthcheck path, all of which work against `:memory:`.
os.environ.setdefault("WORKBENCH_DB_URL", "sqlite+aiosqlite:///:memory:")
os.environ.setdefault("WORKBENCH_LOG_LEVEL", "WARNING")
# Tests don't have (and shouldn't use) real Alpaca creds, and shouldn't touch
# the broker network. Disable the lifespan's adapter+scheduler block.
os.environ.setdefault("WORKBENCH_ALPACA_STARTUP_ENABLED", "0")
# P5 §4: the lifespan verifies the Fernet master key at boot and sys.exit(1)s
# if it's missing. Tests run against a fixed throwaway key so the credential
# store round-trips; this is NOT a real key and never touches production data.
os.environ.setdefault(
    "WORKBENCH_MASTER_KEY", "zZ3kP9qHs2vN8wXyB1cD4eF6gH7iJ0kL2mN3oP5qR8s="
)


@pytest.fixture(autouse=True)
def _auth_override(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> None:
    """P5 §3: after the auth stub was removed, every endpoint requires a real
    session cookie. The whole pre-auth test suite seeds ``User(id=1)`` and hits
    endpoints directly, so we transparently authenticate as that user by
    overriding ``get_current_user`` on every app the tests build via
    ``create_app()`` (all test client builders import it lazily, so patching the
    factory reaches them all). The real login / session / TOTP / rate-limit flow
    is exercised separately by tests marked ``@pytest.mark.real_auth``, which
    opt out of this override.
    """
    if request.node.get_closest_marker("real_auth"):
        return

    import app.main as main_mod
    from app.auth.stub import CurrentUser, get_current_user

    real_create_app = main_mod.create_app

    def _patched_create_app():  # type: ignore[no-untyped-def]
        app = real_create_app()
        app.dependency_overrides[get_current_user] = lambda: CurrentUser(
            id=1, email="dev@workbench.local", display_name="Dev", session_id=1
        )
        return app

    monkeypatch.setattr(main_mod, "create_app", _patched_create_app)


@pytest.fixture(autouse=True)
def _market_open(monkeypatch: pytest.MonkeyPatch) -> None:
    """§9A: the StrategyEngine (and, once it lands, the RiskEngine) consult the
    market-session model on every dispatch / order. Pin tests to a REGULAR
    (open) session so the suite isn't wall-clock dependent — otherwise a
    dispatch/order test flips behavior (skipped tick, MARKET_SESSION_CLOSED)
    whenever CI runs overnight, on a weekend, or pre-market.

    Patches ``MarketSession.classify`` at the class level so *every* consumer
    (``MarketSession()`` in the StrategyEngine, ``default_market_session()`` in
    the RiskEngine) sees an open market for a **no-argument** "classify now"
    call. Calls with an EXPLICIT instant pass through untouched, so the session
    unit tests (which always pass an instant) and any test that injects its own
    session keep the real classification.
    """
    from datetime import UTC, datetime

    from app.market.session import MarketSession

    # A Wednesday, 11:00 ET (15:00 UTC) — squarely inside regular hours.
    open_instant = datetime(2026, 6, 17, 15, 0, tzinfo=UTC)
    real_classify = MarketSession.classify

    def _classify(self, instant=None):  # type: ignore[no-untyped-def]
        return real_classify(self, open_instant if instant is None else instant)

    monkeypatch.setattr(MarketSession, "classify", _classify)


@pytest_asyncio.fixture
async def client() -> AsyncIterator[AsyncClient]:
    from app.config import get_settings
    from app.db import models  # noqa: F401 - register models on Base.metadata
    from app.db.base import Base
    from app.db.session import get_engine, get_sessionmaker
    from app.main import create_app

    get_settings.cache_clear()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()

    # Apply the full schema to the production engine the endpoints will reach.
    engine = get_engine()
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        yield ac

    await engine.dispose()
    get_engine.cache_clear()
    get_sessionmaker.cache_clear()


@pytest_asyncio.fixture
async def session_factory() -> AsyncIterator[async_sessionmaker]:
    """A per-test async session factory bound to a fresh in-memory SQLite DB.

    Schema is created via Base.metadata.create_all so service tests can write
    to real tables without depending on alembic migrations running first.
    """
    # Import inside the fixture so `app.db.models` is fully populated before
    # `Base.metadata.create_all` is called.
    from app.db import models  # noqa: F401 - register models on Base.metadata
    from app.db.base import Base

    engine = create_async_engine("sqlite+aiosqlite:///:memory:", future=True)
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        yield factory
    finally:
        await engine.dispose()
