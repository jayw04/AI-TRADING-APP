"""Static second line of defence (WP0.4): RANGE-002 compute modules must require the capability.

EXACT CLAIM. This is a *convenience check for accidental omissions and casual shortcuts*
(Level 1). It is NOT a security boundary: Python is dynamic, and an AST walk cannot see
``setattr``/``exec``/``importlib`` games, C extensions, code generated at run time, or anything
a determined developer writes on purpose. What it does is catch, in the existing backend FULL
pass, the patterns a developer could plausibly write by accident or to save time, and each such
pattern has a synthetic test below. The runtime capability is the first line; this is the
second, and neither claims to stop code execution (Level 2, design-only).

I/O lint (NF6). The ``REVIEWED_PURE_IO`` check is NAME-BASED on ``ast.Call`` nodes. It does NOT
see aliased ``open`` (``o = open``), ``from os import remove``, ``subprocess``, ``sqlite3``,
``socket``/``urllib``, ``getattr(p, "read_text")()``, numpy/pandas/pickle loaders, ``importlib``,
``os.environ``, or I/O reached through a helper function. It is a TEST-ONLY developer
safeguard, not a CI invariant script and not a security boundary.

This lint is a DEVELOPER SAFEGUARD, not an adversary-resistant boundary. Known bypasses it does
NOT catch (round 4, documented rather than closed; the lint is deliberately not expanded):
re-exporting a guarded callable through a private lambda; a dict (or other container) of
undecorated functions; aliased imports of capability-bearing objects from other libraries or
modules; and anything under ``scripts/`` (not linted at all).

Rules for every module under ``app/research/range002/`` outside ``governance/``
(``__init__.py`` files included):

R-A  every public callable -- top-level ``def``/``async def`` (also nested under
     ``if``/``try``/``with``/``for``/``while``), public methods of every class, dunder
     methods other than a small harmless set (``__call__``, ``__iter__``, ``__getattr__``,
     ... are entry points), and public names bound to a ``lambda`` or to an undecorated local
     function -- must be decorated with ``requires_capability`` *as imported from
     governance.results_guard* (aliases and relative imports are resolved; the name must be
     bound exactly once in the whole module, so a local definition or ANY re-binding -- tuple
     assignment, ``for``/``with`` target, walrus, ``global``, class-body or function-body
     import -- voids the trust), unless ``module:name`` is in ``REVIEWED_PURE`` below AND the
     module also declares the name in its own ``PURE_FUNCTIONS`` tuple (declaration alone is
     not enough);
R-A2 a public module- or class-level name may only be bound to a plain ``def``/``class`` or a
     constant expression. A call, lambda, partial, comprehension, walrus or any other computed
     value bound to a public name (by assignment, tuple unpacking, ``for`` or ``with ... as``)
     is flagged, which also covers a private factory that returns a closure or class, and
     ``globals()``/``vars()``/``exec``/``eval`` namespace games. Reviewed exceptions go in
     ``REVIEWED_VALUES``;
R-B  no import of, or attribute access to, an underscore-private name of a governance
     module (``rg._ISSUE``, ``_BOUND_REGISTRIES``, dotted or aliased, ``getattr(rg, "_x")``),
     following imports made in ANY scope, function bodies included;
R-C  no reference whatsoever to ``ResultsCapability`` outside governance (import, name,
     attribute, annotation string) -- the type is not public API for compute code;
R-D  no dynamic import of a governance module (``importlib.import_module`` / ``__import__``);
R-E  no ``.__wrapped__`` access, ``"__wrapped__"`` string or ``inspect.unwrap`` call, which would
     reach the undecorated function behind ``requires_capability``.

The modules the plan reserves for compute (``engine``, ``stats``, ``controls``) do not
exist yet; the real-tree test passes on the spec package alone until they do.
"""

from __future__ import annotations

import ast
from collections import Counter
from pathlib import Path

RANGE002 = Path(__file__).resolve().parents[4] / "app" / "research" / "range002"
PKG = "app.research.range002"
GOVERNANCE = f"{PKG}.governance"
RESULTS_GUARD = f"{GOVERNANCE}.results_guard"
DEFAULT_MODULE = f"{PKG}.engine.mod"

