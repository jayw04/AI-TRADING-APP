"""ADR 0043 PR5 — the loss-control structural invariant checker itself.

Two directions per invariant: the REAL repo passes (no false positives), and a synthetic violation
is CAUGHT (no false negatives) — including the aliased-import and market-session-classify cases the
AST approach exists to handle.
"""

from __future__ import annotations

import ast
import importlib.util
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[2]
CHECKER = BACKEND / "scripts" / "check_loss_control_invariants.py"

_spec = importlib.util.spec_from_file_location("_lc_invariants", CHECKER)
assert _spec and _spec.loader
mod = importlib.util.module_from_spec(_spec)
sys.modules[_spec.name] = mod  # register so the checker's @dataclass can resolve its module
_spec.loader.exec_module(mod)


def _run_one(check, rel: str, src: str):
    return check(rel, ast.parse(src))


def _invariants(violations) -> set[str]:
    return {v.invariant for v in violations}


# --------------------------------------------------------------- the real repo is clean


def test_real_repo_passes():
    paths = sorted((BACKEND / "app").rglob("*.py"))
    assert mod.run(paths) == []


# --------------------------------------------------------------- §1 single-persister


def test_single_persister_flags_writes_outside_service():
    src = (
        "from app.db.models.risk_loss_control_state import RiskLossControlState\n"
        "def f(session):\n"
        "    row = RiskLossControlState(account_id=1)\n"  # constructor
        "    session.add(row)\n"
        "    row.state_version = 5\n"  # direct CAS-column write
    )
    v = _run_one(mod.check_single_persister, "app/risk/loss_control/gate.py", src)
    assert len(v) >= 2 and _invariants(v) == {"single-persister"}


def test_single_persister_flags_update_and_table_string():
    src = (
        "from sqlalchemy import update\n"
        "from app.db.models.risk_control_event import RiskControlEvent\n"
        "def f(session):\n"
        "    session.execute(update(RiskControlEvent).values(x=1))\n"
        "    session.execute('DELETE FROM risk_control_events')\n"
    )
    v = _run_one(mod.check_single_persister, "app/api/v1/risk.py", src)
    assert len(v) >= 2


def test_single_persister_allows_reads_and_service():
    reads = (
        "from sqlalchemy import select\n"
        "from app.db.models.risk_loss_control_state import RiskLossControlState\n"
        "def f(session):\n"
        "    return session.scalar(select(RiskLossControlState))\n"  # a READ — allowed everywhere
    )
    assert _run_one(mod.check_single_persister, "app/risk/loss_control/gate.py", reads) == []
    # The same writes ARE allowed inside the transition service.
    writes = (
        "from app.db.models.risk_control_event import RiskControlEvent\n"
        "def f(session):\n"
        "    session.add(RiskControlEvent(account_id=1))\n"
    )
    assert _run_one(mod.check_single_persister, mod.SERVICE, writes) == []


# --------------------------------------------------------------- §2 gate only via engine


def test_gate_flags_import_outside_engine_even_aliased():
    src = "from app.risk.loss_control.gate import LossControlGate as G\ndef f(): return G\n"
    v = _run_one(mod.check_gate_only_via_engine, "app/orders/router.py", src)
    assert _invariants(v) == {"gate-only-via-engine"}  # aliasing does not evade the check


def test_gate_allows_engine_and_gate_module():
    src = "from app.risk.loss_control.gate import LossControlGate\n"
    assert _run_one(mod.check_gate_only_via_engine, mod.ENGINE, src) == []
    assert _run_one(mod.check_gate_only_via_engine, mod.GATE, src) == []


# --------------------------------------------------------------- §6 sanctioned trigger placement (PR6)


def test_recovery_trigger_allowed_in_coordinator():
    src = "from app.risk.loss_control.state_machine import TRIGGER_RECOVERY_REQUEST\n"
    assert _run_one(mod.check_sanctioned_trigger_placement,
                    "app/risk/loss_control/recovery.py", src) == []


def test_recovery_trigger_forbidden_in_engine_and_api():
    src = ("from app.risk.loss_control.state_machine import TRIGGER_PREFLIGHT_PASS\n"
           "def f(): return TRIGGER_PREFLIGHT_PASS\n")
    assert _invariants(_run_one(mod.check_sanctioned_trigger_placement,
                                "app/risk/engine.py", src)) == {"sanctioned-trigger-placement"}
    assert _invariants(_run_one(mod.check_sanctioned_trigger_placement,
                                "app/api/v1/risk.py", src)) == {"sanctioned-trigger-placement"}


