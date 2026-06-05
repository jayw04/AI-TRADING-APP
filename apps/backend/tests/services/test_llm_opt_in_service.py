"""P6b §5 — LLMOptInService lifecycle (initiate guards, opt-out, completion)."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.audit_log import AuditLog
from app.db.models.eval_harness import HARNESS_ACTIVE, EvalHarness
from app.db.models.llm_opt_in import (
    OPT_IN_ACTIVE,
    OPT_IN_OPTED_OUT,
    OPT_IN_PENDING,
    LLMOptIn,
)
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.security import CredentialKind, CredentialStore
from app.services.llm_live_gate import service
from app.services.llm_live_gate.service import (
    RISK_ACK_PHRASE,
    complete_pending_opt_in,
    initiate_opt_in,
    opt_out,
)

NOW = datetime(2026, 6, 15, 12, 0, tzinfo=UTC)
SID, UID = 7, 1


@dataclass
class _Verdict:
    eligible: bool


class _FakeEngine:
    def __init__(self) -> None:
        self.calls: list[tuple[str, int]] = []

    async def register(self, sid: int) -> None:
        self.calls.append(("register", sid))

    async def unregister(self, sid: int, *, reason: str = "") -> None:
        self.calls.append(("unregister", sid))


async def _seed(
    session_factory, *, status=StrategyStatus.LIVE, with_harness=True, version="0.1.0"
) -> None:
    async with session_factory() as s:
        s.add(User(id=UID, email="jay@test"))
        s.add(Strategy(
            id=SID, user_id=UID, name="S1", version=version, code_path="s.py",
            params_json={}, symbols_json=["AAPL"], status=status,
            created_at=NOW, updated_at=NOW,
        ))
        if with_harness:
            s.add(EvalHarness(
                id=1, user_id=UID, parent_strategy_id=SID,
                mode_a_strategy_id=SID, mode_b_strategy_id=SID,
                state=HARNESS_ACTIVE, started_at=NOW,
            ))
        await s.commit()
        await CredentialStore(s).set(UID, CredentialKind.TOTP_SECRET, "SECRET")
        await s.commit()


def _patch(monkeypatch, *, eligible=True, totp_ok=True):
    async def _elig(session, harness):  # noqa: ANN001, ANN202
        return _Verdict(eligible=eligible)

    monkeypatch.setattr(service, "check_eligibility", _elig)
    import app.auth.totp as totp_mod

    monkeypatch.setattr(totp_mod, "verify_code", lambda secret, code, **kw: totp_ok)


async def test_initiate_success_pending_and_audit(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch(monkeypatch)
    async with session_factory() as s:
        opt_in = await initiate_opt_in(
            s, strategy_id=SID, user_id=UID,
            acknowledgment_text=RISK_ACK_PHRASE, totp_code="123456",
        )
    assert opt_in.state == OPT_IN_PENDING
    assert opt_in.strategy_version == "0.1.0"
    async with session_factory() as s:
        audits = (await s.execute(
            select(AuditLog).where(AuditLog.action == "LLM_OPT_IN_INITIATED")
        )).scalars().all()
    assert len(audits) == 1


async def test_initiate_rejects_non_live(session_factory, monkeypatch):
    await _seed(session_factory, status=StrategyStatus.PAPER)
    _patch(monkeypatch)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="parent_not_live"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text=RISK_ACK_PHRASE, totp_code="1")


async def test_initiate_rejects_no_eligible_harness(session_factory, monkeypatch):
    await _seed(session_factory, with_harness=False)
    _patch(monkeypatch)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="no_eligible_harness"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text=RISK_ACK_PHRASE, totp_code="1")


async def test_initiate_rejects_when_ineligible(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch(monkeypatch, eligible=False)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="no_eligible_harness"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text=RISK_ACK_PHRASE, totp_code="1")


async def test_initiate_rejects_ack_mismatch(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch(monkeypatch)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="acknowledgment_mismatch"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text="nope", totp_code="123456")


async def test_initiate_rejects_bad_totp(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch(monkeypatch, totp_ok=False)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="totp_invalid"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text=RISK_ACK_PHRASE, totp_code="000000")


async def test_initiate_rejects_second_opt_in(session_factory, monkeypatch):
    await _seed(session_factory)
    _patch(monkeypatch)
    async with session_factory() as s:
        await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                              acknowledgment_text=RISK_ACK_PHRASE, totp_code="123456")
    async with session_factory() as s:
        with pytest.raises(ValueError, match="opt_in_already_active"):
            await initiate_opt_in(s, strategy_id=SID, user_id=UID,
                                  acknowledgment_text=RISK_ACK_PHRASE, totp_code="123456")


async def _seed_opt_in(session_factory, *, state, initiated_days_ago=0, version="0.1.0"):
    async with session_factory() as s:
        s.add(LLMOptIn(
            id=1, user_id=UID, strategy_id=SID, strategy_version=version, state=state,
            acknowledgment_text="ack", daily_cap_cents=500,
            initiated_at=datetime.now(UTC) - timedelta(days=initiated_days_ago),
            created_at=NOW, updated_at=NOW,
        ))
        await s.commit()


async def test_opt_out_active_reregisters(session_factory):
    await _seed(session_factory)
    await _seed_opt_in(session_factory, state=OPT_IN_ACTIVE)
    eng = _FakeEngine()
    async with session_factory() as s:
        await opt_out(s, strategy_id=SID, user_id=UID, engine=eng)
    async with session_factory() as s:
        row = await s.get(LLMOptIn, 1)
    assert row.state == OPT_IN_OPTED_OUT
    assert ("unregister", SID) in eng.calls and ("register", SID) in eng.calls


async def test_opt_out_not_found_raises(session_factory):
    await _seed(session_factory)
    async with session_factory() as s:
        with pytest.raises(ValueError, match="opt_in_not_found"):
            await opt_out(s, strategy_id=SID, user_id=UID)


async def test_complete_activates_after_cooldown(session_factory):
    await _seed(session_factory)
    await _seed_opt_in(session_factory, state=OPT_IN_PENDING, initiated_days_ago=8)
    eng = _FakeEngine()
    async with session_factory() as s:
        ok = await complete_pending_opt_in(s, opt_in_id=1, engine=eng)
    assert ok is True
    async with session_factory() as s:
        row = await s.get(LLMOptIn, 1)
    assert row.state == OPT_IN_ACTIVE
    assert ("register", SID) in eng.calls


async def test_complete_noop_before_cooldown(session_factory):
    await _seed(session_factory)
    await _seed_opt_in(session_factory, state=OPT_IN_PENDING, initiated_days_ago=2)
    async with session_factory() as s:
        ok = await complete_pending_opt_in(s, opt_in_id=1, engine=None)
    assert ok is False
    async with session_factory() as s:
        assert (await s.get(LLMOptIn, 1)).state == OPT_IN_PENDING


async def test_complete_invalidates_on_version_drift(session_factory):
    await _seed(session_factory, version="0.2.0")  # strategy version moved on
    await _seed_opt_in(session_factory, state=OPT_IN_PENDING, initiated_days_ago=8, version="0.1.0")
    async with session_factory() as s:
        ok = await complete_pending_opt_in(s, opt_in_id=1, engine=None)
    assert ok is False
    async with session_factory() as s:
        row = await s.get(LLMOptIn, 1)
    assert row.state == OPT_IN_OPTED_OUT
    assert row.opted_out_reason == "invalidated"
