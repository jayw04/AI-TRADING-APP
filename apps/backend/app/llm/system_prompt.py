"""Build the agent's system prompt per session.

Three parts:

1. **Static framing** — who the agent is, what the user is doing, what
   capabilities are explicitly absent. Anchors the agent to the
   workbench's read-only-from-the-agent's-side surface (see
   :file:`docs/adr/0006-llm-not-in-order-path.md`).
2. **Dynamic context** — current account mode, equity, open position
   count, registered strategy counts. Inlining these prevents the agent
   from wasting tokens on a redundant ``get_account_state`` call as the
   first thing in every conversation.
3. **Mode-specific suffix** — B1 (read-only, no suggestions) vs B2
   (interactive, structured ``Suggestion:`` blocks). B3 raises — the
   runtime rejects B3 sessions at start, but this is the defense in depth.

B3_AUTONOMOUS is permanently paused per ADR 0006 — the rejection here is
not "deferred" or "P3-only," it stands until a successor ADR replaces 0006.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES,
    AgentSessionMode,
)
from app.db.models.account import Account
from app.db.models.account_state import AccountState
from app.db.models.position import Position
from app.db.models.strategy import Strategy as StrategyRow

_BASE_PROMPT = """\
You are an assistant integrated into a personal trading workbench. The user
runs this workbench locally to paper-trade US equities through Alpaca and
to develop systematic Python trading strategies.

Capabilities you have:
  - Read account state, positions, orders, fills via tools.
  - Read registered strategies, their runs, signals they've emitted, past
    backtest results.
  - Pull quotes, bars, and computed technical indicators for any symbol
    the user trades.

Capabilities you DO NOT have:
  - Execute trades (submit, cancel, modify orders).
  - Start, stop, or modify strategies.
  - Change risk limits.
  - Write to any persistent state.

If the user asks you to do something you can't (e.g. "buy 100 AAPL", "start
the RSI strategy"), respond clearly that you can only suggest — they must
execute via the UI.

Be concise. The user is technical; skip basic finance explanations unless
asked. When citing a number, prefer the most recent data — call a tool if
you're not sure.
"""

_B2_SUFFIX = """\

When you suggest an action, format the suggestion in this exact shape so the
UI can render it as an action card:

  Suggestion: <plain English of the suggested action>
  Why: <brief rationale, 1-2 sentences>
  Confidence: low | medium | high

Always include all three lines. Use this format only for actions the user
should take in the UI — not for informational answers.
"""

_B1_SUFFIX = """\

Do not suggest actions or recommend changes to positions, strategies, or
parameters. Answer questions about state factually and concisely. If the
user requests a suggestion, politely tell them this session is read-only
and recommend they start an Interactive (B2) session for that.
"""


@dataclass
class UserContextSummary:
    """Compact snapshot of workbench state at session start."""

    mode: str  # 'paper' | 'live' | 'unknown'
    strategies_active: int
    strategies_total: int
    positions_open: int
    equity: str  # formatted string with leading '$' or 'unknown'


async def gather_user_context(
    session: AsyncSession, user_id: int
) -> UserContextSummary:
    """Pull a compact summary of the user's current workbench state.

    Sub-fetches that fail leave the corresponding field as ``"unknown"``
    (or ``0`` for counts). The agent can still call tools to fill gaps;
    a transient DB hiccup shouldn't block session creation.
    """
    mode = "unknown"
    equity_str = "unknown"
    account = (
        await session.execute(
            select(Account).where(Account.user_id == user_id).limit(1)
        )
    ).scalars().first()
    if account is not None:
        mode = account.mode.value if hasattr(account.mode, "value") else str(account.mode)
        state = (
            await session.execute(
                select(AccountState).where(AccountState.account_id == account.id)
            )
        ).scalars().first()
        if state is not None and state.equity is not None:
            equity_str = f"${state.equity}"

    strategies_total = (
        await session.execute(
            select(func.count(StrategyRow.id)).where(StrategyRow.user_id == user_id)
        )
    ).scalar() or 0
    strategies_active = (
        await session.execute(
            select(func.count(StrategyRow.id)).where(
                StrategyRow.user_id == user_id,
                StrategyRow.status.in_(list(ACTIVE_STRATEGY_STATUSES)),
            )
        )
    ).scalar() or 0

    positions_open = 0
    if account is not None:
        positions_open = (
            await session.execute(
                select(func.count(Position.id)).where(
                    Position.account_id == account.id
                )
            )
        ).scalar() or 0

    return UserContextSummary(
        mode=mode,
        strategies_active=int(strategies_active),
        strategies_total=int(strategies_total),
        positions_open=int(positions_open),
        equity=equity_str,
    )


def build_system_prompt(
    mode: AgentSessionMode, ctx: UserContextSummary
) -> str:
    """Assemble the per-session system prompt.

    Raises :class:`ValueError` on :attr:`AgentSessionMode.B3_AUTONOMOUS`
    — B3 is paused indefinitely per ADR 0006 and reaching this branch is
    a defensive defense-in-depth check (the runtime refuses B3 sessions
    at start).
    """
    context_block = (
        "Current workbench state at session start:\n"
        f"  - Trading mode: {ctx.mode}\n"
        f"  - Account equity: {ctx.equity}\n"
        f"  - Open positions: {ctx.positions_open}\n"
        f"  - Registered strategies: {ctx.strategies_total} "
        f"(of which {ctx.strategies_active} actively running)\n"
    )
    base = _BASE_PROMPT.rstrip() + "\n\n" + context_block

    if mode == AgentSessionMode.B1_READONLY:
        return base + _B1_SUFFIX
    if mode == AgentSessionMode.B2_INTERACTIVE:
        return base + _B2_SUFFIX
    raise ValueError(
        f"AgentSessionMode {mode.value} not supported. B3_AUTONOMOUS is "
        "paused indefinitely per ADR 0006 (docs/adr/0006-llm-not-in-order-path.md)."
    )
