"""P7 §5 — authoring history: save persists the conversation; GET reads it back."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"

VALID = """
from __future__ import annotations
from typing import Any, ClassVar
from app.strategies import Strategy

class Authored(Strategy):
    name: ClassVar[str] = "authored"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["AAPL"]
    schedule: ClassVar[str] = "event"
    default_params: ClassVar[dict[str, Any]] = {"timeframe": "1Min"}

    async def on_bar(self, bar) -> None:
        pass
"""


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch, tmp_path):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(User(id=2, email="other@test"))
        await s.commit()
    import app.api.v1.strategy_authoring as ep

    monkeypatch.setattr(ep, "_strategies_root", lambda: tmp_path / "strategies_user")
    return client


async def test_save_with_history_persists_turns(client):
    history = [
        {"kind": "generation", "user_message": "rsi reversion", "assumptions": ["RSI 14"],
         "explanation": "buys oversold", "code": VALID, "backtest": {"status": "ok"}, "cost_usd": 0.03},
        {"kind": "refinement", "user_message": "tighter stop", "assumptions": [],
         "explanation": "added 2x ATR stop", "code": VALID, "backtest": {"status": "no_trades"}, "cost_usd": 0.02},
    ]
    r = await client.post(
        f"{BASE}/strategies/author/save",
        json={"code": VALID, "name": "Hist Strat", "history": history},
    )
    assert r.status_code == 200, r.text
    sid = r.json()["id"]
    g = await client.get(f"{BASE}/strategies/{sid}/authoring-history")
    assert g.status_code == 200
    body = g.json()
    assert body["authoring_method"] == "nl_generation"
    revs = body["revisions"]
    assert [x["seq"] for x in revs] == [0, 1]
    assert revs[0]["kind"] == "generation"
    assert revs[0]["user_message"] == "rsi reversion"
    assert revs[1]["kind"] == "refinement"
    assert revs[1]["backtest"]["status"] == "no_trades"


async def test_save_without_history_records_one_generation_turn(client):
    r = await client.post(
        f"{BASE}/strategies/author/save", json={"code": VALID, "name": "No Hist"}
    )
    sid = r.json()["id"]
    g = await client.get(f"{BASE}/strategies/{sid}/authoring-history")
    revs = g.json()["revisions"]
    assert len(revs) == 1
    assert revs[0]["kind"] == "generation"
    assert revs[0]["code"] == VALID


async def test_history_empty_for_manual_strategy(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(Strategy(
            id=99, user_id=1, name="Manual", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="m.py", params_json={}, symbols_json=[],
            schedule="event", authoring_method="manual", created_at=now, updated_at=now,
        ))
        await s.commit()
    g = await client.get(f"{BASE}/strategies/99/authoring-history")
    assert g.status_code == 200
    assert g.json()["revisions"] == []
    assert g.json()["authoring_method"] == "manual"


async def test_history_other_user_404(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(Strategy(
            id=9, user_id=2, name="X", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", authoring_method="nl_generation", created_at=now, updated_at=now,
        ))
        await s.commit()
    g = await client.get(f"{BASE}/strategies/9/authoring-history")
    assert g.status_code == 404
