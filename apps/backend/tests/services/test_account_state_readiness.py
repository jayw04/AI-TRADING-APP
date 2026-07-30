"""Sync-before-admit: startup waits for the first baseline-bearing sync, bounded.

The wait exists so the daily-loss gate is not routinely refusing orders during a boot race. It is
NOT the safety control — the account-scoped gate is — so its contract is narrow: make the window
short, measure it, alert if it does not close, and never hang or crash the boot.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

import pytest

from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.services.account_state_readiness import (
    accounts_missing_state,
    await_account_state_ready,
)
from tests.account_state_helpers import synced_account_state

FAST = dict(timeout_seconds=0.25, poll_interval_seconds=0.01)


def _now() -> datetime:
    return datetime.now(UTC)


async def _add_accounts(session_factory, *ids: int) -> None:
    """One account per user — `accounts` is unique on (user_id, broker, mode)."""
    async with session_factory() as s:
        for i in ids:
            s.add(User(id=i, email=f"u{i}@local"))
            s.add(Account(id=i, user_id=i, broker="alpaca", mode=AccountMode.paper,
                          label=f"a{i}", created_at=_now()))
        await s.commit()


async def _add_state(session_factory, *ids: int) -> None:
    async with session_factory() as s:
        for i in ids:
            s.add(synced_account_state(account_id=i))
        await s.commit()


# ------------------------------------------------------------------ detection

async def test_missing_state_is_detected_per_account(session_factory):
    await _add_accounts(session_factory, 1, 2, 3)
    await _add_state(session_factory, 2)

    async with session_factory() as s:
        assert await accounts_missing_state(s) == (1, 3)


async def test_no_accounts_means_nothing_missing(session_factory):
    async with session_factory() as s:
        assert await accounts_missing_state(s) == ()


# ----------------------------------------------------------------- the wait

async def test_ready_immediately_when_every_account_has_state(session_factory):
    await _add_accounts(session_factory, 1, 2)
    await _add_state(session_factory, 1, 2)
    calls = []

    result = await await_account_state_ready(
        session_factory, lambda: calls.append(1), **FAST
    )

    assert result.ready
    assert result.missing_account_ids == ()
    assert calls == [], "already-ready must not trigger a sync"


async def test_waits_and_becomes_ready_once_sync_writes_state(session_factory):
    await _add_accounts(session_factory, 1)
    attempts = {"n": 0}

    async def fake_sync():
        attempts["n"] += 1
        if attempts["n"] >= 2:  # the first poll finds nothing; the second writes the row
            await _add_state(session_factory, 1)

    result = await await_account_state_ready(session_factory, fake_sync, **FAST)

    assert result.ready
    assert result.attempts >= 2
    assert result.elapsed_seconds >= 0


async def test_bound_expires_and_reports_the_missing_accounts(session_factory):
    """The alert path. Boot continues; the gate keeps these accounts non-admitting."""
    await _add_accounts(session_factory, 1, 2)

    async def never_syncs():
        return None

    result = await await_account_state_ready(session_factory, never_syncs, **FAST)

    assert not result.ready
    assert result.missing_account_ids == (1, 2)
    assert result.elapsed_seconds >= 0.25


async def test_a_failing_sync_does_not_abort_the_wait(session_factory):
    """An unreachable broker at boot must not crash startup — it just leaves accounts pending."""
    await _add_accounts(session_factory, 1)

    async def boom():
        raise RuntimeError("broker unreachable")

    result = await await_account_state_ready(session_factory, boom, **FAST)

    assert not result.ready
    assert result.missing_account_ids == (1,)
    assert result.attempts >= 1


async def test_cancellation_propagates(session_factory):
    """Shutdown must not be swallowed by the retry loop."""
    await _add_accounts(session_factory, 1)

    async def cancel():
        raise asyncio.CancelledError

    with pytest.raises(asyncio.CancelledError):
        await await_account_state_ready(session_factory, cancel, **FAST)


async def test_works_with_no_sync_callable(session_factory):
    """Pure wait: useful where something else drives the sync."""
    await _add_accounts(session_factory, 1)

    result = await await_account_state_ready(session_factory, None, **FAST)

    assert not result.ready
    assert result.attempts == 0
