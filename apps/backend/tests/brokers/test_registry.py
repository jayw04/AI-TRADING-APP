"""P5 §2 — BrokerRegistry: per-account adapter construction & lifecycle.

Adapter construction is network-free (the registry never calls connect()), so
these tests need only env credentials, not a broker connection.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.brokers.registry import BrokerRegistry
from app.config import get_settings
from app.db.models.account import Account, AccountMode
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
def paper_creds(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "paper-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


@pytest.fixture
def paper_and_live_creds(monkeypatch):
    monkeypatch.setenv("ALPACA_PAPER_API_KEY", "paper-key")
    monkeypatch.setenv("ALPACA_PAPER_API_SECRET", "paper-secret")
    monkeypatch.setenv("ALPACA_LIVE_API_KEY", "live-key")
    monkeypatch.setenv("ALPACA_LIVE_API_SECRET", "live-secret")
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


async def _seed_paper(session) -> None:
    session.add(User(id=1, email="t@t.test", display_name="T"))
    await session.flush()
    session.add(
        Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="p")
    )
    await session.commit()


@pytest.mark.asyncio
async def test_load_all_constructs_paper_adapter(session_factory, paper_creds):
    async with session_factory() as s:
        await _seed_paper(s)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    adapter = reg.get(1)
    assert adapter is not None
    assert adapter.is_paper is True


@pytest.mark.asyncio
async def test_get_unknown_account_returns_none(session_factory, paper_creds):
    async with session_factory() as s:
        await _seed_paper(s)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    assert reg.get(999) is None


@pytest.mark.asyncio
async def test_refresh_constructs_for_new_account(session_factory, paper_creds):
    async with session_factory() as s:
        await _seed_paper(s)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()

    # A genuinely new account. UniqueConstraint(user_id, broker, mode) means a
    # second paper alpaca account needs a different user; use user 2.
    async with session_factory() as s:
        s.add(User(id=2, email="u2@t.test", display_name="U2"))
        await s.flush()
        s.add(
            Account(id=2, user_id=2, broker="alpaca", mode=AccountMode.paper, label="p2")
        )
        await s.commit()
    assert reg.get(2) is None
    await reg.refresh(2)
    assert reg.get(2) is not None


@pytest.mark.asyncio
async def test_bad_credentials_skips_account_without_crashing(
    session_factory, monkeypatch
):
    """A credential failure for one account must not crash load_all — the
    account is simply skipped and get() returns None.

    We force the failure at the credential lookup (rather than via env vars,
    which a developer's real .env would override) so the test asserts the
    registry's resilience directly.
    """
    from app.brokers import registry as registry_module
    from app.brokers.alpaca.credentials import CredentialsError

    def _boom(mode: str):
        raise CredentialsError(f"no creds for {mode}")

    monkeypatch.setattr(registry_module, "credentials_for_mode", _boom)

    async with session_factory() as s:
        await _seed_paper(s)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()  # must not raise
    assert reg.get(1) is None  # construction failed → skipped


@pytest.mark.asyncio
async def test_live_account_constructs_live_adapter(session_factory, paper_and_live_creds):
    async with session_factory() as s:
        session_user = User(id=1, email="t@t.test", display_name="T")
        s.add(session_user)
        await s.flush()
        s.add(
            Account(
                id=3, user_id=1, broker="alpaca", mode=AccountMode.live, label="live",
                broker_mode_locked_at=_now(),
            )
        )
        await s.commit()
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    adapter = reg.get(3)
    assert adapter is not None
    assert adapter.is_paper is False  # paper=False selected for a live account


@pytest.mark.asyncio
async def test_register_and_close_all(session_factory, paper_creds):
    closed = {"n": 0}

    class _SpyAdapter:
        is_paper = True
        is_connected = False

        def disconnect(self):
            closed["n"] += 1

    reg = BrokerRegistry(session_factory)
    spy = _SpyAdapter()
    reg.register(42, spy)
    assert reg.get(42) is spy
    reg.close_all()
    assert closed["n"] == 1
    assert reg.get(42) is None
