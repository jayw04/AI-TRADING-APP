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
from app.risk.reason_codes import ReasonCode
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


async def _set_limits(session_factory, **fields):
    async with session_factory() as s:
        rl = await s.get(RiskLimits, 1)
        for k, v in fields.items():
            setattr(rl, k, v)
        await s.commit()


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


# ============================================================ §Finding 1 — trigger commit failure


def _break_trigger_transition(monkeypatch):
    """Make the trigger's request_transition raise (simulating a persistence-write failure)."""
    import app.risk.loss_control.service as svc_mod

    async def _boom(self, **kwargs):
        raise RuntimeError("transition write failed")

    monkeypatch.setattr(svc_mod.LossControlService, "request_transition", _boom)


async def _audit_rows(session_factory, action):
    async with session_factory() as s:
        return (
            await s.execute(select(AuditLog).where(AuditLog.action == action))
        ).scalars().all()


def _spy_comparisons(monkeypatch) -> list:
    """Capture every emit_comparison call (structlog isn't reliably captured by caplog)."""
    seen: list = []
    real = engine_mod.emit_comparison

    def _spy(decision, **kwargs):
        seen.append(decision)
        return real(decision, **kwargs)

    monkeypatch.setattr(engine_mod, "emit_comparison", _spy)
    return seen


async def test_enforce_trigger_commit_failure_fails_closed(seeded, monkeypatch):
    # ENFORCE: the governing daily-loss transition fails to persist → the order is failed CLOSED
    # with LOSS_CONTROL_STOP + durable provenance (trigger identity + committed=False), NOT
    # evaluated against the stale NORMAL state (§Finding 1).
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _breaching_state(seeded)
    await _set_state(seeded, C.STATE_NORMAL)  # persisted state is (and stays) NORMAL
    _break_trigger_transition(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT
    assert any(str(r) == "LOSS_CONTROL_STOP" for r in out.reason_codes)
    rows = await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED")
    assert len(rows) == 1
    prov = json.loads(rows[0].payload_json)
    assert prov["trigger"] == "DAILY_LOSS_BREACH"
    assert prov["trigger_committed"] == "False"
    assert prov["error"] == "TRIGGER_COMMIT_FAILED"
    # State was NOT advanced past NORMAL by a failed write (fail-closed, not stale-evaluated).
    row = await _state_row(seeded)
    assert row is not None and row.state == C.STATE_NORMAL


async def test_shadow_trigger_commit_failure_keeps_legacy(seeded, monkeypatch):
    # SHADOW: the failure is evidence-only and cannot alter the decision. The legacy daily-loss gate
    # still rejects the BUY; the order still gets its SINGLE comparison at finalize (the guard emits
    # none, so the denominator stays exactly one per order); no LOSS_CONTROL_ENFORCED audit.
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _breaching_state(seeded)
    await _set_state(seeded, C.STATE_NORMAL)  # stays NORMAL (the trigger write fails)
    _break_trigger_transition(monkeypatch)
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT  # legacy daily-loss still rejects the non-reduction BUY
    assert [str(r) for r in out.reason_codes] == ["CIRCUIT_BREAKER"]  # legacy reason only
    assert await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED") == []  # no authoritative audit
    assert len(seen) == 1  # exactly one comparison for this order
    # The stale NORMAL state would have permitted; legacy denied → ADR_LOOSER, evidence only.
    assert seen[0].divergence == "ADR_LOOSER"


# ============================================================ §Finding 2 — provenance on matched denial


async def test_enforce_matched_daily_loss_denial_records_durable_provenance(seeded, monkeypatch):
    # Legacy daily-loss rejects a non-reduction BUY AND the ENFORCE state machine (REDUCTION_ONLY)
    # also denies it → a MATCH denial. The independent CIRCUIT_BREAKER reason is preserved AND
    # LOSS_CONTROL_STOP is appended, with a durable LOSS_CONTROL_ENFORCED audit (§Finding 2).
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _breaching_state(seeded)
    await _set_state(seeded, C.STATE_REDUCTION_ONLY_DAILY_LOSS)  # already locked (trigger no-ops)
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT
    reasons = [str(r) for r in out.reason_codes]
    assert "CIRCUIT_BREAKER" in reasons  # independent reason NOT discarded
    assert "LOSS_CONTROL_STOP" in reasons  # loss control's authoritative contribution recorded
    rows = await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED")
    assert len(rows) == 1
    prov = json.loads(rows[0].payload_json)
    assert prov["divergence"] == "MATCH"
    assert prov["loss_control_state"] == "REDUCTION_ONLY_DAILY_LOSS"


async def test_enforce_matched_breaker_denial_records_durable_provenance(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_REDUCTION_ONLY_BREAKER)
    async with seeded() as s:  # pre-trip the breaker so step 13 rejects
        acct = await s.get(Account, 1)
        acct.circuit_breaker_tripped_at = NOW
        await s.commit()
    out = await _evaluate(seeded, _order())
    assert out.decision == REJECT
    reasons = [str(r) for r in out.reason_codes]
    assert "CIRCUIT_BREAKER" in reasons and "LOSS_CONTROL_STOP" in reasons
    rows = await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED")
    assert len(rows) == 1


async def test_enforce_looser_preserves_legacy_reason_no_audit(seeded, monkeypatch):
    # ADR_LOOSER: legacy rejects but loss control PERMITS. ENFORCE must preserve the legacy reason,
    # NOT append LOSS_CONTROL_STOP, and NOT write a loss-control audit (loss control is not the
    # cause). Tested directly on _enforce_loss_control — the centralized authoritative-denial handler
    # — since a committed trigger makes this shape unreachable via the engine's reject sites.
    from app.risk.loss_control.gate import DIVERGENCE_ADR_LOOSER, LossControlDecision

    permits = LossControlDecision(
        mode="ENFORCE", authoritative=True, state="NORMAL", state_version=0, state_known=True,
        outcome="ALLOW", permits_order=True, verified_reduction=None, legacy_outcome="REFUSE",
        legacy_permits=False, divergence=DIVERGENCE_ADR_LOOSER, reason_code=None,
    )
    engine = RiskEngine(seeded)
    async with seeded() as s:
        final = await engine._enforce_loss_control(
            s, _order(), permits,
            legacy_reasons=[ReasonCode.CIRCUIT_BREAKER], legacy_rejecting=True,
        )
        await s.commit()
    assert final is None  # loss control does not change the (legacy) outcome
    assert await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED") == []  # no audit — not the cause


async def test_off_emits_no_comparison_evidence(seeded, monkeypatch):
    # OFF performs zero comparison events (the denominator is only SHADOW/ENFORCE).
    _set_mode(monkeypatch, LossControlMode.OFF)
    await _set_state(seeded, C.STATE_NORMAL)
    seen = _spy_comparisons(monkeypatch)
    await _evaluate(seeded, _order())
    assert seen == []


# ============================================================ comparison DENOMINATOR (all applicable paths)


async def test_denylist_reject_before_step9_emits_comparison(seeded, monkeypatch):
    # A deny-list rejection (step 5) is BEFORE the daily-loss/breaker gates, yet still applicable —
    # it must emit exactly one comparison so the denominator includes it.
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_NORMAL)
    await _set_limits(seeded, denied_symbols=["AAPL"])
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert [str(r) for r in out.reason_codes] == ["SYMBOL_DENIED"]  # legacy reason unchanged (SHADOW)
    assert len(seen) == 1 and seen[0].legacy_outcome == "REFUSE"


