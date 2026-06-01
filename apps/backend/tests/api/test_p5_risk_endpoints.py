"""/api/v1/risk-limits and /accounts/{id}/risk/* endpoint tests (P5 §5).

Uses the shared `client` fixture (autouse auth override → user id=1) and seeds
via the production sessionmaker the endpoints reach (same pattern as the §4
credentials endpoint test).
"""
from datetime import UTC, datetime
from decimal import Decimal

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.risk_limits import RiskLimits


def _now() -> datetime:
    return datetime.now(UTC)


async def test_list_risk_limits_returns_user_rows(client):
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(RiskLimits(
            id=100, user_id=1, broker_mode=AccountMode.paper,
            scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("2000"),
            created_at=_now(), updated_at=_now(),
        ))
        session.add(RiskLimits(
            id=101, user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()

    r = await client.get("/api/v1/risk-limits")
    assert r.status_code == 200
    by_mode = {i["broker_mode"]: i for i in r.json()["items"]}
    assert by_mode["paper"]["max_daily_loss"] == "2000.0000"
    assert by_mode["live"]["max_daily_loss"] == "500.0000"


async def test_update_risk_limits_changes_value_and_audits(client):
    from sqlalchemy import select

    from app.db.models.audit_log import AuditLog
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        rl = RiskLimits(
            user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        )
        session.add(rl)
        await session.commit()
        await session.refresh(rl)
        limits_id = rl.id

    r = await client.put(f"/api/v1/risk-limits/{limits_id}",
                         json={"max_daily_loss": "400"})
    assert r.status_code == 200
    assert r.json()["max_daily_loss"] == "400.0000"

    async with get_sessionmaker()() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "RISK_LIMITS_UPDATED")
        )).scalars().all()
    assert len(audits) >= 1


async def test_update_risk_limits_other_user_returns_404(client):
    from app.db.models.user import User
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(User(id=2, email="other@local"))
        rl = RiskLimits(
            user_id=2, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL, max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        )
        session.add(rl)
        await session.commit()
        await session.refresh(rl)
        other_id = rl.id

    r = await client.put(f"/api/v1/risk-limits/{other_id}",
                         json={"max_daily_loss": "1"})
    assert r.status_code == 404


async def test_risk_state_returns_breaker_and_pdt(client):
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper", created_at=_now()))
        await session.commit()

    r = await client.get("/api/v1/accounts/1/risk-state")
    assert r.status_code == 200
    body = r.json()
    assert "circuit_breaker" in body and "pdt" in body
    assert body["circuit_breaker"]["tripped"] is False


async def test_reset_with_correct_confirmation(client):
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        account = Account(user_id=1, broker="alpaca", mode=AccountMode.paper,
                          label="Paper", created_at=_now())
        account.circuit_breaker_tripped_at = _now()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        acc_id = account.id

    r = await client.post(
        f"/api/v1/accounts/{acc_id}/risk/reset-circuit-breaker",
        json={"confirmation_text": "Paper"},
    )
    assert r.status_code == 200

    async with get_sessionmaker()() as session:
        acc = await session.get(Account, acc_id)
    assert acc.circuit_breaker_tripped_at is None


async def test_reset_with_wrong_confirmation_returns_400(client):
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        account = Account(user_id=1, broker="alpaca", mode=AccountMode.paper,
                          label="Paper", created_at=_now())
        account.circuit_breaker_tripped_at = _now()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        acc_id = account.id

    r = await client.post(
        f"/api/v1/accounts/{acc_id}/risk/reset-circuit-breaker",
        json={"confirmation_text": "wrong-label"},
    )
    assert r.status_code == 400
