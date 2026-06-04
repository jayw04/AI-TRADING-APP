"""P6b §2c-variant — GET /api/v1/variants (user-scoped in-flight variant list)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)


def _strategy(**kw):
    base = dict(
        user_id=1, name="S", code_path="s.py", params_json={}, symbols_json=["AAPL"],
        created_at=NOW, updated_at=NOW,
    )
    base.update(kw)
    return Strategy(**base)


@pytest.fixture(autouse=True)
async def _users(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        await s.commit()
    return client


async def test_returns_empty_when_none(client):
    r = await client.get(f"{BASE}/variants")
    assert r.status_code == 200
    assert r.json() == {"items": []}


async def test_returns_user_in_flight_variants_with_parent_info(client):
    async with get_sessionmaker()() as s:
        s.add(_strategy(id=1, status=StrategyStatus.LIVE, name="Momentum"))
        s.add(_strategy(id=2, status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1))
        s.add(StrategyProposal(
            id=5, strategy_id=1, user_id=1, state=ProposalState.EVALUATING,
            proposal_payload_json={}, evidence_bundle_json={},
            evaluation_results_json={"paper_variant": {"variant_strategy_id": 2}},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()
    r = await client.get(f"{BASE}/variants")
    items = r.json()["items"]
    assert len(items) == 1
    it = items[0]
    assert it["variant_strategy_id"] == 2
    assert it["parent_strategy_id"] == 1
    assert it["parent_strategy_name"] == "Momentum"
    assert it["parent_strategy_status"] == "live"
    assert it["spawn_proposal_id"] == 5
    assert it["spawned_at"] is not None


async def test_excludes_terminated_variants(client):
    # A terminated variant is IDLE, not PAPER_VARIANT → not listed.
    async with get_sessionmaker()() as s:
        s.add(_strategy(id=1, status=StrategyStatus.LIVE))
        s.add(_strategy(id=2, status=StrategyStatus.IDLE, parent_strategy_id=1))
        await s.commit()
    r = await client.get(f"{BASE}/variants")
    assert r.json()["items"] == []


async def test_other_users_variants_not_returned(client):
    async with get_sessionmaker()() as s:
        s.add(_strategy(id=1, user_id=2, status=StrategyStatus.LIVE))
        s.add(_strategy(id=2, user_id=2, status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1))
        await s.commit()
    r = await client.get(f"{BASE}/variants")
    assert r.json()["items"] == []
