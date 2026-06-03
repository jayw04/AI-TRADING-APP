"""P6 §2b-review — eval-summary endpoint gains n_reviewed/n_thumbs_up/down."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"

_seq = 0


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(id=1, user_id=1, name="S1", params_json={}, symbols_json=[],
                       created_at=now, updated_at=now))
        await s.commit()
    return client


async def _mk(eval_state: dict) -> int:
    global _seq
    _seq += 1
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(minutes=_seq)
        prop = StrategyProposal(
            strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json=eval_state,
            generated_at=ts, transitioned_at=ts, created_at=ts, updated_at=ts,
        )
        s.add(prop)
        await s.commit()
        return prop.id


async def test_summary_counts_reviewed_thumbs_up_thumbs_down(client):
    await _mk({"status": "complete", "human_review": {"rating": "thumbs_up"}})
    await _mk({"status": "complete", "human_review": {"rating": "thumbs_up"}})
    await _mk({"status": "complete", "human_review": {"rating": "thumbs_down"}})
    await _mk({"status": "complete", "human_review": {"rating": None}})  # sampled, unrated
    r = await client.get(f"{BASE}/strategies/1/proposal-eval-summary")
    b = r.json()
    assert b["n_reviewed"] == 3
    assert b["n_thumbs_up"] == 2
    assert b["n_thumbs_down"] == 1


async def test_summary_unaffected_when_no_reviews(client):
    await _mk({"status": "complete", "verdict": "above_baseline"})
    r = await client.get(f"{BASE}/strategies/1/proposal-eval-summary")
    b = r.json()
    assert b["n_reviewed"] == 0
    assert b["n_thumbs_up"] == 0
    assert b["n_thumbs_down"] == 0
    assert b["n_eval_complete"] == 1  # existing behavior intact
