"""P6 §2b-backtest — GET /api/v1/strategies/{id}/proposal-eval-summary."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(id=1, user_id=1, name="S1", params_json={}, symbols_json=[], created_at=now, updated_at=now))
        s.add(Strategy(id=2, user_id=2, name="Other", params_json={}, symbols_json=[], created_at=now, updated_at=now))
        await s.commit()
    return client


# Distinct minute per proposal — §1a's composite-unique-per-minute index blocks
# same-(strategy, minute) duplicates.
_seq = 0


async def _mk(eval_state: dict, *, strategy_id=1, user_id=1):
    global _seq
    _seq += 1
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(minutes=_seq)
        s.add(
            StrategyProposal(
                strategy_id=strategy_id, user_id=user_id, state=ProposalState.REVIEWING,
                proposal_payload_json={}, evidence_bundle_json={},
                evaluation_results_json=eval_state,
                generated_at=ts, transitioned_at=ts, created_at=ts, updated_at=ts,
            )
        )
        await s.commit()


async def test_summary_zero_proposals(client):
    r = await client.get(f"{BASE}/strategies/1/proposal-eval-summary")
    assert r.status_code == 200
    b = r.json()
    assert b["n_proposals"] == 0
    assert b["recent_metrics_summary"] is None


async def test_summary_counts_by_status_and_verdict(client):
    await _mk({"status": "complete", "verdict": "above_baseline", "delta_metrics": {"sharpe_ratio_delta": 0.2}})
    await _mk({"status": "complete", "verdict": "below_baseline"})
    await _mk({"status": "pending"})
    await _mk({"status": "skipped", "skipped_reason": "non_python_strategy"})
    await _mk({"status": "failed", "failure_reason": "x"})
    r = await client.get(f"{BASE}/strategies/1/proposal-eval-summary")
    b = r.json()
    assert b["n_proposals"] == 5
    assert b["n_eval_complete"] == 2
    assert b["n_eval_pending"] == 1
    assert b["n_eval_skipped"] == 1
    assert b["n_eval_failed"] == 1
    assert b["n_above_baseline"] == 1
    assert b["n_below_baseline"] == 1
    assert b["recent_metrics_summary"] is not None


async def test_summary_other_user_strategy_404(client):
    r = await client.get(f"{BASE}/strategies/2/proposal-eval-summary")
    assert r.status_code == 404
