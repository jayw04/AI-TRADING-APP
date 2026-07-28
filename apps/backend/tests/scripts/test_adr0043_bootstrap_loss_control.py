"""The ADR-0043 loss-control bootstrap must be narrow BY CONSTRUCTION, not by configuration.

Phase-0 attempt 1 (2026-07-28) proved the enforcement side: an absent ``risk_loss_control_state``
row is an ``INTEGRITY_STOP``, exactly as designed. These tests prove the provisioning side: the
bootstrap creates that one row through the service's own race-safe path, for exactly one frozen
account, refuses every world it was not built for, and demonstrably changes nothing else —
no control events, no orders, no reservations, no baselines, no account-1 state.
"""

from __future__ import annotations

import ast
import inspect
import json
from datetime import UTC, datetime
from pathlib import Path

import pytest
from sqlalchemy import text

from app.audit.logger import AuditAction
from app.db.models.account import Account, AccountMode
from app.db.models.user import User
from app.risk.loss_control import constants as lc_constants
from scripts import adr0043_bootstrap_loss_control as mod
from scripts.adr0043_bootstrap_loss_control import (
    BOOTSTRAP_ACCOUNT_ID,
    BOOTSTRAP_USER_ID,
    REFUSE_BOOTSTRAP_RESULT,
    REFUSE_ROW_EXISTS,
    REFUSE_UNPROTECTED_ADAPTER,
    BootstrapRefused,
    assess_bootstrap_row,
    assess_side_effects,
    bootstrap_loss_control,
)
from scripts.adr0043_scoped_sync import EXPECTED_BROKER_ACCOUNT, FORBIDDEN_BROKER_ACCOUNTS
from scripts.adr0043_session_open import ReadOnlyBrokerView, SessionOpenRefused

SOURCE = Path(inspect.getfile(mod)).read_text(encoding="utf-8")
TREE = ast.parse(SOURCE)


def _strip_prose(tree: ast.Module) -> str:
    """Source with comments and docstrings removed — the module documents the constructs it
    refuses to use, and scanning raw text would flag the explanation."""
    clone = ast.parse(ast.unparse(tree))
    for node in ast.walk(clone):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                node.body = body[1:] or [ast.Pass()]
    return ast.unparse(clone)


CODE = _strip_prose(TREE)


# ---------------------------------------------------------------------------- structure


def test_target_is_frozen_constants_not_environment():
    assert BOOTSTRAP_USER_ID == 3
    assert BOOTSTRAP_ACCOUNT_ID == 3


def test_module_reads_no_environment_variable_at_all():
    offenders = [
        ast.dump(node)
        for node in ast.walk(TREE)
        if isinstance(node, ast.Attribute) and node.attr in {"environ", "getenv"}
    ]
    assert offenders == [], f"the bootstrap must not read the environment: {offenders}"
    assert "os.environ" not in CODE
    assert "getenv" not in CODE


def test_no_registry_and_no_global_credential_decryption():
    """Attempt 1 showed ``BrokerRegistry.load_all`` touches account 1's credential metadata; the
    bootstrap must use the scoped single-user adapter factory instead."""
    assert "BrokerRegistry" not in CODE
    assert "load_all" not in CODE
    assert "build_scoped_adapter" in CODE


def test_no_ad_hoc_sql_writes_the_state_row():
    """The ONE write goes through ``LossControlService.get_state_row``; the module must contain no
    INSERT/UPDATE/DELETE statement of its own."""
    lowered = CODE.lower()
    for verb in ("insert into", "update risk_", "delete from"):
        assert verb not in lowered, f"ad-hoc SQL write found: {verb!r}"
    assert "get_state_row" in CODE


def test_the_bootstrap_is_not_recorded_as_a_state_transition():
    assert "request_transition" not in CODE, (
        "a bootstrap row is provisioning, not a NORMAL -> NORMAL transition"
    )
    assert mod.AUDIT_ACTION is AuditAction.LOSS_CONTROL_STATE_BOOTSTRAPPED


# ---------------------------------------------------------------------------- pure assessments


