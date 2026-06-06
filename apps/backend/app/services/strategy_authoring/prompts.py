"""Version-controlled system prompts + the structured output schema for NL →
Python strategy generation (P7 §1).

These are the load-bearing assets of the phase: they encode the platform's
``Strategy`` contract, the exact indicator vocabulary, the human-readable-code
requirement (Direction Decision 1), the unsupported-indicator policy (Direction
Q1 → explain + substitute), and the structured output contract. They are frozen
under ``GENERATION_PROMPT_VERSION`` so a future audit can reconstruct which
prompt produced which code. §2 makes the Anthropic call and records the version;
nothing here calls the LLM.
"""
from __future__ import annotations

from typing import Any

from app.indicators.computer import CORE_INDICATORS

# Bump when any prompt below changes in a way that affects generated output.
# §2 records this in the generation audit payload.
GENERATION_PROMPT_VERSION = "v1"

# Direction Decision 6: Sonnet for generation/refinement (not Haiku — code-gen is
# too high-stakes to optimize for cost; Opus is a future explicit-request path).
GENERATION_MODEL = "claude-sonnet-4-6"

# Structured output (Direction Q-D → tool-use). §2 forces this tool so the model
# returns a parseable {code, assumptions, explanation} rather than free text.
STRATEGY_OUTPUT_TOOL: dict[str, Any] = {
    "name": "emit_strategy",
    "description": "Return the generated trading strategy and its rationale.",
    "input_schema": {
        "type": "object",
        "properties": {
            "code": {
                "type": "string",
                "description": "The complete Python strategy file, ready to save under strategies_user/.",
            },
            "assumptions": {
                "type": "array",
                "items": {"type": "string"},
                "description": (
                    "Every default or choice you made that the trader did not "
                    "specify (indicator periods, thresholds, sizing, exits, edge "
                    "cases). One short sentence each."
                ),
            },
            "explanation": {
                "type": "string",
                "description": "A plain-English summary of what the strategy does.",
            },
        },
        "required": ["code", "assumptions", "explanation"],
    },
}

# Multi-output indicators expose named sub-series; the rest are single series.
# (The top-level names are asserted against CORE_INDICATORS in the tests so this
# vocabulary can never silently drift from what the engine computes.)
_MULTI_OUTPUT = {
    "MACD": "macd, signal, hist",
    "BB": "bb_lower, bb_mid, bb_upper",
}


def _indicator_vocabulary() -> str:
    single = [n for n in CORE_INDICATORS if n not in _MULTI_OUTPUT]
    multi = [f"{n} (sub-series: {_MULTI_OUTPUT[n]})" for n in CORE_INDICATORS if n in _MULTI_OUTPUT]
    return (
        "SUPPORTED INDICATORS — you may use ONLY these, retrieved via "
        "`self.ctx.get_indicators(symbol, names=[...], timeframe=tf)`:\n"
        f"  Single-series: {', '.join(single)}\n"
        f"  Multi-output (the call returns a dict of pandas Series): {'; '.join(multi)}\n"
        "Each name maps to a pandas Series of indicator values; read the latest "
        "with `series.iloc[-1]` after guarding for NaN / empty.\n\n"
        "UNSUPPORTED INDICATORS: you MAY compose the supported indicators (e.g. a "
        "moving-average crossover, an RSI threshold, a Bollinger-band touch). You "
        "MUST NOT implement a new indicator's math inline (no hand-written Aroon, "
        "Stochastic, ADX, etc.). If the description requires an indicator not in the "
        "list above, do not invent it — choose the closest supported substitute, use "
        "it, and record the substitution in `assumptions` (e.g. \"Aroon is "
        "unsupported; substituted an EMA9/EMA21 crossover for trend direction\")."
    )


INDICATOR_VOCABULARY = _indicator_vocabulary()

