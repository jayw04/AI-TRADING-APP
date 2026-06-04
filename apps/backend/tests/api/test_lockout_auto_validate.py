"""P6b §3b — lockout blocks the auto-validate spawn, NOT the ACCEPT itself."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.trading_profile import TradingProfile
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
NOW = datetime.now(UTC)


async def _seed(*, last_promoted_days_ago):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(TradingProfile(
            user_id=1, watchlist_json={}, bias_criteria_json={}, bias_thresholds_json={},
            session_preferences_json={}, risk_preferences_json={},
            agent_envelope_json={"auto_validate_proposals": True},
            created_at=NOW, updated_at=NOW,
        ))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            last_promoted_at=NOW - timedelta(days=last_promoted_days_ago),
            created_at=NOW, updated_at=NOW,
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


async def test_accept_succeeds_in_lockout_but_auto_spawn_skipped(client):
    await _seed(last_promoted_days_ago=5)  # in 30-day lockout
    r = await client.patch(f"{BASE}/proposals/1", json={"target_state": "ACCEPTED"})
    assert r.status_code == 200            # ACCEPT is NOT blocked by lockout
    assert r.json()["state"] == "ACCEPTED"  # stayed ACCEPTED (no auto-spawn → EVALUATING)
    assert await _variants() == []          # auto-validate silently skipped


async def test_auto_spawn_fires_when_not_in_lockout(client):
    await _seed(last_promoted_days_ago=31)  # lockout expired
    r = await client.patch(f"{BASE}/proposals/1", json={"target_state": "ACCEPTED"})
    assert r.status_code == 200
    variants = await _variants()
    assert len(variants) == 1               # auto-validate spawned the variant
