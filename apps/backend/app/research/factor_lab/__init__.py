"""Factor Lab — config-driven research programs (plan v0.2, extends ADR 0019).

The Factor Lab turns a research program from a bespoke ~400-line script into a
declarative ``ProgramSpec`` (a factor + construction + verdict tree) run through one
reproducible harness (see ``docs/implementation/TradingWorkbench_FactorLab_Plan_v0.1.md``):
a ``ProgramSpec`` (factor + construction + verdict tree), a factor registry, and the
unified ``run_program`` runner.

Pure data + functions; no order path, no broker, no DB session, no LLM.
"""

from app.research.factor_lab.registry import FACTOR_BUILDERS, build_score_fn
from app.research.factor_lab.runner import run_program
from app.research.factor_lab.spec import ProgramSpec, VerdictRule, VerdictSpec
from app.research.factor_lab.verdict import classify

__all__ = [
    "FACTOR_BUILDERS",
    "ProgramSpec",
    "VerdictRule",
    "VerdictSpec",
    "build_score_fn",
    "classify",
    "run_program",
]
