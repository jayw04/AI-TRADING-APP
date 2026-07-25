"""R5e-2 structural invariants over EVERY production Python surface.

The R5e-2 review made these load-bearing. The disclosed residual — `ForwardSessionRunner` still accepts
the three witness legs as independent optional fields — is acceptable ONLY while these hold, because
what makes the gate real is not that the runner refuses bad wiring but that no production entry point
ever wires it.

Two weaknesses in the first attempt are fixed here.

**Surface.** The original scans looked only under `app/`. `scripts/` is equally a production entry
point — the forward-validation CLI lives there — so a script constructing a runtime would have passed
silently. Both trees are scanned now, and exclusions (tests, generated artifacts, vendored code,
virtualenvs) are named explicitly rather than achieved by scanning less.

**Method.** The original scans were substring matches on source text, which a comment, a string, an
`import ... as` alias, or a call split across lines defeats. Detection is AST-based: calls are resolved
through the module's own import bindings, so `from x import SessionRuntime as SR; SR(...)` is caught
and the words appearing in a docstring are not.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

BACKEND = Path(__file__).resolve().parents[2]

# Every production Python surface. Not "app/ because that is where the interesting code is" — a
# production entry point is anything the deployment can execute.
PRODUCTION_TREES = ("app", "scripts")

# Explicit exclusions. Named so that adding one is a visible decision rather than a silent narrowing.
EXCLUDED_DIR_NAMES = frozenset({
    "tests", "test", "__pycache__", ".venv", "venv", "site-packages", "node_modules",
    "alembic",            # generated migrations
    "research",           # scripts/research: exploratory one-off reproductions, never deployed
})


def _production_files() -> list[Path]:
    out: list[Path] = []
    for tree in PRODUCTION_TREES:
        root = BACKEND / tree
        if not root.is_dir():
            continue
        for path in root.rglob("*.py"):
            if EXCLUDED_DIR_NAMES.intersection(path.relative_to(BACKEND).parts):
                continue
            out.append(path)
    return sorted(out)


def _local_names_for(tree: ast.Module, target_module_suffix: str, target_name: str) -> set[str]:
    """Every local binding in this module that refers to `target_name`, honouring `as` aliases."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and (node.module or "").endswith(target_module_suffix):
            for alias in node.names:
                if alias.name == target_name:
                    names.add(alias.asname or alias.name)
        elif isinstance(node, ast.Import):
            for alias in node.names:
                if alias.name.endswith(target_module_suffix):
                    names.add(f"{alias.asname or alias.name}.{target_name}")
    return names


def _callee_name(node: ast.Call) -> str:
    func = node.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        parts: list[str] = [func.attr]
        cur: ast.expr = func.value
        while isinstance(cur, ast.Attribute):
            parts.append(cur.attr)
            cur = cur.value
        if isinstance(cur, ast.Name):
            parts.append(cur.id)
        return ".".join(reversed(parts))
    return ""


def _call_sites(module_suffix: str, name: str) -> dict[str, list[int]]:
    """Files (repo-relative POSIX) → line numbers where `name` is CALLED, resolved through imports."""
    found: dict[str, list[int]] = {}
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover - a broken file fails elsewhere
            continue
        bound = _local_names_for(tree, module_suffix, name)
        if not bound:
            continue
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.Call) and _callee_name(n) in bound]
        if hits:
            found[path.relative_to(BACKEND).as_posix()] = sorted(hits)
    return found


def _imported_names(module_suffix: str, name: str) -> list[str]:
    """Files that so much as IMPORT `name`, whether or not they call it."""
    out: list[str] = []
    for path in _production_files():
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        if _local_names_for(tree, module_suffix, name):
            out.append(path.relative_to(BACKEND).as_posix())
    return sorted(out)


# ── the scanner itself must be trustworthy ───────────────────────────────────────────────────────────

def test_the_scan_actually_covers_both_production_trees():
    """A structural test that silently scanned nothing would pass forever."""
    files = {p.relative_to(BACKEND).as_posix() for p in _production_files()}
    assert any(f.startswith("app/") for f in files)
    assert any(f.startswith("scripts/") for f in files)
    assert "app/validation/session_composition.py" in files
    assert "scripts/run_forward_validation_session.py" in files
    assert not any("/tests/" in f or f.startswith("tests/") for f in files)


