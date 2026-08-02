"""ADR-0043 canary Model A — Start A capture, binding, observation, consumer fail-closed."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.audit_log import AuditLog
from app.db.models.risk_canary_session_baseline import RiskCanarySessionBaseline
from app.db.models.risk_limits import RiskLimits
from app.db.models.user import User
from app.risk.circuit_breaker import CircuitBreakerError, CircuitBreakerService
from app.risk.engine import RiskEngine
from app.risk.loss_control.daily_loss_observation import (
    ObservationStatus,
    SurfaceAction,
    map_surface_action,
    observe_model_a_daily_loss,
)
from app.risk.loss_control.start_a_baseline import (
    StartACaptureRefused,
    capture_model_a_baseline,
    in_opening_window,
    parse_broker_equity,
    seal_start_a_authorization,
)

ET = ZoneInfo("America/New_York")
D = Decimal
START_A_ID = "ADR0043-LIVE-CANARY-PHASE0-START-001"
FREEZE_ID = "ADR0043-LIVE-CANARY-FREEZE-001"
DESIGN = "ADR0043-CANARY-BASELINE-DESIGN-001-v0.2.1"
CONFIG = "b" * 64
SESSION = "2026-07-31"
NOW = datetime(2026, 7, 31, 15, 0, tzinfo=UTC)


def _state(equity="100000", last_equity="100000", day_change="0") -> AccountState:
    return AccountState(
        account_id=1,
        cash=D("1"),
        equity=D(equity),
        last_equity=D(last_equity),
        buying_power=D("1"),
        portfolio_value=D(equity),
        daytrade_count=0,
        day_change=D(day_change),
        day_change_pct=D("0"),
        status="ACTIVE",
        pattern_day_trader=False,
        trading_blocked=False,
        account_blocked=False,
        updated_at=NOW,
    )


def _limits_row(max_daily_loss="500") -> RiskLimits:
    return RiskLimits(
        user_id=1,
        broker_mode=AccountMode.paper,
        scope_type=RiskScopeType.GLOBAL,
        max_daily_loss=D(max_daily_loss),
        created_at=NOW,
        updated_at=NOW,
    )


def _open_et(hour=9, minute=32, day=31) -> datetime:
    return datetime(2026, 7, day, hour, minute, 0, tzinfo=ET).astimezone(UTC)


def _payload(equity="100000.125", account_id="PA34USW0Q8UO", **extra):
    return {"equity": equity, "cash": "50000", "id": account_id, **extra}


async def _seal(session, account_id=1, **over):
    kwargs = dict(
        start_a_id=START_A_ID,
        freeze_id=FREEZE_ID,
        freeze_body_sha256="a" * 64,
        broker_account_id="PA34USW0Q8UO",
        workbench_account_id=account_id,
        configuration_digest=CONFIG,
        image_digest="sha256:deadbeef",
        commit_sha="c" * 40,
        authorized_session_date=SESSION,
        design_version=DESIGN,
        applicable_daily_loss_limit=D("500"),
        authorization_status="EFFECTIVE",
    )
    kwargs.update(over)
    row = await seal_start_a_authorization(session, **kwargs)
    await session.commit()
    return row


@pytest.fixture
async def acct(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="canary@test"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="C"))
        await s.commit()
    return 1


def test_opening_window_bounds():
    assert in_opening_window(_open_et(9, 30))
    assert in_opening_window(_open_et(9, 34))
    assert not in_opening_window(datetime(2026, 7, 31, 9, 35, 0, tzinfo=ET).astimezone(UTC))
    assert not in_opening_window(datetime(2026, 7, 31, 9, 29, 59, tzinfo=ET).astimezone(UTC))
    assert not in_opening_window(datetime(2026, 7, 31, 11, 30, 0, tzinfo=ET).astimezone(UTC))


def test_parse_equity_rejects_scientific_and_neg_zero():
    raw, exact = parse_broker_equity("100000.12")
    assert raw == "100000.12" and exact == D("100000.12")
    with pytest.raises(StartACaptureRefused) as e:
        parse_broker_equity("1e5")
    assert e.value.reason_code == "EQUITY_SCIENTIFIC_NOTATION"
    with pytest.raises(StartACaptureRefused) as e2:
        parse_broker_equity("-0")
    assert e2.value.reason_code == "EQUITY_NEGATIVE_ZERO"


def test_policy_mapper_surfaces():
    assert map_surface_action(ObservationStatus.AVAILABLE, surface="new_risk") == SurfaceAction.EVALUATE
    assert map_surface_action(ObservationStatus.UNAVAILABLE, surface="phase0") == SurfaceAction.REFUSE
    assert map_surface_action(ObservationStatus.CONFLICT, surface="recovery") == SurfaceAction.FAIL
    assert (
        map_surface_action(ObservationStatus.INVALID, surface="verified_reduction")
        == SurfaceAction.PERMIT_REDUCTION_ADR0042_ONLY
    )
    assert (
        map_surface_action(ObservationStatus.UNAVAILABLE, surface="new_risk") == SurfaceAction.REJECT
    )


async def test_capture_inside_window_and_reuse(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    payload = _payload()
    async with session_factory() as s:
        r1 = await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=payload, now=_open_et(9, 31)
        )
        assert r1.reused is False
        assert r1.baseline_equity == D("100000.125")
    async with session_factory() as s:
        r2 = await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=payload, now=_open_et(9, 32)
        )
        assert r2.reused is True
        assert r2.baseline_id == r1.baseline_id


async def test_capture_outside_window_refused(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(11, 0),
            )
        assert e.value.reason_code == "OUTSIDE_OPENING_WINDOW"


async def test_start_a_not_effective_refused(session_factory, acct):
    async with session_factory() as s:
        await _seal(s, authorization_status="DRAFT", start_a_id="DRAFT-001")
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id="DRAFT-001",
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(9, 31),
            )
        assert e.value.reason_code == "START_A_NOT_EFFECTIVE"


async def test_fabricated_start_a_id_cannot_authorize(session_factory, acct):
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id="CALLER-FABRICATED-EFFECTIVE",
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(9, 31),
            )
        assert e.value.reason_code == "START_A_NOT_FOUND"


async def test_conflict_on_hash_mismatch(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(equity="100000"), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100001"),
                now=_open_et(9, 32),
            )
        assert e.value.reason_code == "BASELINE_IDENTITY_CONFLICT"


async def test_wrong_payload_broker_id_refuses(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100000", account_id="OTHER"),
                now=_open_et(9, 31),
            )
        assert e.value.reason_code == "BROKER_PAYLOAD_ACCOUNT_ID_MISMATCH"


async def test_broker_timestamp_other_date_refuses(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    other_day = datetime(2026, 7, 30, 9, 31, 0, tzinfo=ET).astimezone(UTC)
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(
                    equity="100000",
                    timestamp=other_day.isoformat().replace("+00:00", "Z"),
                ),
                now=_open_et(9, 31),
            )
        assert e.value.reason_code == "SESSION_DATE_MISMATCH"


async def test_audit_success_and_refusal_durable(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused):
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(11, 0),
            )
    async with session_factory() as s:
        rows = (
            await s.scalars(
                select(AuditLog).where(AuditLog.action == "CANARY_MODEL_A_BASELINE_CAPTURE")
            )
        ).all()
    outcomes = {__import__("json").loads(r.payload_json)["outcome"] for r in rows}
    assert "CAPTURED" in outcomes
    assert "REFUSED" in outcomes


async def test_capture_refuses_dirty_session(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        s.add(_state(equity="1", last_equity="1", day_change="0"))
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(9, 31),
            )
        assert e.value.reason_code == "SESSION_NOT_CLEAN"


async def test_observe_model_a_available(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(equity="100000.5"), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("99000.5"), session_date=SESSION
        )
    assert obs is not None
    assert obs.status == ObservationStatus.AVAILABLE
    assert obs.daily_pnl == D("-1000.0")
    assert obs.canary_model_a is True
    assert obs.binding is not None


async def test_observe_none_without_binding(session_factory, acct):
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("100000"), session_date=SESSION
        )
    assert obs is None


async def test_effective_binding_missing_baseline_unavailable(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("100000"), session_date=SESSION
        )
    assert obs is not None
    assert obs.status == ObservationStatus.UNAVAILABLE
    assert obs.reason_code == "MODEL_A_BASELINE_MISSING"
    assert map_surface_action(obs.status, surface="new_risk") == SurfaceAction.REJECT


async def test_prior_freeze_baseline_not_selected(session_factory, acct):
    async with session_factory() as s:
        await _seal(s, freeze_id="PRIOR-FREEZE", start_a_id="PRIOR-START")
    async with session_factory() as s:
        await capture_model_a_baseline(
            s,
            start_a_id="PRIOR-START",
            broker_account_payload=_payload(equity="111111"),
            now=_open_et(9, 31),
        )
    async with session_factory() as s:
        from app.db.models.risk_canary_start_a_authorization import RiskCanaryStartAAuthorization

        prior = await s.scalar(
            select(RiskCanaryStartAAuthorization).where(
                RiskCanaryStartAAuthorization.start_a_id == "PRIOR-START"
            )
        )
        prior.authorization_status = "REVOKED"
        await s.commit()
    async with session_factory() as s:
        await _seal(
            s,
            start_a_id=START_A_ID,
            freeze_id=FREEZE_ID,
        )
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("100000"), session_date=SESSION
        )
    assert obs.status == ObservationStatus.UNAVAILABLE
    assert obs.reason_code == "MODEL_A_BASELINE_MISSING"
    assert obs.binding is not None
    assert obs.binding.freeze_id == FREEZE_ID


async def test_wrong_config_digest_refuses_selection(session_factory, acct):
    async with session_factory() as s:
        await _seal(s, configuration_digest="d" * 64, start_a_id="CFG-A")
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id="CFG-A", broker_account_payload=_payload(equity="100000"), now=_open_et(9, 31)
        )
    # Revoke prior auth; seal a new EFFECTIVE with different config — prior baseline must not bind.
    async with session_factory() as s:
        from app.db.models.risk_canary_start_a_authorization import RiskCanaryStartAAuthorization

        row = await s.scalar(
            select(RiskCanaryStartAAuthorization).where(
                RiskCanaryStartAAuthorization.start_a_id == "CFG-A"
            )
        )
        row.authorization_status = "REVOKED"
        await s.commit()
    async with session_factory() as s:
        await _seal(s, configuration_digest=CONFIG, start_a_id=START_A_ID)
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("99000"), session_date=SESSION
        )
    assert obs.status == ObservationStatus.UNAVAILABLE
    assert obs.reason_code == "MODEL_A_BASELINE_MISSING"


async def test_dry_run_does_not_persist(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        with pytest.raises(StartACaptureRefused) as e:
            await capture_model_a_baseline(
                s,
                start_a_id=START_A_ID,
                broker_account_payload=_payload(equity="100000"),
                now=_open_et(9, 31),
                dry_run=True,
            )
        assert e.value.reason_code == "DRY_RUN_OK"
    async with session_factory() as s:
        obs = await observe_model_a_daily_loss(
            s, 1, current_equity=D("100000"), session_date=SESSION
        )
        assert obs is not None
        assert obs.status == ObservationStatus.UNAVAILABLE  # binding exists, no baseline


async def test_breaker_unavailable_not_zero_pnl_pass(session_factory, acct, monkeypatch):
    import app.risk.circuit_breaker as cb_mod

    monkeypatch.setattr(cb_mod, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
        s.add(_limits_row())
        s.add(_state())
        await s.commit()
    async with session_factory() as s:
        dp, basis, _br, model_a = await CircuitBreakerService(session=s)._compute_daily_pnl(
            1, realized=D("0"), unrealized=D("0"), max_loss=D("500")
        )
        assert dp is None
        assert basis == "MODEL_A_UNAVAILABLE"
        assert model_a is not None and model_a.status == ObservationStatus.UNAVAILABLE
        with pytest.raises(CircuitBreakerError) as e:
            await CircuitBreakerService(session=s).check(1)
        assert e.value.trip_recorded is False
        acct_row = await s.get(Account, 1)
        assert acct_row.circuit_breaker_tripped_at is None


async def test_engine_step9_unavailable_rejects_new_risk_signal(session_factory, acct, monkeypatch):
    import app.risk.engine as engine_mod

    monkeypatch.setattr(engine_mod, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
        s.add(_limits_row())
        await s.commit()
    engine = RiskEngine(session_factory)
    state = _state(equity="100000", last_equity="99999", day_change="1")
    async with session_factory() as s:
        limits = (
            await s.scalars(select(RiskLimits).where(RiskLimits.user_id == 1))
        ).first()
        day_change, basis, model_a = await engine._daily_loss_day_change(s, 1, limits, state)
    assert day_change is None
    assert model_a is not None
    assert model_a.status == ObservationStatus.UNAVAILABLE
    assert map_surface_action(model_a.status, surface="new_risk") == SurfaceAction.REJECT
    # Legacy day_change would have been +1 (pass); Model A must not fall through to that.
    assert state.day_change == D("1")


async def test_removal_of_baseline_does_not_reactivate_legacy(session_factory, acct, monkeypatch):
    import app.risk.engine as engine_mod

    monkeypatch.setattr(engine_mod, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(equity="100000"), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        row = await s.scalar(select(RiskCanarySessionBaseline))
        await s.delete(row)
        await s.commit()
    engine = RiskEngine(session_factory)
    state = _state(equity="100000", last_equity="90000", day_change="10000")
    async with session_factory() as s:
        limits = _limits_row()
        day_change, basis, model_a = await engine._daily_loss_day_change(s, 1, limits, state)
    assert model_a is not None and model_a.status == ObservationStatus.UNAVAILABLE
    assert day_change is None  # not legacy +10000


def test_unavailable_permits_verified_reduction_surface_only():
    """Ruling: new risk REJECT; independently verified reduction PERMIT under UNAVAILABLE."""
    assert (
        map_surface_action(ObservationStatus.UNAVAILABLE, surface="new_risk")
        == SurfaceAction.REJECT
    )
    assert (
        map_surface_action(ObservationStatus.UNAVAILABLE, surface="verified_reduction")
        == SurfaceAction.PERMIT_REDUCTION
    )
    assert (
        map_surface_action(ObservationStatus.INVALID, surface="verified_reduction")
        == SurfaceAction.PERMIT_REDUCTION_ADR0042_ONLY
    )
    assert (
        map_surface_action(ObservationStatus.UNAVAILABLE, surface="recovery")
        == SurfaceAction.FAIL_OR_INCOMPLETE
    )


async def test_corrupt_baseline_evidence_is_invalid_not_legacy(session_factory, acct, monkeypatch):
    import app.risk.circuit_breaker as cb_mod

    monkeypatch.setattr(cb_mod, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(equity="100000"), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        row = await s.scalar(select(RiskCanarySessionBaseline))
        row.raw_response_json = ""
        row.raw_response_sha256 = ""
        await s.commit()
    async with session_factory() as s:
        s.add(_limits_row())
        s.add(_state(equity="99000", last_equity="100000", day_change="-1000"))
        await s.commit()
    async with session_factory() as s:
        dp, basis, _br, model_a = await CircuitBreakerService(session=s)._compute_daily_pnl(
            1, realized=D("-50"), unrealized=D("0"), max_loss=D("500")
        )
    assert model_a is not None
    assert model_a.status == ObservationStatus.INVALID
    assert dp is None  # not cumulative -50, not zero pass
    assert basis == "MODEL_A_INVALID"


async def test_iso_broker_timestamp_same_session_accepted(session_factory, acct):
    async with session_factory() as s:
        await _seal(s)
    ts = datetime(2026, 7, 31, 9, 31, 15, tzinfo=ET).astimezone(UTC)
    async with session_factory() as s:
        r = await capture_model_a_baseline(
            s,
            start_a_id=START_A_ID,
            broker_account_payload=_payload(
                equity="100000",
                timestamp=ts.strftime("%Y-%m-%dT%H:%M:%S") + "Z",
            ),
            now=_open_et(9, 32),
        )
    assert r.reused is False


async def test_recovery_preflight_fails_without_bound_baseline(session_factory, acct, monkeypatch):
    import app.risk.loss_control.preflight as pf

    monkeypatch.setattr(pf, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        ctx = pf.PreflightContext(
            session=s,
            account_id=1,
            origin_state=None,
            request_event=None,
            trip_type=None,
            trip_cause=None,
        )
        baseline_check = await pf._session_baseline_valid(ctx)
        loss_check = await pf._daily_loss_recomputed(ctx)
    assert baseline_check.passed is False
    assert baseline_check.evidence["reason_code"] == "MODEL_A_BASELINE_MISSING"
    assert loss_check.passed is False
    assert loss_check.evidence["status"] == "UNAVAILABLE"


async def test_recovery_uses_bound_freeze_baseline(session_factory, acct, monkeypatch):
    import app.risk.loss_control.preflight as pf

    monkeypatch.setattr(pf, "resolve_session_date", lambda _now: SESSION)
    async with session_factory() as s:
        await _seal(s)
    async with session_factory() as s:
        await capture_model_a_baseline(
            s, start_a_id=START_A_ID, broker_account_payload=_payload(equity="100000.5"), now=_open_et(9, 31)
        )
    async with session_factory() as s:
        s.add(_state(equity="99000.5", last_equity="100000.5", day_change="-1000"))
        await s.commit()
    async with session_factory() as s:
        ctx = pf.PreflightContext(
            session=s,
            account_id=1,
            origin_state=None,
            request_event=None,
            trip_type=None,
            trip_cause=None,
        )
        baseline_check = await pf._session_baseline_valid(ctx)
        loss_check = await pf._daily_loss_recomputed(ctx)
    assert baseline_check.passed is True
    assert baseline_check.evidence["freeze_id"] == FREEZE_ID
    assert baseline_check.evidence["start_a_id"] == START_A_ID
    assert loss_check.passed is True
    assert D(loss_check.evidence["day_change"]) == D("-1000")
