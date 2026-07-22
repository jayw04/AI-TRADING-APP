"""ADR 0043 — the settlement-barrier structural invariant for governed harnesses (AST-based).

Phase 0 burned two live attempts on the same mistake: an order was submitted and the next decision
was taken before the local ledger caught up. The fix is the per-order REST barrier — but a barrier
you have to REMEMBER to call is a convention, not an invariant, and conventions are exactly what
fail at 3pm on the second attempt.

So the barrier is structural. Every ADR-0043 harness places orders through ONE seam,
``GovernedSubmitter`` in ``scripts/adr0043_canary_lib.py``, which pairs the submit with the barrier
in a single call. This checker proves no harness can express "submit without settling":

  1. NO DIRECT SUBMIT. No ``scripts/adr0043_*.py`` module other than the seam's own may call
     ``.submit(...)`` on anything — router, adapter, or otherwise. Governed harnesses submit through
     ``GovernedSubmitter.submit_and_settle`` / ``submit_expecting_refusal``.
  2. NO DIRECT BARRIER. No governed harness may import or call ``settle_order`` itself. Calling the
     barrier ad hoc bypasses the evidence record and the SETTLEMENT_BARRIER_FAILED stop, which is
     most of its value — the diagnostics are how a failed attempt gets diagnosed without re-running
     it against a live account.
  3. THE SEAM ACTUALLY SETTLES. ``GovernedSubmitter.submit_and_settle`` must call the barrier, and
     ``submit_expecting_refusal`` must reach it too (for the unexpected-broker-order reconcile).
     Without this the first two rules would be satisfied by a seam that settles nothing.

NOT enforced here, deliberately: the LIVE order path. ``app/`` submits orders and relies on the
trade-updates stream plus ``reconcile_stuck_orders`` — making every production submit block on a
synchronous REST poll would be a significant behavioural change to the order path and needs an ADR,
not a CI script. This invariant governs the ADR-0043 harnesses, which trade deliberately against a
live account with no human watching the ledger.

Disabling any of these requires an ADR.

Runs from ``apps/backend``:  python scripts/check_settlement_barrier.py
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"

# The one module allowed to own the seam — and therefore the only one allowed to submit or settle.
SEAM_MODULE = "adr0043_canary_lib.py"
SEAM_CLASS = "GovernedSubmitter"
# Methods of the seam that must demonstrably reach the barrier.
MUST_SETTLE = ("submit_and_settle", "submit_expecting_refusal")
BARRIER_NAMES = frozenset({"settle_order", "settle_existing", "_settle_impl"})


@dataclass(frozen=True)
class Violation:
    invariant: str
    path: str
    line: int
    detail: str


def governed_files() -> list[Path]:
    """Every ADR-0043 harness module. A glob, not a list, so a NEW harness script is governed the
    moment it is added — opting out would require editing this checker, which is the point."""
    return sorted(SCRIPTS.glob("adr0043_*.py"))


def _calls(tree: ast.AST) -> list[ast.Call]:
    return [n for n in ast.walk(tree) if isinstance(n, ast.Call)]


def _enclosing_class_methods(tree: ast.AST, class_name: str) -> dict[str, ast.AST]:
    out: dict[str, ast.AST] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == class_name:
            for item in node.body:
                if isinstance(item, ast.AsyncFunctionDef | ast.FunctionDef):
                    out[item.name] = item
    return out


def check_no_direct_submit(rel: str, tree: ast.AST) -> list[Violation]:
    """(1) Only the seam module may call ``.submit(...)``."""
    if rel.endswith(SEAM_MODULE):
        return []
    out = []
    for call in _calls(tree):
        fn = call.func
        if isinstance(fn, ast.Attribute) and fn.attr == "submit":
            out.append(Violation(
                "no-direct-submit", rel, call.lineno,
                "calls .submit() directly; ADR-0043 harnesses must place orders through "
                "GovernedSubmitter.submit_and_settle / submit_expecting_refusal so the barrier "
                "cannot be skipped",
            ))
    return out


def check_no_direct_barrier(rel: str, tree: ast.AST) -> list[Violation]:
    """(2) Only the seam module may import or call ``settle_order``."""
    if rel.endswith(SEAM_MODULE):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "settle_order":
                    out.append(Violation(
                        "no-direct-barrier", rel, node.lineno,
                        "imports settle_order; call it through the governed seam so the evidence "
                        "record and the SETTLEMENT_BARRIER_FAILED stop are not bypassed",
                    ))
        elif isinstance(node, ast.Call):
            fn = node.func
            name = fn.id if isinstance(fn, ast.Name) else (
                fn.attr if isinstance(fn, ast.Attribute) else None)
            if name == "settle_order":
                out.append(Violation(
                    "no-direct-barrier", rel, node.lineno,
                    "calls settle_order directly rather than through the governed seam",
                ))
    return out


def check_seam_settles(rel: str, tree: ast.AST) -> list[Violation]:
    """(3) The seam's sanctioned submissions must actually reach the barrier."""
    if not rel.endswith(SEAM_MODULE):
        return []
    methods = _enclosing_class_methods(tree, SEAM_CLASS)
    out = []
    if not methods:
        return [Violation("seam-missing", rel, 0,
                          f"{SEAM_CLASS} not found — the governed submit seam must exist here")]
    for name in MUST_SETTLE:
        node = methods.get(name)
        if node is None:
            out.append(Violation("seam-missing", rel, 0,
                                 f"{SEAM_CLASS}.{name} is missing"))
            continue
        reached = any(
            (isinstance(c.func, ast.Attribute) and c.func.attr in BARRIER_NAMES)
            or (isinstance(c.func, ast.Name) and c.func.id in BARRIER_NAMES)
            for c in _calls(node)
        )
        if not reached:
            out.append(Violation(
                "seam-does-not-settle", rel, node.lineno,
                f"{SEAM_CLASS}.{name} never reaches the barrier ({'/'.join(sorted(BARRIER_NAMES))});"
                f" the seam would satisfy the other rules while settling nothing",
            ))
    return out


CHECKS = (check_no_direct_submit, check_no_direct_barrier, check_seam_settles)


def run(paths: list[Path]) -> list[Violation]:
    violations: list[Violation] = []
    for p in paths:
        rel = p.relative_to(BACKEND).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"), filename=str(p))
        except SyntaxError as exc:
            violations.append(Violation("parse-error", rel, exc.lineno or 0, str(exc)))
            continue
        for check in CHECKS:
            violations.extend(check(rel, tree))
    return violations


def main() -> int:
    paths = governed_files()
    if not paths:
        print("ADR 0043 settlement-barrier invariant: no governed harness modules found",
              file=sys.stderr)
        return 1
    violations = run(paths)
    if violations:
        print("ADR 0043 settlement-barrier invariant VIOLATIONS:", file=sys.stderr)
        for v in violations:
            print(f"  [{v.invariant}] {v.path}:{v.line} — {v.detail}", file=sys.stderr)
        print(
            "\nPhase 0 lost two live attempts to a submit that was not settled before the next "
            "decision. Disabling this requires an ADR.",
            file=sys.stderr,
        )
        return 1
    print(f"ADR 0043 settlement-barrier invariant OK ({len(paths)} governed harness module(s): "
          f"no-direct-submit, no-direct-barrier, seam-settles)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
