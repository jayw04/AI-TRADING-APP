"""ADR 0043 Phase-0 orchestrator — the guards that make its output evidence rather than a claim.

Hermetic: no broker, no database, no host. Each guard is exercised directly.

The tool's output is what a Phase-0 session gets authorized from, so the tests are written against
the question "could this package be produced by a run that was not what it says it was?" — wrong
host, wrong database, wrong broker account, changed limits, a market that is not open, a baseline
that already exists, or a truncated file that reads as complete.
"""

from __future__ import annotations

import json
from decimal import Decimal as D
from pathlib import Path

import pytest

from scripts.adr0043_reachability import Caps
from scripts.adr0043_session_open import (
    ALLOWED_BROKER_METHODS,
    REFUSE_BASELINE_CONTRADICTORY,
    REFUSE_BROKER_IDENTITY,
    REFUSE_BROKER_UNREACHABLE,
    REFUSE_CONFIG,
    REFUSE_DB_PATH,
    REFUSE_INSTANCE,
    REFUSE_LIMITS,
    REFUSE_MUTATING_CALL,
    REFUSE_NOT_FLAT,
    REFUSE_POSITIONS,
    REFUSE_SESSION,
    Config,
    ReadOnlyBrokerView,
    SessionOpenRefused,
    build_package,
    check_broker_identity,
    check_db_path,
    check_flat,
    check_instance,
    check_limits,
    check_positions,
    check_session_open,
    fetch_account,
    limits_sha256,
    select_existing_baseline,
    write_package_atomically,
)

CANARY = "PA34USW0Q8UO"
MOMENTUM = "PA3QRX9KSPXA"

ENV = {
    "ADR0043_USER": "3",
    "ADR0043_ACCOUNT": "3",
    "ADR0043_EXPECTED_BROKER_ACCOUNT": CANARY,
    "ADR0043_FORBIDDEN_BROKER_ACCOUNT": MOMENTUM,
    "ADR0043_EXPECTED_INSTANCE_ID": "i-0canary",
    "ADR0043_EXPECTED_DB_URL": "sqlite+aiosqlite:////app/data/workbench.sqlite",
    "ADR0043_FROZEN_LIMITS_SHA256": "da665933",
    "ADR0043_LEGS": "MSFT:19",
    "ADR0043_CHURN": "IEUS,KOKU",
    "ADR0043_LOSS_TARGET": "3000",
    "ADR0043_MAX_ROUND_TRIPS": "12",
    "ADR0043_MAX_SETUP_NOTIONAL": "25000",
    "ADR0043_MAX_POSITION_QTY": "1000",
}

LIMITS_ROW = {
    "user_id": 3,
    "scope_type": "GLOBAL",
    "scope_id": None,
    "broker_mode": "paper",
    "max_daily_loss": "3000.00",
    "max_position_qty": "1000",
    "max_position_notional": "30000.00",
    "max_gross_exposure": "100000.00",
    "max_orders_per_minute": 30,
    "max_orders_per_day": 100,
    "allow_short": False,
    "allowed_symbols": '["MSFT","IEUS","KOKU"]',
    "denied_symbols": "[]",
}


def _cfg(**over) -> Config:
    return Config.from_env({**ENV, **over})


# ------------------------------------------------------------------ configuration is required


@pytest.mark.parametrize("missing", sorted(ENV))
def test_every_identity_must_be_supplied(missing):
    """A tool that defaults its own identity can run correctly against the wrong machine."""
    env = {k: v for k, v in ENV.items() if k != missing}
    with pytest.raises(SessionOpenRefused) as exc:
        Config.from_env(env)
    assert exc.value.code == REFUSE_CONFIG
    assert exc.value.diagnostics["missing"] == missing


def test_config_carries_the_frozen_caps():
    cfg = _cfg()
    assert cfg.caps == Caps(
        loss_target=D("3000"),
        max_round_trips=12,
        max_setup_notional=D("25000"),
        max_position_qty=D("1000"),
    )
    assert cfg.protected == (("MSFT", D("19")),)


# ------------------------------------------------------------------ host and database identity


