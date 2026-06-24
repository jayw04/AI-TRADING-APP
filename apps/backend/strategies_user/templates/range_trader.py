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

Safeguards:
  - Stop-out halt: once the hard stop fires (or price is at/below the stop
    level), the range is treated as broken — no further entries that ET day.
  - In-flight order guard: a per-symbol pending flag prevents duplicate
    entry/exit submissions across consecutive bars before the fill lands;
    reconciled against actual position state every bar and cleared on fill.
  - Level-ordering validation: entries require ``stop < entry < exit`` for
    whichever levels are set. Invalid combinations make the strategy inert
    for entries (exits/stops still protect an existing position).

Levels come from one of two modes (``level_mode``):
  - ``opening_range`` (default): the levels are derived EACH DAY from today's first
    ``opening_range_minutes`` of bars (entry = range low, exit = range high,
    stop = range_low × (1 − ``stop_buffer_pct``)). No entries while the range
    forms. Self-contained from the intraday feed — no stale daily-bar dependency.
    This is the default so the strategy (and its proposal eval) simulate live,
    daily-adaptive rules rather than a frozen snapshot — evaluating fixed levels
    measures a historical artifact, not the strategy (review E5).
  - ``fixed``: the ``entry/exit/stop`` PARAMETERS. 0 (unset) by default, so a
    freshly applied strategy with no Range Insight is inert until set. These are
    frozen — they do not track the current day's price (an explicit static study).

