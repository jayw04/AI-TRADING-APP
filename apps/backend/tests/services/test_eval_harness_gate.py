"""P6b §4 — the Mode-B LLM decision gate + wrapped submit_order_fn.

Covers: structured signal payload, the per-harness 24h budget sum,
query_llm_decision parsing (mocked Anthropic call), and the make_harness_submit_fn
wrapper (A always submits; B is LLM-gated + budget-capped; one paired decision
row per intent).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.db.enums import OrderSide, OrderSourceType, OrderType, StrategyStatus
from app.db.models.eval_harness import (
    HARNESS_ACTIVE,
    HARNESS_PAUSED_BUDGET,
    EvalHarness,
    EvalHarnessDecision,
)
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.risk import OrderRequest
from app.services.eval_harness import gate

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
MODE_A_ID, MODE_B_ID, HARNESS_ID = 10, 11, 1


def _req(source_id: str = str(MODE_A_ID)) -> OrderRequest:
    return OrderRequest(
        user_id=1, account_id=1, symbol_ticker="AAPL", side=OrderSide.BUY,
        qty=Decimal("10"), type=OrderType.MARKET,
        source_type=OrderSourceType.STRATEGY, source_id=source_id,
    )


async def _seed_harness(session_factory, *, state: str = HARNESS_ACTIVE) -> None:
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        for sid, role, status in (
            (MODE_A_ID, "mode_a", StrategyStatus.PAPER_VARIANT),
            (MODE_B_ID, "mode_b", StrategyStatus.IDLE),
        ):
            s.add(Strategy(
                id=sid, user_id=1, name=f"S {role}", code_path="s.py",
                params_json={}, symbols_json=["AAPL"], status=status,
                harness_role=role, parent_strategy_id=1,
                created_at=NOW, updated_at=NOW,
            ))
        s.add(EvalHarness(
            id=HARNESS_ID, user_id=1, parent_strategy_id=1,
            mode_a_strategy_id=MODE_A_ID, mode_b_strategy_id=MODE_B_ID,
            state=state, started_at=NOW,
        ))
        await s.commit()


class _Order:
    def __init__(self, oid: int) -> None:
        self.id = oid


class _Recorder:
    """Stand-in OrderRouter.submit — records every OrderRequest it receives."""

    def __init__(self) -> None:
        self.requests: list[OrderRequest] = []

    async def __call__(self, req: OrderRequest) -> _Order:
        self.requests.append(req)
        return _Order(len(self.requests))


class _FakeCredStore:
    def __init__(self, session) -> None:  # noqa: ANN001
        pass

    async def get(self, user_id, kind):  # noqa: ANN001, ANN201
        return "fake-anthropic-key"


# ----------------------------- unit helpers --------------------------------


def test_signal_payload_is_structured_only():
    payload = gate.signal_payload_from_order(_req())
    assert payload == {
        "symbol": "AAPL", "side": "buy", "qty": "10", "type": "market",
        "limit_price": None, "stop_price": None, "tif": "day",
    }


async def test_spend_today_sums_only_recent_rows(session_factory):
    await _seed_harness(session_factory)
    async with session_factory() as s:
        s.add(EvalHarnessDecision(
            harness_id=HARNESS_ID, signal_uuid="u1", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="act",
            llm_cost_cents=Decimal("3.5"), recorded_at=NOW,
        ))
        s.add(EvalHarnessDecision(  # 48h old → excluded
            harness_id=HARNESS_ID, signal_uuid="u2", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="skip",
            llm_cost_cents=Decimal("9.0"), recorded_at=NOW - timedelta(hours=48),
        ))
        await s.commit()
    async with session_factory() as s:
        spend = await gate._harness_spend_today_cents(s, HARNESS_ID, NOW)
    assert spend == Decimal("3.5")


async def test_query_llm_decision_parses_act(monkeypatch):
    class _Call:
        content_blocks = [{"type": "text",
                           "text": '{"action": "act", "rationale": "looks fine"}'}]
        input_tokens = 100
        output_tokens = 20

    async def _fake_create_message(**kwargs):  # noqa: ANN003
        return _Call()

    monkeypatch.setattr(gate, "create_message", _fake_create_message)
    action, rationale, cost = await gate.query_llm_decision("k", {"symbol": "AAPL"})
    assert action == "act"
    assert rationale == "looks fine"
    assert cost > 0


async def test_query_llm_decision_defaults_skip_on_garbage(monkeypatch):
    class _Call:
        content_blocks = [{"type": "text", "text": "not json at all"}]
        input_tokens = 5
        output_tokens = 5

    async def _fake_create_message(**kwargs):  # noqa: ANN003
        return _Call()

    monkeypatch.setattr(gate, "create_message", _fake_create_message)
    action, rationale, _ = await gate.query_llm_decision("k", {})
    assert action == "skip"
    assert "defaulted_skip" in rationale


# ----------------------------- the wrapper ---------------------------------


async def _run_submit(session_factory, monkeypatch, *, action: str):
    monkeypatch.setattr(gate, "CredentialStore", _FakeCredStore)

    async def _fake_query(api_key, payload):  # noqa: ANN001, ANN202
        return action, f"rationale-{action}", Decimal("2.5")

    monkeypatch.setattr(gate, "query_llm_decision", _fake_query)
    recorder = _Recorder()
    submit = gate.make_harness_submit_fn(
        harness_id=HARNESS_ID, mode_a_id=MODE_A_ID, mode_b_id=MODE_B_ID,
        user_id=1, real_submit=recorder, session_factory=session_factory,
    )
    await submit(_req())
    return recorder


async def test_wrapper_act_submits_both_and_records(session_factory, monkeypatch):
    await _seed_harness(session_factory)
    recorder = await _run_submit(session_factory, monkeypatch, action="act")
    # A then B.
    assert len(recorder.requests) == 2
    assert recorder.requests[0].source_id == str(MODE_A_ID)
    assert recorder.requests[1].source_id == str(MODE_B_ID)
    # B inherits A's account (paper-only guarantee).
    assert recorder.requests[1].account_id == recorder.requests[0].account_id
    async with session_factory() as s:
        rows = (await s.execute(select(EvalHarnessDecision))).scalars().all()
    assert len(rows) == 1
    assert rows[0].mode_a_decision == "act"
    assert rows[0].mode_b_decision == "act"
    assert rows[0].mode_b_order_id is not None
    assert rows[0].llm_cost_cents == Decimal("2.5")


async def test_wrapper_skip_submits_only_a(session_factory, monkeypatch):
    await _seed_harness(session_factory)
    recorder = await _run_submit(session_factory, monkeypatch, action="skip")
    assert len(recorder.requests) == 1  # A only
    async with session_factory() as s:
        rows = (await s.execute(select(EvalHarnessDecision))).scalars().all()
    assert len(rows) == 1
    assert rows[0].mode_b_decision == "skip"
    assert rows[0].mode_b_order_id is None


async def test_wrapper_budget_pauses_harness(session_factory, monkeypatch):
    await _seed_harness(session_factory)
    async with session_factory() as s:  # already over the $5/day cap
        s.add(EvalHarnessDecision(
            harness_id=HARNESS_ID, signal_uuid="u", signal_payload_json={},
            mode_a_decision="act", mode_b_decision="act",
            llm_cost_cents=Decimal("600"), recorded_at=datetime.now(UTC),
        ))
        await s.commit()
    recorder = await _run_submit(session_factory, monkeypatch, action="act")
    assert len(recorder.requests) == 1  # A submitted, B skipped (budget)
    async with session_factory() as s:
        h = await s.get(EvalHarness, HARNESS_ID)
        rows = (await s.execute(
            select(EvalHarnessDecision).where(EvalHarnessDecision.signal_uuid != "u")
        )).scalars().all()
    assert h.state == HARNESS_PAUSED_BUDGET
    assert rows == []  # no new decision row when paused


async def test_wrapper_no_key_submits_only_a(session_factory, monkeypatch):
    await _seed_harness(session_factory)

    class _NoKeyStore:
        def __init__(self, session) -> None:  # noqa: ANN001
            pass

        async def get(self, user_id, kind):  # noqa: ANN001, ANN201
            return None

    monkeypatch.setattr(gate, "CredentialStore", _NoKeyStore)
    recorder = _Recorder()
    submit = gate.make_harness_submit_fn(
        harness_id=HARNESS_ID, mode_a_id=MODE_A_ID, mode_b_id=MODE_B_ID,
        user_id=1, real_submit=recorder, session_factory=session_factory,
    )
    await submit(_req())
    assert len(recorder.requests) == 1
    async with session_factory() as s:
        assert (await s.execute(select(EvalHarnessDecision))).scalars().all() == []


async def test_wrapper_terminated_harness_only_submits_a(session_factory, monkeypatch):
    await _seed_harness(session_factory, state="terminated")
    recorder = await _run_submit(session_factory, monkeypatch, action="act")
    assert len(recorder.requests) == 1  # A only; harness not ACTIVE → no B eval