def test_the_wrong_instance_refuses():
    with pytest.raises(SessionOpenRefused) as exc:
        check_instance(_cfg(), "i-0production")
    assert exc.value.code == REFUSE_INSTANCE


def test_an_unreadable_instance_identity_is_not_assumed():
    with pytest.raises(SessionOpenRefused) as exc:
        check_instance(_cfg(), None)
    assert exc.value.code == REFUSE_INSTANCE


def test_the_right_instance_passes():
    assert check_instance(_cfg(), "i-0canary")["ok"] is True


def test_a_database_that_merely_looks_similar_refuses():
    """`ssh workbench` is the production stack and its database has the same basename. Matching on
    a suffix would accept exactly the mistake this guard exists to prevent."""
    with pytest.raises(SessionOpenRefused) as exc:
        check_db_path(_cfg(), "sqlite+aiosqlite:////opt/prod/data/workbench.sqlite")
    assert exc.value.code == REFUSE_DB_PATH


def test_an_absent_database_url_refuses():
    with pytest.raises(SessionOpenRefused) as exc:
        check_db_path(_cfg(), None)
    assert exc.value.code == REFUSE_DB_PATH


# ------------------------------------------------------------------ the broker cannot be mutated


def test_the_broker_view_exposes_only_reads():
    class Adapter:
        def get_account(self):
            return {"account_number": CANARY}

        def submit_order(self, *a, **k):  # pragma: no cover - must never be reached
            raise AssertionError("the tool must not be able to reach this")

    view = ReadOnlyBrokerView(Adapter())
    assert view.get_account() == {"account_number": CANARY}
    with pytest.raises(SessionOpenRefused) as exc:
        _ = view.submit_order  # noqa: B018 — the attribute ACCESS is what must refuse
    assert exc.value.code == REFUSE_MUTATING_CALL


@pytest.mark.parametrize(
    "method", ["submit_order", "cancel_order", "replace_order", "close_position", "close_all_positions"]
)
def test_no_mutating_method_is_reachable(method):
    """Not 'the source contains no such call' — a property of the object, so a future edit that
    reaches for one fails loudly instead of trading."""
    assert method not in ALLOWED_BROKER_METHODS
    with pytest.raises(SessionOpenRefused):
        getattr(ReadOnlyBrokerView(object()), method)


def test_read_calls_are_recorded_for_the_evidence():
    class Adapter:
        def get_positions(self):
            return []

    view = ReadOnlyBrokerView(Adapter())
    view.get_positions()
    assert view.calls == ["get_positions"]


# ------------------------------------------------------------------ broker identity


def test_the_forbidden_momentum_account_is_named_in_the_refusal():
    with pytest.raises(SessionOpenRefused) as exc:
        check_broker_identity(_cfg(), {"account_number": MOMENTUM, "status": "ACTIVE"})
    assert exc.value.code == REFUSE_BROKER_IDENTITY
    assert exc.value.diagnostics["forbidden"] == MOMENTUM


def test_an_unknown_account_refuses():
    with pytest.raises(SessionOpenRefused):
        check_broker_identity(_cfg(), {"account_number": "PA00000000", "status": "ACTIVE"})


def test_a_non_active_canary_account_refuses():
    with pytest.raises(SessionOpenRefused):
        check_broker_identity(_cfg(), {"account_number": CANARY, "status": "ACCOUNT_CLOSED"})


def test_the_canary_account_passes():
    assert check_broker_identity(_cfg(), {"account_number": CANARY, "status": "ACTIVE"})["ok"]


# ------------------------------------------------------------------ bounded retries


def test_a_flap_is_retried_then_succeeds(monkeypatch):
    monkeypatch.setattr("scripts.adr0043_session_open.time.sleep", lambda _s: None)
    calls = {"n": 0}

    class Flaky:
        def get_account(self):
            calls["n"] += 1
            if calls["n"] < 3:
                raise ConnectionError("50010000")
            return {"account_number": CANARY}

    assert fetch_account(Flaky())["account_number"] == CANARY
    assert calls["n"] == 3