Position size scales to the LIVE account equity (``ctx.get_account_equity``),
refreshed once per day, with ``initial_equity_estimate`` as the fallback.
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
        # Level source: "opening_range" (default) derives entry/exit/stop each day from
        # today's first ``opening_range_minutes`` of bars (daily-adaptive — so the eval
        # simulates the real rules, review E5); "fixed" uses the static params below.
        "level_mode": "opening_range",
        "opening_range_minutes": 30,
        "stop_buffer_pct": 0.005,
        "entry_price": 0.0,  # buy when price <= this (near support) — fixed mode
        "exit_price": 0.0,  # sell when price >= this (near resistance) — fixed mode
        "stop_price": 0.0,  # hard stop (below support) — fixed mode
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
        "level_mode": {
            "type": "enum",
            "choices": ["fixed", "opening_range"],
            "default": "opening_range",
            "description": "opening_range (default) = derive entry/exit/stop each day "
            "from the first N minutes of price action; fixed = use the static params.",
        },
        "opening_range_minutes": {
            "type": "integer",
            "min": 1,
            "default": 30,
            "description": "opening_range mode: minutes after 09:30 ET used to build "
            "the day's range (no entries while it forms).",
        },
        "stop_buffer_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.005,
            "description": "opening_range mode: stop = range-low × (1 − this).",
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
        # Fix #1: once stopped out (or price breaks the stop level), no more
        # entries for the rest of the ET day — the range is considered broken.
        self._stopped_today = False
        # Fix #2: per-symbol in-flight order flag ("entry" | "exit") to prevent
        # duplicate submissions across bars before the fill lands.
        self._pending: dict[str, str] = {}
        # Fix #4: log invalid-level inertness at most once per day.
        self._invalid_logged_day: str | None = None
        # opening_range mode: today's range, built from the first
        # ``opening_range_minutes`` of bars, then frozen for the rest of the day.
        self._or_high: float | None = None
        self._or_low: float | None = None
        self._dyn_levels: tuple[float, float, float] | None = None

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
            # DAY orders expired at the prior close; stale flags would
            # otherwise block the new session.
            self._pending.pop(symbol, None)
            # New day: reset the opening range, and refresh the sizing equity from
            # the LIVE account balance (fall back to the configured estimate when no
            # broker snapshot exists yet).
            self._or_high = None
            self._or_low = None
            self._dyn_levels = None
            equity = await self.ctx.get_account_equity()
            if equity is not None and equity > 0:
                self._equity_estimate = equity

        # Resolve today's levels: fixed (params) or dynamic opening-range. In
        # opening_range mode this also accumulates the range while it is forming.
        entry, exit_, stop = self._resolve_levels(p, bar, tod)

        position = await self.ctx.get_position_for(symbol)
        in_long = (
            position is not None
            and getattr(position, "side", None) == "long"
            and position.qty > 0
        )

        # ---- reconcile pending flag against actual position state ----
        # Belt-and-braces alongside on_fill: if the position already reflects
        # the in-flight order, the fill landed and the flag is stale.
        pend = self._pending.get(symbol)
        if (pend == "exit" and not in_long) or (pend == "entry" and in_long):
            self._pending.pop(symbol, None)
            pend = None

        # ---- hard exit near the close ----
        close_cutoff = _shift(SESSION_CLOSE, -int(p.get("hard_exit_before_close_minutes", 5)))
        if tod >= close_cutoff:
            # short-circuit: only submit when not already exiting (combined to
            # avoid a nested if; the submit's side effect runs only if accepted).
            if in_long and pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="time_exit"
            ):
                self._pending[symbol] = "exit"
            return

        # ---- stop loss ----
        if in_long and stop > 0 and price <= stop:
            self._stopped_today = True  # range broken — halt entries for the day
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="stop_loss"
            ):
                self._pending[symbol] = "exit"
            return

        # ---- exit at resistance ----
        if in_long and exit_ > 0 and price >= exit_:
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="range_exit"
            ):
                self._pending[symbol] = "exit"
            return

        # ---- no-trade window after the open ----
        open_cutoff = _shift(SESSION_OPEN, int(p.get("no_trade_open_minutes", 5)))
        if tod < open_cutoff:
            return

        # ---- entry near support (fade the range) ----
        if in_long or pend is not None:
            return
        if entry <= 0 or price > entry:
            return
        if not _levels_ok(entry=entry, exit_=exit_, stop=stop):
            await self._log_invalid_levels(symbol, day_key, entry=entry, exit_=exit_, stop=stop)
            return
        if self._stopped_today:
            return  # stopped out earlier today — do not re-enter a broken range
        if stop > 0 and price <= stop:
            self._stopped_today = True  # price already through the stop: range broken
            return
        if self._trades_today >= int(p.get("max_trades_per_day", 4)):
            return
        qty = self._size_position(entry=entry, stop=stop)
        if qty > 0:
            accepted = await self._submit(
                symbol,
                OrderSide.BUY,
                Decimal(qty),
                reason="range_entry",
                payload={"price": price, "entry": entry},
            )
            if accepted:
                # Count only accepted orders so risk-layer rejections don't
                # consume daily slots.
                self._trades_today += 1
                self._pending[symbol] = "entry"

    async def on_fill(self, fill: Any) -> None:
        # Fix #2: clear the in-flight flag once the order fills. The on_bar
        # reconciliation covers any fills this misses. FillEvent.symbol is the
        # framework's confirmed attribute (app/strategies/context.py).
        sym = getattr(fill, "symbol", None)
        if sym:
            self._pending.pop(sym, None)

    # ---- helpers ----

    def _resolve_levels(self, p: dict[str, Any], bar: Any, tod: time) -> tuple[float, float, float]:
        """Return today's ``(entry, exit, stop)``.

        ``fixed`` mode → the configured params (legacy behavior). ``opening_range``
        mode → derived from today's first ``opening_range_minutes`` of price action:
        entry = range low (fade/buy support), exit = range high (sell resistance),
        stop = range_low × (1 − ``stop_buffer_pct``). Returns zeros while the range
        is still forming (so the existing ``entry <= 0`` gate blocks entries), and
        accumulates the range as a side effect during that window."""
        # Fallback matches default_params/schema (opening_range) so the dynamic rules
        # apply even when the caller (e.g. the eval backtest) passes params that don't
        # merge default_params — the base class sets self.params verbatim (E5).
        if p.get("level_mode", "opening_range") != "opening_range":
            return (
                float(p.get("entry_price") or 0),
                float(p.get("exit_price") or 0),
                float(p.get("stop_price") or 0),
            )
        or_end = _shift(SESSION_OPEN, int(p.get("opening_range_minutes", 30)))
        if SESSION_OPEN <= tod < or_end:
            self._or_high = bar.h if self._or_high is None else max(self._or_high, bar.h)
            self._or_low = bar.l if self._or_low is None else min(self._or_low, bar.l)
            return (0.0, 0.0, 0.0)  # range still forming — no levels yet
        if (
            self._dyn_levels is None
            and self._or_high is not None
            and self._or_low is not None
            and self._or_high > self._or_low
        ):
            buf = float(p.get("stop_buffer_pct", 0.005))
            self._dyn_levels = (
                round(self._or_low, 4),
                round(self._or_high, 4),
                round(self._or_low * (1 - buf), 4),
            )
        return self._dyn_levels or (0.0, 0.0, 0.0)

    def _size_position(self, *, entry: float, stop: float) -> int:
        """Risk-based sizing: ``risk_per_trade_pct × equity / per-share-risk``,
        capped at ``max_position_qty``. Per-share risk = entry − stop. The 2%
        fallback applies only when NO stop is set; an inverted stop
        (``stop >= entry``) is a misconfiguration and sizes to zero rather
        than being silently masked (fix #4)."""
        risk = float(self._equity_estimate) * float(
            self.params.get("risk_per_trade_pct", 0.01)
        )
        if stop > 0:
            if entry <= stop:
                return 0  # inverted levels — refuse to trade
            dist = entry - stop
        else:
            dist = entry * 0.02
        if dist <= 0:
            return 0
        raw = risk / dist
        return int(min(raw, float(self.params.get("max_position_qty", 100))))

    async def _log_invalid_levels(
        self, symbol: str, day_key: str, *, entry: float, exit_: float, stop: float
    ) -> None:
        """Surface invalid level ordering once per ET day instead of failing
        silently (fix #4)."""
        if self._invalid_logged_day == day_key:
            return
        self._invalid_logged_day = day_key
        # Logged as INFO (not ENTRY) — this is a skipped-entry diagnostic, not a
        # trade signal, so it must not inflate entry-signal counts.
        await self.ctx.log_signal(
            symbol,
            SignalType.INFO,
            payload={
                "reason": "entry_skipped_invalid_levels",
                "skipped": True,
                "entry": entry,
                "exit": exit_,
                "stop": stop,
            },
        )

    async def _submit(
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        *,
        reason: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
        """Submit via the risk layer. Returns True only when the order was
        accepted, so callers can gate pending flags and the daily counter."""
        if qty <= 0:
            return False
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
        return result is not None and not rejection


def _levels_ok(*, entry: float, exit_: float, stop: float) -> bool:
    """Validate ordering of whichever levels are set: ``stop < entry < exit``.
    Unset (0) levels are skipped. Used to gate ENTRIES only — exits and stops
    still protect an existing position regardless (fix #4)."""
    if entry > 0 and exit_ > 0 and exit_ <= entry:
        return False
    if entry > 0 and stop > 0 and stop >= entry:
        return False
    return not (exit_ > 0 and stop > 0 and stop >= exit_)


def _us_eastern():  # type: ignore[no-untyped-def]
    """Lazy ``zoneinfo`` so import order doesn't matter."""
    from zoneinfo import ZoneInfo

    return ZoneInfo("America/New_York")


def _shift(t: time, minutes: int) -> time:
    """``t`` shifted by ``minutes`` (clamped to [00:00, 23:59])."""
    total = t.hour * 60 + t.minute + minutes
    total = max(0, min(total, 23 * 60 + 59))
    return time(total // 60, total % 60)
