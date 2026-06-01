"""StrategyCooldownService tests (P5 §6).

Adapted to the live schema: strategies have no account_id (mapped via
user_id + status↔mode); the audit action stores the UPPER convention value
'STRATEGY_COOLDOWN_CLEARED'.
"""
import asyncio
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.services.strategy_cooldown import (
    DEFAULT_COOLDOWN_SECONDS,
    StrategyCooldownService,
)


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(StrategyRow(
            id=10, user_id=1, name="s10", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        await session.commit()
    return session_factory


async def test_status_not_in_cooldown_initially(seeded):
    async with seeded() as session:
        status = await StrategyCooldownService(session).status(10)
    assert status.in_cooldown is False
    assert status.seconds_remaining == 0


async def test_default_duration_is_60s():
    assert DEFAULT_COOLDOWN_SECONDS == 60


async def test_set_cooldown_then_status(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10, reason="test")
    async with seeded() as session:
        status = await StrategyCooldownService(session).status(10)
    assert status.in_cooldown is True
    assert 55 <= status.seconds_remaining <= 60


async def test_is_in_cooldown_returns_true_and_until(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10)
    async with seeded() as session:
        in_cd, until = await StrategyCooldownService(session).is_in_cooldown(10)
    assert in_cd is True
    assert until is not None and until > _now()


async def test_is_in_cooldown_missing_strategy_returns_false(seeded):
    async with seeded() as session:
        in_cd, until = await StrategyCooldownService(session).is_in_cooldown(999)
    assert in_cd is False and until is None


async def test_cooldown_expires_naturally(seeded):
    async with seeded() as session:
        strat = await session.get(StrategyRow, 10)
        strat.cooldown_until = _now() - timedelta(seconds=10)
        await session.commit()
    async with seeded() as session:
        in_cd, until = await StrategyCooldownService(session).is_in_cooldown(10)
    assert in_cd is False and until is None


async def test_set_cooldown_extends_existing(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10, duration_seconds=10)
    async with seeded() as session:
        first = (await session.get(StrategyRow, 10)).cooldown_until
    await asyncio.sleep(0.05)
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10, duration_seconds=60)
    async with seeded() as session:
        second = (await session.get(StrategyRow, 10)).cooldown_until
    assert second > first


async def test_set_cooldown_missing_strategy_is_noop(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(999)  # no raise


async def test_clear_cooldown_resets_state(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10)
    async with seeded() as session:
        await StrategyCooldownService(session).clear_cooldown(10, user_id=1)
    async with seeded() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.cooldown_until is None


async def test_clear_cooldown_audits(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10)
    async with seeded() as session:
        await StrategyCooldownService(session).clear_cooldown(10, user_id=1)
    async with seeded() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_COOLDOWN_CLEARED")
        )).scalars().all()
    assert len(audits) == 1
    assert audits[0].target_id == "10"


async def test_clear_cooldown_other_user_raises_permission(seeded):
    async with seeded() as session:
        session.add(User(id=2, email="other@local"))
        await session.commit()
    async with seeded() as session:
        await StrategyCooldownService(session).set_cooldown(10)
    async with seeded() as session:
        with pytest.raises(PermissionError):
            await StrategyCooldownService(session).clear_cooldown(10, user_id=2)


async def test_clear_cooldown_when_not_set_is_noop_no_audit(seeded):
    async with seeded() as session:
        await StrategyCooldownService(session).clear_cooldown(10, user_id=1)
    async with seeded() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_COOLDOWN_CLEARED")
        )).scalars().all()
    assert len(audits) == 0


async def test_clear_cooldown_missing_strategy_raises_value(seeded):
    async with seeded() as session:
        with pytest.raises(ValueError):
            await StrategyCooldownService(session).clear_cooldown(999, user_id=1)


async def test_status_missing_strategy_raises(seeded):
    async with seeded() as session:
        with pytest.raises(ValueError):
            await StrategyCooldownService(session).status(999)
