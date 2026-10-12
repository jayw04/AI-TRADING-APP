#!/usr/bin/env python3
"""PU-1 export-path closure tripwire (CI check a of the PU-1 presentation gate; mini-ADR 0057).

WHAT THIS CLOSES. ``app.licensing`` gives the platform ONE fail-closed seam for anything that leaves
the owner's private working set. A seam is only worth something if a new path cannot be added
BESIDE it. This script makes "add a new export/render path" a build-visible event: every function
that writes, renders or targets an outbound location must be named in the checked-in registry
``apps/backend/ci/pu1_export_paths.json`` as either

    GATED          it passes through the PU-1 seam (or marks its output) -- verified here, or
    INTERNAL_ONLY  it writes only into the owner's private working set, with a stated reason.

A function that is on neither list fails the build. Nothing here changes what data is fetched,
stored, computed or traded.

WHAT COUNTS AS AN EXPORT/RENDER ENTRY (deterministic; AST only, no execution; every ``def`` /
``async def`` -- the INNERMOST enclosing function owns a node, module level is ``<module>``):

  W  a writer call: ``.write_text`` ``.write_bytes`` ``.to_csv`` ``.to_parquet`` ``.to_excel``
     ``.to_html`` ``.to_markdown`` ``.to_latex`` ``.savefig`` ``.write_html`` ``.write_image``
     ``shutil.copy|copyfile|copy2|copytree|move``  ``json|yaml|pickle.dump``  or ``open()`` /
     ``.open()`` / ``os.fdopen()`` whose literal mode contains ``w``, ``a``, ``x`` or ``+``.
  R  a rendering-library import (pptx, docx, reportlab, weasyprint, fpdf, xhtml2pdf, pdfkit,
     matplotlib, plotly, kaleido, openpyxl, xlsxwriter) -- owned by ``<module>``.
  O  a string literal (including the literal parts of an f-string) containing a path separator
     (``/`` or ``\\``) with a segment equal to one of: outbound, share, shared, export, exports,
     publish, published, presentation, presentations, deck, decks, external.

A frontend print/PDF trigger (``window.print(`` and the libraries in FRONTEND_PATTERNS under
``apps/frontend/src``) is checked by a text rule: the file must be in ``frontend_entries`` and
contain every ``must_contain`` marker (the panel-scope gate), so a new print path cannot appear
ungated either.

RULES
  1. Every W/R/O entry must be covered by a registry entry (same file; ``functions`` lists the
     name, or ``"*"``). Otherwise: UNREGISTERED.
  2. INTERNAL_ONLY needs a non-empty reason, and its functions must carry no R or O marker
     (an internal writer that targets an outbound-named path is not internal).
  3. GATED functions must call a gate API (GATE_CALLS) and, when they also carry a W marker, the
     first gate reference must precede the first writer call (gate-before-write). Files under
     ``app/licensing/`` ARE the seam: exempt from the call test, but ``export_*`` there must
     reference ``assert_presentable``/``PersonalScopeBlocked`` before any writer.
  4. A registry entry naming a missing file or an undefined function fails (stale registry).
  5. Duplicate (file, function) registrations fail.

Run from the repository root. Exit 0 = closed. Exit 1 = violation(s) listed. Exit 2 = unusable
registry. Disabling this check requires an ADR.
"""

from __future__ import annotations

import ast
import json
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
REGISTRY = REPO / "apps" / "backend" / "ci" / "pu1_export_paths.json"

SCAN_ROOTS = (
    "apps/backend/app",
    "apps/backend/scripts",
    "scripts",
    "deploy",
    "apps/mcp-server",
    "apps/mcp-workbench",
    "apps/agent",
)
SKIP_PARTS = {"tests", "test", ".venv", "node_modules", "__pycache__", "alembic", "site-packages"}

