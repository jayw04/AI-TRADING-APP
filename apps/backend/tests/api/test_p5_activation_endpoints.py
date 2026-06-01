"""Activation endpoint tests (P5 §7). Uses the `client` fixture (autauths user
id=1) + get_sessionmaker seeding; WORKBENCH_MASTER_KEY comes from conftest."""
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pyotp
import pytest

from app.db.enums import RiskScopeType, StrategyStatus, StrategyType
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def live_setup(client) -> str:
    """Seed user 1 + live account + strategy + limits + backtest + creds.
    Returns the TOTP secret."""
    from app.db.session import get_sessionmaker
    from app.security.credential_store import CredentialKind, CredentialStore

    async with get_sessionmaker()() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay", totp_verified_at=_now()))
        session.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
                            label="MyLive", created_at=_now()))
        session.add(RiskLimits(user_id=1, broker_mode=AccountMode.live,
                               scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
                               created_at=_now(), updated_at=_now()))
        session.add(StrategyRow(id=10, user_id=1, name="my_strategy", version="0.1.0",
                                type=StrategyType.PYTHON, status=StrategyStatus.IDLE,
                                code_path="x.py", params_json={}, symbols_json=["AAPL"],
                                schedule="event", created_at=_now(), updated_at=_now()))
        session.add(BacktestResult(strategy_id=10, label="bt", params_json={},
                                   metrics_json={}, equity_curve_json=[], trades_json=[],
                                   range_start=_now() - timedelta(days=30), range_end=_now(),
                                   created_at=_now() - timedelta(days=1)))
        await session.commit()
        store = CredentialStore(session)
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "PK")
        await store.set(1, CredentialKind.ALPACA_LIVE_SECRET, "sec")
        secret = pyotp.random_base32()
        await store.set(1, CredentialKind.TOTP_SECRET, secret)
    return secret


async def test_activation_status_returns_prerequisites(client, live_setup):
    r = await client.get("/api/v1/strategies/10/activation")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == 10
    assert body["status"] == "idle"
    assert len(body["prerequisites"]) == 6  # incl. live_account_exists
    assert body["all_satisfied"] is True


async def test_activate_success_transitions_to_pending_live(client, live_setup):
    code = pyotp.TOTP(live_setup).now()
    r = await client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy", "totp_code": code,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_live"
    assert body["seconds_remaining"] > 23 * 3600


async def test_activate_bad_totp_400(client, live_setup):
    r = await client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy", "totp_code": "000000",
    })
    assert r.status_code == 400


async def test_activate_bad_name_400(client, live_setup):
    code = pyotp.TOTP(live_setup).now()
    r = await client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "WRONG", "totp_code": code,
    })
    assert r.status_code == 400


async def test_cancel_returns_to_idle(client, live_setup):
    code = pyotp.TOTP(live_setup).now()
    await client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy", "totp_code": code,
    })
    r = await client.post("/api/v1/strategies/10/activate/cancel")
    assert r.status_code == 200
    r = await client.get("/api/v1/strategies/10/activation")
    assert r.json()["status"] == "idle"


async def test_cancel_not_pending_returns_400(client, live_setup):
    r = await client.post("/api/v1/strategies/10/activate/cancel")
    assert r.status_code == 400


async def test_deactivate_idle_strategy_returns_400(client, live_setup):
    r = await client.post("/api/v1/strategies/10/deactivate", json={"liquidate": False})
    assert r.status_code == 400


async def test_deactivate_live_strategy(client, live_setup):
    from app.db.session import get_sessionmaker
    async with get_sessionmaker()() as session:
        s = await session.get(StrategyRow, 10)
        s.status = StrategyStatus.LIVE
        await session.commit()
    r = await client.post("/api/v1/strategies/10/deactivate", json={"liquidate": False})
    assert r.status_code == 200
    assert r.json()["new_status"] == "idle"


async def test_activation_initiated_audited(client, live_setup):
    from sqlalchemy import select

    from app.db.models.audit_log import AuditLog
    from app.db.session import get_sessionmaker
    code = pyotp.TOTP(live_setup).now()
    await client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy", "totp_code": code,
    })
    async with get_sessionmaker()() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "STRATEGY_ACTIVATION_INITIATED")
        )).scalars().all()
    assert len(audits) >= 1
