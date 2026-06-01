"""P5 §6 — /api/v1/strategies/{id}/cooldown endpoints."""
from datetime import UTC, datetime, timedelta

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_strategy(cooldown_offset_seconds: int | None) -> int:
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        strat = StrategyRow(
            user_id=1, name="s", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="x.py", params_json={},
            symbols_json=[], schedule="event", created_at=_now(), updated_at=_now(),
        )
        if cooldown_offset_seconds is not None:
            strat.cooldown_until = _now() + timedelta(seconds=cooldown_offset_seconds)
        session.add(strat)
        await session.commit()
        await session.refresh(strat)
        return strat.id


async def test_cooldown_status_not_in_cooldown(client):
    sid = await _seed_strategy(None)
    r = await client.get(f"/api/v1/strategies/{sid}/cooldown")
    assert r.status_code == 200
    body = r.json()
    assert body["in_cooldown"] is False
    assert body["seconds_remaining"] == 0


async def test_cooldown_status_in_cooldown(client):
    sid = await _seed_strategy(60)
    r = await client.get(f"/api/v1/strategies/{sid}/cooldown")
    assert r.status_code == 200
    body = r.json()
    assert body["in_cooldown"] is True
    assert body["seconds_remaining"] > 0


async def test_cooldown_status_other_user_404(client):
    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as session:
        session.add(User(id=2, email="other@test"))
        strat = StrategyRow(
            user_id=2, name="s2", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="x.py", params_json={},
            symbols_json=[], schedule="event", created_at=_now(), updated_at=_now(),
        )
        session.add(strat)
        await session.commit()
        await session.refresh(strat)
        other_id = strat.id
    r = await client.get(f"/api/v1/strategies/{other_id}/cooldown")
    assert r.status_code == 404


async def test_clear_cooldown_then_status_clear(client):
    sid = await _seed_strategy(60)
    r = await client.post(f"/api/v1/strategies/{sid}/cooldown/clear")
    assert r.status_code == 200
    assert r.json()["ok"] is True

    r = await client.get(f"/api/v1/strategies/{sid}/cooldown")
    assert r.json()["in_cooldown"] is False


async def test_clear_cooldown_audits(client):
    from sqlalchemy import select

    from app.db.models.audit_log import AuditLog
    from app.db.session import get_sessionmaker

    sid = await _seed_strategy(60)
    await client.post(f"/api/v1/strategies/{sid}/cooldown/clear")
    async with get_sessionmaker()() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_COOLDOWN_CLEARED")
        )).scalars().all()
    assert len(audits) >= 1


async def test_clear_cooldown_other_user_404(client):
    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as session:
        session.add(User(id=2, email="other@test"))
        strat = StrategyRow(
            user_id=2, name="s2", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PAPER, code_path="x.py", params_json={},
            symbols_json=[], schedule="event", created_at=_now(), updated_at=_now(),
        )
        session.add(strat)
        await session.commit()
        await session.refresh(strat)
        other_id = strat.id
    r = await client.post(f"/api/v1/strategies/{other_id}/cooldown/clear")
    assert r.status_code == 404
