"""P6b §5 — the live LLM gate: active-opt-in lookup, per-user budget sum, and the
wrapped submit (act/skip/budget/no-key fail-safe)."""
from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderStatus, OrderType, StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.llm_opt_in import OPT_IN_ACTIVE, LLMOptIn
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.risk import OrderRequest
from app.services.llm_live_gate import gate

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
SID, UID = 7, 1


def _req() -> OrderRequest:
    return OrderRequest(
        user_id=UID, account_id=2, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("10"), type=OrderType.MARKET,
        source_type=OrderSourceType.STRATEGY, source_id=str(SID),
    )


async def _seed(session_factory, *, version="0.1.0", opt_in_version="0.1.0", cap=500) -> None:
    async with session_factory() as s:
        s.add(User(id=UID, email="jay@test"))
        s.add(Strategy(
            id=SID, user_id=UID, name="S1", version=version, code_path="s.py",
            params_json={}, symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            created_at=NOW, updated_at=NOW,
        ))
        s.add(LLMOptIn(
            id=1, user_id=UID, strategy_id=SID, strategy_version=opt_in_version,
            state=OPT_IN_ACTIVE, acknowledgment_text="ack", daily_cap_cents=cap,
            initiated_at=NOW - timedelta(days=8), activated_at=NOW - timedelta(days=1),
            created_at=NOW, updated_at=NOW,
        ))
        await s.commit()


class _FakeCredStore:
    def __init__(self, session) -> None:  # noqa: ANN001
        pass

    async def get(self, user_id, kind):  # noqa: ANN001, ANN201
        return "fake-key"


async def test_find_active_opt_in_version_match(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        assert (await gate.find_active_opt_in(s, SID)) is not None


async def test_find_active_opt_in_version_stale_returns_none(session_factory):
    await _seed(session_factory, version="0.2.0", opt_in_version="0.1.0")
    async with session_factory() as s:
        assert (await gate.find_active_opt_in(s, SID)) is None  # version drifted


async def test_user_spend_sums_live_decisions(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        for cost, ts in ((Decimal("2.5"), NOW), (Decimal("9"), NOW - timedelta(hours=48))):
            s.add(AuditLog(
                user_id=UID, ts=ts, actor_type="system", actor_id="llm_live_gate",
                action="LLM_LIVE_DECISION", target_type="strategy", target_id=str(SID),
                payload_json=json.dumps({"cost_cents": float(cost)}),
            ))
        await s.commit()
    async with session_factory() as s:
        spend = await gate._user_live_spend_today_cents(s, UID, NOW)
    assert spend == Decimal("2.5")  # the 48h-old row is excluded


async def test_query_parses_act_and_captures_prompt_response(monkeypatch):
    class _Call:
        content_blocks = [{"type": "text", "text": '{"action": "act", "rationale": "ok"}'}]
        input_tokens = 100
        output_tokens = 20

    async def _fake(**kw):  # noqa: ANN003
        return _Call()

    monkeypatch.setattr(gate, "create_message", _fake)
    action, rationale, prompt, response, cost = await gate.query_live_llm_decision(
        "k", {"symbol": "AAPL"}
    )
    assert action == "act"
    assert rationale == "ok"
    assert "AAPL" in prompt          # full prompt captured for the audit
    assert "act" in response          # raw response captured
    assert cost > 0


async def _run(session_factory, monkeypatch, *, action):
    monkeypatch.setattr(gate, "CredentialStore", _FakeCredStore)

    async def _fake_query(api_key, payload):  # noqa: ANN001, ANN202
        return action, f"r-{action}", "PROMPT", "RESPONSE", Decimal("2.5")

    monkeypatch.setattr(gate, "query_live_llm_decision", _fake_query)
    real_submit = AsyncMock(return_value=type("O", (), {"id": 55})())
    submit = gate.make_live_llm_submit_fn(
        strategy_id=SID, user_id=UID, real_submit=real_submit,
        session_factory=session_factory,
    )
    return submit, real_submit


async def test_wrapper_act_submits_and_audits(session_factory, monkeypatch):
    await _seed(session_factory)
    submit, real_submit = await _run(session_factory, monkeypatch, action="act")
    result = await submit(_req())
    real_submit.assert_awaited_once()
    assert result.id == 55
    async with session_factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.action == "LLM_LIVE_DECISION")
        )).scalars().all()
    assert len(rows) == 1
    payload = json.loads(rows[0].payload_json)
    assert payload["llm_decision"] == "act"
    assert payload["baseline_decision"] == "act"
    assert payload["prompt"] == "PROMPT" and payload["response"] == "RESPONSE"


async def test_wrapper_skip_suppresses(session_factory, monkeypatch):
    await _seed(session_factory)
    submit, real_submit = await _run(session_factory, monkeypatch, action="skip")
    result = await submit(_req())
    real_submit.assert_not_called()  # the LLM declined to fire
    assert result.status == OrderStatus.REJECTED
    assert result.rejection_reason == "LLM_SKIPPED"
    async with session_factory() as s:
        rows = (await s.execute(
            select(AuditLog).where(AuditLog.action == "LLM_LIVE_DECISION")
        )).scalars().all()
    assert json.loads(rows[0].payload_json)["llm_decision"] == "skip"


async def test_wrapper_over_budget_fails_safe_deterministic(session_factory, monkeypatch):
    await _seed(session_factory, cap=100)
    async with session_factory() as s:  # already over the cap
        s.add(AuditLog(
            user_id=UID, ts=datetime.now(UTC), actor_type="system",
            actor_id="llm_live_gate", action="LLM_LIVE_DECISION",
            target_type="strategy", target_id=str(SID),
            payload_json=json.dumps({"cost_cents": 200.0}),
        ))
        await s.commit()
    submit, real_submit = await _run(session_factory, monkeypatch, action="skip")
    result = await submit(_req())
    real_submit.assert_awaited_once()  # deterministic fired despite "skip"
    assert result.id == 55


async def test_wrapper_no_opt_in_passes_through(session_factory, monkeypatch):
    # version stale → find_active_opt_in returns None → deterministic.
    await _seed(session_factory, version="0.2.0", opt_in_version="0.1.0")
    submit, real_submit = await _run(session_factory, monkeypatch, action="skip")
    result = await submit(_req())
    real_submit.assert_awaited_once()
    assert result.id == 55
