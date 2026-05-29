"""AgentRuntime — orchestrates session lifecycle and the tool-use loop.

One instance per backend process, owned by the FastAPI lifespan. The
runtime is stateless across sessions; each :meth:`append_user_message`
opens its own DB session and reads the full conversation history.

This module — alongside the rest of ``app/agent/`` — is the only place
in the backend permitted to import the Anthropic SDK. The CI invariant
``check_no_llm_in_order_path.sh`` enforces this; see
``docs/adr/0006-llm-not-in-order-path.md`` for the architectural
reasoning. B3 (autonomous order submission) is paused indefinitely per
that ADR; :meth:`start_session` refuses B3 with a clear message.

Tool dispatch happens **server-side at Anthropic** via the MCP connector
pointed at our workbench MCP server. The "loop" here orchestrates
multi-turn exchanges (when the model returns ``tool_use`` blocks without
a follow-on text answer and needs another call to summarize) — not
individual tool calls.

Cost cap is bilateral:

* Pre-call: estimate the next call's cost (~4k input + 1k output, a
  deliberate overestimate) and refuse via :class:`DailyBudgetResolver`
  if it would push the user over their daily budget.
* Post-call: charge real usage from the response. If the user's total
  is now over the cap, transition the session to ``CAPPED`` and append
  a SYSTEM message.
"""

from __future__ import annotations

import asyncio
import time
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from app.agent.anthropic_client import (
    AnthropicCall,
    AnthropicClientNotConfigured,
    create_message,
)
from app.agent.pricing import DailyBudgetResolver, estimate_cost
from app.agent.system_prompt import build_system_prompt, gather_user_context
from app.config import Settings
from app.db.enums import (
    ACTIVE_AGENT_STATUSES,
    AgentMessageRole,
    AgentSessionMode,
    AgentSessionStatus,
)
from app.db.models.agent_message import AgentMessage
from app.db.models.agent_session import AgentSession
from app.db.models.agent_tool_invocation import AgentToolInvocation
from app.events.bus import EventBus

logger = structlog.get_logger(__name__)


# Pre-call estimate — deliberately high so the cap fires conservatively
# before the call rather than after. Underestimating is dangerous; an
# overestimate just means we refuse a borderline call slightly early.
PRE_CALL_INPUT_ESTIMATE_TOKENS = 4000
PRE_CALL_OUTPUT_ESTIMATE_TOKENS = 1000

# Hard cap on tool-use loop iterations. A pathological model could in
# theory loop tool_use -> tool_use forever; this bounds runaway sessions.
MAX_LOOP_ITERATIONS = 5


class AgentRuntimeError(Exception):
    """Base error for runtime-side rejections (B3 mode, missing session, etc.)."""


