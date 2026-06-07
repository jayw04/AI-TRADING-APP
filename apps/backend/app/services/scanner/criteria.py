"""Safe boolean-expression evaluator for scanner criteria (P8 §2).

A criterion is a Python boolean expression over the platform's *supported
indicator names* (bare variables) plus bar fields — e.g.::

    RSI14 < 35 and ATR14 / close > 0.02

Per P8 Decision 6 there is **no new mini-language and no separate parser**: we
reuse Python's own grammar via ``ast.parse`` and restrict the tree to a tiny
*allowlist* of node types. The allowed name set is **derived from
``CORE_INDICATORS``** (drift-proof) plus the bar fields. Because the validated
tree contains only arithmetic / comparison / boolean ops over floats and is
evaluated with an empty ``__builtins__``, ``eval`` is safe — this is the same
AST-walk muscle as P7 §3's ``code_safety.py``, inverted to an allowlist.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from types import CodeType

from app.indicators.computer import CORE_INDICATORS

# Multi-output indicators expand to their named sub-series (matching the keys
# IndicatorComputer.compute returns for these names).
_MULTI: dict[str, tuple[str, ...]] = {
    "MACD": ("macd", "signal", "hist"),
    "BB": ("bb_lower", "bb_mid", "bb_upper"),
}

# Bare indicator names a criterion may reference, derived from CORE_INDICATORS:
# single-output names as-is, multi-output names expanded to their sub-series.
_SINGLE_INDICATORS: frozenset[str] = frozenset(
    n for n in CORE_INDICATORS if n not in _MULTI
)
_MULTI_SUBNAMES: frozenset[str] = frozenset(
    sub for subs in _MULTI.values() for sub in subs
)
INDICATOR_NAMES: frozenset[str] = _SINGLE_INDICATORS | _MULTI_SUBNAMES

# Bar fields. ``price`` aliases ``close``.
FIELD_NAMES: frozenset[str] = frozenset(
    {"open", "high", "low", "close", "volume", "price"}
)

ALLOWED_NAMES: frozenset[str] = INDICATOR_NAMES | FIELD_NAMES

# Reverse map: a referenced bare name → the CORE_INDICATORS entry to compute.
_NAME_TO_CORE: dict[str, str] = {n: n for n in _SINGLE_INDICATORS}
for _core, _subs in _MULTI.items():
    for _sub in _subs:
        _NAME_TO_CORE[_sub] = _core

# Allowlisted AST node types and operators.
_ALLOWED_NODES: tuple[type[ast.AST], ...] = (
    ast.Expression,
    ast.BoolOp,
    ast.UnaryOp,
    ast.BinOp,
    ast.Compare,
    ast.Constant,
    ast.Name,
    ast.Load,
    ast.And,
    ast.Or,
    ast.Not,
    ast.USub,
    ast.UAdd,
    ast.Add,
    ast.Sub,
    ast.Mult,
    ast.Div,
    ast.Lt,
    ast.LtE,
    ast.Gt,
    ast.GtE,
    ast.Eq,
    ast.NotEq,
)


class CriteriaError(ValueError):
    """Raised when a criterion is syntactically invalid or uses a disallowed
    construct / unknown name. Surfaced as HTTP 400."""


@dataclass(frozen=True)
class ParsedCriteria:
    code: CodeType  # compiled ast.Expression
    names: frozenset[str]  # referenced ALLOWED_NAMES
    indicators: frozenset[str]  # CORE_INDICATORS entries to compute


def validate_criteria(expr: str) -> ParsedCriteria:
    """Parse + allowlist-validate ``expr``; return a ParsedCriteria.

    Raises CriteriaError on a syntax error, a disallowed node type / operator,
    a non-numeric constant, or an unknown name.
    """
    if not expr or not expr.strip():
        raise CriteriaError("empty criterion")
    try:
        tree = ast.parse(expr, mode="eval")
    except SyntaxError as exc:
        raise CriteriaError(f"syntax error: {exc.msg}") from exc

    names: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, _ALLOWED_NODES):
            raise CriteriaError(
                f"disallowed expression element: {type(node).__name__}"
            )
        if isinstance(node, ast.Constant):
            if isinstance(node.value, bool) or not isinstance(
                node.value, (int, float)
            ):
                raise CriteriaError("only numeric constants are allowed")
        elif isinstance(node, ast.Name):
            if node.id not in ALLOWED_NAMES:
                raise CriteriaError(f"unknown name: {node.id}")
            names.add(node.id)

    if not names:
        raise CriteriaError("criterion references no indicators or fields")

    indicators = frozenset(
        _NAME_TO_CORE[n] for n in names if n in INDICATOR_NAMES
    )
    code = compile(tree, "<criteria>", "eval")
    return ParsedCriteria(
        code=code, names=frozenset(names), indicators=indicators
    )


def evaluate(parsed: ParsedCriteria, values: dict[str, float]) -> bool:
    """Evaluate the validated criterion against ``values`` (name → float).

    Safe: the tree was allowlist-validated and runs with no builtins. Callers
    must supply every referenced name (the engine skips a symbol whose values
    are incomplete before calling here).
    """
    result = eval(parsed.code, {"__builtins__": {}}, values)  # noqa: S307
    return bool(result)
