"""TradingProfile — the user's soft-preferences layer (P5.5 §1).

One row per user. Five JSON sections capture the trader's *judgment* layer:
watchlist, bias criteria (prose), bias thresholds (the only machine-read
section — the morning brief in §2 consumes it), session preferences, and risk
preferences. This is explicitly NOT the hard-enforcement ``risk_limits`` table:
nothing here alters a risk gate. The profile is fuel for the morning brief
(§2) and the agent (P6+) to consult.

No code path reads this table in §1 — §2 (morning brief) is the first reader.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import JSON, DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class TradingProfile(Base):
    __tablename__ = "trading_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    # One profile per user. Column-level unique constraint (NOT a separate
    # unique index — those would be two spellings of the same thing). The
    # `index=True` here gives the lookup-by-user query its index.
    user_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )

    # Watchlist: symbols to consider in scans + morning brief.
    # Shape: { "core": [...], "swing_candidates": [...], "do_not_trade": [...] }
    watchlist_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Bias criteria: human-readable descriptions of bullish/bearish/neutral.
    # Shape: { "bullish": "string", "bearish": "string", "neutral": "string" }
    # Display/documentation strings only — the morning brief (§2) uses the
    # thresholds field below for actual labeling. These document the trader's
    # mental model for future agent (P6) reference.
    bias_criteria_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Indicator thresholds for the morning brief's automatic labeling (§2).
    # Shape: { "bullish": {"rsi_min": 50, "ema_relationship": "20>50",
    #                       "price_vs_vwap": "above"}, "bearish": {...}, ... }
    bias_thresholds_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Session preferences: when the user wants to be active.
    # Shape: { "preferred_hours": ["09:30-11:00"], "avoid_overnight_holds": false,
    #          "max_correlated_positions": 3 }
    session_preferences_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # Risk preferences: SOFT preferences the agent/morning brief consult. NOT
    # the hard risk_limits table. Examples: preferred_position_size_pct_equity,
    # max_strategies_simultaneously, prefer_paper_validation.
    risk_preferences_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    # P6 §1a (Decision 4): the agent's behavioral envelope. Sixth JSON section,
    # the single canonical home for agent behavioral constraints. All sub-keys
    # optional; read with defensive .get() everywhere. Initial sub-keys:
    #   prohibitions: list[str]            — hard "never propose X"
    #   preferences: dict[str, Any]        — soft "prefer X over Y" weights
    #   prompt_augmentations: str          — text merged into the prompt template
    #   cost_envelope_cents: int           — per-day spend cap (default 200=$2.00)
    #   eval_metric_weights: dict[str, Any]  — backtest-metric weights (Decision 8)
    #   hide_low_confidence_proposals: bool  — UI hint
    agent_envelope_json: Mapped[dict[str, Any]] = mapped_column(
        JSON, nullable=False, default=dict
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
