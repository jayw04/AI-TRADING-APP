"""ADR 0043 §D3 — enforcement wiring at the two daily-loss basis seams.

Flag OFF must be byte-for-byte the legacy behaviour; flag ON must change only the basis source and
the derived day-change, and the basis provenance (source + baseline id) must reach the evidence /
trip payload. resolve_session_date is patched per-module so these don't depend on the wall-clock
trading calendar.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from sqlalchemy import select

import app.risk.circuit_breaker as cb_mod
import app.risk.engine as engine_mod
from app.db.enums import RiskScopeType
from app.db.models.account import Account, AccountMode
from app.db.models.account_state import AccountState
from app.db.models.audit_log import AuditLog
from app.db.models.risk_limits import RiskLimits
from app.db.models.risk_session_baseline import RiskSessionBaseline
from app.db.models.symbol import Symbol
from app.db.models.user import User
from app.risk.circuit_breaker import CircuitBreakerError, CircuitBreakerService
from app.risk.engine import RiskEngine
from app.services.day_change_basis import BROKER_LAST_EQUITY

D = Decimal
TODAY = "2026-07-20"
NOW = datetime(2026, 7, 20, 15, 0, tzinfo=UTC)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as s:
        s.add(User(id=1, email="t@local"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="P"))
        s.add(RiskLimits(id=1, user_id=1, broker_mode=AccountMode.paper,
                         scope_type=RiskScopeType.GLOBAL, max_daily_loss=D("500"),
                         created_at=NOW, updated_at=NOW))
        s.add(Symbol(id=1, ticker="AAPL", exchange="NASDAQ", asset_class="us_equity",
                     name="Apple", active=True))
        await s.commit()
    return session_factory


def _enforce(monkeypatch, module, enabled: bool) -> None:
    monkeypatch.setattr(
        module, "get_settings",
        lambda: SimpleNamespace(session_baseline_enforcement_enabled=enabled),
    )


def _pin_session_date(monkeypatch, module, date=TODAY) -> None:
    monkeypatch.setattr(module, "resolve_session_date", lambda now: date)


def _state(equity="98000", last_equity="95000", day_change="-6000") -> AccountState:
    return AccountState(
        day_change_basis=BROKER_LAST_EQUITY,
        account_id=1, cash=D("1"), equity=D(equity), last_equity=D(last_equity),
        buying_power=D("1"), portfolio_value=D(equity), daytrade_count=0,
        day_change=D(day_change), day_change_pct=D("0"), status="ACTIVE",
        pattern_day_trader=False, trading_blocked=False, account_blocked=False, updated_at=NOW,
    )


async def _limits(session_factory) -> RiskLimits:
    async with session_factory() as s:
        return await s.get(RiskLimits, 1)


async def _add_baseline(session_factory, equity="100000"):
    async with session_factory() as s:
        s.add(RiskSessionBaseline(account_id=1, market_session_date=TODAY, baseline_equity=D(equity),
                                  baseline_source="RECONCILED_OPEN", captured_at=NOW, status="ACTIVE"))
        await s.commit()


# ------------------------------------------------------------ engine step-9 seam


async def test_engine_step9_flag_off_is_byte_identical(seeded, monkeypatch):
    _enforce(monkeypatch, engine_mod, False)
    engine = RiskEngine(seeded)
    limits = await _limits(seeded)
    state = _state(day_change="-6000")
    async with seeded() as s:
        day_change, basis = await engine._daily_loss_day_change(s, 1, limits, state)
    assert day_change == state.day_change == D("-6000")  # exact legacy value
    assert basis is None  # no basis provenance computed when off


async def test_engine_step9_none_state_is_skip(seeded, monkeypatch):
    _enforce(monkeypatch, engine_mod, False)
    engine = RiskEngine(seeded)
    limits = await _limits(seeded)
    async with seeded() as s:
        day_change, basis = await engine._daily_loss_day_change(s, 1, limits, None)
    assert day_change is None and basis is None


async def test_engine_step9_flag_on_uses_baseline_with_provenance(seeded, monkeypatch):
    _enforce(monkeypatch, engine_mod, True)
    _pin_session_date(monkeypatch, engine_mod)
    await _add_baseline(seeded, equity="100000")
    engine = RiskEngine(seeded)
    limits = await _limits(seeded)
    state = _state(equity="98000", last_equity="95000")
    async with seeded() as s:
        day_change, basis = await engine._daily_loss_day_change(s, 1, limits, state)
    assert day_change == D("-2000")  # 98000 − 100000 (baseline), NOT −3000 (last_equity)
    assert basis is not None
    assert basis.basis_source == "SESSION_BASELINE"
    assert basis.baseline_id is not None  # baseline id reaches the trip payload + evidence log
    assert basis.provenance()["baseline_id"] == str(basis.baseline_id)


# ------------------------------------------------------------ circuit-breaker _compute_daily_pnl seam


async def test_compute_daily_pnl_flag_off_legacy_unchanged(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, False)
    async with seeded() as s:
        s.add(_state(equity="99000", last_equity="100000"))
        await s.commit()
    async with seeded() as s:
        dp, basis, basis_result = await CircuitBreakerService(session=s)._compute_daily_pnl(
            1, realized=D("0"), unrealized=D("0"), max_loss=D("500")
        )
    assert dp == D("-1000") and basis == "equity_baseline"  # legacy strings, unchanged
    assert basis_result is None  # no provenance object off


async def test_compute_daily_pnl_flag_on_prefers_session_baseline(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, True)
    _pin_session_date(monkeypatch, cb_mod)
    await _add_baseline(seeded, equity="100000")
    async with seeded() as s:
        s.add(_state(equity="99000", last_equity="99900"))
        await s.commit()
    async with seeded() as s:
        dp, basis, basis_result = await CircuitBreakerService(session=s)._compute_daily_pnl(
            1, realized=D("0"), unrealized=D("0"), max_loss=D("500")
        )
    assert basis == "SESSION_BASELINE"
    assert dp == D("-1000")  # 99000 − 100000 (baseline), not −900 (last_equity 99900)
    # Full provenance object retained (not collapsed to a string), incl. the applicable limit.
    assert basis_result is not None and basis_result.baseline_id is not None
    assert basis_result.applicable_limit == D("500")


async def test_compute_daily_pnl_flag_on_falls_back_to_last_equity(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, True)
    _pin_session_date(monkeypatch, cb_mod)
    async with seeded() as s:  # no baseline for today
        s.add(_state(equity="99000", last_equity="100000"))
        await s.commit()
    async with seeded() as s:
        dp, basis, basis_result = await CircuitBreakerService(session=s)._compute_daily_pnl(
            1, realized=D("0"), unrealized=D("0"), max_loss=D("500")
        )
    assert basis == "LEGACY_LAST_EQUITY" and dp == D("-1000")
    assert basis_result is not None and basis_result.fallback_reason == "NO_BASELINE_CAPTURED"


# ------------------------------------------------------------ durable trip payload (check / evaluate)


async def _tripped_payload(session_factory) -> dict:
    async with session_factory() as s:
        row = await s.scalar(
            select(AuditLog).where(AuditLog.action == "CIRCUIT_BREAKER_TRIPPED")
        )
    return json.loads(row.payload_json)


async def test_check_trip_payload_carries_full_provenance(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, True)
    _pin_session_date(monkeypatch, cb_mod)
    await _add_baseline(seeded, equity="100000")
    async with seeded() as s:  # 99000 − 100000 = −1000, breaches the −500 limit
        s.add(_state(equity="99000", last_equity="99999"))
        await s.commit()
    async with seeded() as s:
        with pytest.raises(CircuitBreakerError):
            await CircuitBreakerService(session=s).check(1)
    payload = await _tripped_payload(seeded)
    assert payload["daily_pnl_basis"] == "SESSION_BASELINE"
    prov = payload["daily_loss_basis_provenance"]  # the DURABLE payload, not just the log
    assert prov["basis_source"] == "SESSION_BASELINE"
    assert prov["baseline_id"] is not None
    assert D(prov["applicable_limit"]) == D("500")  # limit reaches the durable payload


async def test_evaluate_trip_payload_carries_full_provenance(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, True)
    _pin_session_date(monkeypatch, cb_mod)
    await _add_baseline(seeded, equity="100000")
    async with seeded() as s:
        s.add(_state(equity="99000", last_equity="99999"))
        await s.commit()
    async with seeded() as s:
        assert await CircuitBreakerService(session=s).evaluate(1) is True
    payload = await _tripped_payload(seeded)
    assert payload["source"] == "monitor"
    assert payload["daily_loss_basis_provenance"]["basis_source"] == "SESSION_BASELINE"


async def test_legacy_fallback_trip_payload_records_reason(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, True)
    _pin_session_date(monkeypatch, cb_mod)
    async with seeded() as s:  # NO baseline → legacy last_equity, with the specific reason recorded
        s.add(_state(equity="99000", last_equity="100000"))  # −1000 breaches the −500 limit
        await s.commit()
    async with seeded() as s:
        with pytest.raises(CircuitBreakerError):
            await CircuitBreakerService(session=s).check(1)
    payload = await _tripped_payload(seeded)
    assert payload["daily_pnl_basis"] == "LEGACY_LAST_EQUITY"
    assert payload["daily_loss_basis_provenance"]["fallback_reason"] == "NO_BASELINE_CAPTURED"


async def test_flag_off_trip_payload_shape_unchanged(seeded, monkeypatch):
    _enforce(monkeypatch, cb_mod, False)
    async with seeded() as s:
        s.add(_state(equity="99000", last_equity="100000"))  # −1000 breaches −500
        await s.commit()
    async with seeded() as s:
        with pytest.raises(CircuitBreakerError):
            await CircuitBreakerService(session=s).check(1)
    payload = await _tripped_payload(seeded)
    assert payload["daily_pnl_basis"] == "equity_baseline"  # legacy value
    assert "daily_loss_basis_provenance" not in payload  # no provenance key when off
