"""Is a strategy factor-consuming? One answer, used by every consumer of that answer.

Two components now need this question answered, and they must not answer it differently:

* ``StrategyEngine`` — at dispatch (may this book be ENTERED right now?) and at
  registration (may this book be ACTIVATED at all?).
* ``ActivationService`` — at the PENDING_LIVE → LIVE completion the scheduler drives, which
  never goes through the engine and so would otherwise carry its own reading.

That is the same shape as the divergence ADR 0051 closed between the refresh verifier and the
readiness watchdog: one question, two implementations, opposite verdicts from one input. It is
cheaper to refuse the second implementation now than to discover it from a filled order.

⚠ **DECLARATION FIRST, INFERENCE SECOND — and that ordering is the repair.** The engine used
to classify a strategy solely by AST-parsing its source. On 2026-08-10, the first live
factor-consuming dispatch after the readiness veto shipped, both production factor books
(strategies 7 and 8) logged ``strategy_factor_classification_unavailable``: neither
``inspect.getsource`` nor the ``sys.modules[...].__file__`` fallback could see the LOADED
INSTANCE's source. Inference returned "not factor-consuming", the gate returned ``True``
before evaluating anything, and 52 orders filled against factor data nothing had verified.

CI was green throughout. Its safety-net test classified template FILES on disk, which parse
perfectly; production dispatches an instance, which does not. The test asserted against an
object the production path never touches.

A class attribute cannot fail to introspect, so ``Strategy.requires_factor_readiness`` is the
authority here and AST inference is the fallback.
"""

from __future__ import annotations

import ast
import contextlib
import inspect
import sys
from pathlib import Path

import structlog

from .base import Strategy

logger = structlog.get_logger(__name__)


def infer_factor_consuming(cls: type[Strategy], strategy_id: int | None = None) -> bool | None:
    """Does this class read ``ctx.factors``? Inferred from source, via AST.

    AST rather than a substring: a docstring mentioning ``ctx.factors`` must not classify a
    strategy as using it. Range Trader does not touch factor data, and blocking it on factor
    staleness would stop a working strategy for no reason.

    Returns ``None`` — *unknown*, deliberately distinct from ``False`` — when the source
    cannot be read. That distinction is the whole point: the original implementation collapsed
    "I looked, and it does not use factors" into "I could not look", and its caller, unable to
    tell them apart, treated both as safe.
    """
    src: str | None = None
    with contextlib.suppress(Exception):
        src = inspect.getsource(cls)
    if src is None:  # dynamically loaded: fall back to the module file
        with contextlib.suppress(Exception):
            mod = sys.modules.get(cls.__module__)
            path = getattr(mod, "__file__", None)
            if path:
                src = Path(path).read_text(encoding="utf-8")
    if src is None:
        logger.warning(
            "strategy_factor_classification_unavailable",
            strategy_id=strategy_id,
            detail="source not introspectable; falling back to the class declaration",
        )
        return None
    try:
        tree = ast.parse(src)
    except SyntaxError:
        return None
    return any(
        isinstance(node, ast.Attribute) and node.attr == "factors" for node in ast.walk(tree)
    )


def requires_factor_readiness(cls: type[Strategy], strategy_id: int | None = None) -> bool:
    """Is this strategy governed by the factor-readiness interlock?

    Three cases, in this order:

    1. **Declared.** Honoured. If inference disagrees — declared ``False`` while the source
       reads ``ctx.factors`` — the strategy is GATED and the contradiction is logged. A
       declaration states intent; it is not a way to opt out of a gate whose subject matter
       the code demonstrably touches, and treating it as one would hand every future author a
       one-line bypass of an interlock that exists because bypasses were expensive.
    2. **Undeclared, inference succeeded.** Inference is used, exactly as before.
    3. **Undeclared AND uninspectable.** Not gated, and loudly logged.

    ⚠ Case 3 remains fail-OPEN, deliberately and on the owner's standing instruction: gating
    everything unclassifiable turns a linecache quirk into a full trading halt, which is a
    worse failure than the one this gate prevents. Making classification RELIABLE is the fix;
    flipping the default is not.

    What changed is that case 3 is no longer the case that ships. Every shipped template
    declares, so no factor book depends on inference at all — case 3 is now reachable only by
    a user strategy that both omits the declaration and cannot be read, and
    ``check_factor_templates_declare.py`` fails the build if a shipped template rejoins that
    population.
    """
    declared = getattr(cls, "requires_factor_readiness", None)

    # ⚠ INFER ONLY WHEN INFERENCE CAN CHANGE THE ANSWER. Until 2026-08-28 this computed
    # ``infer_factor_consuming`` unconditionally, before knowing whether it was needed. For a
    # correctly-declared factor book that is pure cost AND active harm: ``StrategyLoader``
    # never registers the module in ``sys.modules``, so ``inspect.getsource`` and its
    # ``__file__`` fallback both fail for every loaded instance, and inference logged
    # ``strategy_factor_classification_unavailable`` at WARNING on EVERY DISPATCH of a healthy,
    # correctly-declared strategy. That string is the documented signature of the disarmed veto
    # (ADR 0056, ``base.py``, the 2026-08-10 incident record) — the line an operator would grep
    # for to detect the defect this interlock exists to prevent. Emitting it constantly on
    # healthy books destroys it as a signal. A declared ``True`` is authoritative and complete;
    # nothing inference could return would change it, so it is not consulted.
    if declared is True:
        return True

    inferred = infer_factor_consuming(cls, strategy_id)

    if declared is None:
        if inferred is None:
            logger.warning(
                "strategy_factor_classification_undeclared_and_uninspectable",
                strategy_id=strategy_id,
                strategy_class=getattr(cls, "__name__", "?"),
                detail=(
                    "no requires_factor_readiness declaration and source not introspectable; "
                    "treating as non-factor-consuming. Declare requires_factor_readiness on "
                    "the strategy class to remove this gap."
                ),
            )
            return False
        return inferred

    if declared is False and inferred is True:
        logger.warning(
            "strategy_factor_declaration_contradicted",
            strategy_id=strategy_id,
            strategy_class=getattr(cls, "__name__", "?"),
            declared=False,
            inferred=True,
            detail=(
                "class declares requires_factor_readiness=False but its source reads "
                "ctx.factors - GATING anyway. A declaration is a statement of intent, not an "
                "opt-out from a gate whose subject the code touches."
            ),
        )
        return True
    return bool(declared)
