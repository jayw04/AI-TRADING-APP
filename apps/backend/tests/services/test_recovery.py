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
from app.strategies.engine import RegistrationIntent
from app.strategies.factor_readiness import FactorReadinessNotMet


def _now() -> datetime:
    return datetime.now(UTC)


class _FakeEngine:
    """Records register() calls; raises for strategy ids in ``fail_ids`` (the chaos seam)."""

    def __init__(self, fail_ids: set[int] | None = None) -> None:
        self.registered: list[int] = []
        self.intents: list[RegistrationIntent] = []
        self.fail_ids = fail_ids or set()

    async def register(
        self, strategy_id: int, *, intent: RegistrationIntent = RegistrationIntent.ACTIVATE
    ) -> object:
        self.intents.append(intent)
        if strategy_id in self.fail_ids:
            raise RuntimeError("register boom")
        self.registered.append(strategy_id)
        return object()


class _FactorGatedEngine:
    """The engine's REAL rule, in miniature: the readiness interlock applies to ACTIVATE only.

    Not a stand-in for the engine — a stand-in for the *governance decision* the engine makes,
    so this test can assert what resume-on-boot ASKS FOR rather than trusting that it asks.
    """

    def __init__(self) -> None:
        self.registered: list[int] = []
        self.intents: list[RegistrationIntent] = []

    async def register(
        self, strategy_id: int, *, intent: RegistrationIntent = RegistrationIntent.ACTIVATE
    ) -> object:
        self.intents.append(intent)
        if intent is RegistrationIntent.ACTIVATE:
            raise FactorReadinessNotMet(strategy_id, "producer readiness verdict is FAIL")
        self.registered.append(strategy_id)
        return object()


async def _seed(session_factory, statuses: list[StrategyStatus]) -> list[int]:
    ids: list[int] = []
    async with session_factory() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        for i, status in enumerate(statuses, start=1):
            row = StrategyRow(
                id=i,
                user_id=1,
                name=f"s{i}",
                version="0.0.1",
                type=StrategyType.PYTHON,
                status=status,
                code_path="echo_strategy.py",
                params_json={},
                symbols_json=["AAPL"],
                schedule="event",
                risk_limits_id=None,
                created_at=_now(),
                updated_at=_now(),
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


# ---------------------------------------------------- restart recovery vs. activation (2026-08-28)


async def test_resume_on_boot_recovers_a_live_factor_book_while_readiness_is_red(
    session_factory,
) -> None:
    """THE REGRESSION. A restart during a RED factor store must not de-arm a LIVE book.

    ``_running`` is process-local, so after a restart every durable strategy takes the
    not-yet-registered path in ``engine.register``. Until 2026-08-28 that meant the
    factor-readiness ACTIVATION interlock refused them: the row stayed ``LIVE``, the engine had
    no registration, and **nothing re-registers it when readiness recovers** — this pass runs
    once and has no retry. The control plane went on saying LIVE while the execution plane was
    inert. ``factor-refresh.sh`` restarts the backend itself, so the RED store and the restart
    arrive together by construction.

    Blocking new factor-derived activity is the interlock's purpose; silently de-arming an
    already-active book is not.
    """
    await _seed(session_factory, [StrategyStatus.LIVE])
    eng = _FactorGatedEngine()

    summary = await resume_strategies_on_boot(session_factory, eng)

    assert eng.intents == [RegistrationIntent.RECOVER], (
        "resume-on-boot must request RECOVER. With ACTIVATE the readiness interlock refuses a "
        "durably-LIVE factor book and nothing ever re-registers it."
    )
    assert summary.resumed == 1
    assert summary.failed == 0
    assert summary.failed_ids == []
    assert eng.registered == [1]


async def test_the_db_status_is_never_mutated_by_recovery(session_factory) -> None:
    """Recovery restores a registration; it does not re-decide the durable status.

    The converse of the defect: the repair must not paper over a divergence by *writing* one.
    """
    await _seed(session_factory, [StrategyStatus.LIVE])
    await resume_strategies_on_boot(session_factory, _FactorGatedEngine())
    async with session_factory() as session:
        row = await session.get(StrategyRow, 1)
        assert row.status is StrategyStatus.LIVE


async def test_activation_intent_is_the_default_so_a_new_call_site_is_gated() -> None:
    """The safe default. Every other caller of ``register`` activates, and must stay gated.

    A boolean flag defaulting the other way is how an interlock quietly stops applying.
    """
    import inspect

    from app.strategies.engine import StrategyEngine

    default = inspect.signature(StrategyEngine.register).parameters["intent"].default
    assert default is RegistrationIntent.ACTIVATE
