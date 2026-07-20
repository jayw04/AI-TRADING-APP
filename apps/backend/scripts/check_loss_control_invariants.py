"""ADR 0043 PR5 — structural invariants for the loss-control architecture (AST-based).

Five load-bearing properties the PR1–PR4 increments established, enforced structurally so a future
change cannot silently re-introduce the failure modes they closed. **Disabling any of these requires
an ADR.** They are checked with the Python AST — not grep — so aliased and module-qualified imports,
multi-line calls, and docstring/comment mentions are handled correctly (a name in a docstring is not
a violation; ``from ... import Model as X`` / ``import ... as m; m.Model(...)`` still are).

  1. SINGLE-PERSISTER (§D1.1). Only ``app/risk/loss_control/service.py`` performs runtime writes to
     the ``risk_loss_control_state`` / ``risk_control_events`` tables — including via aliased or
     module-qualified model references, and direct mutation of the materialized ``.state`` /
     ``.state_version`` / ``.last_sequence_no`` on a model instance. Reads are unrestricted.
  2. GATE ONLY THROUGH THE ENGINE. ``LossControlGate`` is imported (in any form) or constructed only
     in ``app/risk/engine.py`` (and its own module) — one authoritative decision seam. Importing the
     gate module outside the allowlist is itself the violation (a factory/reference pattern can't
     evade it).
  3. NO DUPLICATE REDUCTION CLASSIFIER. Code under ``app/risk/loss_control/`` never imports the
     ADR 0042 verified-reduction machinery in any form (``from app.risk.risk_effect import ...`` or
     ``import app.risk.risk_effect``, likewise ``decision_service``) nor calls its distinctive
     symbols. The verdict is computed once by the engine and passed into ``order_outcome_for_state``.
  4. NO IMPLICIT BOOTSTRAP AT THE DECISION SEAM. ``app/risk/engine.py`` and the gate never call
     ``get_state_row`` (which may bootstrap NORMAL); the decision path uses ``load_state_row`` so a
     missing state fails closed to INTEGRITY_STOP instead of being silently created.
  5. NO RECOVERY / RE-ARM TRIGGERS IN THE ENGINE. Until PR6/PR7 land, ``app/risk/engine.py`` may
     reference only the sanctioned live triggers (DAILY_LOSS_BREACH, BREAKER_TRIP) — never the
     recovery / re-arm triggers — so recovery policy cannot leak into the order path early.

Runs from ``apps/backend``:  python scripts/check_loss_control_invariants.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

# Repo-relative (posix) paths used in allowlists.
SERVICE = "app/risk/loss_control/service.py"
ENGINE = "app/risk/engine.py"
GATE = "app/risk/loss_control/gate.py"
RECOVERY = "app/risk/loss_control/recovery.py"
STATE_MACHINE = "app/risk/loss_control/state_machine.py"
LOSS_CONTROL_PKG = "app/risk/loss_control/"
STATE_MODELS = "app/db/models/risk_loss_control_state.py"
EVENT_MODELS = "app/db/models/risk_control_event.py"
THIS_SCRIPT = "scripts/check_loss_control_invariants.py"

# The two state-machine tables (§D1.1) and their model classes.
STATE_TABLES = {"risk_loss_control_state", "risk_control_events"}
STATE_MODEL_NAMES = {"RiskLossControlState", "RiskControlEvent"}
WRITE_FUNCS = {"insert", "sqlite_insert", "update", "delete"}
STATE_WRITE_ATTRS_UNCONDITIONAL = {"state_version", "last_sequence_no"}  # distinctive columns
STATE_WRITE_ATTR_INSTANCE = "state"  # generic — only flagged on a resolved model instance
_SQL_WRITE_KEYWORDS = ("insert", "update", "delete")

# §2 — the authoritative gate module.
GATE_MODULE = "app.risk.loss_control.gate"

# §3 — the ADR 0042 classifier machinery loss_control/ must not reach for.
FORBIDDEN_LC_MODULES = ("app.risk.risk_effect", "app.risk.decision_service")
FORBIDDEN_IMPORT_NAMES = {"classify", "RiskDecisionService", "permits_while_locked",
                          "_permits_verified_reduction"}
# A bare ``classify(...)`` is the market-session classifier; ``decide(...)`` is too generic — so the
# CALL check is narrowed to distinctive names. The import boundary above is the real enforcement.
FORBIDDEN_CALL_NAMES = {"RiskDecisionService", "permits_while_locked", "_permits_verified_reduction"}

# §5 — recovery / re-arm triggers forbidden in the engine (identifiers + string spellings).
FORBIDDEN_ENGINE_TRIGGER_NAMES = {
    "TRIGGER_RECOVERY_REQUEST", "TRIGGER_PREFLIGHT_PASS", "TRIGGER_PREFLIGHT_FAIL",
    "TRIGGER_COOLDOWN_COMPLETE", "TRIGGER_HEALTH_REGRESSED",
}
FORBIDDEN_ENGINE_TRIGGER_STRINGS = {
    "RECOVERY_REQUEST", "RECOVERY_REQUESTED", "PREFLIGHT_PASS", "RECOVERY_PREFLIGHT_PASS",
    "PREFLIGHT_FAIL", "RECOVERY_PREFLIGHT_FAIL", "COOLDOWN_COMPLETE", "COOLDOWN_EXPIRED",
    "HEALTH_REGRESSED", "REARM",
}

# §6 — SANCTIONED trigger placement (PR6). The recovery triggers are now legitimate, but only in the
# recovery coordinator, the transition service, and the state-machine definition — not scattered
# across the app (the engine, API handlers, jobs). The re-arm triggers stay confined to the
# state-machine definition until PR7 wires them.
RECOVERY_TRIGGER_NAMES = {"TRIGGER_RECOVERY_REQUEST", "TRIGGER_PREFLIGHT_PASS", "TRIGGER_PREFLIGHT_FAIL"}
REARM_TRIGGER_NAMES = {"TRIGGER_COOLDOWN_COMPLETE", "TRIGGER_HEALTH_REGRESSED"}


def _recovery_trigger_allowed(rel: str) -> bool:
    return rel in (RECOVERY, SERVICE, STATE_MACHINE)


def _rearm_trigger_allowed(rel: str) -> bool:
    return rel == STATE_MACHINE


@dataclass(frozen=True)
class Violation:
    invariant: str
    path: str
    line: int
    detail: str


def _rel(p: Path) -> str:
    return p.relative_to(BACKEND).as_posix()


def _is_test(rel: str) -> bool:
    return "/tests/" in rel or rel.startswith("tests/")


def _func_name(node: ast.Call) -> str:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return ""


# --------------------------------------------------------------------- import / instance resolution


def _model_class_localnames(tree: ast.AST) -> set[str]:
    """Local names bound to a state-model CLASS via ``from ... import Model [as Alias]``."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in STATE_MODEL_NAMES:
                    names.add(a.asname or a.name)
    return names


