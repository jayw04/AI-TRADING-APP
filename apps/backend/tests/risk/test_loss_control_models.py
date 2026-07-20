"""ADR 0043 PR 1 — the loss-control persistence foundation.

Pins the five new tables (round-trip + the constraints that make them safe: one immutable
baseline per session, one state row per account, monotonic per-account event sequence), the
constants vocabulary, and the migration itself — chain integrity plus a real up/down run against a
temp DB, because the unit suite builds schema via ``Base.metadata.create_all`` and would otherwise
never exercise the migration.
"""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.db.models.account import Account, AccountMode
from app.db.models.risk_control_event import RiskControlEvent
from app.db.models.risk_loss_control_state import RiskLossControlState
from app.db.models.risk_recovery_preflight import RiskRecoveryPreflight
from app.db.models.risk_recovery_preflight_check import RiskRecoveryPreflightCheck
from app.db.models.risk_session_baseline import (
    BASELINE_SOURCE_RECONCILED_OPEN,
    BASELINE_STATUS_ACTIVE,
    RiskSessionBaseline,
)
from app.db.models.user import User
from app.risk.loss_control import constants as C

D = Decimal
BACKEND = Path(__file__).resolve().parents[2]
NEW_TABLES = (
    "risk_session_baselines",
    "risk_loss_control_state",
    "risk_control_events",
    "risk_recovery_preflights",
    "risk_recovery_preflight_checks",
)


def _now() -> datetime:
    return datetime.now(UTC)


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="jay@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        await s.commit()
    return 1


# --------------------------------------------------------------------- round-trips


async def test_session_baseline_roundtrip(session_factory, acct):
    async with session_factory() as s:
        s.add(
            RiskSessionBaseline(
                account_id=acct,
                market_session_date="2026-07-20",
                baseline_equity=D("100000.0000"),
                baseline_source=BASELINE_SOURCE_RECONCILED_OPEN,
                captured_at=_now(),
            )
        )
        await s.commit()
    async with session_factory() as s:
        row = (await s.execute(select(RiskSessionBaseline))).scalar_one()
    assert row.baseline_equity == D("100000.0000")
    assert row.session_timezone == "America/New_York"  # server_default applied
    assert row.status == BASELINE_STATUS_ACTIVE
    assert row.created_by == "SYSTEM"
    assert row.superseded_by is None


async def test_loss_control_state_roundtrip(session_factory, acct):
    async with session_factory() as s:
        s.add(
            RiskLossControlState(
                account_id=acct,
                state=C.STATE_NORMAL,
                control_version=C.LOSS_CONTROL_STATE_VERSION,
                updated_at=_now(),
            )
        )
        await s.commit()
    async with session_factory() as s:
        row = (await s.execute(select(RiskLossControlState))).scalar_one()
    assert row.state == C.STATE_NORMAL
    assert row.state_version == 0  # server_default
    assert row.last_sequence_no == 0
    assert row.control_version == C.LOSS_CONTROL_STATE_VERSION


async def test_control_event_roundtrip(session_factory, acct):
    async with session_factory() as s:
        s.add(
            RiskControlEvent(
                account_id=acct,
                session_date="2026-07-20",
                sequence_no=1,
                control_type="DAILY_LOSS",
                from_state=C.STATE_NORMAL,
                to_state=C.STATE_REDUCTION_ONLY_DAILY_LOSS,
                trip_type=C.TRIP_TYPE_DAILY_LOSS,
                trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS,
                trip_evidence_status=C.TRIP_EVIDENCE_CONFIRMED,
                trigger_value=D("-3200.00"),
                threshold_value=D("-3000.00"),
                initiator_type="SYSTEM",
                control_version=C.LOSS_CONTROL_STATE_VERSION,
                created_at=_now(),
            )
        )
        await s.commit()
    async with session_factory() as s:
        row = (await s.execute(select(RiskControlEvent))).scalar_one()
    assert row.to_state == C.STATE_REDUCTION_ONLY_DAILY_LOSS
    assert row.trip_cause == C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS
    assert row.baseline_id is None
    assert row.decision_ledger_id is None


async def test_recovery_preflight_and_checks_roundtrip(session_factory, acct):
    async with session_factory() as s:
        pf = RiskRecoveryPreflight(
            account_id=acct,
            requested_transition="INTEGRITY_STOP->RECOVERY_PREFLIGHT",
            expected_state_version=3,
            trip_type=C.TRIP_TYPE_CIRCUIT_BREAKER,
            trip_cause=C.TRIP_CAUSE_REALIZED_AND_MARK_TO_MARKET_LOSS,
            authority_class=C.AUTHORITY_HUMAN_REQUIRED,
            result=C.PREFLIGHT_PASS,
            initiator_type="USER",
            initiator_id="3",
            control_version=C.LOSS_CONTROL_STATE_VERSION,
            created_at=_now(),
        )
        s.add(pf)
        await s.flush()
        s.add(
            RiskRecoveryPreflightCheck(
                preflight_id=pf.id,
                check_name="positions_reconcile",
                status=C.CHECK_PASS,
                evidence='{"broker": 19, "ledger": 19}',
                created_at=_now(),
            )
        )
        s.add(
            RiskRecoveryPreflightCheck(
                preflight_id=pf.id,
                check_name="baseline_present",
                status=C.CHECK_PASS,
                created_at=_now(),
            )
        )
        await s.commit()
    async with session_factory() as s:
        checks = (
            (await s.execute(select(RiskRecoveryPreflightCheck))).scalars().all()
        )
    assert {c.check_name for c in checks} == {"positions_reconcile", "baseline_present"}