class AgentRuntime:
    """Session lifecycle owner + tool-use loop driver."""

    def __init__(
        self,
        settings: Settings,
        session_factory: async_sessionmaker[AsyncSession],
        bus: EventBus,
        mcp_server_url: str | None = "http://127.0.0.1:8765",
    ) -> None:
        self._settings = settings
        self._session_factory = session_factory
        self._bus = bus
        self._mcp_server_url = mcp_server_url
        # Per-session locks: two concurrent appends on the same session
        # serialize; two appends on DIFFERENT sessions parallelize. This
        # is the right shape for the chat-panel UX (one human, one
        # session at a time) but matters if anything programmatic ever
        # drives the runtime.
        self._session_locks: dict[int, asyncio.Lock] = {}

    # ---------------- session lifecycle ----------------

    async def start_session(
        self,
        *,
        user_id: int,
        mode: AgentSessionMode,
        model: str | None = None,
    ) -> int:
        """Open a new session, superseding any prior ACTIVE session.

        Raises:
          AgentRuntimeError: if ``mode`` is B3_AUTONOMOUS (paused per
            ADR 0006).
          AnthropicClientNotConfigured: if ``ANTHROPIC_API_KEY`` is empty.
        """
        if mode == AgentSessionMode.B3_AUTONOMOUS:
            raise AgentRuntimeError(
                "AgentSessionMode B3_AUTONOMOUS is paused indefinitely "
                "per ADR 0006 (docs/adr/0006-llm-not-in-order-path.md). "
                "Use B1_READONLY or B2_INTERACTIVE."
            )
        if not self._settings.anthropic_api_key:
            raise AnthropicClientNotConfigured(
                "ANTHROPIC_API_KEY is not configured. "
                "Set it in .env to enable the agent."
            )

        used_model = model or self._settings.agent_default_model
        budget = Decimal(str(self._settings.agent_daily_budget_usd))

        async with self._session_factory() as db:
            active = (
                await db.execute(
                    select(AgentSession).where(
                        AgentSession.user_id == user_id,
                        AgentSession.status.in_(list(ACTIVE_AGENT_STATUSES)),
                    )
                )
            ).scalars().all()
            now = datetime.now(UTC)
            for a in active:
                a.status = AgentSessionStatus.ENDED
                a.ended_at = now
                a.end_reason = "superseded"

            new_session = AgentSession(
                user_id=user_id,
                mode=mode,
                status=AgentSessionStatus.ACTIVE,
                model=used_model,
                total_input_tokens=0,
                total_output_tokens=0,
                total_cost_usd=Decimal("0"),
                daily_budget_usd=budget,
                started_at=now,
            )
            db.add(new_session)
            await db.commit()
            await db.refresh(new_session)
            session_id = new_session.id

        await self._publish(
            "agent.session_started",
            {
                "session_id": session_id,
                "user_id": user_id,
                "mode": mode.value,
                "model": used_model,
            },
        )
        return session_id

    async def end_session(
        self, *, session_id: int, reason: str = "user_end"
    ) -> None:
        """Mark an ACTIVE session ENDED. Idempotent on already-terminal sessions."""
        async with self._session_factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None or row.status not in ACTIVE_AGENT_STATUSES:
                return
            row.status = AgentSessionStatus.ENDED
            row.ended_at = datetime.now(UTC)
            row.end_reason = reason
            await db.commit()
        await self._publish(
            "agent.session_ended",
            {"session_id": session_id, "reason": reason},
        )

    # ---------------- user-message turn ----------------

    async def append_user_message(
        self,
        *,
        session_id: int,
        text: str,
    ) -> int:
        """Append a user message and run the agent turn to completion.

        Returns ``session_id``. Streaming events to the WS gateway is the
        REST/WS layer's job (Session 4); this method publishes bus events
        the gateway translates.
        """
        lock = self._session_locks.setdefault(session_id, asyncio.Lock())
        async with lock:
            await self._do_turn(session_id, text)
        return session_id

    async def _do_turn(self, session_id: int, user_text: str) -> None:
        # Load + verify session, persist the user message.
        async with self._session_factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None:
                raise AgentRuntimeError(f"Session {session_id} not found")
            if row.status not in ACTIVE_AGENT_STATUSES:
                raise AgentRuntimeError(
                    f"Session {session_id} is {row.status.value}"
                )
            user_id = row.user_id
            model = row.model
            mode = row.mode
            budget = row.daily_budget_usd

            user_msg = AgentMessage(
                session_id=session_id,
                role=AgentMessageRole.USER,
                content_json=[{"type": "text", "text": user_text}],
                ts=datetime.now(UTC),
            )
            db.add(user_msg)
            await db.commit()
            await db.refresh(user_msg)
            user_msg_id = user_msg.id

        await self._publish(
            "agent.message_appended",
            {
                "session_id": session_id,
                "message_id": user_msg_id,
                "role": "user",
                "text_preview": user_text[:120],
            },
        )

        # Pre-call gate: estimate, refuse if it would blow the budget.
        resolver = DailyBudgetResolver(daily_budget_usd=budget)
        estimated = estimate_cost(
            model,
            PRE_CALL_INPUT_ESTIMATE_TOKENS,
            PRE_CALL_OUTPUT_ESTIMATE_TOKENS,
        )
        async with self._session_factory() as db:
            if await resolver.would_exceed(
                db, user_id=user_id, estimated_cost=estimated
            ):
                await self._handle_cap_hit(
                    session_id, "pre_call_estimate_over_budget"
                )
                return

        async with self._session_factory() as db:
            ctx_summary = await gather_user_context(db, user_id)
        system_prompt = build_system_prompt(mode, ctx_summary)

        for _iteration in range(MAX_LOOP_ITERATIONS):
            messages_payload = await self._build_messages_payload(session_id)
            start = time.monotonic()
            try:
                call = await create_message(
                    api_key=self._settings.anthropic_api_key,
                    model=model,
                    system=system_prompt,
                    messages=messages_payload,
                    mcp_server_url=self._mcp_server_url,
                )
            except Exception as exc:
                logger.exception(
                    "anthropic_call_failed", session_id=session_id
                )
                await self._handle_session_error(session_id, str(exc))
                return
            latency_ms = int((time.monotonic() - start) * 1000)

            await self._persist_assistant_message(
                session_id, call, user_msg_id, latency_ms
            )
            cap_hit = await self._charge_and_check_cap(session_id, call)
            if cap_hit:
                return

            # If the response includes a text answer, we're done. If it's
            # only tool_use with no text, loop and ask the model to follow
            # up. Empty responses also stop (defensive).
            has_text = any(
                b.get("type") == "text" and b.get("text")
                for b in call.content_blocks
            )
            if has_text:
                return
            has_tool_use = any(
                b.get("type") == "tool_use" for b in call.content_blocks
            )
            if not has_tool_use:
                return

        logger.warning(
            "agent_tool_loop_max_iterations",
            session_id=session_id,
            max_iterations=MAX_LOOP_ITERATIONS,
        )

    async def _build_messages_payload(
        self, session_id: int
    ) -> list[dict[str, Any]]:
        """Shape DB messages into Anthropic's wire format.

        SYSTEM-role rows are workbench-emitted notes (e.g. "cost cap
        reached") — not part of the conversation the model should see.
        TOOL_USE messages merge into the preceding assistant turn; the
        Anthropic MCP connector handles ``tool_result`` server-side, so
        we don't replay those.
        """
        async with self._session_factory() as db:
            rows = (
                await db.execute(
                    select(AgentMessage)
                    .where(AgentMessage.session_id == session_id)
                    .order_by(AgentMessage.ts.asc())
                )
            ).scalars().all()

        out: list[dict[str, Any]] = []
        for row in rows:
            if row.role == AgentMessageRole.SYSTEM:
                continue
            if row.role == AgentMessageRole.USER:
                out.append({"role": "user", "content": row.content_json})
            elif row.role == AgentMessageRole.ASSISTANT:
                out.append({"role": "assistant", "content": row.content_json})
            elif row.role == AgentMessageRole.TOOL_USE:
                # tool_use is part of the assistant turn; merge if possible.
                if out and out[-1]["role"] == "assistant":
                    out[-1]["content"].extend(row.content_json)
                else:
                    out.append(
                        {"role": "assistant", "content": row.content_json}
                    )
            elif row.role == AgentMessageRole.TOOL_RESULT:
                out.append({"role": "user", "content": row.content_json})
        return out

    async def _persist_assistant_message(
        self,
        session_id: int,
        call: AnthropicCall,
        parent_message_id: int,
        latency_ms: int,
    ) -> None:
        """Atomically persist the assistant message + any tool invocations.

        Tool dispatch happens server-side at Anthropic; we don't see the
        tool result in the response, so ``AgentToolInvocation.output_json``
        is left ``None`` and ``latency_ms`` reflects the wall-clock of the
        whole API call (not the tool itself).
        """
        async with self._session_factory() as db:
            session_row = await db.get(AgentSession, session_id)
            msg = AgentMessage(
                session_id=session_id,
                role=AgentMessageRole.ASSISTANT,
                content_json=call.content_blocks,
                input_tokens=call.input_tokens,
                output_tokens=call.output_tokens,
                model=session_row.model if session_row else None,
                parent_message_id=parent_message_id,
                ts=datetime.now(UTC),
            )
            db.add(msg)
            await db.flush()
            assistant_msg_id = msg.id

            for block in call.content_blocks:
                if block.get("type") == "tool_use":
                    db.add(
                        AgentToolInvocation(
                            session_id=session_id,
                            message_id=assistant_msg_id,
                            tool_name=block.get("name", ""),
                            input_json=block.get("input", {}),
                            output_json=None,
                            latency_ms=latency_ms,
                            ts=datetime.now(UTC),
                        )
                    )
            await db.commit()

        await self._publish(
            "agent.message_appended",
            {
                "session_id": session_id,
                "message_id": assistant_msg_id,
                "role": "assistant",
                "has_tool_use": any(
                    b.get("type") == "tool_use" for b in call.content_blocks
                ),
                "input_tokens": call.input_tokens,
                "output_tokens": call.output_tokens,
            },
        )

    async def _charge_and_check_cap(
        self, session_id: int, call: AnthropicCall
    ) -> bool:
        """Apply real usage to the session totals. Return True if the cap fired."""
        async with self._session_factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None:
                return False
            cost = estimate_cost(
                row.model, call.input_tokens, call.output_tokens
            )
            row.total_input_tokens += call.input_tokens
            row.total_output_tokens += call.output_tokens
            row.total_cost_usd = (
                row.total_cost_usd + cost
            ).quantize(Decimal("0.0001"))
            await db.commit()
            await db.refresh(row)

            resolver = DailyBudgetResolver(
                daily_budget_usd=row.daily_budget_usd
            )
            spent = await resolver.spent_today(db, user_id=row.user_id)
            if spent >= row.daily_budget_usd:
                await self._handle_cap_hit(
                    session_id, "post_call_actual_over_budget"
                )
                return True
        return False

    async def _handle_cap_hit(self, session_id: int, reason: str) -> None:
        async with self._session_factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None or row.status not in ACTIVE_AGENT_STATUSES:
                return
            row.status = AgentSessionStatus.CAPPED
            row.ended_at = datetime.now(UTC)
            row.end_reason = reason
            sys_msg = AgentMessage(
                session_id=session_id,
                role=AgentMessageRole.SYSTEM,
                content_json=[
                    {
                        "type": "text",
                        "text": (
                            "Session cost cap reached. This session is now "
                            "read-only. Start a new session to continue."
                        ),
                    }
                ],
                ts=datetime.now(UTC),
            )
            db.add(sys_msg)
            await db.commit()
        await self._publish(
            "agent.session_capped",
            {"session_id": session_id, "reason": reason},
        )

    async def _handle_session_error(
        self, session_id: int, error_text: str
    ) -> None:
        async with self._session_factory() as db:
            row = await db.get(AgentSession, session_id)
            if row is None or row.status not in ACTIVE_AGENT_STATUSES:
                return
            row.status = AgentSessionStatus.ERROR
            row.ended_at = datetime.now(UTC)
            row.end_reason = error_text[:2048]
            sys_msg = AgentMessage(
                session_id=session_id,
                role=AgentMessageRole.SYSTEM,
                content_json=[
                    {
                        "type": "text",
                        "text": (
                            f"Session ended due to error: {error_text[:200]}"
                        ),
                    }
                ],
                ts=datetime.now(UTC),
            )
            db.add(sys_msg)
            await db.commit()
        await self._publish(
            "agent.session_error",
            {"session_id": session_id, "error": error_text},
        )

    async def _publish(self, topic: str, payload: dict[str, Any]) -> None:
        try:
            await self._bus.publish(topic, payload)
        except Exception:
            logger.exception("agent_publish_failed", topic=topic)
