"""Reference RSI mean-reversion strategy.

⚠ **THIS IS A REFERENCE IMPLEMENTATION, NOT A RECOMMENDED TRADING STRATEGY.**
It exists to exercise the Strategy interface end-to-end on a recognizable
template. Do not deploy it live without re-doing the math from scratch.

Logic:

- Universe: configurable (default ``["AAPL", "MSFT", "SPY"]``).
- Each 1-minute bar per symbol:
  - Compute RSI(14) and ATR(14).
  - If ``RSI < entry_threshold`` (default 30) AND no current position:
    - Compute position size: ``risk_per_trade_pct × equity / (atr_multiple × ATR)``,
      rounded down to whole shares; capped at ``max_position_qty``.
    - Submit a MARKET BUY.
  - If long position AND ``RSI > exit_threshold`` (default 55):
    - Submit a MARKET SELL for the full quantity.
- Hard stop: ``atr_multiple_for_stop × ATR`` below entry. Real paper
  trading would submit a STOP order in ``on_fill``; the backtester only
  simulates market orders (per P2 Checklist §5.3), so during backtest
  the stop is enforced via a virtual price check in ``on_bar`` instead.
- Time stop: at end-of-day (16:00 ET), exit any remaining position.
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

# US/Eastern regular-session close. Bar timestamps from Alpaca arrive as
# UTC; we convert at use time.
SESSION_CLOSE = time(16, 0)


class RsiMeanReversion(Strategy):
    name: ClassVar[str] = "rsi-mean-reversion"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = ["AAPL", "MSFT", "SPY"]
    schedule: ClassVar[str] = "*/1 * * * *"  # every minute
    default_params: ClassVar[dict[str, Any]] = {
        "timeframe": "1Min",
        "entry_threshold": 30.0,
        "exit_threshold": 55.0,
        "atr_multiple_for_stop": 2.0,
        "atr_multiple_for_sizing": 2.0,
        "risk_per_trade_pct": 0.01,  # 1% of equity at risk
        "initial_equity_estimate": 100_000,
        "max_position_qty": 50,  # hard ceiling beyond the Risk Engine
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "timeframe": {
            "type": "enum",
            "choices": ["1Min", "5Min", "15Min", "1Hour", "1Day"],
            "default": "1Min",
            "description": "Bar timeframe driving on_bar dispatch.",
        },
        "entry_threshold": {
            "type": "number",
            "min": 0,
            "max": 100,
            "default": 30.0,
            "description": "Enter long when RSI dips below this.",
        },
        "exit_threshold": {
            "type": "number",
            "min": 0,
            "max": 100,
            "default": 55.0,
            "description": "Exit long when RSI crosses above this.",
        },
        "atr_multiple_for_stop": {
            "type": "number",
            "min": 0.1,
            "max": 10,
            "step": 0.1,
            "default": 2.0,
            "description": "ATR multiple used to size the hard stop.",
        },
        "atr_multiple_for_sizing": {
            "type": "number",
            "min": 0.1,
            "max": 10,
            "step": 0.1,
            "default": 2.0,
            "description": "ATR multiple used for risk-based position sizing.",
        },
        "risk_per_trade_pct": {
            "type": "number",
            "min": 0,
            "max": 0.1,
            "step": 0.001,
            "default": 0.01,
            "description": "Fraction of equity risked per trade (0.01 = 1%).",
        },
        "initial_equity_estimate": {
            "type": "number",
            "min": 0,
            "default": 100000,
            "description": (
                "Equity estimate used for sizing before live account state "
                "is available. Live runtime swaps in real equity."
            ),
        },
        "max_position_qty": {
            "type": "integer",
            "min": 1,
            "max": 10000,
            "default": 50,
            "description": "Hard share-count ceiling layered on top of the Risk Engine.",
        },
    }

    def __init__(self, ctx, params):
        super().__init__(ctx, params)
        # Per-symbol entry state for the backtest virtual-stop check.
        self._entry_state: dict[str, dict[str, Decimal]] = {}

    async def on_init(self) -> None:
        # In paper mode the ctx could fetch live equity; for MVP fall back
        # to the configured estimate. Stored as Decimal so sizing math
        # avoids float drift on the cash side.
        self._equity_estimate = Decimal(
            str(self.params.get("initial_equity_estimate", 100_000))
        )

    async def on_bar(self, bar) -> None:
        symbol = bar.symbol
        tf = self.params["timeframe"]

        indicators = await self.ctx.get_indicators(
            symbol, names=["RSI14", "ATR14"], timeframe=tf
        )
        rsi_series = indicators.get("RSI14")
        atr_series = indicators.get("ATR14")
        if rsi_series is None or rsi_series.dropna().empty:
            return
        if atr_series is None or atr_series.dropna().empty:
            return

        rsi = float(rsi_series.iloc[-1])
        atr = float(atr_series.iloc[-1])
        # NaN / nonpositive ATR guard.
        if rsi != rsi or atr != atr or atr <= 0:
            return

        position = await self.ctx.get_position_for(symbol)
        in_long = (
            position is not None
            and getattr(position, "side", None) == "long"
            and position.qty > 0
        )

        # ---- Virtual stop check (backtester substitute for a real STOP) ----
        if in_long:
            state = self._entry_state.get(symbol)
            if state is not None:
                stop_distance = state["atr_at_entry"] * Decimal(
                    str(self.params["atr_multiple_for_stop"])
                )
                stop_price = state["entry_price"] - stop_distance
                if Decimal(str(bar.c)) <= stop_price:
                    await self._submit(
                        symbol, OrderSide.SELL, position.qty, reason="stop_loss"
                    )
                    return

        # ---- Time stop (end of regular session) ----
        bar_et = bar.t.astimezone(_us_eastern())
        if in_long and bar_et.time() >= SESSION_CLOSE:
            await self._submit(symbol, OrderSide.SELL, position.qty, reason="eod")
            return

        # ---- Entry ----
        entry_threshold = float(self.params["entry_threshold"])
        if not in_long and rsi < entry_threshold:
            qty = self._size_position(price=bar.c, atr=atr)
            if qty > 0:
                self._entry_state[symbol] = {
                    "entry_price": Decimal(str(bar.c)),
                    "atr_at_entry": Decimal(str(atr)),
                }
                await self._submit(
                    symbol,
                    OrderSide.BUY,
                    Decimal(qty),
                    reason="rsi_oversold",
                    payload={"rsi": rsi, "atr": atr},
                )
                return

        # ---- Exit ----
        exit_threshold = float(self.params["exit_threshold"])
        if in_long and rsi > exit_threshold:
            await self._submit(
                symbol,
                OrderSide.SELL,
                position.qty,
                reason="rsi_exit",
                payload={"rsi": rsi},
            )

    async def on_fill(self, fill) -> None:
        # Keep entry_state synced so the backtest's virtual-stop logic works
        # regardless of whether on_bar saw the entry first.
        if fill.side == "buy":
            self._entry_state.setdefault(fill.symbol, {})
            self._entry_state[fill.symbol]["entry_price"] = Decimal(str(fill.price))
        elif fill.side == "sell":
            self._entry_state.pop(fill.symbol, None)

    # ---- helpers ----

    def _size_position(self, *, price: float, atr: float) -> int:  # noqa: ARG002
        """Risk-based sizing: ``risk_per_trade_pct × equity / (atr_multiple × ATR)``,
        capped at ``max_position_qty``."""
        risk_per_trade = float(self._equity_estimate) * float(
            self.params["risk_per_trade_pct"]
        )
        stop_distance = float(self.params["atr_multiple_for_sizing"]) * atr
        if stop_distance <= 0:
            return 0
        raw = risk_per_trade / stop_distance
        ceiling = float(self.params["max_position_qty"])
        return int(min(raw, ceiling))

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
        # Log a signal for visibility regardless of accept/reject.
        sig_type = SignalType.ENTRY if side == OrderSide.BUY else SignalType.EXIT
        log_payload: dict[str, Any] = {"reason": reason, **(payload or {})}
        rejection = getattr(result, "rejection_reason", None)
        if rejection:
            log_payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig_type, payload=log_payload)


def _us_eastern():
    """Lazy ``zoneinfo`` so import order doesn't matter."""
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")
