"""Trading-domain enums.

Every enum is a `StrEnum` so it serializes naturally to strings in JSON and
maps cleanly to a VARCHAR column in SQLite (we use `native_enum=False` in the
model declarations).
"""

from __future__ import annotations

from enum import StrEnum


class OrderSide(StrEnum):
    BUY = "buy"
    SELL = "sell"


class OrderType(StrEnum):
    MARKET = "market"
    LIMIT = "limit"
    STOP = "stop"
    STOP_LIMIT = "stop_limit"


class TimeInForce(StrEnum):
    DAY = "day"
    GTC = "gtc"  # good til canceled
    IOC = "ioc"  # immediate or cancel
    FOK = "fok"  # fill or kill


class OrderStatus(StrEnum):
    """Internal order lifecycle.

    Happy path:
        PENDING_RISK -> PENDING_SUBMIT -> SUBMITTED
            -> PARTIALLY_FILLED -> FILLED       (terminal)

    Other terminal states: CANCELED, EXPIRED, REJECTED, REPLACED.

    Alpaca's own order statuses (new, pending_new, accepted, ...) are mapped
    to these by the trade-update consumer in Session 5.
    """

    PENDING_RISK = "pending_risk"
    PENDING_SUBMIT = "pending_submit"
    SUBMITTED = "submitted"
    PARTIALLY_FILLED = "partially_filled"
    FILLED = "filled"
    CANCELED = "canceled"
    EXPIRED = "expired"
    REJECTED = "rejected"
    REPLACED = "replaced"


# Terminal states — orders in these states never transition again.
TERMINAL_ORDER_STATUSES = frozenset(
    {
        OrderStatus.FILLED,
        OrderStatus.CANCELED,
        OrderStatus.EXPIRED,
        OrderStatus.REJECTED,
        OrderStatus.REPLACED,
    }
)


class OrderSourceType(StrEnum):
    """Who initiated the order. Audited on every order row."""

    MANUAL = "manual"
    STRATEGY = "strategy"
    AGENT_STRATEGY = "agent_strategy"  # B3 in Implementation Plan §13.3
    AGENT_PROPOSAL = "agent_proposal"  # B2 approved-by-human
    PINE = "pine"  # webhook from TradingView


class RiskDecision(StrEnum):
    PASS = "pass"
    REJECT = "reject"


class RiskScopeType(StrEnum):
    """Scope at which a RiskLimits row applies.

    For P1 only GLOBAL is used. STRATEGY and AGENT_SESSION become relevant in
    P2 and P3 respectively; their referenced tables don't exist yet, so the
    risk_limits.scope_id column is a bare INTEGER for now (no FK).
    """

    GLOBAL = "global"
    ACCOUNT = "account"
    STRATEGY = "strategy"
    AGENT_SESSION = "agent_session"


# ---- Strategies (P2 Session 2) ----


class StrategyType(StrEnum):
    """How a strategy is implemented.

    Only ``PYTHON`` is dispatched in P2. ``PINE`` (TradingView webhook
    receiver) lands in P4; ``AGENT`` (Claude Code agent loop) lands in P6.
    The enum values are reserved here so we don't migrate the column twice.
    """

    PYTHON = "python"
    PINE = "pine"
    AGENT = "agent"


class StrategyStatus(StrEnum):
    """Lifecycle state of a registered strategy.

    Typical transitions::

        IDLE -> BACKTEST -> IDLE
        IDLE -> PAPER    -> IDLE | HALTED | ERROR
        IDLE -> LIVE     -> IDLE | HALTED | ERROR     (P5)
    """

    IDLE = "idle"
    BACKTEST = "backtest"
    PAPER = "paper"
    # P5 §7: the 24-hour holding state between activation-wizard completion and
    # live order flow (ADR 0005). Cannot submit orders; the scheduler flips it
    # to LIVE after the cooldown elapses, or the user cancels back to IDLE.
    PENDING_LIVE = "pending_live"
    LIVE = "live"
    HALTED = "halted"
    ERROR = "error"
    # P6b §2a: a cloned proposal-validation variant. Runs forward on paper in
    # parallel with its LIVE parent (ADR 0007). Engine-runnable but deliberately
    # NOT user-facing-active (excluded from ACTIVE_STRATEGY_STATUSES so
    # _is_active / proposal-cadence / morning-brief skip it).
    PAPER_VARIANT = "paper_variant"


