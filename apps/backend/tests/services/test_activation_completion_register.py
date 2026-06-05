"""P6b §4.5 (ADR 0015) — the activation-completion job registers a strategy with
the engine when it transitions PENDING_LIVE → LIVE (so it begins live dispatch).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.jobs.activation_completion import run_activation_completion


class _FakeEngine:
    def __init__(self) -> None:
        self.registered: list[int] = []

    async def register(self, sid: int) -> None:
        self.registered.append(sid)


async def _seed_pending(session_factory) -> int:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=2, user_id=1, broker="alpaca", mode=AccountMode.live, label="L"))
        row = Strategy(
            user_id=1, name="S1", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PENDING_LIVE, code_path="s.py",
            params_json={}, symbols_json=["AAPL"], schedule="event",
            live_activation_initiated_at=datetime.now(UTC) - timedelta(hours=25),
            created_at=datetime.now(UTC), updated_at=datetime.now(UTC),
        )
        s.add(row)
        await s.commit()
        return row.id


async def test_completion_registers_now_live_strategy(session_factory):
    sid = await _seed_pending(session_factory)
    eng = _FakeEngine()
    transitioned = await run_activation_completion(session_factory, bus=None, engine=eng)
    assert transitioned == 1
    assert eng.registered == [sid]
    async with session_factory() as s:
        row = await s.get(Strategy, sid)
    assert row.status == StrategyStatus.LIVE


async def test_completion_without_engine_still_transitions(session_factory):
    sid = await _seed_pending(session_factory)
    transitioned = await run_activation_completion(session_factory, bus=None, engine=None)
    assert transitioned == 1  # engine is optional; transition still happens
    async with session_factory() as s:
        row = await s.get(Strategy, sid)
    assert row.status == StrategyStatus.LIVE