#: Reviewed allowlist (module:qualified-name). The only callables exempt from
#: ``@requires_capability``: spec handling computes no returns. Adding an entry is a
#: reviewed change to THIS file; a module's own ``PURE_FUNCTIONS`` cannot grant itself an
#: exemption.
REVIEWED_PURE: tuple[str, ...] = (
    f"{PKG}.spec.hashing:canonical_json",
    f"{PKG}.spec.hashing:content_sha256",
    f"{PKG}.spec.hashing:file_sha256",
    f"{PKG}.spec.hashing:loads_strict",
    f"{PKG}.spec.loader:parse_draft",
    f"{PKG}.spec.loader:load_draft",
    f"{PKG}.spec.loader:spec_sha256",
    f"{PKG}.spec.loader:is_loader_minted",
    f"{PKG}.spec.loader:load_frozen",
    f"{PKG}.spec.loader:SpecView.__copy__",  # raise: a minted view cannot be copied
    f"{PKG}.spec.loader:SpecView.__deepcopy__",
    f"{PKG}.spec.loader:SpecView.__reduce__",
    f"{PKG}.spec.immutable:deep_freeze",
    f"{PKG}.spec.schema:validate_partition_layout",
    f"{PKG}.spec.schema:draft_skeleton",
    f"{PKG}.spec.schema:DraftSpec.hashable_payload",
    f"{PKG}.spec.schema:DraftSpec.unset_p0_fields",
    f"{PKG}.spec.schema:DraftSpec.missing_signoff_fields",
    f"{PKG}.spec.schema:FrozenSpec.from_draft",
    f"{PKG}.spec.schema:FrozenSpec.draft",
    f"{PKG}.spec.schema:FrozenSpec.__setattr__",  # raises: the frozen spec is immutable
    f"{PKG}.spec.genesis:is_canonical_uuid4",  # round 5: genesis id format check
    f"{PKG}.spec.genesis:new_genesis_id",
    f"{PKG}.spec.manifest:parse_manifest",  # round 5: owner-approved governance manifest
    f"{PKG}.spec.manifest:GovernanceManifest.is_genesis_approved",
    f"{PKG}.spec.manifest:GovernanceManifest.require_genesis",
    f"{PKG}.spec.manifest:GovernanceManifest.require_limits",
    f"{PKG}.spec.manifest:GovernanceManifest.check_genesis",
    f"{PKG}.spec.manifest:GovernanceManifest.check_limits",
)

#: Reviewed pure-but-does-file-I/O entries (module:function), each the NARROWEST possible. These
#: are exempt from ``@requires_capability`` like REVIEWED_PURE, but a function that performs file
#: I/O directly is accepted ONLY if it is listed here by exact name; any other I/O function is
#: flagged even if it is also in REVIEWED_PURE. No blanket or module-wide exemption.
REVIEWED_PURE_IO: tuple[str, ...] = (
    # I/O performed: reads the single fixed committed governance manifest file (or, as a test
    # seam, the one file named by its ``path`` argument): is_symlink/is_file/stat/read_bytes on
    # that one path. Nothing else is opened, written, listed or deleted; no data, no network.
    f"{PKG}.spec.manifest:load_manifest",
    # I/O performed: opens the ONE file whose path it is given, read-only and streamed, to hash
    # its bytes. No writes; nothing else is touched.
    f"{PKG}.spec.hashing:file_sha256",
)

#: Attribute calls treated as file I/O by the lint (direct calls in the function body only; I/O
#: reached through a helper is not seen -- a Level 1 convenience check, not a boundary).
_IO_ATTRS = frozenset(
    {
        "open", "read_text", "read_bytes", "write_text", "write_bytes", "stat", "lstat",
        "is_file", "is_dir", "is_symlink", "exists", "iterdir", "glob", "rglob", "unlink",
        "mkdir", "rmdir", "rename", "touch", "readlink", "listdir", "remove", "scandir",
    }
)  # fmt: skip
_IO_ROOTS = frozenset({"os", "shutil", "io", "tempfile"})