def test_retries_are_bounded_and_end_in_a_refusal(monkeypatch):
    monkeypatch.setattr("scripts.adr0043_session_open.time.sleep", lambda _s: None)

    class Dead:
        def get_account(self):
            raise ConnectionError("50010000")

    with pytest.raises(SessionOpenRefused) as exc:
        fetch_account(Dead(), attempts=4)
    assert exc.value.code == REFUSE_BROKER_UNREACHABLE


def test_an_empty_payload_is_not_a_valid_account(monkeypatch):
    monkeypatch.setattr("scripts.adr0043_session_open.time.sleep", lambda _s: None)

    class Empty:
        def get_account(self):
            return {}

    with pytest.raises(SessionOpenRefused):
        fetch_account(Empty(), attempts=2)


# ------------------------------------------------------------------ frozen limits


def test_the_frozen_digest_is_stable_over_representation():
    """Decimal strings and JSON-encoded symbol lists must normalise, or an untouched row would
    appear changed and abort a legitimate session."""
    a = limits_sha256(LIMITS_ROW)
    b = limits_sha256({**LIMITS_ROW, "max_daily_loss": 3000, "allowed_symbols": ["MSFT", "IEUS", "KOKU"]})
    assert a == b


def test_a_raised_limit_changes_the_digest_and_refuses():
    """Raising the cap is exactly the mutation ADR 0043 exists to prevent; it must break continuity
    rather than quietly permit a bigger loss."""
    cfg = _cfg(ADR0043_FROZEN_LIMITS_SHA256=limits_sha256(LIMITS_ROW))
    assert check_limits(cfg, [LIMITS_ROW])["sha_unchanged"] is True
    with pytest.raises(SessionOpenRefused) as exc:
        check_limits(cfg, [{**LIMITS_ROW, "max_daily_loss": "5000.00"}])
    assert exc.value.code == REFUSE_LIMITS


@pytest.mark.parametrize("rows", [[], [LIMITS_ROW, LIMITS_ROW]])
def test_anything_but_exactly_one_limits_row_refuses(rows):
    with pytest.raises(SessionOpenRefused) as exc:
        check_limits(_cfg(), rows)
    assert exc.value.code == REFUSE_LIMITS


# ------------------------------------------------------------------ positions and flatness


def test_the_frozen_legs_must_match_on_both_sides():
    cfg = _cfg()
    assert check_positions(cfg, {"MSFT": D("19")}, {"MSFT": D("19")})["ok"]


@pytest.mark.parametrize(
    ("broker", "db"),
    [
        ({"MSFT": D("18")}, {"MSFT": D("19")}),                    # broker drifted
        ({"MSFT": D("19")}, {"MSFT": D("18")}),                    # ledger drifted
        ({"MSFT": D("19"), "KOKU": D("5")}, {"MSFT": D("19")}),    # unrelated position
        ({}, {}),                                                  # the leg is gone
    ],
)
def test_any_position_discrepancy_refuses(broker, db):
    with pytest.raises(SessionOpenRefused) as exc:
        check_positions(_cfg(), broker, db)
    assert exc.value.code == REFUSE_POSITIONS


def test_a_zero_quantity_row_is_not_a_position():
    assert check_positions(_cfg(), {"MSFT": D("19"), "IEUS": D("0")}, {"MSFT": D("19")})["ok"]


@pytest.mark.parametrize(("orders", "held"), [(1, 0), (0, 1), (2, 3)])
def test_open_orders_or_held_reservations_refuse(orders, held):
    with pytest.raises(SessionOpenRefused) as exc:
        check_flat(orders, held)
    assert exc.value.code == REFUSE_NOT_FLAT


# ------------------------------------------------------------------ the session must be open


def test_capture_requires_a_positively_open_market():
    with pytest.raises(SessionOpenRefused) as exc:
        check_session_open(False, required=True)
    assert exc.value.code == REFUSE_SESSION


def test_an_unknown_clock_is_not_an_open_market():
    """A baseline minted outside the session it claims to describe is unauditable, and the
    same-session rule means it cannot be corrected afterwards."""
    with pytest.raises(SessionOpenRefused):
        check_session_open(None, required=True)


def test_the_read_only_precheck_runs_outside_the_session():
    assert check_session_open(False, required=False)["market_open_now"] is False


# ------------------------------------------------------------------ baseline idempotency


