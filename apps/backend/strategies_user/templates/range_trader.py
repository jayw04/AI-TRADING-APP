"""Range-trading template (P8 §7) — fade-the-range mean reversion.

A REGULAR deterministic Strategy file (Direction Decision 3): declared params,
the standard signal/lifecycle. "Apply range template to {symbol}" creates a
Strategy row that references THIS file with params prefilled from the symbol's
Range Insight (§5); the trader edits them via the standard param form.

Logic (fade the range):
  - Buy when price dips to/below ``entry_price`` (near support / the 80% low band).
  - Sell when price reaches ``exit_price`` (near resistance / the 80% high band).
  - Hard stop: sell when price ≤ ``stop_price`` (below support).
  - Time-of-day gates: no entries in the first ``no_trade_open_minutes`` after
    09:30 ET; force-exit any position in the last ``hard_exit_before_close_minutes``
    before 16:00 ET.
  - At most ``max_trades_per_day`` entries per ET day.

The price levels are PARAMETERS. They are 0 (unset) by default — a freshly
applied strategy with no Range Insight is inert until the trader sets them.
Orders route through ``self.ctx.submit_order`` only (ADR 0002).
"""

from __future__ import annotations

from datetime import time
from decimal import Decimal
from typing import Any, ClassVar

from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    SignalType,
    TimeInForce,
)
from app.risk import OrderRequest
from app.strategies import Strategy

SESSION_OPEN = time(9, 30)
SESSION_CLOSE = time(16, 0)


class RangeTrader(Strategy):
    name: ClassVar[str] = "range-trader"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = []  # set per applied strategy
    schedule: ClassVar[str] = "*/5 * * * *"

    default_params: ClassVar[dict[str, Any]] = {
        "timeframe": "5Min",
        "entry_price": 0.0,  # buy when price <= this (near support)
        "exit_price": 0.0,  # sell when price >= this (near resistance)
        "stop_price": 0.0,  # hard stop (below support)
        "risk_per_trade_pct": 0.01,
        "initial_equity_estimate": 100_000,
        "max_position_qty": 100,
        "max_trades_per_day": 4,
        "no_trade_open_minutes": 5,
        "hard_exit_before_close_minutes": 5,
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "timeframe": {
            "type": "enum",
            "choices": ["1Min", "5Min", "15Min", "1Hour"],
            "default": "5Min",
            "description": "Bar timeframe driving on_bar dispatch.",
        },
        "entry_price": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "Buy when price dips to/below this (near support).",
        },
        "exit_price": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "Sell when price rises to/above this (near resistance).",
        },
        "stop_price": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "Hard stop — sell when price falls to/below this.",
        },
        "risk_per_trade_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.01,
            "description": "Fraction of equity risked per trade.",
        },
        "initial_equity_estimate": {
            "type": "number",
            "min": 0,
            "default": 100_000,
            "description": "Equity estimate used for position sizing.",
        },
        "max_position_qty": {
            "type": "integer",
            "min": 0,
            "default": 100,
            "description": "Hard cap on shares per position.",
        },
        "max_trades_per_day": {
            "type": "integer",
            "min": 0,
            "default": 4,
            "description": "Maximum entries per trading day.",
        },
        "no_trade_open_minutes": {
            "type": "integer",
            "min": 0,
            "default": 5,
            "description": "No entries in the first N minutes after 09:30 ET.",
        },
        "hard_exit_before_close_minutes": {
            "type": "integer",
            "min": 0,
            "default": 5,
            "description": "Force-exit in the last N minutes before 16:00 ET.",
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(
            str(self.params.get("initial_equity_estimate", 100_000))
        )
        self._trade_day: str | None = None
        self._trades_today = 0

    async def on_bar(self, bar: Any) -> None:
        p = self.params
        entry = float(p.get("entry_price") or 0)
        exit_ = float(p.get("exit_price") or 0)
        stop = float(p.get("stop_price") or 0)
        price = float(bar.c)

        bar_et = bar.t.astimezone(_us_eastern())
        tod = bar_et.time()
        day_key = bar_et.date().isoformat()
        if self._trade_day != day_key:
            self._trade_day = day_key
            self._trades_today = 0

        position = await self.ctx.get_position_for(bar.symbol)
        in_long = (
            position is not None
            and getattr(position, "side", None) == "long"
            and position.qty > 0
        )

        # ---- hard exit near the close ----
        close_cutoff = _shift(SESSION_CLOSE, -int(p.get("hard_exit_before_close_minutes", 5)))
        if tod >= close_cutoff:
            if in_long:
                await self._submit(bar.symbol, OrderSide.SELL, position.qty, reason="time_exit")
            return

        # ---- stop loss ----
        if in_long and stop > 0 and price <= stop:
            await self._submit(bar.symbol, OrderSide.SELL, position.qty, reason="stop_loss")
            return

        # ---- exit at resistance ----
        if in_long and exit_ > 0 and price >= exit_:
            await self._submit(bar.symbol, OrderSide.SELL, position.qty, reason="range_exit")
            return

        # ---- no-trade window after the open ----
        open_cutoff = _shift(SESSION_OPEN, int(p.get("no_trade_open_minutes", 5)))
        if tod < open_cutoff:
            return

        # ---- entry near support (fade the range) ----
        if not in_long and entry > 0 and price <= entry:
            if self._trades_today >= int(p.get("max_trades_per_day", 4)):
                return
            qty = self._size_position(entry=entry, stop=stop)
            if qty > 0:
                self._trades_today += 1
                await self._submit(
                    bar.symbol,
                    OrderSide.BUY,
                    Decimal(qty),
                    reason="range_entry",
                    payload={"price": price, "entry": entry},
                )

    async def on_fill(self, fill: Any) -> None:
        # Reset the daily counter cannot happen here; entry tracking is implicit
        # via position state. No-op kept for interface completeness.
        return

    # ---- helpers ----

    def _size_position(self, *, entry: float, stop: float) -> int:
        """Risk-based sizing: ``risk_per_trade_pct × equity / per-share-risk``,
        capped at ``max_position_qty``. Per-share risk = entry − stop, falling
        back to 2% of price when no stop is set (never divides by zero)."""
        risk = float(self._equity_estimate) * float(self.params["risk_per_trade_pct"])
        dist = entry - stop if (stop > 0 and entry > stop) else entry * 0.02
        if dist <= 0:
            return 0
        raw = risk / dist
        return int(min(raw, float(self.params["max_position_qty"])))

    async def _submit(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> None:
        if qty <= 0:
            return
        req = OrderRequest(
            user_id=0,  # context fills these
            account_id=0,
            symbol_ticker=symbol,
            side=side,
            qty=qty,
            type=OrderType.MARKET,
            tif=TimeInForce.DAY,
            source_type=OrderSourceType.STRATEGY,
            source_id=None,  # context stamps the strategy id
        )
        result = await self.ctx.submit_order(req)
        sig_type = SignalType.ENTRY if side == OrderSide.BUY else SignalType.EXIT
        log_payload: dict[str, Any] = {"reason": reason, **(payload or {})}
        rejection = getattr(result, "rejection_reason", None)
        if rejection:
            log_payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig_type, payload=log_payload)


def _us_eastern():  # type: ignore[no-untyped-def]
    """Lazy ``zoneinfo`` so import order doesn't matter."""
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


def _shift(t: time, minutes: int) -> time:
    """``t`` shifted by ``minutes`` (clamped to [00:00, 23:59])."""
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)