def _io_calls(fn: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Name-based scan of ``ast.Call`` nodes only. It does not see aliased ``open``, ``from os
    import remove``, subprocess, sqlite3, socket/urllib, ``getattr(p, "read_text")()``, numpy,
    pandas or pickle loaders, importlib, ``os.environ`` or I/O reached through a helper."""
    found: list[str] = []
    for node in ast.walk(fn):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == "open":
            found.append("open")
        elif isinstance(func, ast.Attribute):
            root = _dotted(func) or ""
            if func.attr in _IO_ATTRS or root.split(".")[0] in _IO_ROOTS:
                found.append(func.attr)
    return found


#: Reviewed non-constant public value bindings (module:name). Adding one is a reviewed change.
REVIEWED_VALUES: tuple[str, ...] = (
    # pydantic type aliases and model config: declarative, not callable compute
    f"{PKG}.spec.schema:OptPos",
    f"{PKG}.spec.schema:OptPosInt",
    f"{PKG}.spec.schema:OptNonNeg",
    f"{PKG}.spec.schema:ExitFamily",
    f"{PKG}.spec.schema:_Model.model_config",
)

#: Dunder methods of a class that cannot hand back computed results on their own.
SAFE_DUNDERS = frozenset(
    {"__init__", "__post_init__", "__repr__", "__str__", "__hash__", "__eq__", "__init_subclass__"}
)
_NAMESPACE_GAMES = frozenset({"globals", "vars", "locals", "exec", "eval"})

_BLOCK_FIELDS = ("body", "orelse", "finalbody", "handlers")


def _is_private(name: str) -> bool:
    return name.startswith("_") and not (name.startswith("__") and name.endswith("__"))


def _module_package(module: str, is_init: bool) -> list[str]:
    parts = module.split(".")
    return parts if is_init else parts[:-1]


def _resolve_from(node: ast.ImportFrom, module: str, is_init: bool) -> str:
    if node.level == 0:
        return node.module or ""
    base = _module_package(module, is_init)
    base = base[: len(base) - (node.level - 1)] if node.level > 1 else base
    return ".".join([*base, *([node.module] if node.module else [])])


def _statements(body: list[ast.stmt]) -> list[ast.stmt]:
    """Every statement reachable without entering a function or class body."""
    out: list[ast.stmt] = []
    for stmt in body:
        out.append(stmt)
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            continue
        for field in _BLOCK_FIELDS:
            for child in getattr(stmt, field, []) or []:
                if isinstance(child, ast.ExceptHandler):
                    out.extend(_statements(child.body))
                elif isinstance(child, ast.stmt):
                    out.extend(_statements([child]))
        if isinstance(stmt, ast.Match):
            for case in stmt.cases:
                out.extend(_statements(case.body))
    return out


def _dotted(node: ast.AST) -> str | None:
    parts: list[str] = []
    while isinstance(node, ast.Attribute):
        parts.append(node.attr)
        node = node.value
    if isinstance(node, ast.Name):
        parts.append(node.id)
        return ".".join(reversed(parts))
    return None


def _binding_counts(tree: ast.Module) -> Counter[str]:
    """How many times each name is bound ANYWHERE in the module, in any scope and by any form:
    assignment targets (tuple/star/walrus/for/with-as/del), def/class names, parameters,
    imports (also inside functions), ``global``/``nonlocal`` declarations, except-as and match
    captures. Deliberately over-counts: a name bound twice is not trusted as an import alias."""
    counts: Counter[str] = Counter()
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store | ast.Del):
            counts[node.id] += 1
        elif isinstance(node, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            counts[node.name] += 1
        elif isinstance(node, ast.arg):
            counts[node.arg] += 1
        elif isinstance(node, ast.Import | ast.ImportFrom):
            for a in node.names:
                counts[a.asname or a.name.split(".")[0]] += 1
        elif isinstance(node, ast.Global | ast.Nonlocal):
            for n in node.names:
                counts[n] += 1
        elif (
            isinstance(node, ast.ExceptHandler)
            and node.name
            or isinstance(node, ast.MatchAs | ast.MatchStar)
            and node.name
        ):
            counts[node.name] += 1
        elif isinstance(node, ast.MatchMapping) and node.rest:
            counts[node.rest] += 1
    return counts


class _Aliases:
    """Import aliases, resolved to fully qualified dotted targets.

    ``resolve`` (used to trust a DECORATOR) only believes a module-level import whose local name is
    bound exactly once in the whole module, in any scope and by any binding form. ``resolve_any``
    (used to find access to governance privates) is the opposite and conservative: it follows
    imports from every scope, including function bodies, and every candidate target.
    """

    def __init__(self, tree: ast.Module, module: str, is_init: bool) -> None:
        counts = _binding_counts(tree)
        top = {id(s) for s in _statements(tree.body) if isinstance(s, ast.Import | ast.ImportFrom)}
        self.trusted: dict[str, str] = {}
        self.anywhere: dict[str, set[str]] = {}
        for node in ast.walk(tree):
            if not isinstance(node, ast.Import | ast.ImportFrom):
                continue
            pairs: list[tuple[str, str]] = []
            if isinstance(node, ast.Import):
                for a in node.names:
                    if a.asname:
                        pairs.append((a.asname, a.name))
                    else:
                        pairs.append((a.name.split(".")[0], a.name.split(".")[0]))
            else:
                base = _resolve_from(node, module, is_init)
                for a in node.names:
                    pairs.append((a.asname or a.name, f"{base}.{a.name}" if base else a.name))
            for local, target in pairs:
                self.anywhere.setdefault(local, set()).add(target)
                if id(node) in top and counts[local] == 1:
                    self.trusted[local] = target

    def resolve(self, node: ast.AST) -> str | None:
        """Qualified name through a TRUSTED (single-binding, module-level) import alias."""
        dotted = _dotted(node)
        if dotted is None:
            return None
        head, _, rest = dotted.partition(".")
        base = self.trusted.get(head)
        if base is None:
            return None
        return f"{base}.{rest}" if rest else base

    def resolve_any(self, node: ast.AST) -> set[str]:
        """Every qualified name this chain could mean, through imports from any scope."""
        dotted = _dotted(node)
        if dotted is None:
            return set()
        head, _, rest = dotted.partition(".")
        return {f"{b}.{rest}" if rest else b for b in self.anywhere.get(head, set())}


def _is_governance(qualified: str | None) -> bool:
    return qualified is not None and (
        qualified == GOVERNANCE or qualified.startswith(GOVERNANCE + ".")
    )


def _decorated(fn: ast.FunctionDef | ast.AsyncFunctionDef, aliases: _Aliases) -> bool:
    return any(
        aliases.resolve(d) == f"{RESULTS_GUARD}.requires_capability" for d in fn.decorator_list
    )


def lint_source(
    source: str,
    filename: str = "<mod>",
    module: str = DEFAULT_MODULE,
    *,
    is_init: bool = False,
    reviewed: tuple[str, ...] | None = None,
    reviewed_io: tuple[str, ...] | None = None,
) -> list[str]:
    reviewed_set = set(REVIEWED_PURE if reviewed is None else reviewed)
    io_set = set(REVIEWED_PURE_IO if reviewed_io is None else reviewed_io)
    reviewed_set |= io_set  # an I/O entry is also a reviewed-pure entry, but only by exact name
    reviewed_values = set(REVIEWED_VALUES)
    tree = ast.parse(source, filename)
    aliases = _Aliases(tree, module, is_init)
    problems: list[str] = []

    declared: set[str] = set()
    for top in _statements(tree.body):
        if isinstance(top, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "PURE_FUNCTIONS" for t in top.targets
        ):
            try:
                declared = {str(x) for x in ast.literal_eval(top.value)}
            except (ValueError, SyntaxError):
                problems.append(f"{filename}: PURE_FUNCTIONS must be a literal tuple of names")
    for name in sorted(declared):
        if f"{module}:{name}" not in reviewed_set:
            problems.append(
                f"{filename}: PURE_FUNCTIONS declares '{name}' which is not in the reviewed "
                f"allowlist (add '{module}:{name}' to REVIEWED_PURE in test_import_lint.py)"
            )

    def exempt(qualname: str) -> bool:
        # both halves: declared by the module AND reviewed here (class members are reviewed
        # as Class.member; the module-level tuple lists the bare function names)
        key = f"{module}:{qualname}"
        return key in reviewed_set and (qualname in declared or "." in qualname)

    def io_problem(fn: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str) -> None:
        calls = _io_calls(fn)
        if calls and f"{module}:{qualname}" not in io_set:
            problems.append(
                f"{filename}:{fn.lineno}: '{qualname}' performs file I/O ({sorted(set(calls))}) "
                f"but is not in REVIEWED_PURE_IO (add '{module}:{qualname}' with a comment "
                "stating exactly what it reads or writes)"
            )

    def check_callable(
        fn: ast.FunctionDef | ast.AsyncFunctionDef, qualname: str, in_class: bool
    ) -> None:
        if _is_private(fn.name):
            return
        if fn.name.startswith("__") and in_class and fn.name in SAFE_DUNDERS:
            return
        if _decorated(fn, aliases):
            return
        if exempt(qualname):
            io_problem(fn, qualname)
            return
        kind = "dunder method" if fn.name.startswith("__") else "public callable"
        problems.append(
            f"{filename}:{fn.lineno}: {kind} '{qualname}' lacks @requires_capability "
            "(imported from governance.results_guard) or a reviewed PURE declaration"
        )

    def flatten(target: ast.AST) -> list[ast.Name]:
        if isinstance(target, ast.Name):
            return [target]
        if isinstance(target, ast.Tuple | ast.List):
            return [n for elt in target.elts for n in flatten(elt)]
        if isinstance(target, ast.Starred):
            return flatten(target.value)
        return []

    def constant_expr(node: ast.AST | None) -> bool:
        if node is None or isinstance(node, ast.Constant):
            return True
        if isinstance(node, ast.UnaryOp):
            return constant_expr(node.operand)
        if isinstance(node, ast.BinOp):
            return constant_expr(node.left) and constant_expr(node.right)
        if isinstance(node, ast.Tuple | ast.List | ast.Set):
            return all(constant_expr(e) for e in node.elts)
        if isinstance(node, ast.Dict):
            return all(k is not None and constant_expr(k) for k in node.keys) and all(
                constant_expr(v) for v in node.values
            )
        return isinstance(node, ast.Name | ast.Attribute)  # plain re-export / alias of a name

    def value_pairs(stmt: ast.stmt) -> list[tuple[ast.Name, ast.AST | None, str]]:
        """(public target, value, binding form) for every name this statement binds."""
        out: list[tuple[ast.Name, ast.AST | None, str]] = []
        if isinstance(stmt, ast.Assign):
            for t in stmt.targets:
                if isinstance(t, ast.Tuple | ast.List) and isinstance(
                    stmt.value, ast.Tuple | ast.List
                ):
                    elts = stmt.value.elts
                    names = t.elts
                    if len(elts) == len(names) and not any(
                        isinstance(e, ast.Starred) for e in (*elts, *names)
                    ):
                        out += [
                            (n, e, "tuple assignment")
                            for nm, e in zip(names, elts, strict=True)
                            for n in flatten(nm)
                        ]
                        continue
                out += [(n, stmt.value, "assignment") for n in flatten(t)]
        elif isinstance(stmt, ast.AnnAssign):
            out += [(n, stmt.value, "assignment") for n in flatten(stmt.target)]
        elif isinstance(stmt, ast.AugAssign):
            out += [(n, stmt.value, "augmented assignment") for n in flatten(stmt.target)]
        elif isinstance(stmt, ast.For | ast.AsyncFor):
            out += [(n, None, "for target") for n in flatten(stmt.target)]
        elif isinstance(stmt, ast.With | ast.AsyncWith):
            for item in stmt.items:
                if item.optional_vars is not None:
                    out += [(n, item.context_expr, "with-as") for n in flatten(item.optional_vars)]
        return [
            (n, v, form)
            for n, v, form in out
            if not _is_private(n.id) and not n.id.startswith("__")
        ]

    def stmt_exprs(stmt: ast.stmt) -> list[ast.AST]:
        if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef | ast.ClassDef):
            return []
        found: list[ast.AST] = []
        for child in ast.iter_child_nodes(stmt):
            if isinstance(child, ast.stmt | ast.ExceptHandler | ast.match_case):
                continue
            found.extend(ast.walk(child))
        return found

    def check_value(
        stmt: ast.stmt, name: ast.Name, value: ast.AST | None, form: str, prefix: str
    ) -> None:
        qual = f"{prefix}{name.id}"
        if f"{module}:{qual}" in reviewed_values or name.id == "PURE_FUNCTIONS":
            return
        if isinstance(value, ast.Lambda):
            if not exempt(qual):
                problems.append(
                    f"{filename}:{stmt.lineno}: public name '{qual}' is bound to a lambda "
                    "(a compute entry point without @requires_capability)"
                )
        elif isinstance(value, ast.Name) and value.id in local_funcs_by_scope.get(prefix, {}):
            target_fn = local_funcs_by_scope[prefix][value.id]
            if not (_decorated(target_fn, aliases) or exempt(qual)):
                problems.append(
                    f"{filename}:{stmt.lineno}: public alias '{qual}' "
                    f"re-exports undecorated '{value.id}'"
                )
        elif (form == "for target" or not constant_expr(value)) and not exempt(qual):
            what = type(value).__name__ if value is not None else form
            extra = ""
            if isinstance(value, ast.Call):
                callee = _dotted(value.func) or "<call>"
                extra = f" (a call to '{callee}': a factory/partial can return a closure or class)"
            problems.append(
                f"{filename}:{stmt.lineno}: public name '{qual}' is bound by {form} to a "
                f"non-constant value ({what}){extra}; only plain def/class/constants may be "
                "public (add to REVIEWED_VALUES if reviewed)"
            )

    local_funcs_by_scope: dict[str, dict[str, ast.FunctionDef | ast.AsyncFunctionDef]] = {}

    def check_body(body: list[ast.stmt], prefix: str, in_class: bool = False) -> None:
        local_funcs: dict[str, ast.FunctionDef | ast.AsyncFunctionDef] = {}
        for stmt in _statements(body):
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                local_funcs[stmt.name] = stmt
        local_funcs_by_scope[prefix] = local_funcs
        for stmt in _statements(body):
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                check_callable(stmt, f"{prefix}{stmt.name}", in_class)
            elif isinstance(stmt, ast.ClassDef):
                check_body(stmt.body, f"{prefix}{stmt.name}.", True)
            else:
                for name, value, form in value_pairs(stmt):
                    check_value(stmt, name, value, form, prefix)
                for expr in stmt_exprs(stmt):
                    if (
                        isinstance(expr, ast.NamedExpr)
                        and isinstance(expr.target, ast.Name)
                        and not _is_private(expr.target.id)
                        and not expr.target.id.startswith("__")
                    ):
                        check_value(stmt, expr.target, expr.value, "walrus", prefix)

    check_body(tree.body, "")

    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            resolved = _resolve_from(node, module, is_init)
            if _is_governance(resolved):
                for alias in node.names:
                    if _is_private(alias.name):
                        problems.append(
                            f"{filename}:{node.lineno}: imports private '{alias.name}' "
                            "from governance"
                        )
            for alias in node.names:
                if alias.name == "ResultsCapability":
                    problems.append(f"{filename}:{node.lineno}: imports ResultsCapability")
        if isinstance(node, ast.Name) and node.id == "ResultsCapability":
            problems.append(f"{filename}:{node.lineno}: references ResultsCapability")
        if isinstance(node, ast.Attribute):
            if node.attr == "ResultsCapability":
                problems.append(f"{filename}:{node.lineno}: references ResultsCapability")
            if node.attr == "__wrapped__":
                problems.append(
                    f"{filename}:{node.lineno}: accesses '.__wrapped__' (reaches behind "
                    "@requires_capability)"
                )
            if _is_private(node.attr) and any(_is_governance(r) for r in aliases.resolve_any(node)):
                problems.append(
                    f"{filename}:{node.lineno}: accesses private '{node.attr}' of governance"
                )
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if "ResultsCapability" in node.value:
                problems.append(f"{filename}:{node.lineno}: string mentions ResultsCapability")
            if "__wrapped__" in node.value:
                problems.append(f"{filename}:{node.lineno}: string mentions '__wrapped__'")
        if isinstance(node, ast.Call):
            raw = _dotted(node.func) or ""
            callees = {raw, *aliases.resolve_any(node.func)} - {""}
            args = node.args
            first = args[0] if args else None
            if callees & {"inspect.unwrap", "functools.unwrap"}:
                problems.append(
                    f"{filename}:{node.lineno}: calls inspect.unwrap (reaches behind "
                    "@requires_capability)"
                )
            if raw in _NAMESPACE_GAMES:
                problems.append(
                    f"{filename}:{node.lineno}: calls {raw}() (dynamic namespace access can "
                    "bind a public name outside the checked forms)"
                )
            if "getattr" in callees and len(args) >= 2:
                targets = aliases.resolve_any(args[0])
                attr = args[1]
                if (
                    any(_is_governance(t) for t in targets)
                    and isinstance(attr, ast.Constant)
                    and isinstance(attr.value, str)
                    and (_is_private(attr.value) or attr.value == "ResultsCapability")
                ):
                    problems.append(
                        f"{filename}:{node.lineno}: getattr() of private governance "
                        f"name '{attr.value}'"
                    )
            if (
                callees & {"importlib.import_module", "__import__"}
                and isinstance(first, ast.Constant)
                and isinstance(first.value, str)
                and _is_governance(first.value)
            ):
                problems.append(f"{filename}:{node.lineno}: dynamic import of a governance module")
    return sorted(set(problems))


def lint_tree(
    root: Path,
    package: str = PKG,
    reviewed: tuple[str, ...] | None = None,
    reviewed_io: tuple[str, ...] | None = None,
) -> list[str]:
    problems: list[str] = []
    for path in sorted(root.rglob("*.py")):
        rel = path.relative_to(root)
        if rel.parts[0] == "governance":
            continue
        is_init = path.name == "__init__.py"
        parts = [*rel.parts[:-1], *([] if is_init else [path.stem])]
        module = ".".join([package, *parts])
        problems += lint_source(
            path.read_text(encoding="utf-8"),
            str(rel),
            module,
            is_init=is_init,
            reviewed=reviewed,
            reviewed_io=reviewed_io,
        )
    return problems


# --- the real tree ---------------------------------------------------------------------


def test_real_range002_tree_complies() -> None:
    assert RANGE002.is_dir()
    assert lint_tree(RANGE002) == []


def test_reviewed_allowlist_has_no_stale_entries() -> None:
    """Every reviewed pure entry must exist, and every module declaration must be reviewed."""
    seen: set[str] = set()
    for entry in (*REVIEWED_PURE, *REVIEWED_PURE_IO):
        module, _, qual = entry.partition(":")
        rel = Path(*module.split(".")[len(PKG.split(".")) :])
        candidates = [RANGE002 / rel.with_suffix(".py"), RANGE002 / rel / "__init__.py"]
        path = next(p for p in candidates if p.is_file())
        tree = ast.parse(path.read_text(encoding="utf-8"))
        names: set[str] = set()
        for stmt in _statements(tree.body):
            if isinstance(stmt, ast.FunctionDef | ast.AsyncFunctionDef):
                names.add(stmt.name)
            elif isinstance(stmt, ast.ClassDef):
                names.update(
                    f"{stmt.name}.{m.name}"
                    for m in stmt.body
                    if isinstance(m, ast.FunctionDef | ast.AsyncFunctionDef)
                )
        assert qual in names, f"stale reviewed-pure entry {entry}"
        seen.add(entry)
    assert seen == set(REVIEWED_PURE) | set(REVIEWED_PURE_IO)


def test_governance_package_is_research_plane_clean() -> None:
    """Governance must not import the order path, brokers, or any LLM/broker SDK."""
    forbidden = ("app.orders", "app.risk", "app.brokers", "anthropic", "alpaca")
    for path in (RANGE002 / "governance").rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            mods: list[str] = []
            if isinstance(node, ast.Import):
                mods = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                mods = [node.module]
            for m in mods:
                assert not m.startswith(forbidden), f"{path.name} imports {m}"


# --- synthetic: what the lint accepts ----------------------------------------------------

GOOD_IMPORT = f"from {RESULTS_GUARD} import requires_capability\n"


def flagged(src: str, **kw: object) -> list[str]:
    return lint_source(src, **kw)  # type: ignore[arg-type]


def test_lint_accepts_decorated_private_and_reviewed_pure() -> None:
    src = (
        GOOD_IMPORT + "PURE_FUNCTIONS = ('holm',)\n"
        "@requires_capability\n"
        "def run_engine(x, *, capability):\n    return x\n"
        "def holm(p):\n    return p\n"
        "def _helper():\n    return 1\n"
        "class K:\n"
        "    @requires_capability\n"
        "    def method(self, *, capability):\n        return 1\n"
        "    def _private(self):\n        return 1\n"
        "    def __repr__(self):\n        return 'K'\n"
    )
    assert lint_source(src, reviewed=(f"{DEFAULT_MODULE}:holm",)) == []


def test_lint_accepts_attribute_alias_and_relative_import_decorators() -> None:
    attr = f"import {RESULTS_GUARD} as rg\n@rg.requires_capability\ndef f(*, capability):\n    return 1\n"
    assert flagged(attr) == []
    pkg_import = (
        f"from {GOVERNANCE} import results_guard as g\n"
        "@g.requires_capability\ndef f(*, capability):\n    return 1\n"
    )
    assert flagged(pkg_import) == []
    renamed = (
        f"from {RESULTS_GUARD} import requires_capability as rc\n"
        "@rc\ndef f(*, capability):\n    return 1\n"
    )
    assert flagged(renamed) == []
    rel = (
        "from ..governance.results_guard import requires_capability\n"
        "@requires_capability\ndef f(*, capability):\n    return 1\n"
    )
    assert flagged(rel, module=f"{PKG}.engine.mod") == []
    rel_pkg = (
        "from ..governance import results_guard\n"
        "@results_guard.requires_capability\ndef f(*, capability):\n    return 1\n"
    )
    assert flagged(rel_pkg, module=f"{PKG}.engine.mod") == []
    rel_init = (
        "from .. import governance\n"
        "from ..governance.results_guard import requires_capability\n"
        "@requires_capability\ndef f(*, capability):\n    return 1\n"
    )
    assert flagged(rel_init, module=f"{PKG}.engine", is_init=True) == []


# --- synthetic: every previously-bypassing pattern is now flagged ----------------------------


def test_lint_flags_undecorated_public_function_sync_and_async() -> None:
    assert any("lacks @requires_capability" in p for p in flagged("def run(x):\n    return x\n"))
    assert flagged("async def go():\n    return 1\n")


def test_bypass_function_nested_under_if_or_try() -> None:
    assert flagged("if True:\n    def run(x):\n        return x\n")
    assert flagged("try:\n    pass\nexcept ImportError:\n    def run(x):\n        return x\n")
    assert flagged(
        "try:\n    import x\nexcept ImportError:\n    pass\nelse:\n    def run():\n        ...\n"
    )
    assert flagged("try:\n    pass\nfinally:\n    def run():\n        ...\n")
    assert flagged("with open('f') as fh:\n    def run():\n        ...\n")
    assert flagged("for _ in range(1):\n    def run():\n        ...\n")
    assert flagged("while False:\n    def run():\n        ...\n")
    assert flagged("match 1:\n    case 1:\n        def run():\n            ...\n")


def test_bypass_public_method_of_a_class() -> None:
    assert any(
        "K.method" in p for p in flagged("class K:\n    def method(self):\n        return 1\n")
    )
    assert flagged("class K:\n    async def go(self):\n        return 1\n")
    # nested class and a class under an if
    assert flagged("class A:\n    class B:\n        def run(self):\n            return 1\n")
    assert flagged("if True:\n    class K:\n        def run(self):\n            return 1\n")


def test_bypass_lambda_assignment() -> None:
    assert any("lambda" in p for p in flagged("run = lambda x: x\n"))
    assert any("lambda" in p for p in flagged("run: object = lambda x: x\n"))
    assert flagged("if True:\n    run = lambda x: x\n")
    assert flagged("class K:\n    run = lambda self: 1\n")
    assert flagged("a = b = lambda: 1\n")
    assert flagged("_hidden = lambda: 1\n") == []  # private names are not entry points


def test_bypass_public_alias_of_undecorated_private_function() -> None:
    src = "def _impl(x):\n    return x\nrun = _impl\n"
    assert any("re-exports" in p for p in flagged(src))
    ok = (
        GOOD_IMPORT + "@requires_capability\ndef _impl(*, capability):\n    return 1\nrun = _impl\n"
    )
    assert flagged(ok) == []


def test_bypass_init_py_is_linted() -> None:
    assert flagged("def run():\n    ...\n", module=f"{PKG}.engine", is_init=True)


def test_lint_tree_includes_init_files_and_skips_governance(tmp_path: Path) -> None:
    (tmp_path / "engine").mkdir()
    (tmp_path / "governance").mkdir()
    (tmp_path / "engine" / "__init__.py").write_text("def sneaky():\n    return 1\n")
    (tmp_path / "engine" / "sim.py").write_text("def simulate(x):\n    return x\n")
    (tmp_path / "governance" / "g.py").write_text("def exempt(): ...\n")
    problems = lint_tree(tmp_path)
    assert len(problems) == 2
    assert any("sneaky" in p for p in problems) and any("simulate" in p for p in problems)


def test_bypass_local_decorator_with_the_same_name() -> None:
    local = (
        "def requires_capability(f):\n    return f\n"
        "@requires_capability\ndef run(*, capability):\n    return 1\n"
    )
    assert any("lacks" in p and "run" in p for p in flagged(local))
    other_module = (
        "from some.other import requires_capability\n"
        "@requires_capability\ndef run(*, capability):\n    return 1\n"
    )
    assert any("lacks" in p for p in flagged(other_module))
    rebound = (
        GOOD_IMPORT + "requires_capability = lambda f: f\n"
        "@requires_capability\ndef run(*, capability):\n    return 1\n"
    )
    assert any("lacks" in p for p in flagged(rebound))
    wrong_attr = (
        "import functools as rg\n@rg.requires_capability\ndef run(*, capability):\n    return 1\n"
    )
    assert any("lacks" in p for p in flagged(wrong_attr))
    call_form = GOOD_IMPORT + "@requires_capability()\ndef run(*, capability):\n    return 1\n"
    assert any("lacks" in p for p in flagged(call_form))


def test_bypass_pure_functions_declaration_alone_is_not_enough() -> None:
    src = "PURE_FUNCTIONS = ('compute_returns',)\ndef compute_returns(x):\n    return x\n"
    problems = flagged(src)
    assert any("not in the reviewed allowlist" in p for p in problems)
    assert any("lacks @requires_capability" in p for p in problems)
    # allowlisted for the module but not declared by the module: still flagged
    only_reviewed = "def holm(p):\n    return p\n"
    assert flagged(only_reviewed, reviewed=(f"{DEFAULT_MODULE}:holm",))
    # allowlisted for a different module: still flagged
    assert flagged(src, reviewed=(f"{PKG}.other.mod:compute_returns",))
    # declared AND reviewed for this module: accepted
    assert flagged(src, reviewed=(f"{DEFAULT_MODULE}:compute_returns",)) == []


def test_lint_flags_non_literal_pure_declaration() -> None:
    assert any("literal" in p for p in flagged("PURE_FUNCTIONS = make()\n"))
    assert any("literal" in p for p in flagged("if True:\n    PURE_FUNCTIONS = make()\n"))


def test_bypass_private_name_import_and_access() -> None:
    priv = f"from {RESULTS_GUARD} import _ISSUE\n"
    assert any("private" in p for p in flagged(priv))
    rel_priv = "from ..governance.results_guard import _BOUND_REGISTRIES\n"
    assert any("private" in p for p in flagged(rel_priv, module=f"{PKG}.engine.mod"))
    alias_priv = f"from {RESULTS_GUARD} import _ISSUE as innocuous\n"
    assert any("private" in p for p in flagged(alias_priv))
    attr = f"import {RESULTS_GUARD} as rg\nx = rg._ISSUE\n"
    assert any("accesses private '_ISSUE'" in p for p in flagged(attr))
    attr2 = f"from {GOVERNANCE} import results_guard\nresults_guard._BOUND_REGISTRIES.add('x')\n"
    assert any("_BOUND_REGISTRIES" in p for p in flagged(attr2))
    dotted = f"import {RESULTS_GUARD}\nx = {RESULTS_GUARD}._ISSUE\n"
    assert any("private" in p for p in flagged(dotted))
    deep = f"import {GOVERNANCE}\nx = {GOVERNANCE}.results_guard._BOUND_REGISTRIES\n"
    assert any("private" in p for p in flagged(deep))
    rel_attr = "from ..governance import results_guard as r\nx = r._ISSUE\n"
    assert any("private" in p for p in flagged(rel_attr, module=f"{PKG}.engine.mod"))
    via_getattr = f"import {RESULTS_GUARD} as rg\nx = getattr(rg, '_ISSUE')\n"
    assert any("getattr" in p for p in flagged(via_getattr))
    # unrelated modules' private names are none of this lint's business
    assert flagged("import os\nx = os._exit\n") == []


def test_bypass_dynamic_import_of_governance() -> None:
    src = f"import importlib\nm = importlib.import_module('{RESULTS_GUARD}')\n"
    assert any("dynamic import" in p for p in flagged(src))
    assert any("dynamic import" in p for p in flagged(f"m = __import__('{RESULTS_GUARD}')\n"))
    assert flagged("import importlib\nimportlib.import_module('json')\n") == []


def test_bypass_any_reference_to_results_capability() -> None:
    assert any("ResultsCapability" in p for p in flagged("x = ResultsCapability(1)\n"))
    assert any("ResultsCapability" in p for p in flagged("x = rg.ResultsCapability(1)\n"))
    imp = f"from {RESULTS_GUARD} import ResultsCapability\n"
    assert any("imports ResultsCapability" in p for p in flagged(imp))
    aliased = f"from {RESULTS_GUARD} import ResultsCapability as RC\nx = RC(1)\n"
    assert any("imports ResultsCapability" in p for p in flagged(aliased))
    annotation = (
        GOOD_IMPORT + "@requires_capability\n"
        "def f(*, capability: 'ResultsCapability'):\n    return 1\n"
    )
    assert any("string mentions" in p for p in flagged(annotation))
    typed = (
        "from __future__ import annotations\n" + GOOD_IMPORT + "@requires_capability\n"
        "def f(*, capability: ResultsCapability):\n    return 1\n"
    )
    assert any("references ResultsCapability" in p for p in flagged(typed))
    via_getattr = f"import {RESULTS_GUARD} as rg\nx = getattr(rg, 'ResultsCapability')\n"
    assert any("getattr" in p for p in flagged(via_getattr))
