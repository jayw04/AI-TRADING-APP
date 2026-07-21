"""P7 §7-B pieces 4+5 — operational-hold ENFORCEMENT (ADR 0044 inv 5-7).

Behavioral CI invariant: an ACTIVE operational hold makes a strategy
non-activatable through the authoritative choke (``StrategyEngine.register``) and
through the cooldown-completion path (``ActivationService.complete_pending``), and
the block is recorded (deduped) in the audit log. A cleared hold restores
activation. Fail-closed: the guard never treats an unreadable hold as "no hold".

Static path-inventory supplement: ``register()`` is the single guarded choke, and
the set of code paths that call it is frozen — a NEW activation caller trips the
inventory test so its author must confirm it inherits the guard.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from sqlalchemy import func, select

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.events.bus import EventBus
from app.services.activation import ActivationService
from app.strategies import StrategyEngine
from app.strategies.hold_service import HoldService, StrategyOnHold

FIXTURES_ROOT = Path(__file__).resolve().parents[1] / "fixtures" / "strategies"
BLOCKED = "STRATEGY_ACTIVATION_BLOCKED_BY_HOLD"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper"))
        await session.commit()


@pytest.fixture
async def engine(session_factory, seeded):
    scheduler = AsyncIOScheduler(timezone="America/New_York")
    scheduler.start()
    bar_cache = MagicMock()
    bar_cache.get_bars = AsyncMock(return_value=None)
    order_router = MagicMock()
    order_router.submit = AsyncMock(return_value=MagicMock(id=99))
    eng = StrategyEngine(
        scheduler=scheduler, session_factory=session_factory, bus=EventBus(),
        bar_cache=bar_cache, indicator_computer=MagicMock(), order_router=order_router,
        strategies_root=FIXTURES_ROOT,
    )
    await asyncio.sleep(0)
    yield eng
    await eng.shutdown()
    scheduler.shutdown(wait=False)


async def _echo_row(session_factory, status: StrategyStatus = StrategyStatus.IDLE,
                    initiated_at: datetime | None = None) -> int:
    async with session_factory() as session:
        row = StrategyRow(
            user_id=1, name="echo-test", version="0.0.1", type=StrategyType.PYTHON,
            status=status, code_path="echo_strategy.py", params_json={"timeframe": "1Min"},
            symbols_json=["AAPL"], schedule="event", risk_limits_id=None,
            live_activation_initiated_at=initiated_at, created_at=_now(), updated_at=_now(),
        )
        session.add(row)
        await session.commit()
        await session.refresh(row)
        return row.id


async def _place_hold(session_factory, sid: int, reason_code: str = "AWAITING_COLD_START_FIX"):
    return await HoldService(session_factory).place(
        sid, reason_code=reason_code, reason="repair required",
        effective_at="2026-07-20T22:48:22Z", placed_at="2026-07-21T00:00:00Z",
        placed_by="user:4")


async def _blocked_count(session_factory, sid: int) -> int:
    async with session_factory() as session:
        rows = (await session.execute(
            select(AuditLog).where(
                AuditLog.action == BLOCKED,
                func.json_extract(AuditLog.payload_json, "$.strategy_id") == sid,
            ))).scalars().all()
    return len(rows)


# ---- behavioral invariant: register ----

async def test_active_hold_blocks_register_records_audit_and_clears(engine, session_factory):
    sid = await _echo_row(session_factory)
    hold = await _place_hold(session_factory, sid)

    with pytest.raises(StrategyOnHold) as ei:
        await engine.register(sid)
    assert ei.value.strategy_id == sid and ei.value.reason_code == "AWAITING_COLD_START_FIX"
    assert sid not in {r.strategy_id for r in engine.running_strategies()}  # never went live

    rows = await _blocked_count(session_factory, sid)
    assert rows == 1  # the block is on the record
    async with session_factory() as session:
        row = (await session.execute(select(AuditLog).where(AuditLog.action == BLOCKED))).scalars().one()
    p = json.loads(row.payload_json)
    assert p["source"] == "engine.register" and p["hold_rev"] == hold.record.rev

    # Clearing the hold (the separate governed step) restores activation.
    await HoldService(session_factory).clear(
        sid, expected_rev=hold.record.rev, cleared_at=_now().isoformat(), cleared_by="user:4")
    running = await engine.register(sid)
    assert running.strategy_id == sid


async def test_boot_loop_under_same_hold_dedups_to_one_blocked_event(engine, session_factory):
    sid = await _echo_row(session_factory)
    await _place_hold(session_factory, sid)
    for _ in range(3):  # a crash-restart loop re-attempting the same held strategy
        with pytest.raises(StrategyOnHold):
            await engine.register(sid)
    assert await _blocked_count(session_factory, sid) == 1  # one process token -> one event


async def test_cleared_hold_does_not_block(engine, session_factory):
    sid = await _echo_row(session_factory)
    hold = await _place_hold(session_factory, sid)
    await HoldService(session_factory).clear(
        sid, expected_rev=hold.record.rev, cleared_at=_now().isoformat(), cleared_by="user:4")
    running = await engine.register(sid)  # CLEARED != ACTIVE -> allowed
    assert running.strategy_id == sid
    assert await _blocked_count(session_factory, sid) == 0


# ---- behavioral invariant: cooldown completion ----

async def test_complete_pending_refuses_under_hold_and_keeps_pending(session_factory, seeded):
    initiated = _now() - timedelta(hours=48)  # cooldown long elapsed
    sid = await _echo_row(session_factory, status=StrategyStatus.PENDING_LIVE,
                          initiated_at=initiated)
    await _place_hold(session_factory, sid)

    async with session_factory() as session:
        svc = ActivationService(session=session, bus=None)
        completed = await svc.complete_pending(sid)
    assert completed is False  # refused

    async with session_factory() as session:
        row = await session.get(StrategyRow, sid)
    assert row.status == StrategyStatus.PENDING_LIVE  # NOT flipped to LIVE
    assert await _blocked_count(session_factory, sid) == 1
    async with session_factory() as session:
        p = json.loads((await session.execute(
            select(AuditLog).where(AuditLog.action == BLOCKED))).scalars().one().payload_json)
    assert p["source"] == "activation.complete_pending"


# ---- static path-inventory supplement ----

def test_register_is_the_guarded_choke():
    """The guard is wired INTO register (choke + boundary recheck) and the guard
    helper both records the deduped block and raises StrategyOnHold."""
    reg_src = inspect.getsource(StrategyEngine.register)
    assert reg_src.count("_block_if_on_hold") >= 2  # top choke + boundary recheck
    guard_src = inspect.getsource(StrategyEngine._block_if_on_hold)
    assert "record_activation_blocked" in guard_src
    assert "StrategyOnHold" in guard_src
    assert "read_hold" in guard_src  # fail-closed read (Invalid/Unavailable propagate)


def test_register_caller_inventory_is_frozen():
    """Every code path that activates a strategy funnels through the guarded
    ``register()``. This freezes the known caller set: a NEW caller trips this test,
    forcing its author to confirm it inherits the operational-hold guard (ADR 0044)."""
    app_root = Path(__file__).resolve().parents[2] / "app"
    known = {
        "api/v1/strategies.py",
        "jobs/activation_completion.py",
        "services/eval_harness/service.py",
        "services/llm_live_gate/service.py",
        "services/paper_variant.py",
        "services/range_auto_select.py",
        "services/recovery.py",
    }
    found: set[str] = set()
    for path in app_root.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        if "engine.register(" in text or "strategy_engine.register(" in text or \
           "_engine.register(" in text:
            found.add(path.relative_to(app_root).as_posix())
    assert found == known, (
        f"register() caller set changed: new={found - known}, missing={known - found}. "
        "A new activation caller must funnel through the guarded register(); update "
        "this inventory only after confirming it does."
    )