def _row(**over):
    row = {
        "account_id": 3,
        "state": lc_constants.STATE_NORMAL,
        "state_version": 0,
        "last_sequence_no": 0,
        "control_version": lc_constants.LOSS_CONTROL_STATE_VERSION,
    }
    row.update(over)
    return row


def test_the_expected_row_is_accepted():
    ok, detail = assess_bootstrap_row(_row())
    assert ok, detail


@pytest.mark.parametrize(
    "over",
    [
        {"state": "INTEGRITY_STOP"},
        {"state_version": 1},
        {"last_sequence_no": 3},
        {"control_version": 999},
    ],
)
def test_any_deviation_from_the_frozen_row_is_refused(over):
    ok, detail = assess_bootstrap_row(_row(**over))
    assert not ok
    key = next(iter(over))
    assert key in detail


def test_a_missing_row_after_bootstrap_is_refused():
    ok, detail = assess_bootstrap_row(None)
    assert not ok and "no risk_loss_control_state row" in detail


def _counters(**over):
    base = {
        "risk_control_events_total": 0,
        "orders_total": 5,
        "held_reservations_total": 0,
        "session_baselines_total": 2,
        "audit_log_total": 10,
        "account1_loss_control_row": {"state": "NORMAL", "state_version": 2},
    }
    base.update(over)
    return base


def test_side_effects_commit_requires_exactly_one_audit_row():
    ok, problems = assess_side_effects(_counters(), _counters(audit_log_total=11), committed=True)
    assert ok, problems
    ok, problems = assess_side_effects(_counters(), _counters(), committed=True)
    assert not ok and any("audit_log_total" in p for p in problems)
    ok, problems = assess_side_effects(_counters(), _counters(audit_log_total=12), committed=True)
    assert not ok


@pytest.mark.parametrize(
    "over",
    [
        {"risk_control_events_total": 1},
        {"orders_total": 6},
        {"held_reservations_total": 1},
        {"session_baselines_total": 3},
        {"account1_loss_control_row": {"state": "INTEGRITY_STOP", "state_version": 3}},
    ],
)
def test_any_other_change_is_a_side_effect(over):
    ok, problems = assess_side_effects(
        _counters(), _counters(audit_log_total=11, **over), committed=True
    )
    assert not ok, f"expected a problem for {over}"


# ---------------------------------------------------------------------------- rig


async def _seed(session_factory, *, account1_lc: bool = True):
    async with session_factory() as s:
        s.add(User(id=1, email="m@t"))
        s.add(Account(id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="M"))
        s.add(User(id=3, email="c@t"))
        s.add(Account(id=3, user_id=3, broker="alpaca", mode=AccountMode.paper, label="C"))
        await s.commit()
    if account1_lc:
        async with session_factory() as s:
            await s.execute(
                text(
                    "INSERT INTO risk_loss_control_state (account_id, state, state_version, "
                    "last_sequence_no, control_version, updated_at) "
                    "VALUES (1, 'NORMAL', 2, 7, :cv, :now)"
                ),
                {"cv": lc_constants.LOSS_CONTROL_STATE_VERSION, "now": datetime.now(UTC)},
            )
            await s.commit()


class _Broker:
    def __init__(self, account_number=EXPECTED_BROKER_ACCOUNT):
        self.account_number = account_number

    def get_account(self):
        return {"account_number": self.account_number, "status": "ACTIVE"}


def _factory(broker=None):
    async def factory(sf):
        return ReadOnlyBrokerView(broker or _Broker())

    return factory


async def _lc_row(session_factory, account_id):
    async with session_factory() as s:
        row = (
            await s.execute(
                text(
                    "SELECT state, state_version, last_sequence_no, control_version "
                    "FROM risk_loss_control_state WHERE account_id = :a"
                ),
                {"a": account_id},
            )
        ).mappings().first()
    return dict(row) if row else None


async def _audit_rows(session_factory):
    async with session_factory() as s:
        return [
            dict(r)
            for r in (
                await s.execute(
                    text("SELECT action, target_type, target_id, payload_json FROM audit_log")
                )
            ).mappings()
        ]