def _is_model_ref(node: ast.expr, localnames: set[str]) -> bool:
    """Does ``node`` reference a state-model class — direct, aliased, or module-qualified?

    Catches ``RiskLossControlState``, an aliased ``StateRow`` (localnames), and any
    ``<anything>.RiskLossControlState`` (module-qualified) — no legitimate non-model symbol is
    literally named ``.RiskLossControlState`` / ``.RiskControlEvent``."""
    if isinstance(node, ast.Name):
        return node.id in STATE_MODEL_NAMES or node.id in localnames
    if isinstance(node, ast.Attribute):
        return node.attr in STATE_MODEL_NAMES
    return False


def _state_instance_vars(tree: ast.AST, localnames: set[str]) -> set[str]:
    """Local names known to hold a state-model INSTANCE: assigned from a constructor, or a
    parameter / annotated variable typed as a state model. Used to catch ``row.state = ...``."""
    vars_: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign) and isinstance(node.value, ast.Call) and _is_model_ref(
            node.value.func, localnames
        ):
            for t in node.targets:
                if isinstance(t, ast.Name):
                    vars_.add(t.id)
        elif isinstance(node, ast.AnnAssign) and node.annotation is not None and _is_model_ref(
            node.annotation, localnames
        ):
            if isinstance(node.target, ast.Name):
                vars_.add(node.target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            for arg in [*node.args.posonlyargs, *node.args.args, *node.args.kwonlyargs]:
                if arg.annotation is not None and _is_model_ref(arg.annotation, localnames):
                    vars_.add(arg.arg)
    return vars_


def _attr_root(node: ast.Attribute) -> str | None:
    return node.value.id if isinstance(node.value, ast.Name) else None


def _is_raw_sql_write(value: str) -> str | None:
    """Return the table name if ``value`` is raw SQL WRITING a state table, else None (a docstring
    that merely mentions the table has no INSERT/UPDATE/DELETE keyword, so it is not flagged)."""
    low = value.lower()
    if not any(kw in low for kw in _SQL_WRITE_KEYWORDS):
        return None
    for table in STATE_TABLES:
        if table in value:
            return table
    return None


# --------------------------------------------------------------------- the five checks


def check_single_persister(rel: str, tree: ast.AST) -> list[Violation]:
    """§1 — only service.py may WRITE the two state-machine tables (reads are fine everywhere)."""
    if rel in (SERVICE, STATE_MODELS, EVENT_MODELS, THIS_SCRIPT) or _is_test(rel) or "/alembic/" in rel:
        return []
    localnames = _model_class_localnames(tree)
    state_vars = _state_instance_vars(tree, localnames)
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if _is_model_ref(node.func, localnames):
                out.append(Violation("single-persister", rel, node.lineno,
                                     "constructs a state-machine model outside the transition service"))
            elif _func_name(node) in WRITE_FUNCS and node.args and _is_model_ref(
                node.args[0], localnames
            ):
                out.append(Violation("single-persister", rel, node.lineno,
                                     f"{_func_name(node)}() targets a state-machine table outside the service"))
        elif isinstance(node, (ast.Assign, ast.AugAssign, ast.AnnAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if not isinstance(t, ast.Attribute):
                    continue
                if t.attr in STATE_WRITE_ATTRS_UNCONDITIONAL:
                    out.append(Violation("single-persister", rel, node.lineno,
                                         f"assigns .{t.attr} outside the transition service"))
                elif t.attr == STATE_WRITE_ATTR_INSTANCE and _attr_root(t) in state_vars:
                    out.append(Violation("single-persister", rel, node.lineno,
                                         "mutates .state on a state-machine model outside the service"))
        elif isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value in STATE_TABLES:
                out.append(Violation("single-persister", rel, node.lineno,
                                     f"references table {node.value!r} outside the service"))
            else:
                table = _is_raw_sql_write(node.value)
                if table is not None:
                    out.append(Violation("single-persister", rel, node.lineno,
                                         f"raw SQL writes table {table!r} outside the service"))
    return out


def check_gate_only_via_engine(rel: str, tree: ast.AST) -> list[Violation]:
    """§2 — the gate is imported (any form) or constructed only in engine.py (+ its module, tests)."""
    if rel in (ENGINE, GATE) or _is_test(rel):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(GATE_MODULE):
            for a in node.names:
                if a.name == "LossControlGate":
                    out.append(Violation("gate-only-via-engine", rel, node.lineno,
                                         "imports LossControlGate outside the engine"))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if a.name == GATE_MODULE or a.name.startswith(GATE_MODULE + "."):
                    out.append(Violation("gate-only-via-engine", rel, node.lineno,
                                         "imports the gate module outside the engine"))
        elif isinstance(node, ast.Call) and _func_name(node) == "LossControlGate":
            out.append(Violation("gate-only-via-engine", rel, node.lineno,
                                 "constructs LossControlGate outside the engine"))
    return out


def check_no_duplicate_classifier(rel: str, tree: ast.AST) -> list[Violation]:
    """§3 — loss_control/ must not import (any form) or call the ADR 0042 classifier machinery."""
    if not rel.startswith(LOSS_CONTROL_PKG) or _is_test(rel):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(mod.startswith(m) for m in FORBIDDEN_LC_MODULES):
                out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                     f"loss_control/ imports from {mod} (reuse the engine's verdict)"))
            for a in node.names:
                if a.name in FORBIDDEN_IMPORT_NAMES:
                    out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                         f"loss_control/ imports {a.name} (reuse the engine's verdict)"))
        elif isinstance(node, ast.Import):
            for a in node.names:
                if any(a.name == m or a.name.startswith(m + ".") for m in FORBIDDEN_LC_MODULES):
                    out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                         f"loss_control/ imports module {a.name} (reuse the engine's verdict)"))
        elif isinstance(node, ast.Call) and _func_name(node) in FORBIDDEN_CALL_NAMES:
            out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                 f"loss_control/ calls {_func_name(node)}() (reuse the engine's verdict)"))
    return out


