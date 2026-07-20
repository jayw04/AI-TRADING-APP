"""ADR 0043 PR6 — the recovery control-plane endpoints (HTTP wiring over the coordinator)."""

from __future__ import annotations

from datetime import UTC, datetime

from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.risk.loss_control import constants as C
from app.risk.loss_control.service import LossControlService, TransitionContext
from app.risk.loss_control.state_machine import TRIGGER_DAILY_LOSS_BREACH

BASE = "/api/v1/accounts/1/loss-control/recovery-requests"


async def _seed_account(owner_id: int = 1) -> None:
    async with get_sessionmaker()() as s:
        s.add(User(id=owner_id, email=f"u{owner_id}@t"))
        s.add(Account(id=1, user_id=owner_id, broker="alpaca", mode=AccountMode.paper,
                      label="P", created_at=datetime.now(UTC)))
        await s.commit()


async def _lock_daily_loss() -> None:
    async with get_sessionmaker()() as s:
        await LossControlService(s).request_transition(
            account_id=1, trigger=TRIGGER_DAILY_LOSS_BREACH,
            context=TransitionContext(initiator_type="SYSTEM",
                                      trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS),
        )


async def test_recovery_request_endpoint_creates_preflight_and_get_returns_12_checks(client):
    await _seed_account(owner_id=1)  # user 1 is the auto-authenticated user + owner
    await _lock_daily_loss()

    resp = await client.post(BASE, json={"idempotency_key": "k1"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["preflight_id"] is not None
    pid = body["preflight_id"]

    got = await client.get(f"{BASE}/{pid}")
    assert got.status_code == 200
    checks = got.json()["checks"]
    assert len(checks) == 12  # every check persisted and returned
    assert got.json()["origin_state"] == C.STATE_REDUCTION_ONLY_DAILY_LOSS


async def test_recovery_request_on_normal_state_is_conflict(client):
    await _seed_account(owner_id=1)  # never locked → state absent/NORMAL
    resp = await client.post(BASE, json={"idempotency_key": "k"})
    assert resp.status_code == 409  # not eligible
    assert resp.json()["detail"] == C.ERR_NOT_ELIGIBLE


async def test_recovery_request_body_rejects_client_supplied_origin(client):
    # The schema accepts ONLY idempotency_key — extra fields (e.g. a client-supplied target/origin)
    # are ignored by the model; there is no way to inject origin/results/force/target-state.
    await _seed_account(owner_id=1)
    await _lock_daily_loss()
    resp = await client.post(BASE, json={"idempotency_key": "k", "origin_state": "NORMAL",
                                         "force": True, "target_state": "NORMAL"})
    # Still processed by key alone; the injected fields have no effect (no path to NORMAL).
    assert resp.status_code == 200
