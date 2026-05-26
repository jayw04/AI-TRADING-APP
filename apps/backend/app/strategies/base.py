"""Strategy base class — the contract user strategies implement.

Subclass :class:`Strategy`, set the four class attributes, override
whichever of ``on_bar`` / ``on_signal`` / ``on_fill`` are needed. The
defaults are no-ops, so a strategy that only reacts to bars only overrides
``on_bar``.

Lifecycle::

    cls = MyStrategy
    instance = cls(ctx=StrategyContext(...), params={...})
    await instance.on_init()
    while engine is running:
        instance.on_bar(bar)          # at the configured cadence
        instance.on_signal(signal)    # when relevant signals arrive
        instance.on_fill(fill)        # when this strategy's orders fill
    await instance.on_shutdown()
"""

from __future__ import annotations

from typing import Any, ClassVar

from .context import Bar, FillEvent, SignalEvent, StrategyContext


class Strategy:
    """Base class for user-authored Python strategies."""

    # ---- class-level metadata (every subclass MUST set name + version) ----

    name: ClassVar[str] = "<unset>"
    version: ClassVar[str] = "0.1.0"

    # Default symbol universe; can be overridden per registration.
    symbols: ClassVar[list[str]] = []

    # Cadence: cron-ish string ("*/1 * * * *") for periodic on_bar dispatch,
    # OR the literal string "event" for purely event-driven strategies.
    schedule: ClassVar[str] = "*/1 * * * *"

    # Default parameter dict. Merged with the registered strategy's
    # params_json (registered values override defaults).
    default_params: ClassVar[dict[str, Any]] = {}

    # Optional UI form schema (P4 §7). When a subclass declares this, the
    # frontend Params tab renders a typed form (integer / number / string /
    # boolean / enum). When ``None`` the frontend falls back to a raw JSON
    # textarea. The schema lives in code, not the DB — the engine reads
    # ``type(running.instance).params_schema`` at response time, so a
    # hot-reload picks up schema edits for free.
    params_schema: ClassVar[dict[str, Any] | None] = None

    # ---- instance ----

    def __init__(self, ctx: StrategyContext, params: dict[str, Any]) -> None:
        self.ctx = ctx
        # `params` already contains defaults merged with registered overrides.
        self.params = params

    # ---- hooks (override in subclass; defaults are no-op) ----

    async def on_bar(self, bar: Bar) -> None:
        """Called for each (symbol, timeframe) bar tick at the configured cadence."""
        pass

    async def on_signal(self, signal: SignalEvent) -> None:
        """Called when a signal scoped to this strategy is emitted by another component."""
        pass

    async def on_fill(self, fill: FillEvent) -> None:
        """Called when one of this strategy's orders fills (or partially fills)."""
        pass

    # ---- optional lifecycle hooks ----

    async def on_init(self) -> None:
        """Called once after construction, before the first ``on_bar``.

        Useful for warming up indicators or fetching historical state."""
        pass

    async def on_shutdown(self) -> None:
        """Called once when the engine unregisters the strategy.

        Useful for emitting a final 'flat' signal or summarizing the session.
        Exceptions raised here are logged but otherwise swallowed."""
        pass
