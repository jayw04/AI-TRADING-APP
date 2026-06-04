"""P6b §2a-variant — validate / stop-validation endpoints + variant exclusion."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        now = _now()
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="strat.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE, created_at=now, updated_at=now,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=now, transitioned_at=now, created_at=now, updated_at=now,
        ))
        await s.commit()
    return client


async def _set_parent_status(status):
    async with get_sessionmaker()() as s:
        strat = await s.get(Strategy, 1)
        strat.status = status
        await s.commit()


async def test_validate_spawns_and_returns_evaluating(client):
    r = await client.post(f"{BASE}/proposals/1/validate")
    assert r.status_code == 200
    assert r.json()["state"] == "EVALUATING"


async def test_validate_non_live_400(client):
    await _set_parent_status(StrategyStatus.PAPER)
    r = await client.post(f"{BASE}/proposals/1/validate")
    assert r.status_code == 400
    assert r.json()["detail"] == "parent_not_live"


async def test_validate_second_409(client):
    await client.post(f"{BASE}/proposals/1/validate")
    async with get_sessionmaker()() as s:
        ts = _now() + timedelta(minutes=1)
        s.add(StrategyProposal(
            id=2, strategy_id=1, user_id=1, state=ProposalState.ACCEPTED,
            proposal_payload_json={"changes": []}, evidence_bundle_json={},
            evaluation_results_json={}, generated_at=ts, transitioned_at=ts,
            created_at=ts, updated_at=ts,
        ))
        await s.commit()
    r = await client.post(f"{BASE}/proposals/2/validate")
    assert r.status_code == 409


async def test_validate_other_user_404(client):
    async with get_sessionmaker()() as s:
        now = _now()
        s.add(Strategy(id=9, user_id=2, name="X", code_path="s.py", params_json={},
                       symbols_json=[], status=StrategyStatus.LIVE, created_at=now, updated_at=now))
        s.add(StrategyProposal(id=9, strategy_id=9, user_id=2, state=ProposalState.ACCEPTED,
              proposal_payload_json={"changes": []}, evidence_bundle_json={},
              evaluation_results_json={}, generated_at=now, transitioned_at=now,
              created_at=now, updated_at=now))
        await s.commit()
    r = await client.post(f"{BASE}/proposals/9/validate")
    assert r.status_code == 404


async def test_stop_validation_terminates(client):
    await client.post(f"{BASE}/proposals/1/validate")
    r = await client.post(f"{BASE}/proposals/1/stop-validation")
    assert r.status_code == 200
    assert r.json()["state"] == "REJECTED"


async def test_stop_validation_not_evaluating_400(client):
    r = await client.post(f"{BASE}/proposals/1/stop-validation")  # still ACCEPTED
    assert r.status_code == 400


async def test_variant_excluded_from_strategies_list(client):
    await client.post(f"{BASE}/proposals/1/validate")  # spawns a PAPER_VARIANT clone
    r = await client.get(f"{BASE}/strategies")
    statuses = [it["status"] for it in r.json()["items"]]
    assert "paper_variant" not in statuses
    assert all(it["id"] == 1 for it in r.json()["items"])  # only the parent
