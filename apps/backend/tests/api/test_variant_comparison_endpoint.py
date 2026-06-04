"""P6b §2b-variant — GET /strategies/{id}/variant-comparison endpoint."""
from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"
START = datetime.now(UTC) - timedelta(days=3)


@pytest.fixture(autouse=True)
async def _seed(client):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", code_path="s.py", params_json={"rsi": 30},
            symbols_json=["AAPL"], status=StrategyStatus.LIVE, created_at=START, updated_at=START,
        ))
        await s.commit()
    return client


async def _add_variant():
    async with get_sessionmaker()() as s:
        s.add(Strategy(
            id=2, user_id=1, name="S1 (variant)", code_path="s.py", params_json={"rsi": 40},
            symbols_json=["AAPL"], status=StrategyStatus.PAPER_VARIANT, parent_strategy_id=1,
            created_at=START, updated_at=START,
        ))
        await s.commit()


async def test_returns_no_active_variant_when_none(client):
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    assert r.status_code == 200
    assert r.json()["status"] == "no_active_variant"


async def test_returns_comparison_when_in_flight(client):
    await _add_variant()
    r = await client.get(f"{BASE}/strategies/1/variant-comparison")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "variant_active"
    assert body["variant_strategy_id"] == 2
    comp = body["comparison"]
    assert comp["parent_strategy_id"] == 1
    assert comp["variant_strategy_id"] == 2
    # metrics serialize to the five-field shape on both sides.
    for side in ("live_metrics", "variant_metrics"):
        assert set(comp[side]) == {
            "trade_count", "win_rate", "avg_return_per_trade",
            "sharpe_ratio", "max_drawdown",
        }
    assert set(comp["deltas"]) == {
        "sharpe_delta_pct", "max_drawdown_delta_pct",
        "win_rate_delta_pp", "avg_return_delta_pct",
    }


async def test_other_users_strategy_404(client):
    async with get_sessionmaker()() as s:
        s.add(Strategy(
            id=9, user_id=2, name="X", code_path="s.py", params_json={},
            symbols_json=[], status=StrategyStatus.LIVE, created_at=START, updated_at=START,
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/9/variant-comparison")
    assert r.status_code == 404