def check_no_implicit_bootstrap(rel: str, tree: ast.AST) -> list[Violation]:
    """§4 — the decision seam (engine.py + gate.py) must use load_state_row, never get_state_row."""
    if rel not in (ENGINE, GATE):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) and (
            node.func.attr == "get_state_row"
        ):
            out.append(Violation("no-implicit-bootstrap", rel, node.lineno,
                                 "calls get_state_row (may bootstrap NORMAL) — use load_state_row"))
    return out


def check_no_recovery_triggers_in_engine(rel: str, tree: ast.AST) -> list[Violation]:
    """§5 — engine.py may reference only the sanctioned live triggers, never recovery / re-arm."""
    if rel != ENGINE:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and node.id in FORBIDDEN_ENGINE_TRIGGER_NAMES:
            out.append(Violation("no-recovery-triggers", rel, node.lineno,
                                 f"engine references recovery/re-arm trigger {node.id} (PR6/PR7 only)"))
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                if a.name in FORBIDDEN_ENGINE_TRIGGER_NAMES:
                    out.append(Violation("no-recovery-triggers", rel, node.lineno,
                                         f"engine imports recovery/re-arm trigger {a.name} (PR6/PR7 only)"))
        elif isinstance(node, ast.Constant) and node.value in FORBIDDEN_ENGINE_TRIGGER_STRINGS:
            out.append(Violation("no-recovery-triggers", rel, node.lineno,
                                 f"engine references recovery/re-arm trigger {node.value!r} (PR6/PR7 only)"))
    return out


