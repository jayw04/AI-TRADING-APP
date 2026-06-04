"""P6b §2b-variant — find_in_flight_variant helper."""
from __future__ import annotations

from datetime import UTC, datetime

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.services.paper_variant import find_in_flight_variant

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _strategy(**kw):
    base = dict(
        user_id=1, name="S", code_path="s.py", params_json={}, symbols_json=[],
        created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return Strategy(**base)


async def test_returns_paper_variant_for_parent(session_factory):
    async with session_factory() as s:
        s.add(_strategy(id=1, status=StrategyStatus.LIVE))
        s.add(_strategy(id=2, status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1))
        await s.commit()
    async with session_factory() as s:
        v = await find_in_flight_variant(s, 1)
    assert v is not None and v.id == 2


async def test_returns_none_when_no_variant(session_factory):
    async with session_factory() as s:
        s.add(_strategy(id=1, status=StrategyStatus.LIVE))
        await s.commit()
    async with session_factory() as s:
        assert await find_in_flight_variant(s, 1) is None


async def test_ignores_terminated_variants(session_factory):
    # A variant that was terminated is IDLE, not PAPER_VARIANT → not in-flight.
    async with session_factory() as s:
        s.add(_strategy(id=1, status=StrategyStatus.LIVE))
        s.add(_strategy(id=2, status=StrategyStatus.IDLE, parent_strategy_id=1))
        await s.commit()
    async with session_factory() as s:
        assert await find_in_flight_variant(s, 1) is None
