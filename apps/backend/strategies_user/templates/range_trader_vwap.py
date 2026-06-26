"""VWAP±σ range-trading variant (P10) — dynamic-level fade-the-range.

Why this exists: the fixed-level ``range-trader`` (range_trader.py) only enters
when price visits a *static* support level, so over a multi-month window it
fires ~0.2–1 entries/session regardless of how much the symbol oscillates —
every §5c backtest came back INCONCLUSIVE (13–23 trades). See
``TradingWorkbench_RangeTrader_5c_TestResults_v0.1.md``.

This variant replaces the three fixed price params with **session-VWAP bands**
recomputed every bar, so an entry opportunity exists most days and price can
round-trip the band multiple times per session (same-day re-entry, which the
base lifecycle already supports up to ``max_trades_per_day``):

  - **VWAP** = session cumulative volume-weighted typical price ((h+l+c)/3).
  - **σ** = running std of (price − VWAP) within the session (warm-up gated).
  - **Entry (buy):** price ≤ VWAP − ``entry_sigma``·σ   (stretched below the mean)
  - **Exit (sell):** price ≥ VWAP − ``exit_sigma``·σ    (revert toward VWAP; default exit_sigma=0 ⇒ VWAP)
  - **Hard stop (sell):** price ≤ VWAP − ``stop_sigma``·σ (further stretch ⇒ range broken for the day)

Everything else — the EOD force-flat, the no-trade-open window, the per-day cap,
the in-flight guard, stop-out halt, and risk-based sizing — is inherited
unchanged from :class:`RangeTrader`. Orders route through ``ctx.submit_order``
only (ADR 0002). Levels are dynamic, so the ``stop < entry < exit`` ordering
holds by construction whenever ``stop_sigma > entry_sigma > exit_sigma``.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any, ClassVar

from app.db.enums import OrderSide

from .range_trader import SESSION_CLOSE, SESSION_OPEN, RangeTrader, _shift, _us_eastern


class RangeTraderVWAP(RangeTrader):
    name: ClassVar[str] = "range-trader-vwap"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = []
    schedule: ClassVar[str] = "*/5 * * * *"

    default_params: ClassVar[dict[str, Any]] = {
        "timeframe": "5Min",
        "entry_sigma": 1.0,      # buy at VWAP - entry_sigma·σ
        "exit_sigma": 0.0,       # sell at VWAP - exit_sigma·σ (0 ⇒ at VWAP)
        "stop_sigma": 2.0,       # hard stop at VWAP - stop_sigma·σ
        "sigma_warmup_bars": 6,  # bars into the session before σ is trusted
        "risk_per_trade_pct": 0.01,
        "initial_equity_estimate": 100_000,
        "max_position_qty": 100,
        "max_trades_per_day": 4,
        "no_trade_open_minutes": 5,
        "hard_exit_before_close_minutes": 5,
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "timeframe": {
            "type": "enum", "choices": ["1Min", "5Min", "15Min", "1Hour"],
            "default": "5Min", "description": "Bar timeframe driving on_bar dispatch.",
        },
        "entry_sigma": {
            "type": "number", "min": 0, "default": 1.0,
            "description": "Buy when price <= VWAP - entry_sigma·σ.",
        },
        "exit_sigma": {
            "type": "number", "min": 0, "default": 0.0,
            "description": "Sell when price >= VWAP - exit_sigma·σ (0 = at VWAP).",
        },
        "stop_sigma": {
            "type": "number", "min": 0, "default": 2.0,
            "description": "Hard stop when price <= VWAP - stop_sigma·σ. Must exceed entry_sigma.",
        },
        "sigma_warmup_bars": {
            "type": "integer", "min": 1, "default": 6,
            "description": "Bars into the session before σ is trusted enough to trade.",
        },
        "risk_per_trade_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.01,
            "description": "Fraction of equity risked per trade.",
        },
        "initial_equity_estimate": {
            "type": "number", "min": 0, "default": 100_000,
            "description": "Equity estimate used for position sizing.",
        },
        "max_position_qty": {
            "type": "integer", "min": 0, "default": 100,
            "description": "Hard cap on shares per position.",
        },
        "max_trades_per_day": {
            "type": "integer", "min": 0, "default": 4,
            "description": "Maximum entries per trading day (enables same-day re-entry).",
        },
        "no_trade_open_minutes": {
            "type": "integer", "min": 0, "default": 5,
            "description": "No entries in the first N minutes after 09:30 ET.",
        },
        "hard_exit_before_close_minutes": {
            "type": "integer", "min": 0, "default": 5,
            "description": "Force-exit in the last N minutes before 16:00 ET.",
        },
    }

    async def on_init(self) -> None:
        await super().on_init()
        # This VWAP variant keeps its OWN single-symbol scalar state (it has its own on_bar
        # and does not use the parent's per-symbol _SymState model). The parent's on_init
        # now sets up only ``self._sym`` / equity, so re-declare the scalars this class uses.
        self._trade_day: str | None = None
        self._trades_today = 0
        self._stopped_today = False
        self._pending: dict[str, str] = {}
        # Per-session VWAP + deviation accumulators (running, O(1) per bar).
        self._cum_pv = 0.0
        self._cum_v = 0.0
        self._dev_n = 0
        self._dev_sum = 0.0
        self._dev_sumsq = 0.0

    def _reset_session(self) -> None:
        self._cum_pv = self._cum_v = 0.0
        self._dev_n = 0
        self._dev_sum = self._dev_sumsq = 0.0

    def _levels(self, bar: Any) -> tuple[float, float, float] | None:
        """Update the session VWAP/σ accumulators with this bar and return
        (entry, exit, stop) price levels, or None until σ has warmed up."""
        p = self.params
        typical = (float(bar.h) + float(bar.l) + float(bar.c)) / 3.0
        vol = float(bar.v) or 1.0
        self._cum_pv += typical * vol
        self._cum_v += vol
        vwap = self._cum_pv / self._cum_v if self._cum_v else float(bar.c)

        dev = float(bar.c) - vwap
        self._dev_n += 1
        self._dev_sum += dev
        self._dev_sumsq += dev * dev

        if self._dev_n < int(p.get("sigma_warmup_bars", 6)):
            return None
        var = self._dev_sumsq / self._dev_n - (self._dev_sum / self._dev_n) ** 2
        sigma = var ** 0.5 if var > 0 else 0.0
        if sigma <= 0:
            return None

        entry = vwap - float(p.get("entry_sigma", 1.0)) * sigma
        exit_ = vwap - float(p.get("exit_sigma", 0.0)) * sigma
        stop = vwap - float(p.get("stop_sigma", 2.0)) * sigma
        return entry, exit_, stop

    async def on_bar(self, bar: Any) -> None:
        p = self.params
        price = float(bar.c)
        symbol = bar.symbol
        bar_et = bar.t.astimezone(_us_eastern())
        tod = bar_et.time()
        day_key = bar_et.date().isoformat()
        if self._trade_day != day_key:
            self._trade_day = day_key
            self._trades_today = 0
            self._stopped_today = False
            self._pending.pop(symbol, None)
            self._reset_session()

        levels = self._levels(bar)  # also advances the session accumulators

        position = await self.ctx.get_position_for(symbol)
        in_long = (
            position is not None
            and getattr(position, "side", None) == "long"
            and position.qty > 0
        )

        pend = self._pending.get(symbol)
        if (pend == "exit" and not in_long) or (pend == "entry" and in_long):
            self._pending.pop(symbol, None)
            pend = None

        # ---- hard exit near the close (independent of σ warm-up) ----
        close_cutoff = _shift(SESSION_CLOSE, -int(p.get("hard_exit_before_close_minutes", 5)))
        if tod >= close_cutoff:
            if in_long and pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="time_exit"
            ):
                self._pending[symbol] = "exit"
            return

        if levels is None:
            return  # σ not warmed up yet this session
        entry, exit_, stop = levels

        # ---- hard stop ----
        if in_long and price <= stop:
            self._stopped_today = True  # range broken — no re-entry today
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="stop_loss"
            ):
                self._pending[symbol] = "exit"
            return

        # ---- exit toward VWAP ----
        if in_long and price >= exit_:
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="vwap_revert_exit"
            ):
                self._pending[symbol] = "exit"
            return

        # ---- no-trade window after the open ----
        open_cutoff = _shift(SESSION_OPEN, int(p.get("no_trade_open_minutes", 5)))
        if tod < open_cutoff:
            return

        # ---- entry below the lower band (fade); same-day re-entry allowed ----
        if in_long or pend is not None:
            return
        if price > entry:
            return
        if self._stopped_today:
            return
        if self._trades_today >= int(p.get("max_trades_per_day", 4)):
            return
        qty = self._size_position(entry=entry, stop=stop)
        if qty > 0 and await self._submit(
            symbol, OrderSide.BUY, Decimal(qty),
            reason="vwap_band_entry",
            payload={"price": price, "vwap_entry": entry, "vwap_stop": stop},
        ):
            self._trades_today += 1
            self._pending[symbol] = "entry"
