"""ADR-0043 canary credential install — atomic user-3 paper key+secret, user-1 untouched.

Hermetic: seed the momentum user 1 (+ its two credentials) and the canary user 3 / account 3, then
drive the real installer through atomic success, dry-run, second-write-failure rollback (no half
install), reinstall refusal, key-prefix refusal, precondition refusals, and user-1 non-mutation.
The test master key comes from conftest, so encrypt()/decrypt() work.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

import scripts.adr0043_install_canary_credentials as mod
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.db.models.user_credential import UserCredential
from app.security.credential_store import CredentialKind
from app.security.crypto import decrypt, encrypt

CANARY_KEY = "PKZYTY6ZTF37HVNXHJ2SICMJKN"
CANARY_SECRET = "canary-paper-secret-value-xyz"


async def _seed(sf):
    now = datetime.now(UTC)
    async with sf() as s:
        s.add(User(id=1, email="jay@globalcomplyai.com", display_name="Momentum"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Alpaca Paper"))
        s.add(User(id=3, email="adr0043-canary@localhost", display_name="ADR-0043 Canary"))
        s.add(Account(id=3, user_id=3, broker="alpaca", mode=AccountMode.paper, label="ADR-0043 canary"))
        s.add(UserCredential(user_id=1, kind="alpaca_paper_key",
                             ciphertext=encrypt("PKOJTY-momentum-key"), created_at=now, updated_at=now))
        s.add(UserCredential(user_id=1, kind="alpaca_paper_secret",
                             ciphertext=encrypt("momentum-secret"), created_at=now, updated_at=now))
        await s.commit()


async def _user1_digest(sf) -> str:
    async with sf() as s:
        return await mod._user1_cred_digest(s)


async def test_atomic_install_writes_both_and_round_trip_verifies(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    ev = await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                           expected_user1_digest=d1, apply=True)
    assert ev["mode"] == "installed" and ev["applied"] is True
    assert ev["alpaca_paper_key_active_count"] == 1 and ev["alpaca_paper_secret_active_count"] == 1
    assert ev["key_prefix"] == "PKZYTY" and ev["round_trip_verified"] is True
    assert ev["user1_cred_digest_unchanged"] is True
    # the stored values decrypt back to exactly the inputs
    async with session_factory() as s:
        kr = await mod._active_row(s, 3, CredentialKind.ALPACA_PAPER_KEY)
        sr = await mod._active_row(s, 3, CredentialKind.ALPACA_PAPER_SECRET)
    assert decrypt(kr.ciphertext) == CANARY_KEY and decrypt(sr.ciphertext) == CANARY_SECRET


async def test_dry_run_writes_nothing(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    ev = await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                           expected_user1_digest=d1, apply=False)
    assert ev["mode"] == "dry_run:rolled_back" and ev["applied"] is False
    async with session_factory() as s:  # rolled back — no user-3 credentials persisted
        assert await mod._active_count(s, 3, CredentialKind.ALPACA_PAPER_KEY) == 0
        assert await mod._active_count(s, 3, CredentialKind.ALPACA_PAPER_SECRET) == 0


async def test_second_write_failure_leaves_no_half_install(session_factory, monkeypatch):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    calls = {"n": 0}
    real = mod.encrypt

    def flaky(plaintext):
        calls["n"] += 1
        if calls["n"] == 2:  # fail on the SECOND encrypted write (the secret)
            raise RuntimeError("boom on second write")
        return real(plaintext)

    monkeypatch.setattr(mod, "encrypt", flaky)
    with pytest.raises(RuntimeError, match="boom on second write"):
        await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                          expected_user1_digest=d1, apply=True)
    async with session_factory() as s:  # NEITHER record persisted — no half install
        assert await mod._active_count(s, 3, CredentialKind.ALPACA_PAPER_KEY) == 0
        assert await mod._active_count(s, 3, CredentialKind.ALPACA_PAPER_SECRET) == 0


async def test_reinstall_refused_when_user3_already_has_credentials(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                      expected_user1_digest=d1, apply=True)
    with pytest.raises(mod.InstallError, match="already has .* active credential"):
        await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                          expected_user1_digest=d1, apply=True)


async def test_user1_credentials_unchanged_after_install(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                      expected_user1_digest=d1, apply=True)
    assert await _user1_digest(session_factory) == d1
    async with session_factory() as s:
        assert decrypt((await mod._active_row(s, 1, CredentialKind.ALPACA_PAPER_KEY)).ciphertext) == "PKOJTY-momentum-key"


async def test_key_prefix_mismatch_refused(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    with pytest.raises(mod.InstallError, match="api key prefix"):
        await mod.install(session_factory, user_id=3, api_key="PKOJTY-wrong", secret=CANARY_SECRET,
                          expected_user1_digest=d1, apply=True)
    async with session_factory() as s:
        assert await mod._active_count(s, 3, CredentialKind.ALPACA_PAPER_KEY) == 0


async def test_precondition_missing_user3_refused(session_factory):
    async with session_factory() as s:  # only momentum user 1 — no canary user/account 3
        s.add(User(id=1, email="jay@globalcomplyai.com", display_name="Momentum"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Alpaca Paper"))
        await s.commit()
    d1 = await _user1_digest(session_factory)
    with pytest.raises(mod.InstallError, match="user 3 not present exactly once"):
        await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                          expected_user1_digest=d1, apply=True)


async def test_precondition_open_order_refused(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    async with session_factory() as s:
        info = (await s.execute(mod.text("PRAGMA table_info(orders)"))).fetchall()
        vals = {"user_id": 1, "account_id": 1, "status": "submitted"}
        for _c, name, typ, notnull, dflt, pk in info:
            if pk or name in vals:
                continue
            if notnull and dflt is None:
                t = (typ or "").upper()
                vals[name] = 0 if ("INT" in t or any(k in t for k in ("NUM", "DEC", "REAL"))) else (
                    datetime.now(UTC) if ("DATE" in t or "TIME" in t) else "x")
        cols = ",".join(vals)
        ph = ",".join(f":{k}" for k in vals)
        await s.execute(mod.text(f"INSERT INTO orders ({cols}) VALUES ({ph})"), vals)
        await s.commit()
    with pytest.raises(mod.InstallError, match="open order"):
        await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret=CANARY_SECRET,
                          expected_user1_digest=d1, apply=True)


async def test_empty_secret_refused(session_factory):
    await _seed(session_factory)
    d1 = await _user1_digest(session_factory)
    with pytest.raises(mod.InstallError):
        await mod.install(session_factory, user_id=3, api_key=CANARY_KEY, secret="",
                          expected_user1_digest=d1, apply=True)