async def test_position_cap_reject_emits_exactly_one_comparison(seeded, monkeypatch):
    # An exposure/position-cap rejection (step 7) is applicable. ENFORCE + NORMAL permits, so it's
    # ADR_LOOSER: the independent cap rejection stands, no LOSS_CONTROL_STOP, no audit, one comparison.
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_NORMAL)
    await _set_limits(seeded, max_position_qty=0)  # any BUY exceeds
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert [str(r) for r in out.reason_codes] == ["POSITION_CAP_QTY"]  # not weakened, no LOSS_CONTROL_STOP
    assert len(seen) == 1 and seen[0].divergence == "ADR_LOOSER"
    assert await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED") == []  # loss control not the cause


async def test_rate_limit_reject_emits_comparison(seeded, monkeypatch):
    # An intermediate rate-limit rejection (step 10) is applicable → one comparison.
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_NORMAL)
    await _set_limits(seeded, max_orders_per_minute=0)  # count 0 >= 0 → reject
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert [str(r) for r in out.reason_codes] == ["RATE_LIMIT"]
    assert len(seen) == 1


async def test_enforce_matched_denial_at_early_gate_records_provenance(seeded, monkeypatch):
    # MATCH at an early applicable gate: deny-list rejects AND the state machine (INTEGRITY_STOP)
    # also denies → LOSS_CONTROL_STOP appended + durable audit; independent SYMBOL_DENIED preserved.
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)
    await _set_limits(seeded, denied_symbols=["AAPL"])
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    reasons = [str(r) for r in out.reason_codes]
    assert "SYMBOL_DENIED" in reasons and "LOSS_CONTROL_STOP" in reasons
    assert len(seen) == 1 and seen[0].divergence == "MATCH"
    assert len(await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED")) == 1


async def test_pass_emits_exactly_one_comparison(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.SHADOW)
    await _set_state(seeded, C.STATE_NORMAL)
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order())
    assert out.decision == PASS
    assert len(seen) == 1 and seen[0].divergence == "MATCH"  # both allow


# ------------------------------------------------------------ non-applicable preprocessing → no comparison


async def test_malformed_request_is_non_applicable_no_comparison(seeded, monkeypatch):
    # Malformed request (qty 0) — no meaningful proposed action → non-applicable preprocessing.
    # Even in ENFORCE with a locked state, it persists directly and emits NO comparison.
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)
    seen = _spy_comparisons(monkeypatch)
    out = await _evaluate(seeded, _order(qty="0"))
    assert [str(r) for r in out.reason_codes] == ["INVALID_INPUT"]
    assert seen == []  # non-applicable → not routed through the gate
    assert await _audit_rows(seeded, "LOSS_CONTROL_ENFORCED") == []


async def test_unresolved_symbol_is_non_applicable_no_comparison(seeded, monkeypatch):
    _set_mode(monkeypatch, LossControlMode.ENFORCE)
    await _set_state(seeded, C.STATE_INTEGRITY_STOP)
    seen = _spy_comparisons(monkeypatch)
    req = OrderRequest(user_id=1, account_id=1, symbol_ticker="ZZZZ", side=OrderSide.BUY,
                       qty=D("1"), type=OrderType.MARKET, tif=TimeInForce.DAY,
                       source_type=OrderSourceType.MANUAL)
    out = await _evaluate(seeded, req)
    assert [str(r) for r in out.reason_codes] == ["SYMBOL_DENIED"]  # unresolved symbol (step 3)
    assert seen == []  # no meaningful proposed action → no comparison