def test_rearm_trigger_forbidden_outside_sanctioned_homes():
    src = ("from app.risk.loss_control.state_machine import TRIGGER_COOLDOWN_COMPLETE\n"
           "def f(): return TRIGGER_COOLDOWN_COMPLETE\n")
    # The recovery coordinator, the engine, and API handlers may NOT touch the re-arm triggers.
    for rel in ("app/risk/loss_control/recovery.py", "app/risk/engine.py", "app/api/v1/risk.py"):
        assert _invariants(_run_one(mod.check_sanctioned_trigger_placement, rel, src)) == {
            "sanctioned-trigger-placement"
        }


def test_rearm_trigger_allowed_in_state_machine_and_cooldown_evaluator():
    # PR7: the state-machine definition DEFINES them, and the dedicated cooldown evaluator is the one
    # job allowed to map an §D1.4 verdict onto a transition.
    src = ("from app.risk.loss_control.state_machine import TRIGGER_HEALTH_REGRESSED\n"
           "def f(): return TRIGGER_HEALTH_REGRESSED\n")
    assert _run_one(mod.check_sanctioned_trigger_placement,
                    "app/risk/loss_control/state_machine.py", src) == []
    assert _run_one(mod.check_sanctioned_trigger_placement,
                    "app/risk/loss_control/cooldown.py", src) == []


# --------------------------------------------------------------- §3 no duplicate classifier


def test_classifier_flags_import_in_loss_control():
    src = "from app.risk.risk_effect import classify\n"
    v = _run_one(mod.check_no_duplicate_classifier, "app/risk/loss_control/gate.py", src)
    assert _invariants(v) == {"no-duplicate-classifier"}


def test_classifier_does_not_flag_market_session_classify():
    # The bare market-session `.classify(...)` call must NOT be flagged (the false positive AST fixes).
    src = "def f(ms, now):\n    return ms.classify(now)\n"
    assert _run_one(mod.check_no_duplicate_classifier, "app/risk/loss_control/session_baseline.py", src) == []


def test_classifier_boundary_only_applies_to_loss_control():
    src = "from app.risk.risk_effect import classify\n"  # the ENGINE is allowed to import it
    assert _run_one(mod.check_no_duplicate_classifier, mod.ENGINE, src) == []


# --------------------------------------------------------------- §4 no implicit bootstrap


def test_bootstrap_flags_get_state_row_at_the_seam():
    src = "def f(svc):\n    return svc.get_state_row(1)\n"
    assert _invariants(_run_one(mod.check_no_implicit_bootstrap, mod.ENGINE, src)) == {"no-implicit-bootstrap"}
    assert _invariants(_run_one(mod.check_no_implicit_bootstrap, mod.GATE, src)) == {"no-implicit-bootstrap"}


def test_bootstrap_allows_load_state_row_and_service():
    src = "def f(svc):\n    return svc.load_state_row(1)\n"
    assert _run_one(mod.check_no_implicit_bootstrap, mod.GATE, src) == []
    # get_state_row is fine inside the service (its home) and admin/tests.
    assert _run_one(mod.check_no_implicit_bootstrap, mod.SERVICE, "def f(s): return s.get_state_row(1)\n") == []


# --------------------------------------------------------------- §5 no recovery triggers in engine


def test_recovery_trigger_flagged_in_engine():
    src = (
        "from app.risk.loss_control.state_machine import TRIGGER_RECOVERY_REQUEST\n"
        "def f():\n    return TRIGGER_RECOVERY_REQUEST\n"
    )
    assert _invariants(_run_one(mod.check_no_recovery_triggers_in_engine, mod.ENGINE, src)) == {
        "no-recovery-triggers"
    }


def test_recovery_trigger_string_flagged_in_engine():
    src = "x = 'COOLDOWN_EXPIRED'\n"
    assert _run_one(mod.check_no_recovery_triggers_in_engine, mod.ENGINE, src)


def test_sanctioned_triggers_allowed_in_engine():
    src = (
        "from app.risk.loss_control.state_machine import "
        "TRIGGER_DAILY_LOSS_BREACH, TRIGGER_BREAKER_TRIP\n"
        "def f():\n    return TRIGGER_DAILY_LOSS_BREACH, TRIGGER_BREAKER_TRIP\n"
    )
    assert _run_one(mod.check_no_recovery_triggers_in_engine, mod.ENGINE, src) == []