def test_an_existing_baseline_is_reused_never_replaced():
    rows = [
        {"id": 7, "market_session_date": "2026-07-24", "status": "ACTIVE", "baseline_equity": "84000"},
        {"id": 6, "market_session_date": "2026-07-23", "status": "ACTIVE", "baseline_equity": "83000"},
    ]
    assert select_existing_baseline(rows, "2026-07-24")["id"] == 7


def test_no_baseline_for_this_session_is_not_borrowed_from_another():
    rows = [{"id": 6, "market_session_date": "2026-07-23", "status": "ACTIVE", "baseline_equity": "1"}]
    assert select_existing_baseline(rows, "2026-07-24") is None


def test_a_superseded_baseline_does_not_count_as_existing():
    rows = [{"id": 7, "market_session_date": "2026-07-24", "status": "SUPERSEDED", "baseline_equity": "1"}]
    assert select_existing_baseline(rows, "2026-07-24") is None


def test_contradictory_baselines_refuse():
    rows = [
        {"id": 7, "market_session_date": "2026-07-24", "status": "ACTIVE", "baseline_equity": "84000"},
        {"id": 8, "market_session_date": "2026-07-24", "status": "ACTIVE", "baseline_equity": "90000"},
    ]
    with pytest.raises(SessionOpenRefused) as exc:
        select_existing_baseline(rows, "2026-07-24")
    assert exc.value.code == REFUSE_BASELINE_CONTRADICTORY


# ------------------------------------------------------------------ the evidence package


def test_the_package_names_the_instrument_that_produced_it():
    pkg = build_package(cfg=_cfg(), steps={}, captured_at=_when(), capture_requested=False)
    assert pkg["tool"]["version"]
    assert pkg["tool"]["source_sha256"]["adr0043_session_open.py"] != "ABSENT"
    assert pkg["classification"] == "READ_ONLY_PRECHECK"


def test_a_capture_run_is_classified_differently_from_a_precheck():
    pkg = build_package(cfg=_cfg(), steps={}, captured_at=_when(), capture_requested=True)
    assert pkg["classification"] == "AUTHORITATIVE_SESSION_READINESS"


def test_readiness_requires_every_gate_not_merely_the_last():
    steps = {
        "1_instance": {"ok": True},
        "2_database": {"ok": True},
        "3_identity": {"ok": True},
        "4_positions": {"ok": True},
        "5_flat": {"clean": True},
        "6_limits": {"sha_unchanged": True},
    }
    assert build_package(cfg=_cfg(), steps=steps, captured_at=_when(), capture_requested=False)[
        "READY_FOR_BASELINE_AND_PREFLIGHT"
    ]
    partial = {**steps, "6_limits": {"sha_unchanged": False}}
    assert not build_package(
        cfg=_cfg(), steps=partial, captured_at=_when(), capture_requested=False
    )["READY_FOR_BASELINE_AND_PREFLIGHT"]


def test_the_package_is_written_atomically(tmp_path):
    """A reader must never find a half-written package and mistake it for a complete one."""
    target = tmp_path / "pkg" / "session.json"
    write_package_atomically({"a": 1, "b": [2, 3]}, target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"a": 1, "b": [2, 3]}
    assert not list(target.parent.glob(".sessionpkg-*")), "no temp file may survive"


def test_a_failed_write_leaves_no_partial_file_and_no_debris(tmp_path, monkeypatch):
    target = tmp_path / "session.json"

    def boom(*_a, **_k):
        raise OSError("disk full")

    monkeypatch.setattr("scripts.adr0043_session_open.os.replace", boom)
    with pytest.raises(OSError):
        write_package_atomically({"a": 1}, target)
    assert not target.exists()
    assert not list(Path(tmp_path).glob(".sessionpkg-*"))


def test_rewriting_replaces_the_package_wholesale(tmp_path):
    target = tmp_path / "session.json"
    write_package_atomically({"run": 1}, target)
    write_package_atomically({"run": 2}, target)
    assert json.loads(target.read_text(encoding="utf-8")) == {"run": 2}


def _when():
    from datetime import UTC, datetime

    return datetime(2026, 7, 24, 13, 31, tzinfo=UTC)
