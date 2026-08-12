"""EB-1/EB-2: the executing import closure, derived mechanically rather than maintained by hand.

A hand-written roster binds what someone remembered was important. That is how
``spq1/__init__.py`` -- which defines ``PHASE0_CENSUS_SHA256``, ``PHASE0_OWNER_RULINGS_SHA256``,
``PHASE0_SCHEMA_SHA256`` and ``PRODUCER_CODE_VERSION``, all of which reach ``GOVERNING_IDENTITIES``
and therefore every emitted record -- stayed unbound while the roster still passed. Its constants
could have drifted and no bound hash would have noticed.

So the closure is *computed*, in two independent ways, and the two must agree.

**Static closure** walks the AST from the package and follows every intra-package import. It runs
BEFORE anything is imported, which is what EB-2 requires: bound before access. It also includes
every parent package ``__init__.py``, because Python executes those on the way in -- a zero-byte
``__init__.py`` is still executed code, and its emptiness today is not an invariant.

**Runtime closure** reads ``sys.modules`` after the entry point has been imported. That is ground
truth: whatever Python actually executed is in there, including anything the AST walk failed to
predict (conditional imports, ``importlib``, re-exports).

Static is the binding; runtime is the audit of the binding. A module that appears at runtime but
not in the static closure is precisely the blind spot this module exists to remove, so it refuses.

Three rosters are kept distinct, because conflating them produced a false closure once already --
35 files bound and 35 files imported, but not the same 35:

  EXECUTING            every repository Python file imported from the real entry point;
  EXTERNAL_DEPENDENCY  files supplied by the separately bound dependency bundle;
  GOVERNING_ONLY       frozen specs and reference modules bound for provenance, NOT imported.

Membership is proven by set equality, never by count.
"""

from __future__ import annotations

import ast
import hashlib
import os
import sys

EXECUTING = "executing"
EXTERNAL_DEPENDENCY = "external_dependency"
GOVERNING_ONLY = "governing_only"

# The package the entry point lives in, and the repository root package above it.
PACKAGE = "app.research.mr002"
ROOT_PACKAGE = "app"


class ClosureRefused(Exception):
    """The executing closure cannot be established or does not reproduce. The run must not proceed."""


def _sha256(path: str) -> str:
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def package_root(start: str) -> str:
    """Walk up from a module directory to the directory that CONTAINS the root package."""
    here = os.path.abspath(start)
    while os.path.exists(os.path.join(here, "__init__.py")):
        here = os.path.dirname(here)
    return here


def _module_of(path: str, root: str) -> str:
    rel = os.path.relpath(path, root).replace(os.sep, "/")
    if rel.endswith("/__init__.py"):
        rel = rel[: -len("/__init__.py")]
    elif rel.endswith(".py"):
        rel = rel[:-3]
    return rel.replace("/", ".")


def _path_of(module: str, root: str) -> str | None:
    base = os.path.join(root, *module.split("."))
    for cand in (base + ".py", os.path.join(base, "__init__.py")):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def _parents_of(module: str, root: str) -> list[str]:
    """Every ancestor package initializer Python executes on the way to `module`."""
    parts, out = module.split("."), []
    for i in range(1, len(parts)):
        p = _path_of(".".join(parts[:i]), root)
        if p and p.endswith("__init__.py"):
            out.append(p)
    return out


