"""P7 §4 — POST /strategies/author/save (write file + register + authoring_method)."""
from __future__ import annotations

import pytest
from sqlalchemy import select

from app.db.models.audit_log import AuditLog
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker

BASE = "/api/v1"

VALID = """
from __future__ import annotations
from decimal import Decimal
from typing import Any, ClassVar
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Strategy

class Authored(Strategy):
    name: ClassVar[str] = "authored"
    version: ClassVar[str] = "0.2.0"
    symbols: ClassVar[list[str]] = ["AAPL"]
    schedule: ClassVar[str] = "event"
    default_params: ClassVar[dict[str, Any]] = {"timeframe": "1Min"}

    async def on_bar(self, bar) -> None:
        pass
"""

NO_STRATEGY = "x = 1  # valid python, but no Strategy subclass\n"


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch, tmp_path):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        await s.commit()
    # Point the authored-save root at a tmp dir so the suite never writes into the
    # repo's strategies_user/.
    import app.api.v1.strategy_authoring as ep

    root = tmp_path / "strategies_user"
    monkeypatch.setattr(ep, "_strategies_root", lambda: root)
    return client


async def test_save_success(client):
    r = await client.post(f"{BASE}/strategies/author/save", json={"code": VALID, "name": "My Strat"})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["authoring_method"] == "nl_generation"
    assert body["status"] == "idle"
    assert body["code_path"] == "my_strat.py"
    async with get_sessionmaker()() as s:
        row = await s.get(Strategy, body["id"])
        assert row.authoring_method == "nl_generation"
        assert row.version == "0.2.0"
        audits = (await s.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_REGISTERED")
        )).scalars().all()
    assert len(audits) == 1


async def test_save_unsafe_code_400_no_row(client):
    r = await client.post(
        f"{BASE}/strategies/author/save",
        json={"code": "import os\nos.system('x')", "name": "Bad"},
    )
    assert r.status_code == 400
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Strategy))).scalars().all()
    assert rows == []  # nothing persisted


async def test_save_duplicate_name_409(client):
    await client.post(f"{BASE}/strategies/author/save", json={"code": VALID, "name": "Dup"})
    r = await client.post(f"{BASE}/strategies/author/save", json={"code": VALID, "name": "Dup"})
    assert r.status_code == 409


async def test_save_no_strategy_subclass_400_and_cleanup(client, tmp_path):
    r = await client.post(
        f"{BASE}/strategies/author/save", json={"code": NO_STRATEGY, "name": "Empty"}
    )
    assert r.status_code == 400
    # The temp file was cleaned up (no orphan) and no row persisted.
    assert not (tmp_path / "strategies_user" / "empty.py").exists()
    async with get_sessionmaker()() as s:
        rows = (await s.execute(select(Strategy))).scalars().all()
    assert rows == []
