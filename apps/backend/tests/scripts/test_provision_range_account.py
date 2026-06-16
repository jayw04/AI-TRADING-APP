"""§5a 2-3 — provision_range_account: second-user paper creds + account row.

The script's core (`provision_paper_account`) is loaded directly from the file
(scripts/ is not a package). It is exercised against the in-memory test DB; no
.env / real credentials are touched.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

from app.db.models import User
from app.db.models.account import Account, AccountMode
from app.security.credential_store import CredentialKind, CredentialStore

_SCRIPT = (
    Path(__file__).resolve().parents[2] / "scripts" / "provision_range_account.py"
)
_spec = importlib.util.spec_from_file_location("provision_range_account", _SCRIPT)
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)
provision_paper_account = _mod.provision_paper_account
ProvisionError = _mod.ProvisionError

EMAIL = "range@local"


async def _seed_user(session_factory) -> int:
    async with session_factory() as s:
        u = User(email=EMAIL, display_name="Range Trader")
        s.add(u)
        await s.flush()
        uid = u.id
        await s.commit()
    return uid


async def _stored_key(session_factory, user_id: int) -> str | None:
    async with session_factory() as s:
        return await CredentialStore(s).get(user_id, CredentialKind.ALPACA_PAPER_KEY)


@pytest.mark.asyncio
async def test_provisions_creds_and_account(session_factory):
    uid = await _seed_user(session_factory)
    result = await provision_paper_account(
        session_factory,
        email=EMAIL,
        api_key="paper1-key",
        api_secret="paper1-secret",
        label="Alpaca Paper (Range)",
    )

    assert result["user_id"] == uid
    assert result["actions"] == ["creds", "account"]
    assert result["key_fp"].startswith("sha256:")
    assert "paper1-key" not in result["key_fp"]  # never leak the value

    # Account row created, scoped to the second user, paper/alpaca.
    async with session_factory() as s:
        acct = await s.get(Account, result["account_id"])
        assert acct is not None
        assert acct.user_id == uid
        assert acct.broker == "alpaca"
        assert acct.mode == AccountMode.paper
        assert acct.label == "Alpaca Paper (Range)"
    # Creds stored under the second user.
    assert await _stored_key(session_factory, uid) == "paper1-key"


@pytest.mark.asyncio
async def test_idempotent_leaves_existing_account(session_factory):
    uid = await _seed_user(session_factory)
    async with session_factory() as s:
        s.add(
            Account(
                user_id=uid, broker="alpaca", mode=AccountMode.paper, label="pre-existing"
            )
        )
        await s.commit()

    result = await provision_paper_account(
        session_factory, email=EMAIL, api_key="rotated-key", api_secret="rotated-secret"
    )

    assert result["actions"] == ["creds"]  # account NOT re-created
    assert result["account_exists"] is True
    # creds were still upserted
    assert await _stored_key(session_factory, uid) == "rotated-key"
    # exactly one paper account for this user
    async with session_factory() as s:
        from sqlalchemy import func, select

        n = await s.scalar(
            select(func.count(Account.id)).where(
                Account.user_id == uid, Account.mode == AccountMode.paper
            )
        )
        assert n == 1


@pytest.mark.asyncio
async def test_missing_user_raises(session_factory):
    with pytest.raises(ProvisionError):
        await provision_paper_account(
            session_factory, email="nobody@local", api_key="k", api_secret="s"
        )


@pytest.mark.asyncio
async def test_dry_run_writes_nothing(session_factory):
    uid = await _seed_user(session_factory)
    result = await provision_paper_account(
        session_factory, email=EMAIL, api_key="k", api_secret="s", dry_run=True
    )

    assert result["dry_run"] is True
    assert result["account_exists"] is False
    # nothing persisted
    assert await _stored_key(session_factory, uid) is None
    async with session_factory() as s:
        from sqlalchemy import func, select

        n = await s.scalar(
            select(func.count(Account.id)).where(Account.user_id == uid)
        )
        assert n == 0