WRITE_ATTRS = {
    "write_text", "write_bytes", "to_csv", "to_parquet", "to_excel", "to_html", "to_markdown",
    "to_latex", "savefig", "write_html", "write_image",
}  # fmt: skip
SHUTIL_ATTRS = {"copy", "copyfile", "copy2", "copytree", "move"}
DUMP_MODULES = {"json", "yaml", "pickle"}
RENDER_LIBS = (
    "pptx", "docx", "reportlab", "weasyprint", "fpdf", "fpdf2", "xhtml2pdf", "pdfkit",
    "matplotlib", "plotly", "kaleido", "openpyxl", "xlsxwriter",
)  # fmt: skip
OUTBOUND_SEGMENTS = {
    "outbound", "share", "shared", "export", "exports", "publish", "published", "presentation",
    "presentations", "deck", "decks", "external",
}  # fmt: skip
# Calls that put a function behind (or mark its output with) the PU-1 seam.
GATE_CALLS = {
    "export_for_external_use", "export_file_for_external_use", "write_internal_report",
    "assert_presentable", "stamp", "commercial_safe_section", "footer_for",
    "safe_effective_scope",
}  # fmt: skip
SEAM_REFERENCES = {"assert_presentable", "PersonalScopeBlocked", "scope_of_file"}
LICENSING_DIR = "apps/backend/app/licensing/"
FRONTEND_ROOT = "apps/frontend/src"
FRONTEND_PATTERNS = re.compile(
    r"window\.print\(|\bjspdf\b|\bhtml2canvas\b|\bpptxgenjs\b|\bhtml2pdf\b|\bfile-saver\b|\bsaveAs\("
)


@dataclass
class FuncInfo:
    name: str
    first_write: int | None = None
    markers: set[str] = field(default_factory=set)  # W / R / O
    gate_lines: list[int] = field(default_factory=list)
    seam_lines: list[int] = field(default_factory=list)


def _skip(path: Path) -> bool:
    return any(part in SKIP_PARTS for part in path.parts)


def _mode_writes(node: ast.Call, mode_pos: int) -> bool:
    mode: object = None
    arg = node.args[mode_pos] if len(node.args) > mode_pos else None
    if isinstance(arg, ast.Constant):
        mode = arg.value
    for kw in node.keywords:
        if kw.arg == "mode" and isinstance(kw.value, ast.Constant):
            mode = kw.value.value
    return isinstance(mode, str) and any(c in mode for c in "wax+")


def _is_writer(node: ast.Call) -> bool:
    f = node.func
    if isinstance(f, ast.Attribute):
        if f.attr in WRITE_ATTRS:
            return True
        if isinstance(f.value, ast.Name):
            if f.value.id == "shutil" and f.attr in SHUTIL_ATTRS:
                return True
            if f.value.id in DUMP_MODULES and f.attr == "dump":
                return True
            if f.value.id == "os" and f.attr == "fdopen":
                return _mode_writes(node, 1)
        if f.attr == "open":  # Path.open(mode) -> mode is arg 0
            return _mode_writes(node, 0)
        return False
    if isinstance(f, ast.Name) and f.id == "open":
        return _mode_writes(node, 1)
    return False


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _outbound_literal(value: str) -> bool:
    if "/" not in value and "\\" not in value:
        return False
    return any(seg.lower() in OUTBOUND_SEGMENTS for seg in re.split(r"[\\/]", value))


def _module_of(name: str) -> str:
    return name.split(".")[0]


