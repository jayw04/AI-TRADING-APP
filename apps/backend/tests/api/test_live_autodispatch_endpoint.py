"""P6b §4.5 (ADR 0015) — the live-auto-dispatch master-switch endpoints."""
from __future__ import annotations

import pytest

from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.security import CredentialKind, CredentialStore

BASE = "/api/v1"
GOOD_TOTP = "123456"


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch):
    # A valid TOTP secret so the flip is permitted; verify_code is patched to
    # accept GOOD_TOTP (the real TOTP flow is exercised by the auth suite).
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.TOTP_SECRET, "SECRET")
        await s.commit()

    # The endpoint imports verify_code from app.auth.totp inside the handler,
    # so patch it at the source. Accept GOOD_TOTP regardless of the secret.
    import app.auth.totp as totp_mod

    monkeypatch.setattr(totp_mod, "verify_code", lambda secret, code, **kw: code == GOOD_TOTP)
    return client


async def test_default_off(client):
    r = await client.get(f"{BASE}/system/live-autodispatch")
    assert r.status_code == 200
    assert r.json()["enabled"] is False


async def test_enable_with_valid_totp(client):
    r = await client.post(
        f"{BASE}/system/live-autodispatch",
        json={"enabled": True, "totp_code": GOOD_TOTP},
    )
    assert r.status_code == 200
    assert r.json()["enabled"] is True
    g = await client.get(f"{BASE}/system/live-autodispatch")
    assert g.json()["enabled"] is True


async def test_bad_totp_rejected(client):
    r = await client.post(
        f"{BASE}/system/live-autodispatch",
        json={"enabled": True, "totp_code": "000000"},
    )
    assert r.status_code == 400
    g = await client.get(f"{BASE}/system/live-autodispatch")
    assert g.json()["enabled"] is False  # unchanged


async def test_disable_round_trips(client):
    await client.post(
        f"{BASE}/system/live-autodispatch",
        json={"enabled": True, "totp_code": GOOD_TOTP},
    )
    r = await client.post(
        f"{BASE}/system/live-autodispatch",
        json={"enabled": False, "totp_code": GOOD_TOTP},
    )
    assert r.json()["enabled"] is False
