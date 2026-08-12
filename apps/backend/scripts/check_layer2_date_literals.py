"""CI invariant — no ungoverned date literal in the Layer 2 construction toolchain.

## Why this exists

The Layer 2 toolchain was written for one session (2026-07-27) and carried that date as a module
constant in nine scripts. PR #589 parameterized the ones a sweep found. It did not find
`DECISION_WINDOW = (date(2025, 6, 25), date(2026, 7, 27))`, because that sweep looked for *scalar
assignments* and a tuple is not one. Two of the delta builders likewise declared base-corpus facts
(`BASE_COVERAGE_THROUGH`, `BASE_TICKERS_ROWS`, `BASE_MAX_LASTPRICEDATE`) that move whenever a delta is
committed.

The failure mode is the reason this is an invariant rather than a review habit: a tool that silently
uses the previous session's date produces a corpus, a manifest, an attestation and a readiness receipt
that **all agree with one another and are all wrong together**. Every digest is computed over
internally consistent inputs, so no hash catches it and no later gate can distinguish it from a
correct build.

## Why AST, not grep

A line-based text scan cannot tell code from commentary. The existing
`test_only_the_store_finalizer_writes_dataset_coverage` scan has twice tripped on explanatory comments
that merely *mentioned* the thing they described — which trains people to reword prose to appease a
checker. This walks the parsed tree instead, so:

  * comments are invisible (they are not in the AST at all);
  * docstrings are skipped explicitly, so a tool may document the constant it used to carry;
  * shape is irrelevant — a literal is caught whether it is a bare assignment, a tuple, a list, a dict
    value, a `date(...)` call, a default argument, or an inline comparison.

## Registering a genuine constant

A date that is a **historical contract fact** — a property of an adjudicated ruling or an external
record, which does not move when the corpus moves — is legitimate. Register it in
:data:`REGISTERED_HISTORICAL_CONSTANTS` with a reason. Anything else must be derived from the governed
session or measured from the bound corpus.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path

TOOLCHAIN = Path(__file__).resolve().parent / "forward_validation"

ISO_DATE = re.compile(r"^\d{4}-\d{2}-\d{2}")

#: `<file stem>::<assigned name>` -> (reason, exact literals covered).
#:
#: ⚠ The bar is NOT "we checked it and it is currently right". It is "this describes something outside
#: the corpus, so a corpus change cannot invalidate it". A base-corpus census, a coverage edge, or a
#: session window all fail that bar and must be measured or derived.
#:
#: ⚠ Registration names the EXACT literals it covers, never just the variable. Exempting a whole
#: assignment would silently exempt every future date added to it — and the payload dicts below are
#: exactly the kind of thing a session constant could later be dropped into unnoticed. `None` means
#: "every literal under this name", and is reserved for single-value constants.
REGISTERED_HISTORICAL_CONSTANTS: dict[str, tuple[str, frozenset[str] | None]] = {
    "build_universe_crosswalk::SOURCE_MASTER_BOUNDARY": (
        "the fixed date the vendor source master terminates at for the three keys the owner ruled "
        "EXCLUDED_UNRESOLVED_SOURCE_MASTER on 2026-07-29; a property of that adjudicated evidence, "
        "not of any corpus or session",
        None),
    "generate_construction_manifests::ACTIONS_COVERAGE_START": (
        "the first date SHARADAR/ACTIONS carries; a property of the vendor dataset's history, fixed "
        "for every construction",
        None),
    "layer2_shop_tln_quarantine::QUARANTINE": (
        "the SHOP/TLN anomaly dates as MEASURED by the Step-3 reconciliation on corpus-v2 and named "
        "in the countersigned governed_quarantine declaration; properties of that adjudicated "
        "evidence, not of the session being built",
        frozenset({"2025-06-26", "2025-06-27", "2026-02-02", "2026-02-03"})),
    "layer2_complete_package::pkg": (
        "prose restating the same countersigned SHOP/TLN quarantine anomaly dates inside the "
        "evidence package; descriptive, never used to bound a construction",
        frozenset({"2025-06-26 and 2025-06-27",
                   "2026-02-02 and 2026-02-03; closeadj on 02-02 = 348.36 = the 01-30 "
                   "close exactly — a carried-forward stale value"})),
    "layer2_tolerance_remeasurement::payload": (
        "the window of the SEAM-CONTAMINATED predecessor measurement, retained for comparison only "
        "and explicitly NOT used to justify the tolerance factor; a record of a past measurement",
        frozenset({"2025-07-01..2026-06-15"})),
}


def _docstring_nodes(tree: ast.AST) -> set[int]:
    """Node ids of every docstring constant, so documentation may name a retired constant."""
    out: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Module | ast.ClassDef | ast.FunctionDef | ast.AsyncFunctionDef):
            body = getattr(node, "body", [])
            if (body and isinstance(body[0], ast.Expr)
                    and isinstance(body[0].value, ast.Constant)
                    and isinstance(body[0].value.value, str)):
                out.add(id(body[0].value))
    return out


def _assigned_name(tree: ast.AST, target: ast.AST) -> str | None:
    """The module-level constant name a node sits under, if any."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign | ast.AnnAssign):
            for sub in ast.walk(node):
                if sub is target:
                    targets = node.targets if isinstance(node, ast.Assign) else [node.target]
                    for t in targets:
                        if isinstance(t, ast.Name):
                            return t.id
    return None


