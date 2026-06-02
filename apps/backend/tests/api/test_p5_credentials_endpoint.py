"""P5 §4 — /api/v1/users/me/credentials/ endpoints.

The autouse auth override (root conftest) authenticates every request as user
id=1, so these tests exercise the endpoint surface directly. The shared
in-memory engine the ``client`` fixture builds is the same one the endpoints
reach via ``get_session``.
"""

from __future__ import annotations

import pytest

BASE = "/api/v1/users/me/credentials"


@pytest.fixture(autouse=True)
async def _seed_user(client):
    """Seed user id=1 so the FK target exists (and to mirror real usage)."""
    from app.db.models.user import User
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        await session.commit()
    return client


async def test_list_initially_all_not_set(client):
    r = await client.get(f"{BASE}/")
    assert r.status_code == 200
    items = r.json()
    # All nine kinds represented; none set yet. (P5.5 §3 added WORKBENCH_MCP_KEY;
    # P6 §1a added AGENT_API_KEY.)
    assert len(items) == 9
    assert any(item["kind"] == "agent_api_key" for item in items)
    assert all(item["has_value"] is False for item in items)
    # Metadata never includes plaintext.
    for item in items:
        assert "value" not in item
        assert "ciphertext" not in item


async def test_put_then_list_shows_set(client):
    r = await client.put(f"{BASE}/anthropic_api_key", json={"value": "sk-secret"})
    assert r.status_code == 204

    r = await client.get(f"{BASE}/")
    items = {i["kind"]: i for i in r.json()}
    assert items["anthropic_api_key"]["has_value"] is True
    # Plaintext is never echoed anywhere in the metadata.
    assert "sk-secret" not in r.text


async def test_put_totp_rejected(client):
    r = await client.put(f"{BASE}/totp_secret", json={"value": "JBSWY3DPEHPK3PXP"})
    assert r.status_code == 400


async def test_delete_totp_rejected(client):
    r = await client.delete(f"{BASE}/totp_secret")
    assert r.status_code == 400


async def test_put_unknown_kind_rejected(client):
    r = await client.put(f"{BASE}/not_a_real_kind", json={"value": "x"})
    assert r.status_code == 400


async def test_put_empty_value_rejected(client):
    r = await client.put(f"{BASE}/anthropic_api_key", json={"value": ""})
    assert r.status_code == 400


async def test_delete_revokes(client):
    await client.put(f"{BASE}/pine_webhook_secret", json={"value": "pine-xyz"})
    r = await client.delete(f"{BASE}/pine_webhook_secret")
    assert r.status_code == 204

    r = await client.get(f"{BASE}/")
    items = {i["kind"]: i for i in r.json()}
    assert items["pine_webhook_secret"]["has_value"] is False


async def test_put_rotates_value(client):
    await client.put(f"{BASE}/alpaca_paper_key", json={"value": "key-1"})
    r = await client.put(f"{BASE}/alpaca_paper_key", json={"value": "key-2"})
    assert r.status_code == 204
    # Verify via the store that the active value is the rotated one.
    from app.db.session import get_sessionmaker
    from app.security import CredentialKind, CredentialStore

    async with get_sessionmaker()() as session:
        val = await CredentialStore(session).get(1, CredentialKind.ALPACA_PAPER_KEY)
    assert val == "key-2"
