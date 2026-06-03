"""P6 §2b-review — POST /api/v1/proposals/{id}/review."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"

_seq = 0


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        await s.commit()
    return client


async def _mk(eval_state: dict, *, user_id: int = 1, strategy_id: int = 1) -> int:
    global _seq
    _seq += 1
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(minutes=_seq)
        prop = StrategyProposal(
            strategy_id=strategy_id, user_id=user_id, state=ProposalState.ACCEPTED,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json=eval_state,
            generated_at=ts, transitioned_at=ts, created_at=ts, updated_at=ts,
        )
        s.add(prop)
        await s.commit()
        return prop.id


def _sampled(**over) -> dict:
    hr = {"sampled_at": "2026-06-02T00:00:00+00:00", "reviewed_at": None,
          "rating": None, "reason": None}
    hr.update(over)
    return {"status": "complete", "verdict": "above_baseline", "human_review": hr}


async def _audit_rows(action: str) -> list[AuditLog]:
    async with get_sessionmaker()() as s:
        return list(
            (await s.execute(select(AuditLog).where(AuditLog.action == action)))
            .scalars()
            .all()
        )


async def test_review_thumbs_up_records_audit_and_merges(client):
    pid = await _mk(_sampled())
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "thumbs_up"})
    assert r.status_code == 200
    ev = r.json()["evaluation_results"]
    assert ev["human_review"]["rating"] == "thumbs_up"
    assert ev["human_review"]["reviewed_at"] is not None
    rows = await _audit_rows("PROPOSAL_REVIEW_RECORDED")
    assert len(rows) == 1
    assert rows[0].actor_type == "user"


async def test_review_thumbs_down_with_reason_records_both(client):
    pid = await _mk(_sampled())
    r = await client.post(
        f"{BASE}/proposals/{pid}/review",
        json={"rating": "thumbs_down", "reason": "no actual change"},
    )
    assert r.status_code == 200
    hr = r.json()["evaluation_results"]["human_review"]
    assert hr["rating"] == "thumbs_down"
    assert hr["reason"] == "no actual change"


async def test_review_preserves_existing_eval_subtree(client):
    pid = await _mk(
        {
            "status": "complete",
            "baseline_metrics": {"sharpe_ratio": 1.0},
            "variant_metrics": {"sharpe_ratio": 1.3},
            "verdict": "above_baseline",
            "human_review": {"sampled_at": "2026-06-02T00:00:00+00:00", "rating": None},
        }
    )
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "thumbs_up"})
    assert r.status_code == 200
    ev = r.json()["evaluation_results"]
    assert ev["status"] == "complete"
    assert ev["verdict"] == "above_baseline"
    assert ev["baseline_metrics"] == {"sharpe_ratio": 1.0}
    assert ev["variant_metrics"] == {"sharpe_ratio": 1.3}
    assert ev["human_review"]["rating"] == "thumbs_up"


async def test_review_400_if_proposal_not_sampled(client):
    pid = await _mk({"status": "complete"})  # no human_review sub-key
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "thumbs_up"})
    assert r.status_code == 400
    assert "not been sampled" in r.json()["detail"]


async def test_review_400_if_already_reviewed(client):
    pid = await _mk(_sampled(rating="thumbs_up", reviewed_at="2026-06-02T01:00:00+00:00"))
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "thumbs_down"})
    assert r.status_code == 400
    assert "already reviewed" in r.json()["detail"]


async def test_review_other_user_404(client):
    pid = await _mk(_sampled(), user_id=2, strategy_id=2)
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "thumbs_up"})
    assert r.status_code == 404


async def test_review_invalid_rating_400(client):
    pid = await _mk(_sampled())
    r = await client.post(f"{BASE}/proposals/{pid}/review", json={"rating": "meh"})
    assert r.status_code == 400
