"""P5 §8.2 — subsystem-aware /healthz.

(The clean-system "ok" and db-down "fail" cases live in tests/test_health.py.
These cover the new subsystem `checks` block, the no-auth contract, and the
circuit-breaker degraded path.)"""

from datetime import UTC, datetime


async def test_healthz_exposes_subsystem_checks(client):
    r = await client.get("/healthz")
    assert r.status_code in (200, 503)
    body = r.json()
    assert set(["database", "master_key", "broker_registry", "scheduler",
                "circuit_breakers_clear"]).issubset(body["checks"].keys())
    assert "version" in body and "uptime_seconds" in body


async def test_healthz_requires_no_auth(client):
    # Load balancers won't carry a session cookie — healthz must never 401.
    r = await client.get("/healthz")
    assert r.status_code != 401


async def test_healthz_ok_when_alpaca_disabled(client):
    # Tests run with alpaca-startup disabled → broker_registry + scheduler are
    # intentionally not started → reported "disabled", not degraded/failed.
    r = await client.get("/healthz")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "ok"
    assert body["checks"]["broker_registry"] == "disabled"
    assert body["checks"]["scheduler"] == "disabled"


async def test_healthz_degraded_when_breaker_tripped(client):
    from app.db.models.account import Account, AccountMode
    from app.db.models.user import User
    from app.db.session import get_sessionmaker

    async with get_sessionmaker()() as session:
        session.add(User(id=1, email="jay@test", display_name="Jay"))
        session.add(
            Account(
                user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper",
                created_at=datetime.now(UTC),
                circuit_breaker_tripped_at=datetime.now(UTC),
            )
        )
        await session.commit()

    r = await client.get("/healthz")
    assert r.status_code == 200  # degraded is still served
    body = r.json()
    assert body["status"] == "degraded"
    assert "degraded" in body["checks"]["circuit_breakers_clear"]
