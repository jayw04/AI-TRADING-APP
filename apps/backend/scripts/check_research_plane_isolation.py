#!/usr/bin/env python3
"""Research-plane isolation tripwire — two properties, enforced structurally.

WHY THIS EXISTS. The research plane and the order path are separate for a reason: research
reads whatever it needs and is free to be wrong, while the order path must be auditable and
must never be steered by an artifact nobody governed. Two properties keep that true, and
neither was enforced anywhere. ``CLAUDE.md`` lists two research-plane checks among the CI
invariants; measured 2026-08-31, **neither script exists**. This closes that gap.

WHAT IS CHECKED

  A. The research plane cannot acquire ORDER/BROKER MUTATION capability.
     Roots: app/research, app/factor_data, app/altdata.
     Forbidden: app.orders, app.risk, app.brokers, app.services.order_router, and the
     Alpaca *trading* SDK.

  B. The order path cannot consume the IMMUTABLE MDQ RESEARCH/EVIDENCE ARCHIVE.
     Roots: app/orders, app/risk, app/brokers, app/services/order_router.py, app/strategies.
     Forbidden: the MDQ archive packages (app.research.capture, .mdq_eval, .disc_mdq).

WHAT IS DELIBERATELY *NOT* CHECKED — the prohibition is on capability, not on research

  * Research code MAY read market data. ``alpaca.data`` is permitted; only ``alpaca.trading``
    is not. Blanket-banning market-data access would make the research plane useless and would
    not improve isolation.
  * Non-order-path services MAY consume research. ``app/services/opportunity_history.py`` and
    ``premarket_evidence.py`` legitimately import ``app.research.disc001`` /
    ``gapper_stage0``; property B targets the MDQ *archive* specifically, not all research.
  * ``app.factor_data`` is a permitted dependency of many modules and is a research-plane ROOT
    here, not a forbidden target.

WHY AST AND WHY TRANSITIVE — two bypasses a naive check does not close

  1. **A regex sees comments and strings.** ``app/research/capture/identity.py`` contains the
     prose "deliberately not the alpaca.trading ..." and ``disc001/snapshot.py`` holds the
     *string literal* ``"alpaca.trading"``. Both are correct code; a grep-based check fails
     them. Only real ``import``/``from`` statements are considered here.
  2. **A direct-import check is bypassed by moving the call one module over.** A research
     module that imports a *sibling research* helper which imports ``app.risk`` has the
     capability just the same. So imports are resolved into a graph and the check runs over the
     transitive closure, reporting the full chain.

     ⚠ **Traversal is bounded to the plane being checked**, and that boundary is the whole
     design. Unbounded transitivity is wrong, not merely noisy: research legitimately imports
     ``app.strategies`` to *evaluate* a strategy, and ``app.strategies.engine`` itself dispatches
     orders — so an unbounded walk reports every backtester as holding execution capability.
     Measured on the real tree, that was ~47 KB of false positives. Whether a shared module such
     as ``app.strategies`` may touch the order path is governed by ``check_adr0002.sh`` and
     ``check_strategy_isolation.sh``; it is not this check's question. What this check owns is
     that the plane cannot reach forbidden capability **through modules the plane itself
     controls**.

Path lists are DISCOVERED by walking each root, never enumerated file-by-file: a new module
dropped into the research plane is covered the moment it exists.

Exit 0 = both properties hold. Exit 1 = violation, with the offending import chain.
Disabling this requires an ADR.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

BACKEND = Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

RESEARCH_ROOTS = ("app/research", "app/factor_data", "app/altdata")
ORDER_PATH_ROOTS = (
    "app/orders",
    "app/risk",
    "app/brokers",
    "app/services/order_router.py",
    "app/strategies",
)

# A: capability the research plane must never acquire.
FORBIDDEN_FOR_RESEARCH = (
    "app.orders",
    "app.risk",
    "app.brokers",
    "app.services.order_router",
    "alpaca.trading",
)
# B: the immutable MDQ research/evidence archive the order path must never consume.
FORBIDDEN_FOR_ORDER_PATH = (
    "app.research.capture",
    "app.research.mdq_eval",
    "app.research.disc_mdq",
)


def _module_name(path: Path) -> str:
    rel = path.relative_to(BACKEND).with_suffix("")
    parts = list(rel.parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def _imports_of(path: Path) -> set[str]:
    """Every module this file imports. AST only — comments and strings cannot appear."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    except SyntaxError:
        return set()
    pkg = _module_name(path).rsplit(".", 1)[0] if path.name != "__init__.py" else _module_name(path)
    out: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            out.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:  # relative import -> resolve against the containing package
                base = pkg.split(".")
                base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
                mod = ".".join([*base, node.module]) if node.module else ".".join(base)
            else:
                mod = node.module or ""
            if mod:
                out.add(mod)
                out.update(f"{mod}.{a.name}" for a in node.names)
    return out