def check_sanctioned_trigger_placement(rel: str, tree: ast.AST) -> list[Violation]:
    """§6 — recovery triggers only in the coordinator/service/state-machine; re-arm triggers only in
    the state-machine (until PR7). Tests exempt. A reference is a Name or an ImportFrom name."""
    if _is_test(rel):
        return []
    rec_ok = _recovery_trigger_allowed(rel)
    rearm_ok = _rearm_trigger_allowed(rel)
    out: list[Violation] = []

    def _flag(name: str, line: int) -> None:
        if name in RECOVERY_TRIGGER_NAMES and not rec_ok:
            out.append(Violation("sanctioned-trigger-placement", rel, line,
                                 f"{name} referenced outside the recovery coordinator/service/state-machine"))
        elif name in REARM_TRIGGER_NAMES and not rearm_ok:
            out.append(Violation("sanctioned-trigger-placement", rel, line,
                                 f"{name} referenced outside the state-machine (re-arm is PR7)"))

    for node in ast.walk(tree):
        if isinstance(node, ast.Name):
            _flag(node.id, node.lineno)
        elif isinstance(node, ast.ImportFrom):
            for a in node.names:
                _flag(a.name, node.lineno)
    return out


CHECKS = (
    check_single_persister,
    check_gate_only_via_engine,
    check_no_duplicate_classifier,
    check_no_implicit_bootstrap,
    check_no_recovery_triggers_in_engine,
    check_sanctioned_trigger_placement,
)


def run(paths: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for p in paths:
        rel = _rel(p)
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as exc:  # a real parse failure — surface it, do not swallow
            violations.append(Violation("parse-error", rel, exc.lineno or 0, str(exc)))
            continue
        for check in CHECKS:
            violations.extend(check(rel, tree))
    return violations


def main() -> int:
    paths = sorted(APP.rglob("*.py"))
    violations = run(paths)
    if violations:
        print("ADR 0043 loss-control invariant VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  [{v.invariant}] {v.path}:{v.line} — {v.detail}", file=sys.stderr)
        print(
            "\nEach protects a property PR1–PR4 established. Disabling one requires an ADR.",
            file=sys.stderr,
        )
        return 1
    print("ADR 0043 loss-control invariants OK (single-persister, gate-only-via-engine, "
          "no-duplicate-classifier, no-implicit-bootstrap, no-recovery-triggers, "
          "sanctioned-trigger-placement)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
