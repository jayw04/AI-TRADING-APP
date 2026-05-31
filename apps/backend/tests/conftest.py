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
