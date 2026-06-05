"""P6b §5 — LLM-opt-in endpoints (initiate / opt-out / status)."""
from __future__ import annotations

from datetime import UTC, datetime

import pytest

from app.db.enums import StrategyStatus
from app.db.models.eval_harness import HARNESS_ACTIVE, EvalHarness
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.db.session import get_sessionmaker
from app.security import CredentialKind, CredentialStore
from app.services.eval_harness.eligibility import EligibilityVerdict

BASE = "/api/v1"
ACK = "I understand LLM-driven trading is non-deterministic and I accept the risk"


def _verdict(eligible=True) -> EligibilityVerdict:
    return EligibilityVerdict(
        eligible=eligible, b_trade_count=60, window_days=40, min_trades=50,
        min_days=30, harness_active=True, reasons=[],
    )


@pytest.fixture(autouse=True)
async def _seed(client, monkeypatch):
    now = datetime.now(UTC)
    async with get_sessionmaker()() as s:
        s.add(User(id=1, email="jay@test", display_name="Jay"))
        s.add(Strategy(
            id=1, user_id=1, name="S1", version="0.1.0", code_path="s.py",
            params_json={}, symbols_json=["AAPL"], status=StrategyStatus.LIVE,
            created_at=now, updated_at=now,
        ))
        s.add(EvalHarness(
            id=1, user_id=1, parent_strategy_id=1, mode_a_strategy_id=1,
            mode_b_strategy_id=1, state=HARNESS_ACTIVE, started_at=now,
        ))
        await s.commit()
        await CredentialStore(s).set(1, CredentialKind.TOTP_SECRET, "SECRET")
        await s.commit()

    async def _elig(session, harness):  # noqa: ANN001, ANN202
        return _verdict(True)

    import app.api.v1.llm_opt_in as ep
    import app.auth.totp as totp_mod
    import app.services.llm_live_gate.service as svc

    monkeypatch.setattr(ep, "check_eligibility", _elig)
    monkeypatch.setattr(svc, "check_eligibility", _elig)
    monkeypatch.setattr(totp_mod, "verify_code", lambda secret, code, **kw: code == "123456")
    return client


async def _set_status(status):
    async with get_sessionmaker()() as s:
        strat = await s.get(Strategy, 1)
        strat.status = status
        await s.commit()


async def test_status_none_with_eligibility(client):
    r = await client.get(f"{BASE}/strategies/1/llm-opt-in")
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "none"
    assert body["eligibility"]["eligible"] is True


async def test_opt_in_success_pending(client):
    r = await client.post(
        f"{BASE}/strategies/1/llm-opt-in",
        json={"acknowledgment_text": ACK, "totp_code": "123456"},
    )
    assert r.status_code == 200
    assert r.json()["status"] == "pending"
    g = await client.get(f"{BASE}/strategies/1/llm-opt-in")
    assert g.json()["status"] == "pending"
    assert g.json()["daily_cap_cents"] == 500


async def test_opt_in_non_live_409(client):
    await _set_status(StrategyStatus.PAPER)
    r = await client.post(
        f"{BASE}/strategies/1/llm-opt-in",
        json={"acknowledgment_text": ACK, "totp_code": "123456"},
    )
    assert r.status_code == 409
    assert r.json()["detail"] == "parent_not_live"


async def test_opt_in_ack_mismatch_400(client):
    r = await client.post(
        f"{BASE}/strategies/1/llm-opt-in",
        json={"acknowledgment_text": "wrong", "totp_code": "123456"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "acknowledgment_mismatch"


async def test_opt_in_bad_totp_400(client):
    r = await client.post(
        f"{BASE}/strategies/1/llm-opt-in",
        json={"acknowledgment_text": ACK, "totp_code": "000000"},
    )
    assert r.status_code == 400
    assert r.json()["detail"] == "totp_invalid"


async def test_opt_out_after_opt_in(client):
    await client.post(
        f"{BASE}/strategies/1/llm-opt-in",
        json={"acknowledgment_text": ACK, "totp_code": "123456"},
    )
    r = await client.post(f"{BASE}/strategies/1/llm-opt-out")
    assert r.status_code == 200
    assert r.json()["status"] == "opted_out"
    g = await client.get(f"{BASE}/strategies/1/llm-opt-in")
    assert g.json()["status"] == "none"


async def test_opt_out_nothing_404(client):
    r = await client.post(f"{BASE}/strategies/1/llm-opt-out")
    assert r.status_code == 404
