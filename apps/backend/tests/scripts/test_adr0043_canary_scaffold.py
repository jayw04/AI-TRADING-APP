"""ADR-0043 canary scaffold — governed creation of ONLY user 3 + account 3.

Hermetic: an in-memory schema seeded with the momentum user 1 / account 1, then the real scaffold is
driven through fresh creation, exact-id assignment, idempotent rerun, collision refusal, partial-state
refusal, precondition/transaction rollback, sequence repair, and user-1 non-mutation.
"""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import text

import scripts.adr0043_canary_scaffold as scaf
from app.db.models.account import Account, AccountMode
from app.db.models.user import User


async def _seed_momentum(sf, *, with_cred=False):
    async with sf() as s:
        s.add(User(id=1, email="jay@globalcomplyai.com", display_name="Momentum"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Alpaca Paper"))
        await s.flush()
        if with_cred:
            await s.execute(text(
                "INSERT INTO user_credentials (user_id,kind,ciphertext,created_at,updated_at) "
                "VALUES (1,'alpaca_paper_key',:c,:t,:t)"), {"c": b"CIPHERTEXT-1", "t": datetime.now(UTC)})
        await s.commit()


async def _insert_minimal(sf, table, **overrides):
    """Insert a row filling NOT NULL non-default columns with dummy values, applying overrides.
    Schema-robust so a test doesn't hard-code a model's full column set."""
    async with sf() as s:
        info = (await s.execute(text(f"PRAGMA table_info({table})"))).fetchall()
        vals = {}
        for _cid, name, typ, notnull, dflt, pk in info:
            if pk:
                continue
            if name in overrides:
                vals[name] = overrides[name]
            elif notnull and dflt is None:
                t = (typ or "").upper()
                if "INT" in t:
                    vals[name] = 0
                elif any(k in t for k in ("CHAR", "TEXT", "CLOB")):
                    vals[name] = "x"
                elif any(k in t for k in ("REAL", "FLOA", "DOUB", "NUM", "DEC")):
                    vals[name] = 0
                elif any(k in t for k in ("DATE", "TIME")):
                    vals[name] = datetime.now(UTC)
                else:
                    vals[name] = "x"
        cols = ",".join(vals)
        ph = ",".join(f":{k}" for k in vals)
        await s.execute(text(f"INSERT INTO {table} ({cols}) VALUES ({ph})"), vals)
        await s.commit()


async def test_fresh_creation_assigns_exact_id_3(session_factory):
    await _seed_momentum(session_factory)
    res = await scaf.scaffold(session_factory, apply=True)
    assert res["mode"] == "created"
    assert res["created"] == ["user:3", "account:3"]
    assert res["protected_unchanged"] is True
    async with session_factory() as s:
        u3 = await scaf._row(s, "users", 3)
        a3 = await scaf._row(s, "accounts", 3)
    assert u3 and u3["email"] == scaf.CANARY_EMAIL and u3["display_name"] == scaf.CANARY_DISPLAY
    assert a3 and a3["user_id"] == 3 and a3["broker"] == "alpaca"
    assert str(a3["mode"]) == "paper" and a3["label"] == scaf.CANARY_LABEL


async def test_creates_nothing_else(session_factory):
    await _seed_momentum(session_factory)
    await scaf.scaffold(session_factory, apply=True)
    async with session_factory() as s:
        for tbl in ("positions", "orders", "risk_reservations", "risk_control_events",
                    "risk_loss_control_state", "strategies", "risk_limits"):
            n = (await s.execute(text(f"SELECT COUNT(*) FROM {tbl}"))).scalar()
            assert n == 0, f"{tbl} must stay empty (got {n})"


async def test_user1_and_credentials_not_mutated(session_factory):
    await _seed_momentum(session_factory, with_cred=True)
    res = await scaf.scaffold(session_factory, apply=True)
    assert res["protected_digests_before"] == res["protected_digests_after"]
    assert res["protected_unchanged"] is True
    async with session_factory() as s:
        u1 = await scaf._row(s, "users", 1)
        ch = (await s.execute(text("SELECT hex(ciphertext) FROM user_credentials WHERE user_id=1"))).scalar()
    assert u1["email"] == "jay@globalcomplyai.com" and u1["display_name"] == "Momentum"
    assert ch == b"CIPHERTEXT-1".hex().upper()


async def test_idempotent_rerun_is_a_noop(session_factory):
    await _seed_momentum(session_factory)
    await scaf.scaffold(session_factory, apply=True)
    res2 = await scaf.scaffold(session_factory, apply=True)
    assert res2["mode"] == "idempotent_noop"
    assert res2["created"] == []
    assert res2["counts_after"]["users"] == 2 and res2["counts_after"]["accounts"] == 2


async def test_conflicting_user3_is_refused_not_edited(session_factory):
    await _seed_momentum(session_factory)
    async with session_factory() as s:
        s.add(User(id=3, email="someone-else@x", display_name="Not Canary"))
        s.add(Account(id=3, user_id=3, broker="alpaca", mode=AccountMode.paper, label="other"))
        await s.commit()
    with pytest.raises(scaf.CanaryScaffoldError, match="does not match frozen identity"):
        await scaf.scaffold(session_factory, apply=True)
    async with session_factory() as s:  # the pre-existing rows were NOT edited into conformance
        u3 = await scaf._row(s, "users", 3)
    assert u3["email"] == "someone-else@x"


async def test_partial_state_is_refused(session_factory):
    await _seed_momentum(session_factory)
    async with session_factory() as s:
        s.add(User(id=3, email=scaf.CANARY_EMAIL, display_name=scaf.CANARY_DISPLAY))  # user 3, no account 3
        await s.commit()
    with pytest.raises(scaf.CanaryScaffoldError, match="partial state"):
        await scaf.scaffold(session_factory, apply=True)


async def test_precondition_open_order_fails_closed_and_rolls_back(session_factory):
    await _seed_momentum(session_factory)
    await _insert_minimal(session_factory, "orders", user_id=1, account_id=1, status="submitted")
    with pytest.raises(scaf.CanaryScaffoldError, match="open order"):
        await scaf.scaffold(session_factory, apply=True)
    async with session_factory() as s:  # transaction rolled back — user/account 3 absent
        assert await scaf._row(s, "users", 3) is None
        assert await scaf._row(s, "accounts", 3) is None


async def test_dry_run_writes_nothing(session_factory):
    await _seed_momentum(session_factory)
    res = await scaf.scaffold(session_factory, apply=False)
    assert res["mode"].endswith("dry_run")
    async with session_factory() as s:
        assert await scaf._row(s, "users", 3) is None
        assert await scaf._row(s, "accounts", 3) is None


async def test_sequence_repaired_so_next_insert_does_not_collide(session_factory):
    await _seed_momentum(session_factory)
    res = await scaf.scaffold(session_factory, apply=True)
    seq = res["sequence"]
    assert seq["users"]["next"] > seq["users"]["max_id"]
    assert seq["accounts"]["next"] > seq["accounts"]["max_id"]
    assert seq["users"]["next"] == 4 and seq["accounts"]["next"] == 4
    async with session_factory() as s:  # a subsequent ordinary insert lands at id 4, not colliding with 3
        u = User(email="next@x")
        s.add(u)
        await s.commit()
        nid = (await s.execute(text("SELECT id FROM users WHERE email='next@x'"))).scalar()
    assert nid == 4
