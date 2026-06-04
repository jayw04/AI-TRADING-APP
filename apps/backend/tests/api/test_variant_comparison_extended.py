"""P6b §2c-variant — GET /variant-comparison additive extensions.

The response now carries `spawn_proposal_id` + `live_equity_curve` +
`variant_equity_curve` for the strategy-detail UI. The change is additive — the
existing metrics/deltas shape is unchanged (the §2b MCP tool keeps working).
"""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.strategy_proposal import ProposalState, StrategyProposal
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
START = datetime.now(UTC) - timedelta(days=3)


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE, created_at=START, updated_at=START,
        ))
        s.add(Strategy(
            id=2, user_id=1, name="S1 (variant)", code_path="s.py", params_json={"rsi": 40},
            symbols_json=["AAPL"], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
            created_at=START, updated_at=START,
        ))
        # The EVALUATING proposal that spawned the variant (the spawn_proposal_id source).
        s.add(StrategyProposal(
            id=7, strategy_id=1, user_id=1, state=ProposalState.EVALUATING,
            proposal_payload_json={"changes": [{"param": "rsi", "to": 40}]},
            evidence_bundle_json={},
            evaluation_results_json={"paper_variant": {"variant_strategy_id": 2}},
            generated_at=START, transitioned_at=START, created_at=START, updated_at=START,
        ))
        await s.commit()
    return client


async def test_response_includes_spawn_proposal_id(client):
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    assert r.status_code == 200
    comp = r.json()["comparison"]
    assert comp["spawn_proposal_id"] == 7


async def test_response_includes_equity_curves(client):
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    comp = r.json()["comparison"]
    assert "live_equity_curve" in comp
    assert "variant_equity_curve" in comp
    assert isinstance(comp["live_equity_curve"], list)
    assert isinstance(comp["variant_equity_curve"], list)
    # Each point (if any) is {ts, equity}. Without bar_cache + open positions the
    # curve may be empty/flat, but the shape must hold.
    for pt in comp["live_equity_curve"]:
        assert set(pt) == {"ts", "equity"}


async def test_existing_response_fields_unchanged(client):
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    comp = r.json()["comparison"]
    # The §2b metrics/deltas shape is untouched (additive change).
    for side in ("live_metrics", "variant_metrics"):
        assert set(comp[side]) == {
            "trade_count", "win_rate", "avg_return_per_trade",
            "sharpe_ratio", "max_drawdown",
        }
    assert set(comp["deltas"]) == {
        "sharpe_delta_pct", "max_drawdown_delta_pct",
        "win_rate_delta_pp", "avg_return_delta_pct",
    }


async def test_spawn_proposal_id_null_when_no_evaluating_proposal(client):
    # Drop the EVALUATING proposal → spawn_proposal_id resolves to null, but the
    # comparison still renders (the variant row is the source of truth).
    async with get_sessionmaker()() as s:
        prop = await s.get(StrategyProposal, 7)
        prop.state = ProposalState.REJECTED
        await s.commit()
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    assert r.status_code == 200
    assert r.json()["comparison"]["spawn_proposal_id"] is None