def _matches(module: str, forbidden: tuple[str, ...]) -> str | None:
    for f in forbidden:
        if module == f or module.startswith(f + "."):
            return f
    return None


def _build_graph() -> dict[str, set[str]]:
    return {_module_name(p): _imports_of(p) for p in APP.rglob("*.py")}


def _files_under(root: str) -> list[Path]:
    p = BACKEND / root
    if p.is_file():
        return [p]
    return sorted(p.rglob("*.py")) if p.is_dir() else []


def _violations(roots, forbidden, graph, traverse_prefixes) -> list[str]:
    """Reachability to a forbidden target, traversing only modules the plane itself owns.

    ``traverse_prefixes`` bounds the walk. A hop into a shared module (e.g. ``app.strategies``)
    is a leaf: it is recorded as a direct dependency but not followed, because that module's own
    relationship to the order path is a different invariant's business.
    """
    out: list[str] = []
    for root in roots:
        for f in _files_under(root):
            start = _module_name(f)
            seen: set[str] = set()
            # stack of (module, chain-that-reached-it)
            stack: list[tuple[str, list[str]]] = [(start, [start])]
            while stack:
                mod, chain = stack.pop()
                for imp in graph.get(mod, set()):
                    hit = _matches(imp, forbidden)
                    if hit:
                        via = " -> ".join([*chain, imp])
                        out.append(f"  {start}\n      reaches {hit} via: {via}")
                        continue
                    # traverse ONLY plane-internal modules; everything else is a leaf
                    if (
                        any(imp == t or imp.startswith(t + ".") for t in traverse_prefixes)
                        and imp in graph
                        and imp not in seen
                    ):
                        seen.add(imp)
                        stack.append((imp, [*chain, imp]))
    return out


def main() -> int:
    graph = _build_graph()
    failed = False

    research_pkgs = tuple(r.replace("/", ".") for r in RESEARCH_ROOTS)
    order_pkgs = tuple(r.replace("/", ".").removesuffix(".py") for r in ORDER_PATH_ROOTS)
    a = _violations(RESEARCH_ROOTS, FORBIDDEN_FOR_RESEARCH, graph, research_pkgs)
    if a:
        failed = True
        print(
            "RESEARCH-PLANE CAPABILITY VIOLATION — research code can reach order/broker mutation:",
            file=sys.stderr,
        )
        print("\n".join(a), file=sys.stderr)
        print(
            "\nThe research plane may read market data (alpaca.data is fine). It may not hold "
            "\nexecution capability. Route the decision through a governed seam instead.",
            file=sys.stderr,
        )

    b = _violations(ORDER_PATH_ROOTS, FORBIDDEN_FOR_ORDER_PATH, graph, order_pkgs)
    if b:
        failed = True
        print(
            "\nORDER-PATH ARCHIVE VIOLATION — the order path can reach the immutable MDQ "
            "research/evidence archive:",
            file=sys.stderr,
        )
        print("\n".join(b), file=sys.stderr)
        print(
            "\nThe MDQ archive is governed evidence, not a live data source. A live consumer "
            "\nreads the operational cache, never the archive.",
            file=sys.stderr,
        )

    if failed:
        return 1
    print(
        f"research-plane isolation OK "
        f"({len(graph)} modules; A: research!->order/broker, B: order-path!->MDQ archive)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
