"""P6b §3a-gate — run_promotion_gate_for_user orchestration (morning-brief pass).

Monkeypatches compare_variant_to_parent so the focus is the orchestration
(merge-write, EVALUATING → EVIDENCE_READY transition, stickiness, skips,
resilience, one-audit-row-per-transition) — the gate math is covered separately.
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.services import promotion_gate as pg
from app.services.paper_variant import VariantComparison, VariantSideMetrics

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
START = NOW - timedelta(days=31)


def _comp(*, passing: bool) -> VariantComparison:
    side = VariantSideMetrics(
        trade_count=60, win_rate=0.6, avg_return_per_trade=0.01,
        sharpe_ratio=1.0, max_drawdown=-0.10,
    )
    variant = VariantSideMetrics(
        trade_count=60 if passing else 5, win_rate=0.7, avg_return_per_trade=0.02,
        sharpe_ratio=1.2, max_drawdown=-0.08,
    )
    curve = [
        (START + timedelta(days=i), Decimal(str(100000 + i * 50)))
        for i in range(3)
    ]
    return VariantComparison(
        parent_strategy_id=1, variant_strategy_id=2,
        window_start=START, window_end=NOW,
        live_metrics=side, variant_metrics=variant,
        deltas={}, live_trade_count=60,
        variant_trade_count=60 if passing else 5,
        live_equity_curve=curve, variant_equity_curve=curve,
        capital_base=Decimal("100000"),
    )


def _patch_compare(monkeypatch, comp_or_exc):
    async def fake(session, variant_id, bar_cache=None):
        if isinstance(comp_or_exc, Exception):
            raise comp_or_exc
        return comp_or_exc
    monkeypatch.setattr(pg, "compare_variant_to_parent", fake)


async def _seed(session_factory, *, state=ProposalState.EVALUATING, eval_json=None):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            created_at=START, updated_at=START,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=state,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json=eval_json if eval_json is not None else {
                "paper_variant": {"variant_strategy_id": 2},
                "status": "complete", "verdict": "above_baseline",
            },
            generated_at=START, transitioned_at=START, created_at=START, updated_at=START,
        ))
        await s.commit()


async def _proposal(session_factory):
    async with session_factory() as s:
        return await s.get(StrategyProposal, 1)


async def _transition_audits(session_factory):
    async with session_factory() as s:
        return (await s.execute(
            select(AuditLog)
            .where(AuditLog.action == "STRATEGY_PROPOSAL_TRANSITIONED")
        )).scalars().all()


# ---- non-negotiable: merge-not-overwrite ----


async def test_brief_preserves_existing_eval_subkeys_on_bundle_write(
    session_factory, monkeypatch
):
    await _seed(session_factory)
    _patch_compare(monkeypatch, _comp(passing=True))
    async with session_factory() as s:
        await pg.run_promotion_gate_for_user(s, user_id=1)
    p = await _proposal(session_factory)
    ev = p.evaluation_results_json
    # The §2a / §2b sub-keys survive, and the §3a bundle is added.
    assert ev["paper_variant"]["variant_strategy_id"] == 2
    assert ev["status"] == "complete"
    assert ev["verdict"] == "above_baseline"
    assert "evidence_bundle" in ev
    assert ev["evidence_bundle"]["all_criteria_passed"] is True


# ---- transitions ----


async def test_evaluating_transitions_to_evidence_ready_when_gate_passes(
    session_factory, monkeypatch
):
    await _seed(session_factory)
    _patch_compare(monkeypatch, _comp(passing=True))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    assert result["transitions_fired"] == 1
    p = await _proposal(session_factory)
    assert p.state == ProposalState.EVIDENCE_READY
    audits = await _transition_audits(session_factory)
    assert len(audits) == 1


async def test_evaluating_stays_when_gate_fails(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_compare(monkeypatch, _comp(passing=False))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    assert result["transitions_fired"] == 0
    assert result["bundles_updated"] == 1
    p = await _proposal(session_factory)
    assert p.state == ProposalState.EVALUATING
    assert p.evaluation_results_json["evidence_bundle"]["all_criteria_passed"] is False
    assert await _transition_audits(session_factory) == []  # no audit for non-transition


async def test_evidence_ready_refreshes_bundle_but_no_transition(
    session_factory, monkeypatch
):
    # Sticky: an already-EVIDENCE_READY proposal updates its bundle, no audit.
    await _seed(session_factory, state=ProposalState.EVIDENCE_READY)
    _patch_compare(monkeypatch, _comp(passing=True))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    assert result["transitions_fired"] == 0
    assert result["bundles_updated"] == 1
    p = await _proposal(session_factory)
    assert p.state == ProposalState.EVIDENCE_READY
    assert "evidence_bundle" in p.evaluation_results_json
    assert await _transition_audits(session_factory) == []


# ---- skips + resilience ----


async def test_skips_proposal_without_paper_variant_subkey(session_factory, monkeypatch):
    await _seed(session_factory, eval_json={"status": "complete"})  # no paper_variant
    _patch_compare(monkeypatch, _comp(passing=True))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    assert result["skips"] == 1
    assert result["bundles_updated"] == 0
    p = await _proposal(session_factory)
    assert p.state == ProposalState.EVALUATING


async def test_continues_on_per_proposal_exception(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_compare(monkeypatch, RuntimeError("variant vanished mid-eval"))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    # The exception is isolated; the pass returns without raising.
    assert result["transitions_fired"] == 0
    p = await _proposal(session_factory)
    assert p.state == ProposalState.EVALUATING


async def test_skips_when_comparison_is_none(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_compare(monkeypatch, None)
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=1)
    assert result["skips"] == 1


@pytest.mark.usefixtures("session_factory")
async def test_other_users_proposals_not_evaluated(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch_compare(monkeypatch, _comp(passing=True))
    async with session_factory() as s:
        result = await pg.run_promotion_gate_for_user(s, user_id=999)
    assert result == {"transitions_fired": 0, "bundles_updated": 0, "skips": 0}
