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
     publish, published, presentation, presentations, deck, decks, external. Also: a constant-folded
     string concatenation (or a constant-only f-string) that forms such a path, and a path built from a constant
     outbound segment through ``os.path.join(...)``, ``Path(...)``/``PurePath(...)``,
     ``.joinpath(...)`` or the ``/`` operator.

ALSO DETECTED (added with the PU-1 bypass tests; each has a test that fails if coverage changes):

  W  a *reference* to a writer attribute that is not called here (``w = p.write_text; w(x)``,
     ``functools.partial(df.to_csv, ...)``); ``getattr(obj, "write_text")`` with a constant name;
     ``io.open`` / ``codecs.open`` / ``gzip.open`` / ``bz2.open`` / ``lzma.open`` (mode at position
     1) and names bound to them (``from io import open as op``; ``op = io.open``); an ``open()``
     whose mode argument is present but not a literal (conservative: it may be ``"w"``).
  W  ``subprocess.*`` / ``os.system`` / ``os.popen`` / ``os.exec*`` whose literal arguments contain a
     shell redirection (``>``, ``>>``) or ``tee``.
  W  a call to a third-party egress method by name: put_object, upload_file, upload_fileobj,
     sendmail, send_message, files_upload, files_upload_v2, chat_postMessage.
  R  ``importlib.import_module("<render lib>")`` / ``__import__("<render lib>")`` with a LITERAL name.

NOT PROVEN BY THIS CHECK (the ADR lists the same; ``test_pu1_bypass_routes.py`` asserts each stays
undetected so that a change in coverage forces this list and the ADR to be revised):

  * names that are not literals: ``getattr(o, name)``, ``importlib.import_module(name)``,
    ``open(p, mode_from_function())`` is flagged but ``w = make_writer(); w(x)`` is not, a path
    assembled from variables, a ``subprocess`` command built at run time;
  * writing through a third-party client under any method name not in the egress list, or through
    an HTTP client (requests / httpx / urllib POST/PUT bodies), which is not path-based at all;
  * a redirection performed outside Python (``python report.py > report.md``), a shell wrapper,
    a scheduled task or any non-Python script (shell scripts are out of scope);
  * ``exec`` / ``eval`` / ``compile`` of a string, reflection through ``__dict__``/``vars``, and code
    that is generated and written to a file by another function;
  * a writer imported under another name (``from pandas import DataFrame as D``) when the call is on
    an instance whose method name is not in WRITE_ATTRS (the check is by method name, not by type).

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
OPEN_MODULES = {"io", "codecs", "gzip", "bz2", "lzma", "builtins", "tarfile", "zipfile"}
SUBPROCESS_ATTRS = {"run", "Popen", "call", "check_call", "check_output", "system", "popen"}
EGRESS_ATTRS = {
    "put_object", "upload_file", "upload_fileobj", "sendmail", "send_message",
    "files_upload", "files_upload_v2", "chat_postMessage",
}  # fmt: skip
PATH_BUILDERS = {"join", "Path", "PurePath", "PosixPath", "WindowsPath", "joinpath"}
_MODE_RE = re.compile(r"^[rwaxbt+U]{1,5}$")
_REDIRECT_RE = re.compile(r"(?:^|[\s\d&])>>?\s*\S|\btee\b")
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
    "write_internal_json",
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
    # A literal mode must LOOK like a mode: ``Path.open("data.txt")`` has a file name at position 0
    # (``a`` in it is not an append mode).
    return isinstance(mode, str) and bool(_MODE_RE.match(mode)) and any(c in mode for c in "wax+")


def _mode_is_dynamic(node: ast.Call, mode_pos: int) -> bool:
    """A mode argument is present but is not a literal: conservatively a possible write."""
    if len(node.args) > mode_pos and not isinstance(node.args[mode_pos], ast.Constant):
        return not isinstance(node.args[mode_pos], ast.Starred)
    return any(kw.arg == "mode" and not isinstance(kw.value, ast.Constant) for kw in node.keywords)


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
        if f.attr == "open":
            if isinstance(f.value, ast.Name) and f.value.id in OPEN_MODULES:
                return _mode_writes(node, 1) or _mode_is_dynamic(node, 1)  # io.open(path, mode)
            return _mode_writes(node, 0)  # Path.open(mode) -> mode is arg 0
        return False
    if isinstance(f, ast.Name) and f.id == "open":
        return _mode_writes(node, 1) or _mode_is_dynamic(node, 1)
    return False