def static_closure(start_dir: str) -> dict[str, str]:
    """Derive the executing closure from source, before importing anything.

    Returns {absolute path: sha256}. Refuses if an intra-package import cannot be resolved to a
    file -- an unresolvable import is a missing dependency, not something to skip quietly.
    """
    start_dir = os.path.abspath(start_dir)
    root = package_root(start_dir)
    if not os.path.isdir(os.path.join(root, ROOT_PACKAGE)):
        raise ClosureRefused(f"cannot locate the {ROOT_PACKAGE!r} package root above {start_dir}")

    seeds = [os.path.join(start_dir, f) for f in sorted(os.listdir(start_dir)) if f.endswith(".py")]
    if not seeds:
        raise ClosureRefused(f"no Python modules under {start_dir}")

    found: dict[str, str] = {}
    stack = list(seeds)
    while stack:
        path = os.path.abspath(stack.pop())
        if path in found:
            continue
        try:
            with open(path, encoding="utf-8") as fh:
                src = fh.read()
        except OSError as exc:
            raise ClosureRefused(f"cannot read a module in the closure: {path}: {exc}") from exc
        found[path] = _sha256(path)

        module = _module_of(path, root)
        stack.extend(_parents_of(module, root))
        container = module if path.endswith("__init__.py") else module.rsplit(".", 1)[0]

        for node in ast.walk(ast.parse(src, filename=path)):
            targets: list[str] = []
            if isinstance(node, ast.ImportFrom):
                if node.level:
                    parts = container.split(".")
                    keep = len(parts) - (node.level - 1)
                    if keep < 1:
                        raise ClosureRefused(f"relative import escapes the package in {path}")
                    anchor = ".".join(parts[:keep])
                    base = f"{anchor}.{node.module}" if node.module else anchor
                else:
                    base = node.module or ""
                if not base.startswith(ROOT_PACKAGE + "."):
                    continue
                # `from pkg import name` -- name may be a submodule or an attribute.
                targets = [base] + [f"{base}.{a.name}" for a in node.names]
                if _path_of(base, root) is None:
                    raise ClosureRefused(f"unresolvable intra-package import {base!r} in {path}")
            elif isinstance(node, ast.Import):
                targets = [a.name for a in node.names if a.name.startswith(ROOT_PACKAGE + ".")]

            for target in targets:
                resolved = _path_of(target, root)
                if resolved:
                    stack.append(resolved)
                    stack.extend(_parents_of(target, root))

    return dict(sorted(found.items()))


def runtime_closure(root: str) -> dict[str, str]:
    """What Python ACTUALLY executed, restricted to the REPOSITORY package.

    `root` is the directory containing the `app` package, and in a development checkout that
    directory also contains `.venv`. Scanning it wholesale would sweep in every third-party module
    pytest happened to import, which is not repository code and is bound separately as the
    dependency bundle. The executing closure is repository code, so the scan is anchored on
    `<root>/app`.
    """
    root = os.path.abspath(os.path.join(os.path.abspath(root), ROOT_PACKAGE))
    if not os.path.isdir(root):
        raise ClosureRefused(f"no {ROOT_PACKAGE!r} package under {root}")
    out: dict[str, str] = {}
    for mod in list(sys.modules.values()):
        f = getattr(mod, "__file__", None)
        if not f or not f.endswith(".py"):
            continue
        f = os.path.abspath(f)
        if os.path.commonpath([f, root]) == root and os.path.isfile(f):
            out[f] = _sha256(f)
    return dict(sorted(out.items()))


def verify_static_covers_runtime(static: dict[str, str], runtime: dict[str, str]) -> list[str]:
    """Runtime modules the static binding never predicted. Any such module is unbound executing code."""
    return sorted(set(runtime) - set(static))


def verify(bound: dict[str, str], start_dir: str) -> dict[str, object]:
    """Fail closed on drift, on a missing file, and on an extra file.

    `bound` maps REPOSITORY-RELATIVE path -> sha256, so a binding survives being mounted at a
    different absolute path. Equality is on the set, never on the count.
    """
    start_dir = os.path.abspath(start_dir)
    root = package_root(start_dir)
    actual_abs = static_closure(start_dir)
    actual = {os.path.relpath(p, root).replace(os.sep, "/"): h for p, h in actual_abs.items()}

    missing = sorted(set(bound) - set(actual))
    extra = sorted(set(actual) - set(bound))
    drift = sorted(m for m in set(bound) & set(actual) if bound[m] != actual[m])

    problems = []
    if missing:
        problems.append(f"bound but absent from the mounted closure: {missing}")
    if extra:
        problems.append(f"present and executing but NOT bound: {extra}")
    if drift:
        problems.append(f"identity drift: {drift}")
    if problems:
        raise ClosureRefused("; ".join(problems))

    return {
        "closure_kind": EXECUTING,
        "derivation": "mechanically derived from source; not a hand-maintained list",
        "file_count": len(actual),
        "files": actual,
        "set_equality_proven": True,
        "package_root": root,
    }
