"""P5 §4 — CredentialStore: set/get/revoke/list/hard_delete_revoked."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models.user import User
from app.db.models.user_credential import UserCredential
from app.security import (
    CredentialKind,
    CredentialNotFoundError,
    CredentialStore,
)


async def _seed_user(session_factory, user_id: int = 1) -> None:
    async with session_factory() as s:
        s.add(User(id=user_id, email=f"u{user_id}@t.test", display_name="U"))
        await s.commit()


@pytest.fixture
async def seeded(session_factory):
    await _seed_user(session_factory, 1)
    return session_factory


async def test_set_then_get_round_trips(seeded):
    async with seeded() as s:
        await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk-xyz")
    async with seeded() as s:
        got = await CredentialStore(s).get(1, CredentialKind.ANTHROPIC_API_KEY)
    assert got == "sk-xyz"


async def test_get_missing_returns_none(seeded):
    async with seeded() as s:
        assert await CredentialStore(s).get(1, CredentialKind.TOTP_SECRET) is None


async def test_get_required_raises_when_missing(seeded):
    async with seeded() as s:
        with pytest.raises(CredentialNotFoundError):
            await CredentialStore(s).get(
                1, CredentialKind.TOTP_SECRET, required=True
            )


async def test_set_twice_rotates_in_place(seeded):
    async with seeded() as s:
        store = CredentialStore(s)
        await store.set(1, CredentialKind.ALPACA_PAPER_KEY, "old")
        await store.set(1, CredentialKind.ALPACA_PAPER_KEY, "new")
    async with seeded() as s:
        assert await CredentialStore(s).get(1, CredentialKind.ALPACA_PAPER_KEY) == "new"
        # Exactly one active row — rotation overwrites, no history kept.
        rows = (
            await s.execute(
                select(UserCredential).where(
                    UserCredential.user_id == 1,
                    UserCredential.kind == CredentialKind.ALPACA_PAPER_KEY.value,
                )
            )
        ).scalars().all()
    assert len(rows) == 1


async def test_revoke_then_get_returns_none(seeded):
    async with seeded() as s:
        store = CredentialStore(s)
        await store.set(1, CredentialKind.PINE_WEBHOOK_SECRET, "pine")
        await store.revoke(1, CredentialKind.PINE_WEBHOOK_SECRET)
    async with seeded() as s:
        assert await CredentialStore(s).get(1, CredentialKind.PINE_WEBHOOK_SECRET) is None


async def test_set_after_revoke_reactivates(seeded):
    async with seeded() as s:
        store = CredentialStore(s)
        await store.set(1, CredentialKind.PINE_WEBHOOK_SECRET, "pine1")
        await store.revoke(1, CredentialKind.PINE_WEBHOOK_SECRET)
        await store.set(1, CredentialKind.PINE_WEBHOOK_SECRET, "pine2")
    async with seeded() as s:
        assert await CredentialStore(s).get(1, CredentialKind.PINE_WEBHOOK_SECRET) == "pine2"


async def test_get_touches_last_used_at(seeded):
    async with seeded() as s:
        await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk")
    async with seeded() as s:
        await CredentialStore(s).get(1, CredentialKind.ANTHROPIC_API_KEY)
    async with seeded() as s:
        row = (
            await s.execute(
                select(UserCredential).where(
                    UserCredential.kind == CredentialKind.ANTHROPIC_API_KEY.value
                )
            )
        ).scalars().first()
    assert row.last_used_at is not None


async def test_list_kinds_returns_all_kinds_no_plaintext(seeded):
    async with seeded() as s:
        await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk")
    async with seeded() as s:
        items = await CredentialStore(s).list_kinds(1)
    # Every kind is represented, set or not.
    assert {i.kind for i in items} == set(CredentialKind)
    by_kind = {i.kind: i for i in items}
    assert by_kind[CredentialKind.ANTHROPIC_API_KEY].has_value is True
    assert by_kind[CredentialKind.TOTP_SECRET].has_value is False
    # Metadata never carries plaintext or ciphertext.
    for i in items:
        assert not hasattr(i, "ciphertext")
        assert not hasattr(i, "value")


async def test_list_kinds_marks_revoked_as_not_set(seeded):
    async with seeded() as s:
        store = CredentialStore(s)
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "k")
        await store.revoke(1, CredentialKind.ALPACA_LIVE_KEY)
    async with seeded() as s:
        items = await CredentialStore(s).list_kinds(1)
    by_kind = {i.kind: i for i in items}
    assert by_kind[CredentialKind.ALPACA_LIVE_KEY].has_value is False
    assert by_kind[CredentialKind.ALPACA_LIVE_KEY].revoked_at is not None


async def test_hard_delete_revoked_respects_retention(seeded):
    """Rows revoked > 7 days ago are deleted; recently-revoked rows survive.

    Exercises the SQLite naive-datetime coercion in _ensure_aware: we backdate
    revoked_at to a naive value to mimic SQLite's round-trip.
    """
    async with seeded() as s:
        store = CredentialStore(s)
        await store.set(1, CredentialKind.ALPACA_PAPER_KEY, "old")
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "recent")
        await store.revoke(1, CredentialKind.ALPACA_PAPER_KEY)
        await store.revoke(1, CredentialKind.ALPACA_LIVE_KEY)

    # Backdate the paper row's revoked_at to 8 days ago (naive, as SQLite returns).
    async with seeded() as s:
        paper = (
            await s.execute(
                select(UserCredential).where(
                    UserCredential.kind == CredentialKind.ALPACA_PAPER_KEY.value
                )
            )
        ).scalars().first()
        paper.revoked_at = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=8)
        await s.commit()

    async with seeded() as s:
        deleted = await CredentialStore(s).hard_delete_revoked()
    assert deleted == 1

    async with seeded() as s:
        remaining = (
            await s.execute(select(UserCredential.kind))
        ).scalars().all()
    assert CredentialKind.ALPACA_PAPER_KEY.value not in remaining
    assert CredentialKind.ALPACA_LIVE_KEY.value in remaining


async def test_set_rejects_empty_plaintext(seeded):
    async with seeded() as s:
        with pytest.raises(ValueError):
            await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "")


async def test_revoke_missing_is_noop(seeded):
    async with seeded() as s:
        # No row exists — revoke should not raise.
        await CredentialStore(s).revoke(1, CredentialKind.TOTP_SECRET)
