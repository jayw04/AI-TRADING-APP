"""Replay service tests (P11 §4, ADR 0021).

Covers the pure verifiers (breaker trip + reconciliation discrepancy), the registry
dispatch (SKIPPED / ERROR), the determinism invariant, the persisted-run + alert path
(REPLAY_MISMATCH audit + replay_runs row + metrics), and the coverage ratio.

Replay is read-only: a test asserts it never imports the order path.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.models.audit_log import AuditLog
from app.db.models.replay_run import ReplayRun
from app.services import replay as rp
from app.services.replay import (
    ALGORITHM_VERSION,
    CAPABILITY,
    REPLAY_REGISTRY,
    BreakerTripVerifier,
    ReconciliationDiscrepancyVerifier,
    RegistryInconsistencyError,
    Verdict,
    coverage_ratio,
    replay_audit_row,
    run_replay,
    validate_registry,
)


def _trip_payload(realized="-300", unrealized="-250", net="-550", limit="500") -> dict:
    return {
        "realized_pnl_today": realized, "unrealized_pnl_now": unrealized,
        "net_pnl": net, "max_daily_loss": limit, "reason": "daily_loss_exceeded",
        "halted_strategy_ids": [1],
    }


async def _add_audit(session_factory, action: str, payload: dict) -> int:
    async with session_factory() as session:
        row = AuditLogger.write(
            session, actor_type=AuditActorType.SYSTEM, actor_id="test",
            action=action, target_type="account", target_id=1, payload=payload,
        )
        await session.commit()
        return row.id


# ---- BreakerTripVerifier (pure) -----------------------------------------------

def test_breaker_trip_match() -> None:
    v = BreakerTripVerifier().replay(1, _trip_payload())  # -300 + -250 = -550 <= -500
    assert v.verdict is Verdict.MATCH


def test_breaker_trip_mismatch_rule_not_satisfied() -> None:
    # net reproduces (-100) but -100 is NOT <= -500 → the recorded trip is unjustified.
    v = BreakerTripVerifier().replay(1, _trip_payload("-60", "-40", "-100", "500"))
    assert v.verdict is Verdict.MISMATCH
    assert "does not satisfy" in v.note


def test_breaker_trip_mismatch_net_does_not_reproduce() -> None:
    # realized+unrealized = -550 but recorded net says -999 → inputs inconsistent.
    v = BreakerTripVerifier().replay(1, _trip_payload("-300", "-250", "-999", "500"))
    assert v.verdict is Verdict.MISMATCH
    assert "net_pnl != recorded" in v.note


# ---- ReconciliationDiscrepancyVerifier (pure) ---------------------------------

@pytest.mark.parametrize(
    "local,broker,kind",
    [("10", None, "missing_broker"), (None, "10", "missing_local"), ("10", "7", "qty_mismatch")],
)
def test_reconciliation_match(local, broker, kind) -> None:
    payload = {"domain": "position", "kind": kind, "local": local, "broker": broker}
    v = ReconciliationDiscrepancyVerifier().replay(1, payload)
    assert v.verdict is Verdict.MATCH


def test_reconciliation_mismatch() -> None:
    # recorded says qty_mismatch but broker is None → recompute = missing_broker.
    payload = {"domain": "position", "kind": "qty_mismatch", "local": "10", "broker": None}
    v = ReconciliationDiscrepancyVerifier().replay(1, payload)
    assert v.verdict is Verdict.MISMATCH


def test_reconciliation_mismatch_equal_quantities() -> None:
    # Both present and EQUAL → recompute kind=None (no discrepancy should exist) → MISMATCH.
    payload = {"domain": "position", "kind": "qty_mismatch", "local": "10", "broker": "10"}
    v = ReconciliationDiscrepancyVerifier().replay(1, payload)
    assert v.verdict is Verdict.MISMATCH
    assert v.recomputed["kind"] is None


def test_reconciliation_intent_domain_skipped() -> None:
    payload = {"domain": "intent", "kind": "gross_drift", "local": None, "broker": None}
    v = ReconciliationDiscrepancyVerifier().replay(1, payload)
    assert v.verdict is Verdict.SKIPPED


# ---- registry dispatch --------------------------------------------------------

def test_replay_audit_row_unknown_action_skipped() -> None:
    row = AuditLog(id=5, ts=datetime.now(UTC), action="ORDER_SUBMITTED", payload_json="{}")
    assert replay_audit_row(row).verdict is Verdict.SKIPPED


def test_replay_audit_row_malformed_payload_errors() -> None:
    # CIRCUIT_BREAKER_TRIPPED verifier needs keys; an empty payload raises KeyError → ERROR.
    row = AuditLog(id=6, ts=datetime.now(UTC),
                   action=AuditAction.CIRCUIT_BREAKER_TRIPPED.value, payload_json="{}")
    v = replay_audit_row(row)
    assert v.verdict is Verdict.ERROR


def test_determinism_same_payload_same_verdict() -> None:
    row = AuditLog(id=7, ts=datetime.now(UTC),
                   action=AuditAction.CIRCUIT_BREAKER_TRIPPED.value,
                   payload_json=json.dumps(_trip_payload()))
    assert replay_audit_row(row).verdict is replay_audit_row(row).verdict is Verdict.MATCH


def test_coverage_ratio() -> None:
    # 2 supported of 4 catalogued.
    assert coverage_ratio() == pytest.approx(0.5)
    assert set(CAPABILITY.values()) <= {"supported", "unsupported", "unreplayable"}


# ---- run_replay (persist + alert + metrics) -----------------------------------

async def test_run_replay_clean(session_factory) -> None:
    await _add_audit(session_factory, AuditAction.CIRCUIT_BREAKER_TRIPPED.value, _trip_payload())
    async with session_factory() as session:
        run = await run_replay(session)
    assert run.n_checked == 1
    assert run.n_matched == 1
    assert run.n_mismatched == 0
    assert run.algorithm_version == ALGORITHM_VERSION
    assert run.detail_json is None
    # MATCH → no REPLAY_MISMATCH audit row.
    async with session_factory() as session:
        mm = (await session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.REPLAY_MISMATCH.value)
        )).scalars().all()
        assert mm == []


async def test_run_replay_mismatch_alerts(session_factory) -> None:
    await _add_audit(
        session_factory, AuditAction.CIRCUIT_BREAKER_TRIPPED.value,
        _trip_payload("-60", "-40", "-100", "500"),  # unjustified trip
    )
    async with session_factory() as session:
        run = await run_replay(session)
    assert run.n_mismatched == 1
    assert run.detail_json is not None
    async with session_factory() as session:
        mm = (await session.execute(
            select(AuditLog).where(AuditLog.action == AuditAction.REPLAY_MISMATCH.value)
        )).scalars().all()
        assert len(mm) == 1
        assert mm[0].target_type == "audit_log"
        runs = (await session.execute(select(ReplayRun))).scalars().all()
        assert len(runs) == 1


async def test_run_replay_window_bounds(session_factory) -> None:
    # A recon discrepancy logged now: included in a window around now, excluded by a
    # future `since` (the audit_log is append-only, so we filter by window, not by mutating ts).
    await _add_audit(
        session_factory, AuditAction.RECONCILIATION_DISCREPANCY.value,
        {"domain": "position", "kind": "qty_mismatch", "local": "10", "broker": "7"},
    )
    now = datetime.now(UTC)
    async with session_factory() as session:
        inside = await run_replay(session, since=now - timedelta(days=1), until=now + timedelta(days=1))
    assert inside.n_checked == 1 and inside.n_matched == 1
    async with session_factory() as session:
        outside = await run_replay(session, since=now + timedelta(days=1))
    assert outside.n_checked == 0


async def test_run_replay_limit(session_factory) -> None:
    for _ in range(3):
        await _add_audit(session_factory, AuditAction.CIRCUIT_BREAKER_TRIPPED.value, _trip_payload())
    async with session_factory() as session:
        run = await run_replay(session, limit=2)
    assert run.n_checked == 2


async def test_run_replay_empty_is_consistent(session_factory) -> None:
    async with session_factory() as session:
        run = await run_replay(session)
    assert run.n_checked == 0
    assert run.n_mismatched == 0


async def test_run_daily_replay_best_effort(session_factory) -> None:
    await _add_audit(session_factory, AuditAction.CIRCUIT_BREAKER_TRIPPED.value, _trip_payload())
    # Should not raise.
    await rp.run_daily_replay(session_factory, window_hours=48)
    async with session_factory() as session:
        runs = (await session.execute(select(ReplayRun))).scalars().all()
        assert len(runs) == 1


async def test_run_daily_replay_logs_mismatch(session_factory) -> None:
    await _add_audit(
        session_factory, AuditAction.CIRCUIT_BREAKER_TRIPPED.value,
        _trip_payload("-60", "-40", "-100", "500"),  # unjustified → mismatch path
    )
    await rp.run_daily_replay(session_factory, window_hours=48)
    async with session_factory() as session:
        runs = (await session.execute(select(ReplayRun))).scalars().all()
        assert len(runs) == 1 and runs[0].n_mismatched == 1


async def test_run_daily_replay_swallows_failure() -> None:
    def _bad_factory():
        raise RuntimeError("db gone")
    await rp.run_daily_replay(_bad_factory)  # logs + returns, no raise


# ---- registry integrity + invariants ------------------------------------------

def test_registry_keys_are_real_audit_actions() -> None:
    valid = {a.value for a in AuditAction}
    for key in REPLAY_REGISTRY:
        assert key in valid, f"REPLAY_REGISTRY key {key} is not an AuditAction"


def test_validate_registry_passes_on_shipped_state() -> None:
    # The shipped registry + catalog must be internally consistent (called at boot).
    validate_registry()


def test_validate_registry_detects_supported_without_verifier(monkeypatch) -> None:
    # A capability marked supported but with no wired verifier must fail fast.
    patched = dict(CAPABILITY)
    patched["SOME_NEW_DECISION"] = "supported"
    monkeypatch.setattr(rp, "CAPABILITY", patched)
    with pytest.raises(RegistryInconsistencyError, match="supported_without_verifier"):
        validate_registry()


def test_validate_registry_detects_uncatalogued_verifier(monkeypatch) -> None:
    # A wired verifier not catalogued supported must fail fast.
    patched = dict(REPLAY_REGISTRY)
    patched["ROGUE_ACTION"] = BreakerTripVerifier()
    monkeypatch.setattr(rp, "REPLAY_REGISTRY", patched)
    with pytest.raises(RegistryInconsistencyError, match="registered_not_supported"):
        validate_registry()


def test_replay_never_touches_order_path() -> None:
    import inspect
    src = inspect.getsource(rp)
    assert "OrderRouter" not in src
    assert "order_router" not in src
    assert ".submit(" not in src