def test_recovery_triggers_only_checked_in_engine():
    # state_machine.py legitimately DEFINES the recovery triggers — must not be flagged.
    src = "TRIGGER_RECOVERY_REQUEST = 'RECOVERY_REQUEST'\n"
    assert _run_one(mod.check_no_recovery_triggers_in_engine, "app/risk/loss_control/state_machine.py", src) == []


# ============================================================ AST-evasion hardening (review round 2)


def test_single_persister_catches_aliased_model_constructor():
    src = (
        "from app.db.models.risk_loss_control_state import RiskLossControlState as StateRow\n"
        "def f():\n    return StateRow(account_id=1)\n"  # aliased constructor
    )
    v = _run_one(mod.check_single_persister, "app/api/v1/risk.py", src)
    assert _invariants(v) == {"single-persister"}


def test_single_persister_catches_module_qualified_constructor():
    src = (
        "import app.db.models.risk_loss_control_state as state_model\n"
        "def f():\n    return state_model.RiskLossControlState(account_id=1)\n"  # module-qualified
    )
    v = _run_one(mod.check_single_persister, "app/services/foo.py", src)
    assert _invariants(v) == {"single-persister"}


def test_single_persister_catches_aliased_model_in_write_ops():
    src = (
        "from sqlalchemy import update, delete\n"
        "from app.db.models.risk_loss_control_state import RiskLossControlState as S\n"
        "import app.db.models.risk_control_event as events\n"
        "def f(session):\n"
        "    session.execute(update(S).values(x=1))\n"  # aliased model in update
        "    session.execute(delete(events.RiskControlEvent))\n"  # module-qualified in delete
    )
    v = _run_one(mod.check_single_persister, "app/services/foo.py", src)
    assert len(v) >= 2 and _invariants(v) == {"single-persister"}


def test_single_persister_catches_direct_state_mutation():
    src = (
        "from app.db.models.risk_loss_control_state import RiskLossControlState\n"
        "def f():\n"
        "    row = RiskLossControlState(account_id=1)\n"  # constructor (also flagged)
        "    row.state = 'NORMAL'\n"  # the most obvious forbidden write — .state on the instance
    )
    v = _run_one(mod.check_single_persister, "app/api/v1/risk.py", src)
    details = [x.detail for x in v]
    assert any("mutates .state" in d for d in details)


def test_single_persister_catches_state_mutation_on_annotated_param():
    src = (
        "from app.db.models.risk_loss_control_state import RiskLossControlState\n"
        "def f(row: RiskLossControlState):\n"  # received instance, no constructor in-file
        "    row.state = 'INTEGRITY_STOP'\n"
        "    row.state_version = 9\n"
    )
    v = _run_one(mod.check_single_persister, "app/services/foo.py", src)
    details = [x.detail for x in v]
    assert any("mutates .state" in d for d in details)
    assert any(".state_version" in d for d in details)


def test_single_persister_does_not_flag_unrelated_dot_state():
    # ``.state`` on a non-model object (very common) must NOT be flagged.
    src = "def f(strategy):\n    strategy.state = 'IDLE'\n    return strategy\n"
    assert _run_one(mod.check_single_persister, "app/services/foo.py", src) == []


def test_gate_catches_module_import_and_factory_pattern():
    src = (
        "import app.risk.loss_control.gate as lc_gate\n"  # module import — itself the violation
        "def f():\n"
        "    Gate = lc_gate.LossControlGate\n"  # factory/reference pattern
        "    return Gate\n"
    )
    v = _run_one(mod.check_gate_only_via_engine, "app/orders/router.py", src)
    assert _invariants(v) == {"gate-only-via-engine"}


def test_classifier_catches_plain_module_import():
    src = (
        "import app.risk.risk_effect as re\n"
        "def f(snap, action):\n    return re.classify(snap, action)\n"  # qualified call via module import
    )
    v = _run_one(mod.check_no_duplicate_classifier, "app/risk/loss_control/service.py", src)
    assert _invariants(v) == {"no-duplicate-classifier"}


def test_classifier_catches_decision_service_module_import():
    src = "import app.risk.decision_service\n"
    v = _run_one(mod.check_no_duplicate_classifier, "app/risk/loss_control/gate.py", src)
    assert _invariants(v) == {"no-duplicate-classifier"}
