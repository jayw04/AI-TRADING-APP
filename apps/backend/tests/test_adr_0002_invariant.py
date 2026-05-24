"""Static check for ADR 0002 — single order entry point.

Greps the backend source tree for any call to AlpacaAdapter.submit_order,
.cancel_order, or .replace_order outside of app/orders/. The router is the
only legitimate caller; the adapter's own module contains the method
*definitions* but does not call them.

If this test fails, a future PR has tried to bypass the router. The fix is
NOT to add the offending file to ALLOWED — it's to route the new code path
through OrderRouter.
"""

from __future__ import annotations

import pathlib
import re

# `.submit_order(`, `.cancel_order(`, `.replace_order(` on any reference.
CALL_PATTERN = re.compile(r"\.(submit_order|cancel_order|replace_order)\s*\(")

# Files allowed to contain these patterns.
ALLOWED = {
    "app/orders/router.py",
    "app/brokers/alpaca/adapter.py",  # method definitions
    "tests/test_adr_0002_invariant.py",  # this file
    # Tripwire tests deliberately call the mutation methods to assert they
    # refuse without the router token; the test file is fenced off here.
    "tests/brokers/alpaca/test_adapter.py",
    # StrategyContext tests call ctx.submit_order(...) — the regex matches
    # the literal `.submit_order(` even though this is the *context's*
    # pass-through to the injected order-router callable, not a direct
    # adapter call. ADR 0002 is not violated; the context dispatches
    # through OrderRouter.submit just like every other path.
    "tests/strategies/test_context.py",
    # Same case as test_context.py: these all call `ctx.submit_order(...)`
    # on a StrategyContext or BacktestContext, which dispatches through
    # OrderRouter (or, for backtests, an in-memory simulator that never
    # reaches the adapter). No direct adapter access here.
    "strategies_user/examples/rsi_meanreversion.py",
    "tests/strategies/test_backtester.py",
    "tests/strategies/test_strategy_risk_integration.py",
}

# apps/backend/
BACKEND_ROOT = pathlib.Path(__file__).resolve().parent.parent


def _iter_source_files():
    for p in BACKEND_ROOT.rglob("*.py"):
        rel = p.relative_to(BACKEND_ROOT).as_posix()
        if rel.startswith((".venv/", "alembic/versions/")):
            continue
        yield rel, p


def test_no_direct_adapter_mutation_calls_outside_router() -> None:
    offenders: list[str] = []
    for rel, path in _iter_source_files():
        if rel in ALLOWED:
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for m in CALL_PATTERN.finditer(text):
            # Ignore method *definitions* (`def submit_order(`).
            start = max(0, m.start() - 4)
            window = text[start : m.start() + 1]
            if "def " in window:
                continue
            offenders.append(f"{rel}: {m.group(0)}")
    assert not offenders, (
        "ADR 0002 violation — these files call AlpacaAdapter mutation methods "
        "outside the OrderRouter:\n  " + "\n  ".join(offenders)
    )
