"""Pydantic models for ``POST /api/v1/range-template/apply`` (P8 §7)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ApplyRangeTemplateRequest(BaseModel):
    symbol: str = Field(min_length=1, max_length=16)
    name: str | None = Field(default=None, max_length=128)


class ApplyRangeTemplateResponse(BaseModel):
    id: int
    name: str
    status: str
    code_path: str
    authoring_method: str
    symbol: str
    prefilled_from_range_insight: bool
