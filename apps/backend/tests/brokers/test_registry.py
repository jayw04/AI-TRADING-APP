"""P5 §2 — BrokerRegistry: per-account adapter construction & lifecycle.

Adapter construction is network-free (the registry never calls connect()), so
these tests need only credentials, not a broker connection. P5 §4 swapped the
credential source from env vars to the encrypted credential store, so each test
seeds the store for the account's user before constructing the registry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.brokers.registry import BrokerRegistry
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.security import CredentialKind, CredentialStore


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_paper_creds(session_factory, user_id: int) -> None:
    async with session_factory() as s:
        store = CredentialStore(s)
        await store.set(user_id, CredentialKind.ALPACA_PAPER_KEY, "paper-key")
        await store.set(user_id, CredentialKind.ALPACA_PAPER_SECRET, "paper-secret")


async def _seed_live_creds(session_factory, user_id: int) -> None:
    async with session_factory() as s:
        store = CredentialStore(s)
        await store.set(user_id, CredentialKind.ALPACA_LIVE_KEY, "live-key")
        await store.set(user_id, CredentialKind.ALPACA_LIVE_SECRET, "live-secret")


async def _seed_paper(session) -> None:
    session.add(User(id=1, email="t@t.test", display_name="T"))
    await session.flush()
    session.add(
        Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="p")
    )
    await session.commit()


@pytest.mark.asyncio
async def test_load_all_constructs_paper_adapter(session_factory):
    async with session_factory() as s:
        await _seed_paper(s)
    await _seed_paper_creds(session_factory, 1)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    adapter = reg.get(1)
    assert adapter is not None
    assert adapter.is_paper is True


@pytest.mark.asyncio
async def test_get_unknown_account_returns_none(session_factory):
    async with session_factory() as s:
        await _seed_paper(s)
    await _seed_paper_creds(session_factory, 1)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    assert reg.get(999) is None


@pytest.mark.asyncio
async def test_refresh_constructs_for_new_account(session_factory):
    async with session_factory() as s:
        await _seed_paper(s)
    await _seed_paper_creds(session_factory, 1)
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
    await _seed_paper_creds(session_factory, 2)
    assert reg.get(2) is None
    await reg.refresh(2)
    assert reg.get(2) is not None


@pytest.mark.asyncio
async def test_bad_credentials_skips_account_without_crashing(
    session_factory, monkeypatch
):
    """A credential failure for one account must not crash load_all — the
    account is simply skipped and get() returns None.

    We force the failure at the credential lookup (rather than via missing
    store rows, which would exercise the same path but less explicitly) so the
    test asserts the registry's resilience directly. The patched function
    matches the P5 §4 async signature.
    """
    from app.brokers import registry as registry_module
    from app.brokers.alpaca.credentials import CredentialsError

    async def _boom(mode, user_id, session_factory):
        raise CredentialsError(f"no creds for {mode}")

    monkeypatch.setattr(registry_module, "credentials_for_mode", _boom)

    async with session_factory() as s:
        await _seed_paper(s)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()  # must not raise
    assert reg.get(1) is None  # construction failed → skipped


@pytest.mark.asyncio
async def test_missing_store_credentials_skips_account(session_factory):
    """With no credentials seeded for the user, construction raises
    CredentialsError internally and the account is skipped (not crashed)."""
    async with session_factory() as s:
        await _seed_paper(s)
    # Deliberately do NOT seed any credentials.
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    assert reg.get(1) is None


@pytest.mark.asyncio
async def test_live_account_constructs_live_adapter(session_factory):
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
    await _seed_live_creds(session_factory, 1)
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    adapter = reg.get(3)
    assert adapter is not None
    assert adapter.is_paper is False  # paper=False selected for a live account


@pytest.mark.asyncio
async def test_register_and_close_all(session_factory):
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