def analyse(tree: ast.AST) -> dict[str, FuncInfo]:
    """Per-function markers. Same-named functions in one file are merged (conservative)."""
    out: dict[str, FuncInfo] = {}

    def info(name: str) -> FuncInfo:
        return out.setdefault(name, FuncInfo(name))

    def visit(node: ast.AST, owner: str) -> None:
        for child in ast.iter_child_nodes(node):
            if isinstance(child, ast.FunctionDef | ast.AsyncFunctionDef):
                info(child.name)
                visit(child, child.name)
                continue
            if isinstance(child, ast.Import):
                for a in child.names:
                    if _module_of(a.name) in RENDER_LIBS:
                        info("<module>").markers.add("R")
            elif isinstance(child, ast.ImportFrom):
                if child.module and _module_of(child.module) in RENDER_LIBS:
                    info("<module>").markers.add("R")
            elif isinstance(child, ast.Call):
                fi = info(owner)
                if _is_writer(child):
                    fi.markers.add("W")
                    ln = child.lineno
                    fi.first_write = ln if fi.first_write is None else min(fi.first_write, ln)
                name = _call_name(child)
                if name in GATE_CALLS:
                    fi.gate_lines.append(child.lineno)
                if name in SEAM_REFERENCES:
                    fi.seam_lines.append(child.lineno)
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                if _outbound_literal(child.value):
                    info(owner).markers.add("O")
            elif isinstance(child, ast.Name) and child.id in SEAM_REFERENCES:
                info(owner).seam_lines.append(child.lineno)
            visit(child, owner)

    visit(tree, "<module>")
    return out