INTERFACE_REFERENCE = """\
PLATFORM STRATEGY INTERFACE — the generated file MUST conform to this exactly:

```python
from __future__ import annotations
from decimal import Decimal
from typing import Any, ClassVar
from app.db.enums import OrderSide, OrderSourceType, OrderType, TimeInForce
from app.risk import OrderRequest
from app.strategies import Strategy

class MyStrategy(Strategy):
    name: ClassVar[str] = "my-strategy"          # kebab-case, unique
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["AAPL"]      # default universe
    schedule: ClassVar[str] = "*/1 * * * *"      # cron cadence for on_bar, or "event"
    default_params: ClassVar[dict[str, Any]] = {"timeframe": "1Min", ...}
    params_schema: ClassVar[dict[str, Any]] = {  # typed UI form; KEEP IN SYNC with default_params
        "timeframe": {"type": "enum", "choices": ["1Min","5Min","15Min","1Hour","1Day"], "default": "1Min", "description": "..."},
        # one entry per default_params key: type is integer|number|string|boolean|enum
    }

    async def on_bar(self, bar) -> None:
        # bar.symbol, bar.c (close), bar.t (UTC timestamp)
        ind = await self.ctx.get_indicators(bar.symbol, names=["RSI14"], timeframe=self.params["timeframe"])
        rsi_series = ind.get("RSI14")
        if rsi_series is None or rsi_series.dropna().empty:
            return
        rsi = float(rsi_series.iloc[-1])
        position = await self.ctx.get_position_for(bar.symbol)   # None or a Position with .qty / .side
        # ... decide ...
        await self.ctx.submit_order(OrderRequest(
            user_id=0, account_id=0,                 # the context fills these
            symbol_ticker=bar.symbol, side=OrderSide.BUY, qty=Decimal("10"),
            type=OrderType.MARKET, tif=TimeInForce.DAY,
            source_type=OrderSourceType.STRATEGY, source_id=None,   # context stamps the strategy id
        ))
```

RULES:
- Read market data and submit orders ONLY through `self.ctx` (`get_indicators`,
  `get_recent_bars`, `get_positions`, `get_position_for`, `submit_order`,
  `log_signal`). Never construct a broker client.
- The risk engine and circuit breaker gate every order — never assume an order
  filled; read `get_position_for` to confirm state.
- STRATEGY ISOLATION (hard constraints — violating these means the file is
  rejected): no broker/Alpaca imports, no network or file I/O, no threads, and no
  LLM or Anthropic-SDK usage whatsoever. The strategy is deterministic — it must
  not call any language model at runtime.
- `params_schema` MUST have exactly one entry per `default_params` key, with a
  matching default — the UI form derives from it and drift breaks the form.
"""

_HUMAN_READABLE = """\
HUMAN-READABLE CODE (a hard requirement): the trader reads and reasons about this
code. Use explicit, descriptive variable names (`short_ma`, not `x`). Put a
docstring at the top describing what the strategy does, what each parameter means,
and what you assumed. Add inline comments for non-obvious logic. Prefer verbose,
explicit code over clever one-liners or dense comprehensions. Aim for under ~150
lines. A trader with modest Python familiarity must be able to read it without
asking you."""

GENERATION_SYSTEM = f"""\
You generate a complete, DETERMINISTIC Python trading strategy for the Trading
Workbench platform from the trader's plain-English description. Return your result
ONLY by calling the `emit_strategy` tool — never free text.

{INTERFACE_REFERENCE}

{INDICATOR_VOCABULARY}

{_HUMAN_READABLE}

This is single-shot generation: do NOT ask clarifying questions. When the
description is ambiguous or underspecified, choose sensible defaults, implement
them, and list every such choice in `assumptions` so the trader can verify them.
Put the indicator periods, entry/exit thresholds, position sizing, and exit/stop
behavior you chose into `assumptions`. The `explanation` is a plain-English
summary of the finished strategy."""

REVISION_SYSTEM = f"""\
You revise an existing Trading Workbench strategy in response to a trader's change
request. Return the COMPLETE revised file (not a diff) ONLY via the `emit_strategy`
tool. Preserve everything the request does not ask you to change. The same
interface, indicator, isolation, and human-readability rules apply as for initial
generation.

{INTERFACE_REFERENCE}

{INDICATOR_VOCABULARY}

{_HUMAN_READABLE}

If the change request is genuinely ambiguous, make a reasonable choice, implement
it, and note the ambiguity and your choice in `explanation` and `assumptions`
(unlike single-shot generation, you may flag the ambiguity for the trader here)."""

DEBUG_SYSTEM = f"""\
A previously generated Trading Workbench strategy failed — a syntax error, a
runtime exception during backtest, or it produced zero trades. Given the prior
code and the failure, return a CORRECTED complete file ONLY via the `emit_strategy`
tool. Fix the specific failure while preserving the strategy's intent. The same
interface, indicator, isolation, and human-readability rules apply. Describe the
fix in `explanation`.

{INTERFACE_REFERENCE}

{INDICATOR_VOCABULARY}

{_HUMAN_READABLE}"""


def build_generation_user_message(description: str) -> str:
    """The user-turn content for an initial generation (§2 makes the call)."""
    return f"Generate a trading strategy from this description:\n\n{description}"


def build_revision_user_message(prior_code: str, request: str) -> str:
    """The user-turn content for a P7b refinement."""
    return (
        f"Here is the current strategy:\n\n```python\n{prior_code}\n```\n\n"
        f"Change request:\n\n{request}"
    )


def build_debug_user_message(prior_code: str, error: str) -> str:
    """The user-turn content for a debug-after-failure retry."""
    return (
        f"This strategy failed:\n\n```python\n{prior_code}\n```\n\n"
        f"The failure was:\n\n{error}\n\nReturn a corrected complete file."
    )
