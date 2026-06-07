"""P7 §2 — POST /strategies/author endpoint."""
from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

import pytest

from app.db.models.audit_log import AuditLog
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.security import CredentialKind, CredentialStore

BASE = "/api/v1"


def _fake_call():
    return SimpleNamespace(
        content_blocks=[{
            "type": "tool_use", "name": "emit_strategy",
            "input": {"code": "class S:\n    pass\n", "assumptions": ["a"], "explanation": "x"},
        }],
        input_tokens=4000, output_tokens=2000,
    )


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch):
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.ANTHROPIC_API_KEY, "sk-test")
        await s.commit()

    import app.services.strategy_authoring.service as svc

    async def _fake(**kwargs):  # noqa: ANN003
        return _fake_call()

    monkeypatch.setattr(svc, "create_message", _fake)
    return client


async def test_author_success(client):
    r = await client.post(f"{BASE}/strategies/author", json={"description": "RSI on AAPL"})
    assert r.status_code == 200
    body = r.json()
    assert "class S" in body["code"]
    assert body["assumptions"] == ["a"]
    assert body["cost_usd"] > 0
    assert body["model"] == "claude-sonnet-4-6"
    # P7 §3: the response carries a backtest outcome. The test app has no
    # bar_cache wired (alpaca startup disabled) → "unavailable", but the key is
    # present and shaped.
    assert "backtest" in body
    assert body["backtest"]["status"] == "unavailable"
    assert body["auto_fixed"] is False  # P7 §6: no bar_cache → no backtest → no autofix


async def test_refine_returns_revised(client):
    r = await client.post(
        f"{BASE}/strategies/author/refine",
        json={"prior_code": "class Old:\n    pass\n", "request": "tighten the stop"},
    )
    assert r.status_code == 200
    body = r.json()
    assert "class S" in body["code"]
    assert "backtest" in body
    assert "auto_fixed" in body


async def test_author_budget_429(client):
    async with get_sessionmaker()() as s:
        s.add(AuditLog(
            user_id=1, ts=datetime.now(UTC), actor_type="user", actor_id="1",
            action="STRATEGY_GENERATED", target_type="strategy_authoring", target_id=None,
            payload_json=json.dumps({"cost_usd": 2.0}),
        ))
        await s.commit()
    r = await client.post(f"{BASE}/strategies/author", json={"description": "x"})
    assert r.status_code == 429


async def test_author_no_key_400(client):
    async with get_sessionmaker()() as s:
        # remove the key by overwriting with empty is not allowed; instead use a
        # different user with no key via the auth override (user 1) — delete creds.
        from sqlalchemy import delete

        from app.db.models.user_credential import UserCredential
        await s.execute(delete(UserCredential).where(UserCredential.user_id == 1))
        await s.commit()
    r = await client.post(f"{BASE}/strategies/author", json={"description": "x"})
    assert r.status_code == 400