# ---------------------------------------------------------------------------- dry run


async def test_dry_run_performs_every_check_and_writes_nothing(session_factory, tmp_path):
    await _seed(session_factory)
    out = tmp_path / "ev.json"
    ev = await bootstrap_loss_control(
        sf=session_factory, adapter_factory=_factory(), commit=False, out=out
    )
    assert ev["outcome"] == "DRY_RUN_NO_WRITE"
    assert ev["before_row"] is None
    assert ev["would_bootstrap"]["state"] == "NORMAL"
    assert await _lc_row(session_factory, 3) is None, "a dry run must not create the row"
    assert await _audit_rows(session_factory) == [], "a dry run must not write an audit record"
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["outcome"] == "DRY_RUN_NO_WRITE"
    assert written["broker_calls"] == ["get_account"]


# ---------------------------------------------------------------------------- commit


async def test_commit_creates_exactly_the_frozen_row(session_factory, tmp_path):
    await _seed(session_factory)
    out = tmp_path / "ev.json"
    ev = await bootstrap_loss_control(
        sf=session_factory, adapter_factory=_factory(), commit=True, out=out
    )
    assert ev["outcome"] == "COMMITTED"
    row = await _lc_row(session_factory, 3)
    assert row == {
        "state": "NORMAL",
        "state_version": 0,
        "last_sequence_no": 0,
        "control_version": lc_constants.LOSS_CONTROL_STATE_VERSION,
    }


async def test_commit_writes_one_governance_audit_record_and_no_transition(
    session_factory, tmp_path
):
    await _seed(session_factory)
    await bootstrap_loss_control(
        sf=session_factory, adapter_factory=_factory(), commit=True, out=tmp_path / "ev.json"
    )
    audits = await _audit_rows(session_factory)
    assert [a["action"] for a in audits] == ["LOSS_CONTROL_STATE_BOOTSTRAPPED"]
    payload = json.loads(audits[0]["payload_json"])
    assert payload["account_id"] == 3
    assert payload["initial_state"] == "NORMAL"
    assert payload["reason"] == "ADR0043_CANARY_PROVISIONING"
    async with session_factory() as s:
        events = (await s.execute(text("SELECT COUNT(*) FROM risk_control_events"))).scalar()
    assert events == 0, "a bootstrap must not fabricate a state-machine transition"


async def test_commit_leaves_account_1_and_every_counter_unchanged(session_factory, tmp_path):
    await _seed(session_factory, account1_lc=True)
    before_acct1 = await _lc_row(session_factory, 1)
    ev = await bootstrap_loss_control(
        sf=session_factory, adapter_factory=_factory(), commit=True, out=tmp_path / "ev.json"
    )
    assert await _lc_row(session_factory, 1) == before_acct1
    checks = {c["name"]: c["result"] for c in ev["checks"]}
    assert checks["no_side_effects"] == "PASS"
    assert ev["counters_before"]["orders_total"] == ev["counters_after"]["orders_total"] == 0


# ---------------------------------------------------------------------------- refusals


@pytest.mark.parametrize("state", ["NORMAL", "REDUCTION_ONLY_DAILY_LOSS", "INTEGRITY_STOP"])
async def test_an_existing_row_in_any_state_refuses(session_factory, tmp_path, state):
    """First provisioning only: prior state — even a correct-looking NORMAL — is a finding to
    investigate, never something to overwrite or silently accept."""
    await _seed(session_factory)
    async with session_factory() as s:
        await s.execute(
            text(
                "INSERT INTO risk_loss_control_state (account_id, state, state_version, "
                "last_sequence_no, control_version, updated_at) VALUES (3, :st, 0, 0, :cv, :now)"
            ),
            {"st": state, "cv": lc_constants.LOSS_CONTROL_STATE_VERSION, "now": datetime.now(UTC)},
        )
        await s.commit()
    out = tmp_path / "ev.json"
    with pytest.raises(BootstrapRefused) as exc:
        await bootstrap_loss_control(
            sf=session_factory, adapter_factory=_factory(), commit=True, out=out
        )
    assert exc.value.code == REFUSE_ROW_EXISTS
    assert await _audit_rows(session_factory) == []
    written = json.loads(out.read_text(encoding="utf-8"))
    assert written["outcome"] == "REFUSED"
    assert written["refusal_code"] == REFUSE_ROW_EXISTS