# Statuses in which the engine actively dispatches to a strategy.
# PENDING_LIVE is deliberately excluded — it cannot submit orders.
ACTIVE_STRATEGY_STATUSES = frozenset(
    {StrategyStatus.PAPER, StrategyStatus.LIVE}
)

# P6b §2a: statuses the engine RUNS + resumes-on-boot. Superset of
# ACTIVE_STRATEGY_STATUSES with PAPER_VARIANT — so variants run/resume but stay
# out of every user-facing "active" surface.
ENGINE_RUNNABLE_STATUSES = ACTIVE_STRATEGY_STATUSES | frozenset(
    {StrategyStatus.PAPER_VARIANT}
)


class SignalType(StrEnum):
    """Type of a ``signals`` row.

    ``ENTRY``/``EXIT``/``FLAT`` are produced by Python strategies.
    ``AGENT_ACTION`` is reserved for B3 (P6). ``PINE_ALERT`` is reserved for
    the TradingView webhook (P4). ``INFO`` is a free-form annotation
    (e.g. "considered entry but RSI=29.99").
    """

    ENTRY = "entry"
    EXIT = "exit"
    FLAT = "flat"
    INFO = "info"
    AGENT_ACTION = "agent_action"
    PINE_ALERT = "pine_alert"


class BacktestJobStatus(StrEnum):
    """Lifecycle of a backtest job.

    Transitions::

        QUEUED  -> RUNNING   (worker picks up)
        RUNNING -> COMPLETED (full result persisted)
        RUNNING -> FAILED    (uncaught exception OR orphaned on worker restart)
        RUNNING -> CANCELLED (user cancellation honored mid-bar)
        QUEUED  -> CANCELLED (cancelled before worker started)
    """

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# Jobs in these states are in-flight or waiting; single-flight checks use this.
PENDING_BACKTEST_JOB_STATUSES = frozenset(
    {BacktestJobStatus.QUEUED, BacktestJobStatus.RUNNING}
)


# ---- Agent (P3) ----


class AgentSessionMode(StrEnum):
    """How a session interacts with the workbench.

    B1_READONLY: agent answers questions about state but never produces
        recommendations.
    B2_INTERACTIVE: agent answers AND suggests actions via a structured
        ``Suggestion:`` block. User always executes manually.
    B3_AUTONOMOUS: reserved for P6. Runtime rejects this value in P3 —
        same forward-compat pattern as ``StrategyType.PINE``/``AGENT``.
    """

    B1_READONLY = "b1_readonly"
    B2_INTERACTIVE = "b2_interactive"
    B3_AUTONOMOUS = "b3_autonomous"


class AgentSessionStatus(StrEnum):
    """Lifecycle state of a session.

    Transitions::

        ACTIVE -> ENDED    (user clicks End, or a new session supersedes)
        ACTIVE -> CAPPED   (cost cap reached mid-conversation; read-only forever)
        ACTIVE -> ERROR    (API error / unrecoverable failure; read-only forever)
    """

    ACTIVE = "active"
    ENDED = "ended"
    CAPPED = "capped"
    ERROR = "error"


class AgentMessageRole(StrEnum):
    """Role of a message in an agent session.

    USER         — text from the trader.
    ASSISTANT    — text from the model.
    TOOL_USE     — model invoked a tool; content carries (tool_name, input).
    TOOL_RESULT  — result of a tool invocation; content carries output.
    SYSTEM       — workbench-emitted note ("cost cap reached", "session
                   ended"), NOT the same as the system prompt.
    """

    USER = "user"
    ASSISTANT = "assistant"
    TOOL_USE = "tool_use"
    TOOL_RESULT = "tool_result"
    SYSTEM = "system"


# Sessions in these states are still mutable.
ACTIVE_AGENT_STATUSES = frozenset({AgentSessionStatus.ACTIVE})