def _load_registry() -> tuple[list[dict], list[dict]]:
    try:
        data = json.loads(REGISTRY.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        print(f"PU-1 export-path closure: registry unusable ({exc})", file=sys.stderr)
        raise SystemExit(2) from exc
    ents, fe = data.get("entries"), data.get("frontend_entries", [])
    if data.get("schema") != 1 or not isinstance(ents, list) or not isinstance(fe, list):
        print("PU-1 export-path closure: registry schema invalid", file=sys.stderr)
        raise SystemExit(2)
    return ents, fe


def _iter_files() -> list[Path]:
    files: list[Path] = []
    for root in SCAN_ROOTS:
        base = REPO / root
        if base.is_dir():
            files.extend(p for p in sorted(base.rglob("*.py")) if not _skip(p.relative_to(REPO)))
    return files


def check() -> list[str]:
    entries, frontend_entries = _load_registry()
    problems: list[str] = []

    by_file: dict[str, list[dict]] = {}
    seen: set[tuple[str, str]] = set()
    for i, e in enumerate(entries):
        f, cls = e.get("file"), e.get("classification")
        funcs = e.get("functions", "*")
        reason = e.get("reason")
        where = f"entries[{i}] ({f})"
        if not isinstance(f, str) or cls not in ("GATED", "INTERNAL_ONLY"):
            problems.append(f"{where}: needs 'file' and classification GATED|INTERNAL_ONLY")
            continue
        if not isinstance(reason, str) or not reason.strip():
            problems.append(f"{where}: a non-empty 'reason' is required")
        names = ["*"] if funcs == "*" else funcs
        if not isinstance(names, list) or not all(isinstance(n, str) for n in names):
            problems.append(f"{where}: 'functions' must be \"*\" or a list of names")
            continue
        for n in names:
            if (f, n) in seen:
                problems.append(f"{where}: duplicate registration of {f}::{n}")
            seen.add((f, n))
        if cls == "GATED" and names == ["*"] and not f.startswith(LICENSING_DIR):
            problems.append(f"{where}: GATED outside app/licensing must list its functions")
        if not (REPO / f).is_file():
            problems.append(f"{where}: file does not exist (stale registry)")
            continue
        by_file.setdefault(f, []).append({"cls": cls, "names": names})

    analysed: dict[str, dict[str, FuncInfo]] = {}
    for path in _iter_files():
        rel = path.relative_to(REPO).as_posix()
        try:
            analysed[rel] = analyse(ast.parse(path.read_text(encoding="utf-8"), filename=rel))
        except (SyntaxError, UnicodeDecodeError) as exc:
            problems.append(f"{rel}: cannot parse ({exc})")
    for f in by_file:  # registered files outside SCAN_ROOTS are still analysed
        if f not in analysed and f.endswith(".py"):
            tree = ast.parse((REPO / f).read_text(encoding="utf-8"), filename=f)
            analysed[f] = analyse(tree)

    def classification(rel: str, func: str) -> str | None:
        for reg in by_file.get(rel, []):
            if func in reg["names"]:
                return reg["cls"]
        for reg in by_file.get(rel, []):
            if "*" in reg["names"]:
                return reg["cls"]
        return None

    # stale function names
    for rel, regs in by_file.items():
        defined = set(analysed.get(rel, {}))
        for reg in regs:
            for n in reg["names"]:
                if n != "*" and n not in defined:
                    problems.append(f"{rel}: registered function {n!r} is not defined (stale)")

    # rules 1-3 over every analysed file
    for rel, funcs in sorted(analysed.items()):
        in_seam = rel.startswith(LICENSING_DIR)
        for name, fi in sorted(funcs.items()):
            cls = classification(rel, name)
            is_entry = bool(fi.markers)
            if is_entry and cls is None:
                problems.append(
                    f"UNREGISTERED export/render entry {rel}::{name} markers={sorted(fi.markers)}"
                    " -- route it through app.licensing or register it in "
                    "apps/backend/ci/pu1_export_paths.json"
                )
                continue
            if cls == "INTERNAL_ONLY" and fi.markers & {"R", "O"}:
                problems.append(
                    f"{rel}::{name}: registered INTERNAL_ONLY but carries "
                    f"{sorted(fi.markers & {'R', 'O'})} (render / outbound-path marker)"
                )
            if cls == "GATED" and (is_entry or _listed(by_file, rel, name)):
                if in_seam:
                    if name.startswith("export_"):
                        first = min(fi.seam_lines, default=None)
                        if first is None or (fi.first_write is not None and first > fi.first_write):
                            problems.append(f"{rel}::{name}: seam export must gate before writing")
                    continue
                first_gate = min(fi.gate_lines, default=None)
                if first_gate is None:
                    problems.append(f"{rel}::{name}: registered GATED but calls no gate API")
                elif fi.first_write is not None and first_gate > fi.first_write:
                    problems.append(f"{rel}::{name}: writes before the first gate call")

    # frontend text rule
    fe_by_file = {e.get("file"): e for e in frontend_entries if isinstance(e, dict)}
    fe_root = REPO / FRONTEND_ROOT
    hit_files: set[str] = set()
    if fe_root.is_dir():
        for p in sorted(fe_root.rglob("*")):
            if p.suffix not in (".ts", ".tsx", ".js", ".jsx") or "node_modules" in p.parts:
                continue
            text = p.read_text(encoding="utf-8", errors="replace")
            if not FRONTEND_PATTERNS.search(text):
                continue
            rel = p.relative_to(REPO).as_posix()
            hit_files.add(rel)
            ent = fe_by_file.get(rel)
            if ent is None:
                problems.append(f"UNREGISTERED frontend print/export trigger in {rel}")
                continue
            for marker in ent.get("must_contain", []):
                if marker not in text:
                    problems.append(f"{rel}: frontend gate marker {marker!r} missing")
            if not str(ent.get("reason", "")).strip() or not ent.get("must_contain"):
                problems.append(f"{rel}: frontend entry needs reason and must_contain markers")
    for fe_file in fe_by_file:
        if fe_file not in hit_files:
            problems.append(
                f"frontend entry {fe_file} has no print/export trigger any more (stale)"
            )
    return problems


def _listed(by_file: dict[str, list[dict]], rel: str, name: str) -> bool:
    return any(name in reg["names"] for reg in by_file.get(rel, []))


def main() -> int:
    problems = check()
    if problems:
        print("PU-1 EXPORT-PATH CLOSURE VIOLATION(S):", file=sys.stderr)
        for p in problems:
            print(f"  - {p}", file=sys.stderr)
        print(
            "\nA function that writes, renders or targets an outbound location must either go "
            "through app.licensing (export_for_external_use / export_file_for_external_use / "
            "write_internal_report) or be registered with a reason in "
            "apps/backend/ci/pu1_export_paths.json. There is no override.",
            file=sys.stderr,
        )
        return 1
    print("PU-1 export-path closure OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