def _const_str(node: ast.AST) -> str | None:
    """Constant-fold a string made only of literals (``"a" + "b"``, constant-only f-strings)."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.BinOp) and isinstance(node.op, ast.Add):
        left, right = _const_str(node.left), _const_str(node.right)
        if left is not None and right is not None:
            return left + right
    if isinstance(node, ast.JoinedStr):
        parts: list[str] = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                return None
        return "".join(parts)
    return None


def _strings_in(node: ast.AST) -> list[str]:
    return [
        n.value for n in ast.walk(node) if isinstance(n, ast.Constant) and isinstance(n.value, str)
    ]


def _call_name(node: ast.Call) -> str | None:
    f = node.func
    if isinstance(f, ast.Name):
        return f.id
    if isinstance(f, ast.Attribute):
        return f.attr
    return None


def _is_bypass_writer(node: ast.Call, open_aliases: set[str]) -> bool:
    """Writers reached through an alias, ``getattr``, a subprocess redirection or an egress call."""
    f = node.func
    if isinstance(f, ast.Name):
        if f.id in open_aliases:
            return _mode_writes(node, 1) or _mode_is_dynamic(node, 1)
        if f.id == "getattr" and len(node.args) >= 2:
            a = node.args[1]
            return (
                isinstance(a, ast.Constant)
                and isinstance(a.value, str)
                and (a.value in WRITE_ATTRS or a.value in EGRESS_ATTRS)
            )
        return False
    if isinstance(f, ast.Attribute):
        if f.attr in EGRESS_ATTRS:
            return True
        if (
            f.attr in SUBPROCESS_ATTRS
            and isinstance(f.value, ast.Name)
            and f.value.id in ("subprocess", "os")
        ):
            return any(_REDIRECT_RE.search(t) for t in _strings_in(node))
        if f.attr.startswith("exec") and isinstance(f.value, ast.Name) and f.value.id == "os":
            return any(_REDIRECT_RE.search(t) for t in _strings_in(node))
    return False


def _is_dynamic_render_import(node: ast.Call) -> bool:
    """``importlib.import_module("pptx")`` / ``__import__("pptx")`` with a literal name."""
    f = node.func
    named = (isinstance(f, ast.Attribute) and f.attr == "import_module") or (
        isinstance(f, ast.Name) and f.id in ("__import__", "import_module")
    )
    if not named or not node.args:
        return False
    first = node.args[0]
    return (
        isinstance(first, ast.Constant)
        and isinstance(first.value, str)
        and _module_of(first.value) in RENDER_LIBS
    )


def _builds_outbound_path(node: ast.Call) -> bool:
    """``os.path.join("out", "share", ...)`` / ``Path("export")`` / ``.joinpath("deck")``."""
    if _call_name(node) not in PATH_BUILDERS:
        return False
    for a in node.args:
        text = _const_str(a)
        if text is not None and any(
            seg.lower() in OUTBOUND_SEGMENTS for seg in re.split(r"[\\/]", text) if seg
        ):
            return True
    return False


def _outbound_operand(node: ast.BinOp) -> bool:
    """``Path("out") / "share" / "deck.pdf"``: a constant operand that is an outbound segment."""
    for side in (node.left, node.right):
        text = _const_str(side)
        if text is not None and any(
            seg.lower() in OUTBOUND_SEGMENTS for seg in re.split(r"[\\/]", text) if seg
        ):
            return True
    return False


def _outbound_literal(value: str) -> bool:
    if "/" not in value and "\\" not in value:
        return False
    return any(seg.lower() in OUTBOUND_SEGMENTS for seg in re.split(r"[\\/]", value))


def _module_of(name: str) -> str:
    return name.split(".")[0]


def _open_aliases(tree: ast.AST) -> set[str]:
    """Local names bound to an ``open``-like callable by a simple import or assignment."""
    names: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module in OPEN_MODULES:
            names.update((a.asname or a.name) for a in node.names if a.name in ("open", "fdopen"))
        elif isinstance(node, ast.Assign) and len(node.targets) == 1:
            t, v = node.targets[0], node.value
            if isinstance(t, ast.Name) and (
                (isinstance(v, ast.Name) and v.id == "open")
                or (isinstance(v, ast.Attribute) and v.attr in ("open", "fdopen"))
            ):
                names.add(t.id)
    names.discard("open")
    return names


def analyse(tree: ast.AST) -> dict[str, FuncInfo]:
    """Per-function markers. Same-named functions in one file are merged (conservative)."""
    out: dict[str, FuncInfo] = {}
    open_aliases = _open_aliases(tree)

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
                if _is_writer(child) or _is_bypass_writer(child, open_aliases):
                    fi.markers.add("W")
                    ln = child.lineno
                    fi.first_write = ln if fi.first_write is None else min(fi.first_write, ln)
                if _is_dynamic_render_import(child):
                    info("<module>").markers.add("R")
                    fi.markers.add("R")
                if _builds_outbound_path(child):
                    fi.markers.add("O")
                name = _call_name(child)
                if name in GATE_CALLS:
                    fi.gate_lines.append(child.lineno)
                if name in SEAM_REFERENCES:
                    fi.seam_lines.append(child.lineno)
            elif isinstance(child, ast.Attribute):
                # a writer attribute REFERENCED but not called here: ``w = p.write_text``
                if child.attr in WRITE_ATTRS and isinstance(child.ctx, ast.Load):
                    fi = info(owner)
                    fi.markers.add("W")
                    fi.first_write = (
                        child.lineno
                        if fi.first_write is None
                        else min(fi.first_write, child.lineno)
                    )
            elif isinstance(child, ast.Constant) and isinstance(child.value, str):
                if _outbound_literal(child.value):
                    info(owner).markers.add("O")
            elif isinstance(child, ast.BinOp) and isinstance(child.op, ast.Add):
                folded = _const_str(child)
                if folded is not None and _outbound_literal(folded):
                    info(owner).markers.add("O")
            elif isinstance(child, ast.BinOp) and isinstance(child.op, ast.Div):
                if _outbound_operand(child):
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
