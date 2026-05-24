"""Pydantic schemas for the TradingView Pine alert webhook.

``payload`` is deliberately permissive (``dict[str, Any]``) so TV alert
authors can include arbitrary metadata (price, indicator values, comment,
etc.) without us shipping a schema bump each time.
"""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class TVWebhookRequest(BaseModel):
    """Body of a ``POST /api/v1/alerts/tv``.

    Example body the trader pastes into TradingView's alert template::

        {
          "secret": "{{your_secret_here}}",
          "symbol": "{{ticker}}",
          "side": "buy",
          "payload": {
            "price": "{{close}}",
            "rsi": "{{plot_0}}",
            "comment": "RSI cross under 30"
          }
        }

    TradingView substitutes the ``{{...}}`` tokens at alert time.
    """

    model_config = ConfigDict(extra="forbid")

    secret: str = Field(min_length=8, max_length=128)
    symbol: str = Field(min_length=1, max_length=32)
    # Some alerts are pure information events (RSI cross, volume spike)
    # without a directional bias — ``side`` stays optional.
    side: Literal["buy", "sell", "long", "short", "flat"] | None = None
    # If set, the alert binds to a Strategy row; the secret's user must own
    # the strategy or we 404.
    strategy_id: int | None = Field(default=None, ge=1)
    payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("symbol")
    @classmethod
    def _upper(cls, v: str) -> str:
        return v.strip().upper()


class TVWebhookAcceptedResponse(BaseModel):
    """Response for accepted or deduped alerts. Both return 200."""

    signal_id: int | None  # None if deduped
    deduped: bool
    received_at: str  # ISO timestamp