def test_the_scanner_resolves_aliases_and_ignores_text(tmp_path):
    """Pins the AST method against the substring method it replaced: an aliased import is a real call
    site, and the same words in a comment or string are not."""
    source = (
        "from app.validation.session_orchestration import SessionRuntime as SR\n"
        "# SessionRuntime( in a comment\n"
        "DOC = 'SessionRuntime('\n"
        "x = SR(store=None)\n"
    )
    tree = ast.parse(source)
    bound = _local_names_for(tree, "session_orchestration", "SessionRuntime")
    assert bound == {"SR"}
    hits = [n.lineno for n in ast.walk(tree)
            if isinstance(n, ast.Call) and _callee_name(n) in bound]
    assert hits == [4], "the alias call must be found, and comment/string text must not"


# ── the invariants ───────────────────────────────────────────────────────────────────────────────────

def test_one_production_session_runtime_construction_site():
    sites = _call_sites("session_orchestration", "SessionRuntime")
    assert list(sites) == ["app/validation/session_composition.py"], (
        f"SessionRuntime is constructed in production outside the composition root: {sites}")


def test_one_production_run_production_session_invocation():
    sites = _call_sites("session_orchestration", "run_production_session")
    assert list(sites) == ["scripts/run_forward_validation_session.py"], (
        f"run_production_session is invoked from an unexpected production path: {sites}")


def test_one_production_forward_session_runner_construction_site():
    """The DISCLOSED RESIDUAL is bounded by exactly this: the runner still takes its three witness legs
    independently, so the only thing standing between that and an unwitnessed record is that precisely
    one production path builds it — the one that goes through the enforced SessionRuntime."""
    sites = _call_sites("forward_session_runner", "ForwardSessionRunner")
    assert list(sites) == ["app/validation/session_orchestration.py"], (
        f"a second production path constructs the runner: {sites}; it would bypass the enforced witness")


def test_no_production_module_assigns_the_witness_legs_independently():
    """The legs may be READ (the SessionRuntime properties do) but never SET outside the runner
    construction that the composition path owns."""
    legs = {"anchor_signer", "anchor_verifier", "external_anchor_sink"}
    offenders: dict[str, list[int]] = {}
    for path in _production_files():
        rel = path.relative_to(BACKEND).as_posix()
        if rel in ("app/validation/session_orchestration.py",
                   "app/validation/forward_session_runner.py"):
            continue                               # the sanctioned construction and the definition
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except SyntaxError:                        # pragma: no cover
            continue
        hits = [n.lineno for n in ast.walk(tree)
                if isinstance(n, ast.keyword) and n.arg in legs]
        hits += [t.attr for t in ast.walk(tree)                     # type: ignore[misc]
                 if isinstance(t, ast.Attribute) and isinstance(t.ctx, ast.Store) and t.attr in legs]
        if hits:
            offenders[rel] = hits                                    # type: ignore[assignment]
    assert offenders == {}, f"production code wires witness legs independently: {offenders}"


def test_production_witness_is_constructed_only_inside_the_enforcement_module():
    sites = _call_sites("witness_enforcement", "ProductionWitness")
    assert sites == {}, (
        f"ProductionWitness is constructed outside witness_enforcement.py: {sites}; only the gate may "
        f"build the carrier")


def test_no_production_module_reaches_for_the_issuance_internals():
    """`_mark_enforced` and `_ISSUANCE_SENTINEL` mint an enforced witness without any gate. Nothing in
    production may import them — the thing production wants is `enforce_production_witness`."""
    for private in ("_mark_enforced", "_ISSUANCE_SENTINEL", "_ISSUANCE_ATTR"):
        importers = [f for f in _imported_names("witness_enforcement", private)
                     if not f.endswith("witness_enforcement.py")]
        assert importers == [], f"production modules import {private}: {importers}"


@pytest.mark.parametrize("name", ["enforce_production_witness"])
def test_the_gate_is_reachable_where_it_should_be(name):
    """The mirror of the refusals above: the sanctioned entry point IS used, so these tests cannot all
    be passing because nothing is wired at all."""
    importers = _imported_names("witness_enforcement", name)
    assert "app/validation/session_composition.py" in importers
    assert "scripts/run_forward_validation_session.py" in importers
