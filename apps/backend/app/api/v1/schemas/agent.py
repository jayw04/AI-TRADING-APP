"""Pydantic schemas for ``/api/v1/agent`` endpoints (P3 Session 4).

The B3 reject in :class:`StartSessionRequest` is the defense-in-depth
layer in front of the runtime's own rejection. Per ADR 0006 it is paused
indefinitely, not just "P3-deferred."
"""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator

from app.db.enums import AgentMessageRole, AgentSessionMode, AgentSessionStatus

# ---------- requests ----------


class StartSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    mode: AgentSessionMode = AgentSessionMode.B2_INTERACTIVE
    model: str | None = Field(default=None, max_length=64)

    @field_validator("mode")
    @classmethod
    def _reject_b3(cls, v: AgentSessionMode) -> AgentSessionMode:
        if v == AgentSessionMode.B3_AUTONOMOUS:
            raise ValueError(
                "AgentSessionMode B3_AUTONOMOUS is paused indefinitely "
                "per ADR 0006 (docs/adr/0006-llm-not-in-order-path.md). "
                "Use b1_readonly or b2_interactive."
            )
        return v


class EndSessionRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(default="user_end", max_length=128)


class AppendMessageRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=16384)


# ---------- responses ----------


class SessionSummary(BaseModel):
    """Compact session row for the list view (no messages inline)."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    mode: AgentSessionMode
    status: AgentSessionStatus
    model: str
    total_input_tokens: int
    total_output_tokens: int
    total_cost_usd: Decimal
    daily_budget_usd: Decimal
    started_at: datetime
    ended_at: datetime | None = None
    end_reason: str | None = None
    # Computed per query, not a column on the table.
    message_count: int = 0


class SessionListResponse(BaseModel):
    items: list[SessionSummary]
    count: int


class MessageResponse(BaseModel):
    """One AgentMessage row reshaped for the API. ``content`` mirrors the
    Anthropic content-block format we store in ``content_json``."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    session_id: int
    role: AgentMessageRole
    # validation_alias (not alias) so the ORM's content_json column maps
    # to this field on input, while output serialization uses the field
    # name `content` — that's what the client contract advertises.
    content: list[dict[str, Any]] = Field(validation_alias="content_json")
    input_tokens: int | None = None
    output_tokens: int | None = None
    model: str | None = None
    ts: datetime
    parent_message_id: int | None = None


class SessionDetail(SessionSummary):
    """Session summary + the ordered conversation."""

    messages: list[MessageResponse] = Field(default_factory=list)


class AppendMessageResponse(BaseModel):
    """Returned synchronously when a user message is accepted.

    Assistant responses arrive via the ``agent`` WS topic; the client
    correlates by ``session_id``.
    """

    session_id: int
    user_message_id: int


class BudgetResponse(BaseModel):
    """Today's spending against the configured daily budget."""

    spent_usd: Decimal
    budget_usd: Decimal
    remaining_usd: Decimal
    pct_used: float
