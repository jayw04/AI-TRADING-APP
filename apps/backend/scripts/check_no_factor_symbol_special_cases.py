"""CI invariant: NO TICKER MAY BE SPECIAL-CASED IN THE FACTOR REFRESH / READINESS PATH.

WHY. The adjudication design is that every stale name reaches a verdict through EVIDENCE and
the shared rule in ``factor_adjudication.py``. Twice now the cheapest apparent repair has been
to name a symbol instead: ``EA`` needed a hand-added evidence record on 2026-08-17, and
``WBS`` halted the 06:00 ET refresh on 2026-08-25, 08-26 and 08-27, freezing the live store at
SEP ``2026-08-21``. On each of those mornings, an ``if ticker == "..."`` in the refresh path
would have restored publication immediately.

It would also have left an exemption that nothing measures. The exemption ceiling
(:func:`factor_adjudication.exemption_ceiling`) bounds attribution that goes THROUGH
adjudication — 5% of the pool, above which the whole run's attribution is voided as a
suppressed outage. A branch in a shell script or a literal in a Python condition is invisible
to that ceiling, absent from every report, and counted in no denominator. It is an exemption
no operator can audit and no future reader can find.

So the rule is absolute: EA, WBS, and whatever the next name turns out to be must flow through
evidence and adjudication, or not be excused at all.

WHAT THIS CHECKS. Short, all-uppercase STRING LITERALS in the executable lines of the factor
refresh and readiness path — the shape every plausible exemption takes. Comments and
docstrings are exempt: this file and the code it guards discuss
EA and WBS at length, and prose naming a defect is the opposite of a hidden exemption.

Run: ``python apps/backend/scripts/check_no_factor_symbol_special_cases.py``
Exit 0 = clean; exit 1 = a ticker literal reached the path.
"""

from __future__ import annotations

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]

#: Where a symbol exemption could hide: the two consumers, the shared rule, the evidence
#: generator, and the shell wrappers that drive them.
GUARDED = [
    "deploy/aws/factor-refresh.sh",
    "deploy/aws/factor-freshness.sh",
    "apps/backend/scripts/factor_refresh.py",
    "apps/backend/scripts/factor_adjudication.py",
    "apps/backend/scripts/factor_evidence.py",
]

#: A ticker literal is a short, all-uppercase STRING LITERAL: ``"WBS"``, ``'EA'``,
#: ``{"EA", "WBS"}``, ``if sym == "WBS"``. That is the shape every plausible exemption takes,
#: and it is the shape this invariant hunts.
#:
#: ⚠ An earlier version of this check scanned bare WORDS instead, and it was useless: it
#: flagged ``WHERE``, ``GROUP``, ``FROM`` and ``SUM`` out of SQL, ``APP`` and ``IFS`` out of
#: shell, and ``FRESH`` and ``HOLD`` out of the verdict vocabulary — 50+ hits across five
#: files on a tree containing no exemption at all. An invariant that has to be silenced with
#: a fifty-word allowlist is one nobody will keep accurate, and its next real hit gets waved
#: through with the rest. Matching literals keeps it precise: SQL keywords live INSIDE longer
#: query strings and never appear as a standalone short literal, and shell variables are not
#: string literals at all.
TICKER = re.compile(r"^[A-Z]{1,5}(\.[A-Z]{1,2})?$")

#: Quoted short-uppercase literals in a shell file, e.g. ``"EA"`` or ``'WBS'``.
SHELL_LITERAL = re.compile(r"""["']([A-Z]{1,5}(?:\.[A-Z]{1,2})?)["']""")

#: Ticker-shaped tokens that are not tickets to anything: verdict names, field names, log
#: labels, env vars, verbs, keywords. Each is a token this codebase genuinely uses.
#:
#: ⚠ ``SPY`` is here for a substantive reason, not as a carve-out. It is the corroboration
#: CONTROL symbol: the name whose currency PROVES the alternate source was reachable when the
#: observation was taken. A stale control makes the shared rule REFUSE every attribution that
#: rested on it, so naming it can only tighten the gate, never excuse a symbol from it. It is
#: also configurable (``--control-symbol`` / ``DEFAULT_CONTROL_SYMBOL``), so this is a default
#: rather than a hardcoded dependency on one instrument.
ALLOWED = {
    # The corroboration CONTROL — see above. The only instrument name any of these files may
    # contain, and it can only tighten the gate.
    "SPY",
    # Status and verdict literals this path genuinely compares against. None of them is an
    # instrument, and each appears as a standalone literal for a reason unrelated to symbols.
    "OK",
    "PASS",
    "FAIL",
    "FRESH",
    "LIVE",
    "IDLE",
    "PAPER",
    "ERROR",
    # The heredoc delimiter in both shell wrappers (`<<'PY' ... PY`). Not a literal value at
    # all — it is the token that ends the inline python block.
    "PY",
}


def _python_literals(text: str) -> set[str]:
    """Every short-uppercase STRING CONSTANT in the module, docstrings excluded.

    Docstrings are excluded by AST rather than by regex because this codebase documents its
    incidents in them at length: ``factor_evidence.py`` names both EA and WBS in its module
    docstring while describing exactly the behaviour this invariant forbids. Prose about a
    defect must never be mistaken for the defect.
    """
    tree = ast.parse(text)

    docstring_nodes: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", None)
            if (
                body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                docstring_nodes.add(id(body[0].value))

    return {
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Constant)
        and isinstance(node.value, str)
        and id(node) not in docstring_nodes
        and TICKER.match(node.value)
    }


def _shell_literals(text: str) -> set[str]:
    """Every quoted short-uppercase literal in the executable lines of a shell file."""
    return {
        match
        for line in text.splitlines()
        if not line.lstrip().startswith("#")
        for match in SHELL_LITERAL.findall(line)
    }


def scan(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    literals = _python_literals(text) if path.suffix == ".py" else _shell_literals(text)
    return sorted(literals - ALLOWED)


def main() -> int:
    failed = False
    checked = 0
    for rel in GUARDED:
        path = REPO_ROOT / rel
        if not path.exists():
            print(f"FAIL: guarded file is missing: {rel}")
            print("      A guarded path that vanished is an invariant that stopped checking.")
            failed = True
            continue
        checked += 1
        hits = scan(path)
        if hits:
            failed = True
            print(f"FAIL: ticker-shaped literal(s) in the factor path: {rel}")
            for token in hits:
                print(f"        {token}")
            print("      A symbol must reach a verdict through evidence + adjudication, never")
            print("      a branch: a hardcoded name is an exemption the ceiling cannot see.")
            print("      If this is a false positive, add the token to ALLOWED with its reason.")

    if failed:
        print("\ncheck_no_factor_symbol_special_cases: FAILED")
        return 1
    print(f"check_no_factor_symbol_special_cases: OK ({checked} files, no ticker special-cases)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
