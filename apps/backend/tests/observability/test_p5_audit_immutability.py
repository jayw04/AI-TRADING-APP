"""P5 §8.1 — audit_log immutability: the DB triggers block UPDATE/DELETE, the
hash chain links per user in commit order, and the canonical hash recomputes.

AuditLogger.write is sync, takes an AsyncSession, and does not commit — the
caller commits. The chain links in COMMIT order, so each test commits one row
at a time (the production pattern; see app/db/models/audit_log.py)."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import IntegrityError, OperationalError

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.observability.audit_hash import compute_row_hash


async def _seed_user(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        await s.commit()


async def _write(session_factory, *, target_id, payload, user_id=1):
    async with session_factory() as s:
        AuditLogger.write(
            s,
            actor_type=AuditActorType.SYSTEM,
            actor_id="test",
            action=AuditAction.STRATEGY_LIVE_ACTIVATED,
            target_type="test",
            target_id=target_id,
            payload=payload,
            user_id=user_id,
        )
        await s.commit()


async def test_direct_update_audit_log_raises(session_factory):
    await _seed_user(session_factory)
    await _write(session_factory, target_id=1, payload={})
    async with session_factory() as s:
        with pytest.raises((IntegrityError, OperationalError)) as exc:
            await s.execute(text("UPDATE audit_log SET action='X' WHERE id=1"))
            await s.commit()
    msg = str(exc.value).lower()
    assert "append-only" in msg or "forbidden" in msg


async def test_direct_delete_audit_log_raises(session_factory):
    await _seed_user(session_factory)
    await _write(session_factory, target_id=1, payload={})
    async with session_factory() as s:
        with pytest.raises((IntegrityError, OperationalError)):
            await s.execute(text("DELETE FROM audit_log WHERE id=1"))
            await s.commit()


async def test_chain_continuity_per_user(session_factory):
    await _seed_user(session_factory)
    for i in range(3):
        await _write(session_factory, target_id=i, payload={"i": i})
    async with session_factory() as s:
        rows = (
            await s.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()
    assert len(rows) == 3
    assert rows[0].prev_hash is None
    assert rows[1].prev_hash == rows[0].row_hash
    assert rows[2].prev_hash == rows[1].row_hash
    # row_hash is actually populated (not the "" default).
    assert all(len(r.row_hash) == 64 for r in rows)


async def test_recompute_matches_stored_hash(session_factory):
    await _seed_user(session_factory)
    for i in range(4):
        await _write(session_factory, target_id=i, payload={"i": i})
    async with session_factory() as s:
        rows = (
            await s.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()
    prev = None
    for row in rows:
        expected = compute_row_hash(
            user_id=row.user_id,
            actor_type=row.actor_type,
            actor_id=row.actor_id,
            action=row.action,
            target_type=row.target_type,
            target_id=row.target_id,
            payload_json=row.payload_json,
            ts=row.ts,
            prev_hash=prev,
        )
        assert row.row_hash == expected
        assert row.prev_hash == prev
        prev = row.row_hash


async def test_separate_users_have_independent_chains(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="a@local"))
        s.add(User(id=2, email="b@local"))
        await s.commit()
    await _write(session_factory, target_id=1, payload={}, user_id=1)
    await _write(session_factory, target_id=2, payload={}, user_id=2)
    async with session_factory() as s:
        rows = (
            await s.execute(select(AuditLog).order_by(AuditLog.id))
        ).scalars().all()
    # Each user's first row starts a fresh chain.
    assert rows[0].prev_hash is None
    assert rows[1].prev_hash is None


def test_ts_canonicalization_datetime_and_string_agree():
    """The write path passes a datetime; the verify script passes a SQLite
    string. Both must hash identically."""
    dt = datetime(2026, 6, 1, 12, 0, 0, tzinfo=UTC)
    common = dict(
        user_id=1, actor_type="system", actor_id="x", action="A",
        target_type="t", target_id="1", payload_json='{"a":1}', prev_hash=None,
    )
    from_dt = compute_row_hash(ts=dt, **common)
    from_str = compute_row_hash(ts="2026-06-01 12:00:00+00:00", **common)
    from_naive = compute_row_hash(ts="2026-06-01 12:00:00", **common)
    assert from_dt == from_str == from_naive
