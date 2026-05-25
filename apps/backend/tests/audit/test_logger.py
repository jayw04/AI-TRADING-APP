"""Unit tests for :class:`AuditLogger`.

The tests use the ``session_factory`` fixture (in-memory SQLite with the
full schema applied) so we exercise the real ``AuditLog`` insert path
and the JSON-column round-trip.
"""

from __future__ import annotations

import json

import pytest
from sqlalchemy import select

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.audit_log import AuditLog


async def test_write_with_enum_action_persists_row(session_factory) -> None:
    async with session_factory() as session:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id="42",
            action=AuditAction.ORDER_SUBMITTED,
            target_type="order",
            target_id=7,
            payload={"broker_order_id": "abc-123"},
            user_id=42,
        )
        await session.commit()
        row = (await session.execute(select(AuditLog))).scalars().first()

    assert row is not None
    assert row.action == "ORDER_SUBMITTED"
    assert row.actor_type == "user"
    assert row.actor_id == "42"
    assert row.target_type == "order"
    assert row.target_id == "7"
    assert row.user_id == 42
    assert json.loads(row.payload_json) == {"broker_order_id": "abc-123"}


async def test_write_accepts_plain_string_action(session_factory) -> None:
    """``lifecycle.py`` constructs action names dynamically from
    ``OrderStatus``; the helper must accept a plain string in addition to
    the enum."""
    async with session_factory() as session:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="trade_stream",
            action="ORDER_FILLED",  # string, not enum
            target_type="order",
            target_id=1,
            payload=None,
        )
        await session.commit()
        row = (await session.execute(select(AuditLog))).scalars().first()

    assert row.action == "ORDER_FILLED"
    assert row.payload_json == "{}"


async def test_write_does_not_commit(session_factory) -> None:
    """Caller owns the transaction. After ``write`` but before ``commit``,
    the row is in the session but not visible from a separate session."""
    async with session_factory() as session:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.SYSTEM,
            actor_id=None,
            action=AuditAction.STRATEGY_REGISTERED,
            target_type="strategy",
            target_id=1,
            payload={},
        )
        # No commit yet.
        async with session_factory() as other:
            rows = (await other.execute(select(AuditLog))).scalars().all()
            assert rows == []

        await session.commit()

    async with session_factory() as session:
        rows = (await session.execute(select(AuditLog))).scalars().all()
        assert len(rows) == 1


async def test_target_id_int_is_stringified(session_factory) -> None:
    async with session_factory() as session:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id="1",
            action=AuditAction.STRATEGY_STARTED,
            target_type="strategy",
            target_id=99,  # int
            payload={},
        )
        await session.commit()
        row = (await session.execute(select(AuditLog))).scalars().first()
    assert row.target_id == "99"


async def test_unknown_action_string_can_still_be_constructed_as_enum() -> None:
    """``AuditAction(value)`` raises for unknown strings — the safety net
    that catches typos when callers go through the enum constructor."""
    with pytest.raises(ValueError):
        AuditAction("ORDER_DOES_NOT_EXIST")


def test_all_existing_call_site_strings_are_covered() -> None:
    """The enum must include every literal action string used in the
    codebase today, so the refactor is byte-identical to the prior
    inline ``session.add(AuditLog(...))`` writes."""
    required = {
        # router.py
        "ORDER_RISK_PASSED",
        "ORDER_REJECTED_BY_RISK",
        "ORDER_REJECTED_BY_BROKER",
        "ORDER_SUBMITTED",
        "ORDER_CANCEL_REQUESTED",
        "ORDER_CANCELED_LOCAL",
        "ORDER_CANCEL_REJECTED_BY_BROKER",
        "ORDER_REPLACE_REQUESTED",
        "ORDER_REPLACE_REJECTED_BY_BROKER",
        # lifecycle.py
        "ORDER_FILL_INGESTED",
        "ORDER_PARTIALLY_FILLED",
        "ORDER_FILLED",
        "ORDER_CANCELED",
        "ORDER_EXPIRED",
        "ORDER_REJECTED",
        # engine.py
        "STRATEGY_REGISTERED",
        "STRATEGY_UNREGISTERED",
        "STRATEGY_ERROR",
    }
    enum_values = {a.value for a in AuditAction}
    missing = required - enum_values
    assert not missing, f"AuditAction missing existing call-site values: {missing}"
