"""P6 §2b-review — GET /api/v1/proposals?awaiting_review=true."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"

_seq = 0


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        await s.commit()
    return client


async def _mk(eval_state: dict, *, strategy_id: int = 1) -> int:
    global _seq
    _seq += 1
    async with get_sessionmaker()() as s:
        ts = datetime.now(UTC) - timedelta(minutes=_seq)
        prop = StrategyProposal(
            strategy_id=strategy_id, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json=eval_state,
            generated_at=ts, transitioned_at=ts, created_at=ts, updated_at=ts,
        )
        s.add(prop)
        await s.commit()
        return prop.id


def _hr(**over) -> dict:
    hr = {"sampled_at": "2026-06-02T00:00:00+00:00", "rating": None}
    hr.update(over)
    return {"status": "complete", "human_review": hr}


async def _await_ids(client, extra: str = "") -> set[int]:
    r = await client.get(f"{BASE}/proposals?awaiting_review=true{extra}")
    assert r.status_code == 200
    return {p["id"] for p in r.json()["items"]}


async def test_list_awaiting_review_returns_sampled_unrated(client):
    pid = await _mk(_hr())
    assert pid in await _await_ids(client)


async def test_list_awaiting_review_excludes_already_reviewed(client):
    rated = await _mk(_hr(rating="thumbs_up", reviewed_at="2026-06-02T01:00:00+00:00"))
    assert rated not in await _await_ids(client)


async def test_list_awaiting_review_excludes_unsampled(client):
    unsampled = await _mk({"status": "complete"})  # no human_review
    assert unsampled not in await _await_ids(client)


async def test_list_awaiting_review_combines_with_strategy_filter(client):
    s1 = await _mk(_hr(), strategy_id=1)
    s2 = await _mk(_hr(), strategy_id=2)
    ids = await _await_ids(client, extra="&strategy_id=1")
    assert s1 in ids
    assert s2 not in ids