# --------------------------------------------------------------------- constraints


async def test_baseline_unique_per_account_session(session_factory, acct):
    async with session_factory() as s:
        s.add(
            RiskSessionBaseline(
                account_id=acct, market_session_date="2026-07-20",
                baseline_equity=D("100000"), baseline_source=BASELINE_SOURCE_RECONCILED_OPEN,
                captured_at=_now(),
            )
        )
        await s.commit()
    # A second baseline for the SAME (account, session date) is refused — immutability guard.
    async with session_factory() as s:
        s.add(
            RiskSessionBaseline(
                account_id=acct, market_session_date="2026-07-20",
                baseline_equity=D("95000"), baseline_source=BASELINE_SOURCE_RECONCILED_OPEN,
                captured_at=_now(),
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_loss_control_state_unique_per_account(session_factory, acct):
    async with session_factory() as s:
        s.add(RiskLossControlState(account_id=acct, control_version=1, updated_at=_now()))
        await s.commit()
    async with session_factory() as s:
        s.add(RiskLossControlState(account_id=acct, control_version=1, updated_at=_now()))
        with pytest.raises(IntegrityError):
            await s.commit()


async def test_control_event_sequence_unique_per_account(session_factory, acct):
    async with session_factory() as s:
        s.add(
            RiskControlEvent(
                account_id=acct, sequence_no=1, control_type="DAILY_LOSS",
                to_state=C.STATE_REDUCTION_ONLY_DAILY_LOSS, initiator_type="SYSTEM",
                control_version=1, created_at=_now(),
            )
        )
        s.add(
            RiskControlEvent(
                account_id=acct, sequence_no=2, control_type="RECOVERY",
                to_state=C.STATE_RECOVERY_PREFLIGHT, initiator_type="USER",
                control_version=1, created_at=_now(),
            )
        )
        await s.commit()  # distinct sequence numbers are fine
    # Re-using a sequence number for the same account is refused (monotonic-per-account guard).
    async with session_factory() as s:
        s.add(
            RiskControlEvent(
                account_id=acct, sequence_no=1, control_type="BREAKER",
                to_state=C.STATE_REDUCTION_ONLY_BREAKER, initiator_type="SYSTEM",
                control_version=1, created_at=_now(),
            )
        )
        with pytest.raises(IntegrityError):
            await s.commit()


# --------------------------------------------------------------------- constants vocabulary


def test_constants_vocabulary_is_well_formed():
    assert C.LOSS_CONTROL_STATE_VERSION == 1
    assert len(C.ALL_STATES) == 6
    # The precedence ladder is the normative ordering, most-restrictive first.
    assert C.PRECEDENCE_LADDER == (
        C.OUTCOME_INTEGRITY_STOP,
        C.OUTCOME_ALLOW_REDUCTION_ONLY,
        C.OUTCOME_REFUSE,
        C.OUTCOME_ALLOW,
    )
    # Concentration is deliberately NOT a loss-control trip cause (scope boundary).
    assert not any("CONCENTRATION" in c for c in C.ALL_TRIP_CAUSES)
    assert C.TRIP_TYPE_MANUAL_HALT in C.ALL_TRIP_TYPES  # MANUAL is a type, not a cause
    assert C.PREFLIGHT_PASS != C.CHECK_PASS  # overall verdict vs per-check status differ


# --------------------------------------------------------------------- the migration


def _alembic_config():
    from alembic.config import Config

    cfg = Config(str(BACKEND / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    return cfg


def test_migration_chain_integrity():
    """Chain integrity, no DB: exactly one head, and PR1's revision chains onto the prior head.

    (PR1's revision is no longer the head once later increments add migrations — the single-head
    invariant is enforced generally by scripts/check_alembic_single_head.py.)
    """
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    assert len(script.get_heads()) == 1  # no divergent branches / duplicate heads
    rev = script.get_revision("b6d2f4a9c1e7")
    assert rev.down_revision == "c3f8a1e7d24b"


def test_migration_upgrade_then_downgrade(tmp_path, monkeypatch):
    """Run the real chain to head against a temp DB: the five tables appear on upgrade and are
    gone after downgrade -1. Sync test (no running loop) so env.py's asyncio.run works."""
    from alembic import command
    from app.config import get_settings

    db_file = tmp_path / "adr0043_mig.db"
    monkeypatch.setenv("WORKBENCH_DB_URL", f"sqlite+aiosqlite:///{db_file}")
    get_settings.cache_clear()
    cfg = _alembic_config()
    try:
        command.upgrade(cfg, "head")
        assert _tables(db_file) >= set(NEW_TABLES)

        command.downgrade(cfg, "c3f8a1e7d24b")
        assert _tables(db_file).isdisjoint(NEW_TABLES)
    finally:
        get_settings.cache_clear()


def _tables(db_file: Path) -> set[str]:
    conn = sqlite3.connect(str(db_file))
    try:
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    finally:
        conn.close()
    return {r[0] for r in rows}
