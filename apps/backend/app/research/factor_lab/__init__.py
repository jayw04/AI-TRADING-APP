"""Factor Lab — config-driven research programs (plan v0.2, extends ADR 0019).

The Factor Lab turns a research program from a bespoke ~400-line script into a
declarative ``ProgramSpec`` (a factor + construction + verdict tree) run through one
reproducible harness. This package holds the *foundation* — the spec types and the
pure, data-driven verdict evaluator; the factor registry and the unified runner land
in later sessions (see ``docs/implementation/TradingWorkbench_FactorLab_Plan_v0.1.md``).

Pure data + functions; no order path, no broker, no DB session, no LLM.
"""

from app.research.factor_lab.spec import ProgramSpec, VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

__all__ = ["ProgramSpec", "VerdictRule", "VerdictSpec", "classify"]
