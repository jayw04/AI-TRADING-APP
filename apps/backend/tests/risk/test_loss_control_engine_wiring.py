"""ADR 0043 PR4 — the loss-control gate wired into RiskEngine.evaluate (engine level).

OFF is byte-identical (no reads/writes); SHADOW evaluates + persists transitions + emits evidence
but never changes accept/refuse; ENFORCE is authoritative at its gate but never weakens a stricter
independent control and fails closed on missing state; a shadow exception is isolated and
CancelledError propagates; no recovery/re-arm transition is initiated.
"""

from __future__ import annotations

import asyncio
import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import func, select

import app.risk.engine as engine_mod
from app.config import LossControlMode
from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskDecision,
    RiskScopeType,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.audit_log import AuditLog
from app.db.models.risk_limits import RiskLimits
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.engine import RiskEngine
from app.risk.loss_control import constants as C
from app.risk.types import OrderRequest

D = Decimal
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)
REJECT = RiskDecision.REJECT.value
PASS = RiskDecision.PASS.value


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@l"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P", created_at=NOW))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper, scope_type=RiskScopeType.GLOBAL,
                         max_daily_loss=D("5000"), created_at=NOW, updated_at=NOW))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity", name="Apple", active=True))
        await s.commit()
    return session_factory


def _set_mode(monkeypatch, mode):
    monkeypatch.setattr(
        engine_mod, "get_settings",
        lambda: SimpleNamespace(loss_control_mode=mode, session_baseline_enforcement_enabled=False),
    )


async def _set_state(session_factory, state, *, account_id=1, version=0):
    async with session_factory() as s:
        s.add(RiskLossControlState(account_id=account_id, state=state, state_version=version,
                                   last_sequence_no=version, control_version=1, updated_at=NOW))
        await s.commit()


async def _breaching_state(session_factory):
    async with session_factory() as s:
        s.add(AccountState(account_id=1, cash=D("0"), equity=D("94000"), last_equity=D("100000"),
                           buying_power=D("0"), portfolio_value=D("94000"), daytrade_count=0,
                           day_change=D("-6000"), day_change_pct=D("0"), status="ACTIVE",
                           updated_at=NOW, raw_payload={}))
        await s.commit()


def _order(side=OrderSide.BUY, qty="1"):
    return OrderRequest(user_id=1, account_id=1, symbol_ticker="AAPL", side=side, qty=D(qty),
                        type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.MANUAL)


async def _evaluate(session_factory, req):
    return await RiskEngine(session_factory).evaluate(req, trading_mode="paper")


async def _state_row(session_factory, account_id=1):
    async with session_factory() as s:
        return await s.scalar(
            select(RiskLossControlState).where(RiskLossControlState.account_id == account_id)
        )


# ------------------------------------------------------------ OFF


async def test_off_ignores_state_and_passes(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.OFF)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)  # would block in ENFORCE
    out = await _evaluate(seeded, _order())
    assert out.decision == PASS  # OFF never consults the state machine


async def test_off_fires_no_trigger_on_breach(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.OFF)
    await _breaching_state(seeded)
    await _evaluate(seeded, _order())  # legacy daily-loss still rejects; no loss-control write
    async with seeded() as s:
        n = await s.scalar(select(func.count()).select_from(RiskLossControlState))
    assert n == 0  # OFF performs no loss-control state writes


# ------------------------------------------------------------ SHADOW


async def test_shadow_integrity_state_still_passes(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)
    out = await _evaluate(seeded, _order())
    assert out.decision == PASS  # SHADOW is non-authoritative — the legacy ALLOW stands


async def test_shadow_breach_fires_trigger_persisting_transition(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _breaching_state(seeded)
    out = await _evaluate(seeded, _order())  # BUY is not a reduction → legacy rejects
    assert out.decision == REJECT
    row = await _state_row(seeded)  # but the SHADOW trigger advanced the state machine
    assert row is not None and row.state == C.STATE_REDUCTION_ONLY_DAILY_LOSS


async def test_shadow_exception_leaves_legacy_intact(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)

    class _BoomGate:
        def __init__(self, *a, **k): ...
        async def evaluate(self, **k):
            raise RuntimeError("gate boom")

    monkeypatch.setattr(engine_mod, "LossControlGate", _BoomGate)
    out = await _evaluate(seeded, _order())  # must not raise
    assert out.decision == PASS  # shadow failure ignored; legacy authoritative


async def test_cancelled_error_propagates(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_NORMAL)

    class _CancelGate:
        def __init__(self, *a, **k): ...
        async def evaluate(self, **k):
            raise asyncio.CancelledError

    monkeypatch.setattr(engine_mod, "LossControlGate", _CancelGate)
    with pytest.raises(asyncio.CancelledError):
        await _evaluate(seeded, _order())  # CancelledError is NOT swallowed


# ------------------------------------------------------------ ENFORCE


async def test_enforce_normal_preserves_valid_order(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_NORMAL)
    out = await _evaluate(seeded, _order())
    assert out.decision == PASS


async def test_enforce_integrity_stop_rejects_with_durable_provenance(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP, version=4)
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT
    assert "LOSS_CONTROL_STOP" in out.reason_codes or any(
        r == "LOSS_CONTROL_STOP" for r in [str(x) for x in out.reason_codes]
    )
    async with seeded() as s:
        row = await s.scalar(select(AuditLog).where(AuditLog.action == "LOSS_CONTROL_ENFORCED"))
    assert row is not None
    prov = json.loads(row.payload_json)
    assert prov["loss_control_state"] == "INTEGRITY_STOP"
    assert prov["loss_control_state_version"] == "4"
    assert prov["loss_control_mode"] == "ENFORCE"
    assert prov["loss_control_outcome"] == "INTEGRITY_STOP"
    assert "verified_reduction" in prov


async def test_enforce_missing_state_fails_closed(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)  # no state row at all
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT  # missing state → authoritative INTEGRITY_STOP


async def test_enforce_does_not_weaken_a_stricter_control(seeded, monkeypatch):
    # A SELL with no position is refused by the engine's own long-only guard (step 6), BEFORE the
    # loss-control gate. ENFORCE + NORMAL (which would ALLOW) must NOT rescue it.
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_NORMAL)
    out = await _evaluate(seeded, _order(side=OrderSide.SELL))
    assert out.decision == REJECT  # the stricter independent control stands


# ------------------------------------------------------------ no recovery / re-arm through PR4


async def test_no_recovery_state_reachable_through_pr4(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _breaching_state(seeded)
    await _evaluate(seeded, _order())
    row = await _state_row(seeded)
    # PR4 wires only daily-loss / breaker triggers — never a recovery/re-arm transition.
    assert row is None or row.state not in (
        C.STATE_RECOVERY_PREFLIGHT, C.STATE_RECOVERY_COOLDOWN
    )
