"""Pydantic schemas for ``/api/v1/accounts`` (list + create).

Distinct from ``schemas/account.py`` (singular), which describes the live
AccountState snapshot for a single paper account. This module describes the
account *rows* themselves — including their broker_mode — for the P5 §1
LIVE / PAPER surfaces the frontend renders.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

from app.db.models.account import AccountMode


class AccountResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    broker: str
    mode: AccountMode
    label: str | None = None
    broker_mode_locked_at: datetime | None = None
    created_at: datetime


class AccountListResponse(BaseModel):
    items: list[AccountResponse]
    count: int


class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: str = Field(min_length=1, max_length=32)
    mode: AccountMode = AccountMode.paper
    label: str = Field(min_length=1, max_length=64)
    # P5 §7: required when mode=live. Re-verified server-side against the user's
    # stored TOTP secret — layered defense against "session cookie creates a
    # live account." Ignored for paper.
    totp_code: str | None = Field(default=None, min_length=6, max_length=8)
