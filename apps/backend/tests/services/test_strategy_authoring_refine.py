"""P7 §6 — refine_strategy + the auto-debug backtest orchestration."""
from __future__ import annotations

import json
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import AsyncMock

from sqlalchemy import select

import app.api.v1.strategy_authoring as ep
from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.security import CredentialKind, CredentialStore
from app.services.strategy_authoring import service
from app.services.strategy_authoring.backtest import BacktestOutcome
from app.services.strategy_authoring.service import (
    BudgetExceededError,
    GenerationResult,
    refine_strategy,
)


def _result(code="class A:\n    pass\n") -> GenerationResult:
    return GenerationResult(
        code=code, assumptions=[], explanation="", cost_usd=Decimal("0.01"),
        prompt_version="v1", model="claude-sonnet-4-6",
    )


def _fake_call(code: str):
    return SimpleNamespace(
        content_blocks=[{
            "type": "tool_use", "name": "emit_strategy",
            "input": {"code": code, "assumptions": [], "explanation": "revised"},
        }],
        input_tokens=4000, output_tokens=2000,
    )


# ---- refine_strategy (service) ----


async def test_refine_audits_kind_refinement(session_factory, monkeypatch):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk-test")
        await s.commit()

    async def _fake(**kwargs):  # noqa: ANN003
        return _fake_call("class Refined:\n    pass\n")

    monkeypatch.setattr(service, "create_message", _fake)
    async with session_factory() as s:
        result = await refine_strategy(
            s, user_id=1, prior_code="class Old:\n    pass\n", request="tighten the stop"
        )
    assert "Refined" in result.code
    async with session_factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_GENERATED")
        )).scalars().all()
    payload = json.loads(rows[0].payload_json)
    assert payload["kind"] == "refinement"
    assert payload["request"] == "tighten the stop"


# ---- _backtest_with_autofix (endpoint helper) ----


def _patch_bt(monkeypatch, outcomes):
    seq = list(outcomes)
    calls = {"n": 0}

    async def _fake_bt(*, code, bar_cache, indicator_computer):  # noqa: ANN001, ANN003
        i = min(calls["n"], len(seq) - 1)
        calls["n"] += 1
        return seq[i]

    monkeypatch.setattr(ep, "backtest_generated_code", _fake_bt)
    return calls


async def test_autofix_on_runtime_error(monkeypatch):
    _patch_bt(monkeypatch, [
        BacktestOutcome("runtime_error", None, 0, "boom"),
        BacktestOutcome("ok", {"sharpe_ratio": 1.0}, 3, None),
    ])
    debug_calls = {"n": 0}

    async def _fake_debug(session, *, user_id, prior_code, error):  # noqa: ANN001
        debug_calls["n"] += 1
        return _result("class Fixed:\n    pass\n")

    monkeypatch.setattr(ep, "debug_strategy", _fake_debug)
    result, outcome, auto_fixed = await ep._backtest_with_autofix(
        None, user_id=1, result=_result(), bar_cache=object(), indicator_computer=object()
    )
    assert auto_fixed is True
    assert debug_calls["n"] == 1
    assert outcome.status == "ok"
    assert "Fixed" in result.code


async def test_no_autofix_on_clean(monkeypatch):
    _patch_bt(monkeypatch, [BacktestOutcome("ok", {}, 5, None)])
    debug = AsyncMock()
    monkeypatch.setattr(ep, "debug_strategy", debug)
    result, outcome, auto_fixed = await ep._backtest_with_autofix(
        None, user_id=1, result=_result("X"), bar_cache=object(), indicator_computer=object()
    )
    assert auto_fixed is False
    debug.assert_not_called()


async def test_no_autofix_on_no_trades(monkeypatch):
    _patch_bt(monkeypatch, [BacktestOutcome("no_trades", {}, 0, None)])
    debug = AsyncMock()
    monkeypatch.setattr(ep, "debug_strategy", debug)
    _r, outcome, auto_fixed = await ep._backtest_with_autofix(
        None, user_id=1, result=_result(), bar_cache=object(), indicator_computer=object()
    )
    assert auto_fixed is False  # no_trades is a legitimate result
    debug.assert_not_called()


async def test_debug_budget_failure_keeps_original(monkeypatch):
    _patch_bt(monkeypatch, [BacktestOutcome("runtime_error", None, 0, "boom")])

    async def _fake_debug(session, *, user_id, prior_code, error):  # noqa: ANN001
        raise BudgetExceededError("over budget")

    monkeypatch.setattr(ep, "debug_strategy", _fake_debug)
    result, outcome, auto_fixed = await ep._backtest_with_autofix(
        None, user_id=1, result=_result("orig"), bar_cache=object(), indicator_computer=object()
    )
    assert auto_fixed is False
    assert outcome.status == "runtime_error"
    assert result.code == "orig"
