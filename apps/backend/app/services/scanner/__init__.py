"""P8 scanner — deterministic stock screening (no LLM; ADR / P8 Decision 1).

`criteria` is the safe boolean-expression evaluator; `engine` resolves a
universe and runs a criterion against cached-bar indicators.
"""

from app.services.scanner.criteria import (
    ALLOWED_NAMES,
    CriteriaError,
    ParsedCriteria,
    evaluate,
    validate_criteria,
)
from app.services.scanner.engine import (
    ScanResult,
    SymbolMatch,
    SymbolSkip,
    resolve_universe,
    run_scan,
)

__all__ = [
    "ALLOWED_NAMES",
    "CriteriaError",
    "ParsedCriteria",
    "ScanResult",
    "SymbolMatch",
    "SymbolSkip",
    "evaluate",
    "resolve_universe",
    "run_scan",
    "validate_criteria",
]
