"""AST safety validation for LLM-generated strategy code (P7 §3).

The platform's first execution of freshly-authored, unreviewed Python. The shell
``check_strategy_isolation.sh`` only greps ``app/strategies/`` for ``app.brokers``
imports — it does not cover generated code. This validator runs on the parsed AST
**before** the module is ever executed (``StrategyLoader`` exec's top-level code),
rejecting anything that imports or calls outside the strategy sandbox: brokers,
network, file I/O, subprocess, LLM SDKs, the dynamic-execution builtins, and the
classic sandbox-escape dunders. A denylist of dangerous categories (owner pick) —
the §1 prompt is the first line of defense; this is the enforced gate.
"""
from __future__ import annotations

import ast

# Forbidden top-level import module prefixes. A module ``m`` is forbidden if
# ``m == p`` or ``m.startswith(p + ".")`` for any prefix below.
_FORBIDDEN_MODULES: tuple[str, ...] = (
    "app.brokers",            # ADR 0002 — never bypass OrderRouter
    "socket", "ssl", "requests", "httpx", "urllib", "urllib3", "aiohttp",
    "http", "ftplib", "smtplib", "telnetlib", "poplib", "imaplib",  # network
    "subprocess", "os", "sys", "shutil", "glob", "pathlib", "tempfile",
    "fileinput", "io",        # file / process / system
    "pickle", "marshal", "shelve", "dbm",                            # deser
    "importlib", "imp", "ctypes", "cffi", "mmap",                    # dynamic / native
    "multiprocessing", "threading", "asyncio", "concurrent",         # concurrency
    "webbrowser", "platform", "pty", "signal",
    "anthropic", "openai", "google", "cohere",                       # LLM SDKs
    "builtins", "__main__",
)

# Forbidden builtin calls (dynamic execution / I/O). NOTE: getattr/setattr are NOT
# forbidden — strategies legitimately use getattr(position, "side", None); the
# dunder-attribute check + the import denylist cover the escape vectors.
_FORBIDDEN_CALLS: frozenset[str] = frozenset(
    {"eval", "exec", "compile", "__import__", "open", "input", "breakpoint",
     "globals", "locals", "vars"}
)

# Forbidden attribute access — the classic sandbox-escape chain.
_FORBIDDEN_ATTRS: frozenset[str] = frozenset(
    {"__subclasses__", "__globals__", "__builtins__", "__bases__", "__mro__",
     "__import__", "__loader__", "__code__"}
)


class UnsafeCodeError(Exception):
    """Generated code imports or calls something outside the strategy sandbox."""


def _module_forbidden(module: str) -> bool:
    return any(module == p or module.startswith(p + ".") for p in _FORBIDDEN_MODULES)


def validate_generated_code_tree(tree: ast.AST) -> None:
    """Raise UnsafeCodeError if the AST contains a forbidden import / call / attr."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _module_forbidden(alias.name):
                    raise UnsafeCodeError(f"forbidden import: {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            # `from . import x` has module=None; relative imports aren't resolvable
            # to a file here, so reject them outright (generated code is one file).
            if node.level and node.level > 0:
                raise UnsafeCodeError("forbidden relative import")
            if node.module and _module_forbidden(node.module):
                raise UnsafeCodeError(f"forbidden import: {node.module}")
        elif isinstance(node, ast.Call):
            func = node.func
            if isinstance(func, ast.Name) and func.id in _FORBIDDEN_CALLS:
                raise UnsafeCodeError(f"forbidden call: {func.id}()")
        elif isinstance(node, ast.Attribute) and node.attr in _FORBIDDEN_ATTRS:
            raise UnsafeCodeError(f"forbidden attribute access: {node.attr}")


def validate_generated_code(source: str) -> None:
    """Parse + validate. Raises SyntaxError (unparseable) or UnsafeCodeError."""
    validate_generated_code_tree(ast.parse(source))
