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

SCOPE
-----
This invariant applies to ADR-0043 order-placing scripts. It does NOT redefine the production order
lifecycle or require synchronous REST settlement for general application order submission. Any
expansion into production order paths requires separate architectural review and governance.

The boundary is drawn where it is because the ADR-0043 harnesses have an operating condition the
application does not: they place live paper orders, without reliable trade-update ownership, may not
proceed until the prior order is durably reconciled, and must produce an evidence package that
distinguishes refusal from settlement from reconciliation failure from unexpected broker
submission. None of that implies the production router should become synchronous; ``app/`` keeps its
stream-driven reconciliation plus ``reconcile_stuck_orders``.

``scripts/adr0043_*.py`` is a GOVERNED NAMESPACE, not a filename convenience. A new ``adr0043_*.py``
script inherits this requirement automatically the moment it is added; opting out means editing this
checker, which is a reviewable act.

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


def _getattr_literal(call: ast.Call) -> str | None:
    """The constant attribute name in ``getattr(obj, "name")``, if that is what this call is.

    ``fn = getattr(router, "submit")`` is a bypass a reviewer would not notice; resolving it in
    FULL generality is static-analysis overreach (the name can be computed), so the constant-string
    form is rejected outright and the computed form is prohibited by policy, not detection."""
    if not (isinstance(call.func, ast.Name) and call.func.id == "getattr"):
        return None
    if len(call.args) < 2 or not isinstance(call.args[1], ast.Constant):
        return None
    value = call.args[1].value
    return value if isinstance(value, str) else None


def check_no_direct_submit(rel: str, tree: ast.AST) -> list[Violation]:
    """(1) Only the seam module may reach ``.submit``.

    This flags the ATTRIBUTE, not just the call, because the realistic bypass is not
    ``router.submit(req)`` — a reviewer sees that. It is ``submit = router.submit`` three lines
    earlier, and then an innocuous-looking ``await submit(req)``."""
    if rel.endswith(SEAM_MODULE):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute) and node.attr == "submit":
            out.append(Violation(
                "no-direct-submit", rel, node.lineno,
                "references .submit directly (call or alias); ADR-0043 harnesses must place orders "
                "through GovernedSubmitter.submit_and_settle / submit_expecting_refusal so the "
                "barrier cannot be skipped",
            ))
        elif isinstance(node, ast.Call) and _getattr_literal(node) == "submit":
            out.append(Violation(
                "no-direct-submit", rel, node.lineno,
                "extracts .submit via getattr(); routing around the seam dynamically is prohibited",
            ))
    return out


def check_no_direct_barrier(rel: str, tree: ast.AST) -> list[Violation]:
    """(2) Only the seam module may import or reach ``settle_order``.

    The import check keys off the ORIGINAL name, so ``import settle_order as settle`` is caught at
    the import even though every later use reads as an ordinary local call."""
    if rel.endswith(SEAM_MODULE):
        return []
    out = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            for alias in node.names:
                if alias.name == "settle_order":
                    as_note = f" (aliased to {alias.asname})" if alias.asname else ""
                    out.append(Violation(
                        "no-direct-barrier", rel, node.lineno,
                        f"imports settle_order{as_note}; call it through the governed seam so the "
                        f"evidence record and the SETTLEMENT_BARRIER_FAILED stop are not bypassed",
                    ))
        elif isinstance(node, ast.Attribute) and node.attr == "settle_order":
            out.append(Violation(
                "no-direct-barrier", rel, node.lineno,
                "reaches settle_order directly (call or alias) rather than through the seam",
            ))
        elif isinstance(node, ast.Call):
            if _getattr_literal(node) == "settle_order":
                out.append(Violation(
                    "no-direct-barrier", rel, node.lineno,
                    "extracts settle_order via getattr(); routing around the seam dynamically is "
                    "prohibited",
                ))
            elif isinstance(node.func, ast.Name) and node.func.id == "settle_order":
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
