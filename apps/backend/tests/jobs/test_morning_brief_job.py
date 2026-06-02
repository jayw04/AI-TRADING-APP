"""Scheduled morning-brief job tests (P5.5 §2)."""
from datetime import UTC, datetime

import pytest
from sqlalchemy import func, select

from app.db.models.morning_brief import MorningBrief
from app.db.models.user import User
from app.jobs.morning_brief_generation import run_morning_brief_generation


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        # Two verified users + one un-verified (must be skipped entirely).
        session.add(User(id=1, email="a@local", totp_verified_at=_now()))
        session.add(User(id=2, email="b@local", totp_verified_at=_now()))
        session.add(User(id=3, email="c@local", totp_verified_at=None))
        await session.commit()
    return session_factory


async def test_generates_for_verified_users_only(seeded):
    result = await run_morning_brief_generation(session_factory=seeded)
    assert result == {"generated": 2, "skipped": 0, "failed": 0}
    async with seeded() as session:
        user_ids = (
            await session.execute(select(MorningBrief.user_id).order_by(MorningBrief.user_id))
        ).scalars().all()
    assert user_ids == [1, 2]  # user 3 (un-verified) got no brief


async def test_skips_existing_scheduled_brief(seeded):
    await run_morning_brief_generation(session_factory=seeded)
    result = await run_morning_brief_generation(session_factory=seeded)
    assert result == {"generated": 0, "skipped": 2, "failed": 0}
    async with seeded() as session:
        count = (
            await session.execute(select(func.count()).select_from(MorningBrief))
        ).scalar_one()
    assert count == 2  # idempotent — no duplicates


async def test_continues_on_per_user_failure(seeded, monkeypatch):
    real_generate = None
    from app.services.morning_brief import MorningBriefService

    real_generate = MorningBriefService.generate

    async def _generate(self, user_id, *, trigger="manual"):
        if user_id == 2:
            raise RuntimeError("boom")
        return await real_generate(self, user_id, trigger=trigger)

    monkeypatch.setattr(MorningBriefService, "generate", _generate)

    result = await run_morning_brief_generation(session_factory=seeded)
    assert result == {"generated": 1, "skipped": 0, "failed": 1}
