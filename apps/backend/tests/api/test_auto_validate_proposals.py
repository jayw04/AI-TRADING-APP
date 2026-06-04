"""P6b §2b-variant D5 — auto-spawn paper variant on ACCEPT via envelope flag.

PATCH /proposals/{id} REVIEWING → ACCEPTED triggers the best-effort auto-spawn
when ``agent_envelope_json.auto_validate_proposals`` is set and the parent is
LIVE. The hook must never fail the ACCEPT (spawn self-guards with ValueError).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
NOW = datetime.now(UTC)


async def _seed(*, parent_status=StrategyStatus.LIVE, flag=True):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(TradingProfile(
            user_id=1, watchlist_json={}, bias_criteria_json={}, bias_thresholds_json={},
            session_preferences_json={}, risk_preferences_json={},
            agent_envelope_json={"auto_validate_proposals": flag},
            created_at=NOW, updated_at=NOW,
        ))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=parent_status, created_at=NOW, updated_at=NOW,
        ))
        s.add(StrategyProposal(
            id=1, strategy_id=1, user_id=1, state=ProposalState.REVIEWING,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={}, evaluation_results_json={},
            generated_at=NOW, transitioned_at=NOW, created_at=NOW, updated_at=NOW,
        ))
        await s.commit()


async def _variants():
    async with get_sessionmaker()() as s:
        return (await s.execute(
            select(Strategy).where(Strategy.status == StrategyStatus.PAPER_VARIANT)
        )).scalars().all()


async def _accept(client):
    return await client.patch(f"{BASE}/proposals/1", json={"target_state": "ACCEPTED"})


@pytest.mark.usefixtures("client")
async def test_auto_spawn_fires_when_flag_enabled_and_parent_live(client):
    await _seed(parent_status=StrategyStatus.LIVE, flag=True)
    r = await _accept(client)
    assert r.status_code == 200
    variants = await _variants()
    assert len(variants) == 1
    assert variants[0].parent_strategy_id == 1
    assert variants[0].params_json["rsi"] == 40


async def test_auto_spawn_skipped_when_flag_disabled(client):
    await _seed(parent_status=StrategyStatus.LIVE, flag=False)
    r = await _accept(client)
    assert r.status_code == 200
    assert await _variants() == []


async def test_auto_spawn_skipped_when_parent_idle(client):
    # spawn raises parent_not_live → swallowed; ACCEPT still succeeds.
    await _seed(parent_status=StrategyStatus.IDLE, flag=True)
    r = await _accept(client)
    assert r.status_code == 200
    assert await _variants() == []


async def test_auto_spawn_skipped_when_variant_already_in_flight(client):
    await _seed(parent_status=StrategyStatus.LIVE, flag=True)
    async with get_sessionmaker()() as s:
        s.add(Strategy(
            id=2, user_id=1, name="existing variant", code_path="s.py", params_json={},
            symbols_json=["AAPL"], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
            created_at=NOW - timedelta(minutes=1), updated_at=NOW,
        ))
        await s.commit()
    r = await _accept(client)
    assert r.status_code == 200
    # still exactly the one pre-existing variant (spawn guard swallowed).
    assert len(await _variants()) == 1
