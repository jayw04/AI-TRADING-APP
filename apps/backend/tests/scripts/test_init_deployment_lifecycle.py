"""P7 §7-A/§7-B — deployment-lifecycle init script: dry-run, idempotent, hold-safe."""

from __future__ import annotations

import importlib.util
import sys
from datetime import UTC, datetime
from pathlib import Path

from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.strategy_state import StrategyState
from app.db.models.user import User

_SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "init_deployment_lifecycle.py"
_spec = importlib.util.spec_from_file_location("init_deployment_lifecycle", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = _mod
_spec.loader.exec_module(_mod)

SID = 11
K_DEPLOY = "deployment"
K_HOLD = "operational_hold"


def _now() -> datetime:
    return datetime.now(UTC)


async def _seed_strategy(session_factory) -> None:
    async with session_factory() as session, session.begin():
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(StrategyRow(
            id=SID, user_id=1, name="momentum-daily", version="0.2.0",
            type=__import__("app.db.enums", fromlist=["StrategyType"]).StrategyType.PYTHON,
            status=__import__("app.db.enums", fromlist=["StrategyStatus"]).StrategyStatus.IDLE,
            code_path="templates/momentum_daily.py", params_json={}, symbols_json=["SPY"],
            schedule="event", risk_limits_id=None, created_at=_now(), updated_at=_now()))


async def _seed_state(session_factory, key: str, value: dict) -> None:
    async with session_factory() as session, session.begin():
        session.add(StrategyState(strategy_id=SID, key=key, value=value, updated_at=_now()))


async def _read(session_factory, key: str) -> dict | None:
    async with session_factory() as session:
        from sqlalchemy import select
        return (await session.execute(
            select(StrategyState.value).where(
                StrategyState.strategy_id == SID, StrategyState.key == key))).scalars().first()


async def _run(session_factory, *, apply: bool):
    async with session_factory() as session, session.begin():
        return await _mod.init_deployment_lifecycle(session, SID, apply=apply)


async def test_dry_run_plans_but_writes_nothing(session_factory):
    await _seed_strategy(session_factory)
    res = await _run(session_factory, apply=False)
    assert res.action == "would_write" and res.exit_code == 0
    assert res.planned_blob["state"] == "NEVER_DEPLOYED"
    assert res.planned_blob["has_ever_deployed"] is False
    assert res.planned_blob["first_deployed_at"] is None
    assert res.planned_blob["active_seed_attempt"] is None
    assert res.planned_blob["_rev"] == 0
    assert await _read(session_factory, K_DEPLOY) is None  # nothing persisted


async def test_apply_writes_never_deployed_blob(session_factory):
    await _seed_strategy(session_factory)
    res = await _run(session_factory, apply=True)
    assert res.action == "wrote" and res.exit_code == 0
    stored = await _read(session_factory, K_DEPLOY)
    assert stored is not None
    assert stored["state"] == "NEVER_DEPLOYED" and stored["has_ever_deployed"] is False
    assert stored["first_deployed_at"] is None and stored["active_seed_attempt"] is None
    assert stored["_rev"] == 0


async def test_already_initialized_refuses_and_does_not_overwrite(session_factory):
    await _seed_strategy(session_factory)
    existing = {"_rev": 7, "state": "DEPLOYED", "has_ever_deployed": True,
                "first_deployed_at": "2026-07-01T00:00:00+00:00", "active_seed_attempt": None}
    await _seed_state(session_factory, K_DEPLOY, existing)
    res = await _run(session_factory, apply=True)
    assert res.action == "already_initialized" and res.exit_code == 3
    assert await _read(session_factory, K_DEPLOY) == existing  # untouched, no clobber


async def test_apply_never_touches_operational_hold(session_factory):
    await _seed_strategy(session_factory)
    hold = {"schema_version": 1, "_rev": 3, "status": "ACTIVE",
            "reason_code": "AWAITING_COLD_START_FIX", "effective_at": "2026-07-20T22:48:22Z",
            "placed_at": "2026-07-21T00:00:00Z"}
    await _seed_state(session_factory, K_HOLD, hold)
    res = await _run(session_factory, apply=True)
    assert res.action == "wrote"
    assert res.operational_hold_raw == hold  # echoed read-only
    assert await _read(session_factory, K_HOLD) == hold  # and DURABLY unchanged


async def test_strategy_not_found_writes_nothing(session_factory):
    res = await _run(session_factory, apply=True)  # no strategy seeded
    assert res.action == "strategy_not_found" and res.exit_code == 4
    assert await _read(session_factory, K_DEPLOY) is None
