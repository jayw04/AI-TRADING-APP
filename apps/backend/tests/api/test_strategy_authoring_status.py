"""P7 §7 — authoring-status: detect manual edits (out_of_sync)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import StrategyStatus, StrategyType
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.security import CredentialKind, CredentialStore  # noqa: F401 (parity w/ other tests)

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
    return tmp_path


async def _save(client) -> int:
    r = await client.post(
        f"{BASE}/strategies/author/save", json={"code": VALID, "name": "Synced"}
    )
    assert r.status_code == 200, r.text
    return r.json()["id"]


async def test_in_sync_after_save(client):
    sid = await _save(client)
    r = await client.get(f"{BASE}/strategies/{sid}/authoring-status")
    assert r.status_code == 200
    body = r.json()
    assert body["authoring_method"] == "nl_generation"
    assert body["revision_count"] == 1
    assert body["out_of_sync"] is False


async def test_out_of_sync_after_manual_edit(client, _seed):
    sid = await _save(client)
    # Manually edit the on-disk file.
    path = _seed / "strategies_user" / "synced.py"
    path.write_text(VALID + "\n# hand-tweaked\n", encoding="utf-8")
    r = await client.get(f"{BASE}/strategies/{sid}/authoring-status")
    assert r.json()["out_of_sync"] is True


async def test_manual_strategy_never_out_of_sync(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(Strategy(
            id=50, user_id=1, name="Manual", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="m.py", params_json={}, symbols_json=[],
            schedule="event", authoring_method="manual", created_at=now, updated_at=now,
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/50/authoring-status")
    assert r.json()["out_of_sync"] is False
    assert r.json()["revision_count"] == 0


async def test_status_other_user_404(client):
    async with get_sessionmaker()() as s:
        now = datetime.now(UTC)
        s.add(Strategy(
            id=9, user_id=2, name="X", version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", authoring_method="nl_generation", created_at=now, updated_at=now,
        ))
        await s.commit()
    r = await client.get(f"{BASE}/strategies/9/authoring-status")
    assert r.status_code == 404