def scan_file(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    skip = _docstring_nodes(tree)
    stem = path.stem
    findings: list[str] = []

    for node in ast.walk(tree):
        literal: str | None = None

        raw: str | None = None

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if id(node) in skip or not ISO_DATE.match(node.value):
                continue
            raw = node.value
            literal = repr(node.value)

        elif isinstance(node, ast.Call):
            fn = node.func
            name = (fn.attr if isinstance(fn, ast.Attribute)
                    else fn.id if isinstance(fn, ast.Name) else "")
            if name not in {"date", "datetime"}:
                continue
            args = node.args
            if len(args) < 3 or not all(
                    isinstance(a, ast.Constant) and isinstance(a.value, int) for a in args[:3]):
                continue
            literal = f"{name}({', '.join(str(a.value) for a in args[:3])})"  # type: ignore[attr-defined]

        if literal is None:
            continue

        assigned = _assigned_name(tree, node)
        key = f"{stem}::{assigned}" if assigned else None
        if key and key in REGISTERED_HISTORICAL_CONSTANTS:
            _, covered = REGISTERED_HISTORICAL_CONSTANTS[key]
            if covered is None or (raw is not None and raw in covered):
                continue

        where = f"{assigned} = " if assigned else ""
        findings.append(
            f"{path.name}:{node.lineno}: ungoverned date literal {where}{literal}")

    return findings


def main() -> int:
    if not TOOLCHAIN.is_dir():
        print(f"FAIL: {TOOLCHAIN} does not exist", file=sys.stderr)
        return 1

    files = sorted(TOOLCHAIN.glob("*.py"))
    findings: list[str] = []
    for f in files:
        findings.extend(scan_file(f))

    if findings:
        print("FAIL: ungoverned date literals in the Layer 2 construction toolchain\n")
        for f in findings:
            print(f"  {f}")
        print(
            "\nA construction date must be DERIVED from the governed session (--session / "
            "--governed-cutoff) or MEASURED from the bound corpus.\n"
            "If it is a historical contract fact that does not move when the corpus moves, register "
            "it in REGISTERED_HISTORICAL_CONSTANTS in this script with a reason.")
        return 1

    print(f"OK: {len(files)} Layer 2 toolchain files carry no ungoverned date literal "
          f"({len(REGISTERED_HISTORICAL_CONSTANTS)} registered historical constant(s))")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
