"""ADR 0043 PR5 — structural invariants for the loss-control architecture (AST-based).

Five load-bearing properties the PR1–PR4 increments established, enforced structurally so a future
change cannot silently re-introduce the failure modes they closed. **Disabling any of these requires
an ADR.** They are checked with the Python AST — not grep — so aliased imports, multi-line calls,
and docstring/comment mentions are handled correctly (a name in a docstring is not a violation; an
aliased import of a forbidden symbol still is).

  1. SINGLE-PERSISTER (§D1.1). Only ``app/risk/loss_control/service.py`` performs runtime writes to
     the ``risk_loss_control_state`` / ``risk_control_events`` tables. The transition service is the
     sole persistence authority; reads are unrestricted (the gate must load state).
  2. GATE ONLY THROUGH THE ENGINE. ``LossControlGate`` is imported / constructed only in
     ``app/risk/engine.py`` (and its own module) — one authoritative decision seam, never a second
     one in the router, breaker, API, jobs, or recovery code.
  3. NO DUPLICATE REDUCTION CLASSIFIER. Code under ``app/risk/loss_control/`` never imports or calls
     the ADR 0042 verified-reduction machinery (``risk_effect.classify``, ``RiskDecisionService``,
     the engine's ``_permits_verified_reduction``). The verdict is computed once by the engine and
     passed into the pure ``order_outcome_for_state``.
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
LOSS_CONTROL_PKG = "app/risk/loss_control/"
STATE_MODELS = "app/db/models/risk_loss_control_state.py"
EVENT_MODELS = "app/db/models/risk_control_event.py"
THIS_SCRIPT = "scripts/check_loss_control_invariants.py"

# The two state-machine tables (§D1.1) and their model classes.
STATE_TABLES = {"risk_loss_control_state", "risk_control_events"}
STATE_MODEL_NAMES = {"RiskLossControlState", "RiskControlEvent"}
WRITE_FUNCS = {"insert", "sqlite_insert", "update", "delete"}
STATE_WRITE_ATTRS = {"state_version", "last_sequence_no"}
_SQL_WRITE_KEYWORDS = ("insert", "update", "delete")  # to spot raw SQL, not docstrings


def _is_raw_sql_write(value: str) -> str | None:
    """Return the table name if ``value`` is raw SQL WRITING a state table, else None.

    Matches a string that names a state table AND contains a SQL write keyword — so a docstring that
    merely mentions the table (no INSERT/UPDATE/DELETE) is not a false positive."""
    low = value.lower()
    if not any(kw in low for kw in _SQL_WRITE_KEYWORDS):
        return None
    for table in STATE_TABLES:
        if table in value:
            return table
    return None

# §3 — the ADR 0042 classifier machinery loss_control/ must not reach for. The IMPORT boundary is
# the real enforcement: you cannot use ``risk_effect.classify`` or ``RiskDecisionService`` without
# importing it. So the import checks (module + name) below are comprehensive; the CALL check is
# narrowed to DISTINCTIVE names only — a bare ``classify(...)`` is the market-session classifier, not
# ADR 0042's, and ``decide(...)`` is too generic to flag on the name alone.
FORBIDDEN_IN_LOSS_CONTROL_MODULES = ("app.risk.risk_effect", "app.risk.decision_service")
FORBIDDEN_IMPORT_NAMES = {
    "classify",
    "RiskDecisionService",
    "permits_while_locked",
    "_permits_verified_reduction",
}
FORBIDDEN_CALL_NAMES = {
    "RiskDecisionService",
    "permits_while_locked",
    "_permits_verified_reduction",
}

# §5 — recovery / re-arm triggers forbidden in the engine (identifiers + string spellings).
FORBIDDEN_ENGINE_TRIGGER_NAMES = {
    "TRIGGER_RECOVERY_REQUEST",
    "TRIGGER_PREFLIGHT_PASS",
    "TRIGGER_PREFLIGHT_FAIL",
    "TRIGGER_COOLDOWN_COMPLETE",
    "TRIGGER_HEALTH_REGRESSED",
}
FORBIDDEN_ENGINE_TRIGGER_STRINGS = {
    "RECOVERY_REQUEST", "RECOVERY_REQUESTED",
    "PREFLIGHT_PASS", "RECOVERY_PREFLIGHT_PASS",
    "PREFLIGHT_FAIL", "RECOVERY_PREFLIGHT_FAIL",
    "COOLDOWN_COMPLETE", "COOLDOWN_EXPIRED",
    "HEALTH_REGRESSED", "REARM",
}


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


def _first_arg_name(node: ast.Call) -> str | None:
    if node.args and isinstance(node.args[0], ast.Name):
        return node.args[0].id
    return None


# --------------------------------------------------------------------- the five checks


def check_single_persister(rel: str, tree: ast.AST) -> list[Violation]:
    """§1 — only service.py may WRITE the two state-machine tables (reads are fine everywhere)."""
    if rel in (SERVICE, STATE_MODELS, EVENT_MODELS, THIS_SCRIPT) or _is_test(rel) or "/alembic/" in rel:
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        # Model instantiation: RiskLossControlState(...) / RiskControlEvent(...).
        if isinstance(node, ast.Call) and _func_name(node) in STATE_MODEL_NAMES and isinstance(
            node.func, ast.Name
        ):
            out.append(Violation("single-persister", rel, node.lineno,
                                  f"constructs {_func_name(node)} outside the transition service"))
        # Write ops: insert/update/delete(RiskLossControlState|RiskControlEvent).
        elif isinstance(node, ast.Call) and _func_name(node) in WRITE_FUNCS and (
            _first_arg_name(node) in STATE_MODEL_NAMES
        ):
            out.append(Violation("single-persister", rel, node.lineno,
                                  f"{_func_name(node)}() targets a state-machine table outside the service"))
        # Direct writes to the CAS/sequence columns.
        elif isinstance(node, (ast.Assign, ast.AugAssign)):
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                if isinstance(t, ast.Attribute) and t.attr in STATE_WRITE_ATTRS:
                    out.append(Violation("single-persister", rel, node.lineno,
                                         f"assigns .{t.attr} outside the transition service"))
        # Bare table-name string (e.g. a table= kwarg) or raw SQL writing the table.
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
    """§2 — LossControlGate imported/constructed only in engine.py (+ its own module, tests)."""
    if rel in (ENGINE, GATE) or _is_test(rel):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        # Import of the symbol (survives aliasing — we check the imported name, not the asname).
        if isinstance(node, ast.ImportFrom) and (node.module or "").startswith(
            "app.risk.loss_control.gate"
        ):
            for a in node.names:
                if a.name == "LossControlGate":
                    out.append(Violation("gate-only-via-engine", rel, node.lineno,
                                         "imports LossControlGate outside the engine"))
        # Direct construction.
        elif isinstance(node, ast.Call) and _func_name(node) == "LossControlGate":
            out.append(Violation("gate-only-via-engine", rel, node.lineno,
                                 "constructs LossControlGate outside the engine"))
    return out


def check_no_duplicate_classifier(rel: str, tree: ast.AST) -> list[Violation]:
    """§3 — loss_control/ must not import/call the ADR 0042 reduction classifier machinery."""
    if not rel.startswith(LOSS_CONTROL_PKG) or _is_test(rel):
        return []
    out: list[Violation] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if any(mod.startswith(m) for m in FORBIDDEN_IN_LOSS_CONTROL_MODULES):
                out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                     f"loss_control/ imports from {mod} (reuse the engine's verdict)"))
            for a in node.names:
                if a.name in FORBIDDEN_IMPORT_NAMES:
                    out.append(Violation("no-duplicate-classifier", rel, node.lineno,
                                         f"loss_control/ imports {a.name} (reuse the engine's verdict)"))
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


CHECKS = (
    check_single_persister,
    check_gate_only_via_engine,
    check_no_duplicate_classifier,
    check_no_implicit_bootstrap,
    check_no_recovery_triggers_in_engine,
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
          "no-duplicate-classifier, no-implicit-bootstrap, no-recovery-triggers)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
