"""Recovery service tests (P11 §5, ADR 0021 property 3).

Covers resume-on-boot: it re-registers exactly the ENGINE_RUNNABLE_STATUSES strategies,
is best-effort (one failure never aborts the others), emits the recovery_* metrics, and
returns an accurate summary. The *idempotency under restart* (register twice → no double
run) is proven end-to-end against the real engine in tests/strategies/test_engine.py.

The "chaos" class (a fault injected at the registration seam) is the best-effort test:
a registrar that raises for one strategy must not take down the resume pass.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from prometheus_client import REGISTRY

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.services.recovery import RESUME, resume_strategies_on_boot


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeEngine:
    """Records register() calls; raises for strategy ids in ``fail_ids`` (the chaos seam)."""

    def __init__(self, fail_ids: set[int] | None = None) -> None:
        self.registered: list[int] = []
        self.fail_ids = fail_ids or set()

    async def register(self, strategy_id: int) -> object:
        if strategy_id in self.fail_ids:
            raise RuntimeError("register boom")
        self.registered.append(strategy_id)
        return object()


async def _seed(session_factory, statuses: list[StrategyStatus]) -> list[int]:
    ids: list[int] = []
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        for i, status in enumerate(statuses, start=1):
            row = StrategyRow(
                id=i, user_id=1, name=f"s{i}", version="0.0.1",
                type=StrategyType.PYTHON, status=status, code_path="echo_strategy.py",
                params_json={}, symbols_json=["AAPL"], schedule="event",
                risk_limits_id=None, created_at=_now(), updated_at=_now(),
            )
            session.add(row)
            ids.append(i)
        await session.commit()
    return ids


def _metric(name: str, recovery_type: str = RESUME) -> float:
    return REGISTRY.get_sample_value(name, {"recovery_type": recovery_type}) or 0.0


async def test_resumes_only_runnable_statuses(session_factory) -> None:
    # PAPER + LIVE are runnable; IDLE is not → only the first two re-register.
    await _seed(session_factory, [StrategyStatus.PAPER, StrategyStatus.LIVE, StrategyStatus.IDLE])
    eng = _FakeEngine()
    summary = await resume_strategies_on_boot(session_factory, eng)
    assert summary.attempted == 2
    assert summary.resumed == 2
    assert summary.failed == 0
    assert sorted(eng.registered) == [1, 2]  # the IDLE row (id=3) was not registered


async def test_best_effort_one_failure_does_not_abort(session_factory) -> None:
    await _seed(session_factory, [StrategyStatus.PAPER, StrategyStatus.PAPER, StrategyStatus.LIVE])
    eng = _FakeEngine(fail_ids={2})  # strategy 2 fails to register
    summary = await resume_strategies_on_boot(session_factory, eng)
    assert summary.attempted == 3
    assert summary.resumed == 2
    assert summary.failed_ids == [2]
    assert sorted(eng.registered) == [1, 3]  # 1 and 3 still resumed


async def test_emits_recovery_metrics(session_factory) -> None:
    a0 = _metric("workbench_recovery_attempts_total")
    s0 = _metric("workbench_recovery_success_total")
    f0 = _metric("workbench_recovery_failures_total")
    await _seed(session_factory, [StrategyStatus.PAPER, StrategyStatus.LIVE])
    eng = _FakeEngine(fail_ids={2})
    await resume_strategies_on_boot(session_factory, eng)
    assert _metric("workbench_recovery_attempts_total") == pytest.approx(a0 + 2)
    assert _metric("workbench_recovery_success_total") == pytest.approx(s0 + 1)
    assert _metric("workbench_recovery_failures_total") == pytest.approx(f0 + 1)


async def test_no_runnable_strategies_is_clean_noop(session_factory) -> None:
    await _seed(session_factory, [StrategyStatus.IDLE])
    eng = _FakeEngine()
    summary = await resume_strategies_on_boot(session_factory, eng)
    assert summary.attempted == 0
    assert summary.resumed == 0
    assert eng.registered == []