async def test_the_forbidden_momentum_account_is_refused_by_name(session_factory, tmp_path):
    await _seed(session_factory)
    forbidden = next(iter(FORBIDDEN_BROKER_ACCOUNTS))
    with pytest.raises(SessionOpenRefused):
        await bootstrap_loss_control(
            sf=session_factory,
            adapter_factory=_factory(_Broker(account_number=forbidden)),
            commit=True,
            out=tmp_path / "ev.json",
        )
    assert await _lc_row(session_factory, 3) is None, "nothing may be written after a refusal"
    assert await _audit_rows(session_factory) == []


async def test_a_wrong_user_binding_refuses(session_factory, tmp_path):
    async with session_factory() as s:
        s.add(User(id=9, email="x@t"))
        s.add(Account(id=3, user_id=9, broker="alpaca", mode=AccountMode.paper, label="X"))
        await s.commit()
    with pytest.raises(SessionOpenRefused):
        await bootstrap_loss_control(
            sf=session_factory, adapter_factory=_factory(), commit=True, out=tmp_path / "ev.json"
        )
    assert await _lc_row(session_factory, 3) is None


async def test_a_missing_account_row_refuses(session_factory, tmp_path):
    with pytest.raises(SessionOpenRefused):
        await bootstrap_loss_control(
            sf=session_factory, adapter_factory=_factory(), commit=True, out=tmp_path / "ev.json"
        )


async def test_a_raw_adapter_is_refused(session_factory, tmp_path):
    await _seed(session_factory)

    async def raw_factory(sf):
        return _Broker()

    with pytest.raises(BootstrapRefused) as exc:
        await bootstrap_loss_control(
            sf=session_factory, adapter_factory=raw_factory, commit=True, out=tmp_path / "ev.json"
        )
    assert exc.value.code == REFUSE_UNPROTECTED_ADAPTER


async def test_an_unexpected_persisted_row_is_refused_after_commit(
    session_factory, tmp_path, monkeypatch
):
    """If the service somehow persists something other than the frozen expectation, the tool
    refuses and surfaces the observed row rather than declaring success."""
    await _seed(session_factory)

    async def wrong_row(sf, account_id):
        if account_id == BOOTSTRAP_ACCOUNT_ID:
            return _row(state_version=7)
        return None

    real = mod.read_loss_control_row
    calls = {"n": 0}

    async def sequenced(sf, account_id):
        # first read (absence check) behaves normally; the post-bootstrap read returns the
        # unexpected row
        calls["n"] += 1
        if account_id == BOOTSTRAP_ACCOUNT_ID and calls["n"] > 1:
            return await wrong_row(sf, account_id)
        return await real(sf, account_id)

    monkeypatch.setattr(mod, "read_loss_control_row", sequenced)
    with pytest.raises(BootstrapRefused) as exc:
        await bootstrap_loss_control(
            sf=session_factory, adapter_factory=_factory(), commit=True, out=tmp_path / "ev.json"
        )
    assert exc.value.code == REFUSE_BOOTSTRAP_RESULT


async def test_a_refusal_still_records_the_checks_that_passed(session_factory, tmp_path):
    await _seed(session_factory)
    forbidden = next(iter(FORBIDDEN_BROKER_ACCOUNTS))
    out = tmp_path / "ev.json"
    with pytest.raises(SessionOpenRefused):
        await bootstrap_loss_control(
            sf=session_factory,
            adapter_factory=_factory(_Broker(account_number=forbidden)),
            commit=True,
            out=out,
        )
    written = json.loads(out.read_text(encoding="utf-8"))
    names = {c["name"]: c["result"] for c in written["checks"]}
    assert names["account_row_binding"] == "PASS"
    assert names["no_existing_row"] == "PASS"
    assert names["broker_identity"] == "FAIL"
