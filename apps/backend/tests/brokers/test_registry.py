"""P5 §2 — BrokerRegistry: per-account adapter construction & lifecycle.

Adapter construction is network-free (the registry never calls connect()), so
these tests need only credentials, not a broker connection. P5 §4 swapped the
credential source from env vars to the encrypted credential store, so each test
seeds the store for the account's user before constructing the registry.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.brokers.alpaca import AlpacaAdapter
from app.brokers.alpaca.credentials import AlpacaCredentials
from app.brokers.registry import BrokerRegistry, _adapter_api_key
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.security import CredentialKind, CredentialStore


def _now() -> datetime:
    return datetime.now(UTC)


def _startup_adapter(api_key: str = "startup-bfy6-key") -> AlpacaAdapter:
    """A stand-in for the connected env (BFY6) startup adapter. Construction is
    network-free; we never call connect() in these tests."""
    return AlpacaAdapter(
        credentials=AlpacaCredentials(api_key=api_key, api_secret="s", paper=True)
    )


class _ConnectSpy:
    """Records which adapters adopt_startup_adapter() connected, without a
    network call. Optionally raises to simulate a connect failure."""

    def __init__(self, *, fail: bool = False) -> None:
        self.connected: list[object] = []
        self._fail = fail

    async def __call__(self, adapter) -> None:
        self.connected.append(adapter)
        if self._fail:
            raise RuntimeError("connect blew up")


async def _seed_user_account_creds(
    session_factory, *, user_id: int, account_id: int, api_key: str
) -> None:
    async with session_factory() as s:
        s.add(User(id=user_id, email=f"u{user_id}@t.test", display_name=f"U{user_id}"))
        await s.flush()
        s.add(
            Account(
                id=account_id,
                user_id=user_id,
                broker="alpaca",
                mode=AccountMode.paper,
                label=f"p{account_id}",
            )
        )
        await s.commit()
    async with session_factory() as s:
        store = CredentialStore(s)
        await store.set(user_id, CredentialKind.ALPACA_PAPER_KEY, api_key)
        await store.set(user_id, CredentialKind.ALPACA_PAPER_SECRET, "secret")


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


# ---- §5a: adopt_startup_adapter (the Range Trader isolation fix) ----


@pytest.mark.asyncio
async def test_adopt_reuses_startup_for_matching_account_and_connects_others(
    session_factory,
):
    """The blocker fix: with two paper accounts owned by two users, the startup
    (BFY6) account reuses the connected startup adapter, while the SECOND
    account (ALPACA_PAPER_1) gets its OWN per-user adapter connected — NOT the
    startup adapter. This is the regression that made a second paper account
    silently trade BFY6.
    """
    startup = _startup_adapter("startup-bfy6-key")
    # acct 1 = startup user (same key as the startup adapter); acct 2 = a second
    # user with a distinct ALPACA_PAPER_1 key.
    await _seed_user_account_creds(
        session_factory, user_id=1, account_id=1, api_key="startup-bfy6-key"
    )
    await _seed_user_account_creds(
        session_factory, user_id=2, account_id=2, api_key="alpaca-paper-1-key"
    )

    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    spy = _ConnectSpy()
    await reg.adopt_startup_adapter(startup, connect=spy)

    # acct 1: reused the already-connected startup adapter (no new connect).
    assert reg.get(1) is startup
    # acct 2: its OWN adapter, carrying ALPACA_PAPER_1's key — not BFY6's.
    acct2 = reg.get(2)
    assert acct2 is not startup
    assert _adapter_api_key(acct2) == "alpaca-paper-1-key"
    # Only the second account's adapter was connected; the startup one was not.
    assert acct2 in spy.connected
    assert startup not in spy.connected


@pytest.mark.asyncio
async def test_adopt_falls_back_to_startup_when_no_creds(session_factory):
    """An account with no constructable per-user adapter (missing store creds)
    falls back to the startup adapter so the startup account still works."""
    startup = _startup_adapter("startup-bfy6-key")
    async with session_factory() as s:
        await _seed_paper(s)  # account 1, user 1, but NO creds seeded
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    assert reg.get(1) is None  # load_all couldn't build it

    spy = _ConnectSpy()
    await reg.adopt_startup_adapter(startup, connect=spy)
    assert reg.get(1) is startup
    assert spy.connected == []  # fallback path never connects


@pytest.mark.asyncio
async def test_adopt_survives_per_user_connect_failure(session_factory):
    """A second account whose connect() fails must not crash boot; its
    (unconnected) per-user adapter stays registered to surface a clean error at
    order time rather than at startup — and it is NOT replaced by the startup
    adapter."""
    startup = _startup_adapter("startup-bfy6-key")
    await _seed_user_account_creds(
        session_factory, user_id=1, account_id=1, api_key="startup-bfy6-key"
    )
    await _seed_user_account_creds(
        session_factory, user_id=2, account_id=2, api_key="alpaca-paper-1-key"
    )
    reg = BrokerRegistry(session_factory)
    await reg.load_all()
    constructed2 = reg.get(2)

    spy = _ConnectSpy(fail=True)
    await reg.adopt_startup_adapter(startup, connect=spy)  # must not raise

    assert reg.get(2) is constructed2  # still its own adapter, not the startup
    assert _adapter_api_key(reg.get(2)) == "alpaca-paper-1-key"
