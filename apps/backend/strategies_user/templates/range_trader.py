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
refreshed once per day, with ``initial_equity_estimate`` as the fallback. An optional
``per_position_budget`` caps each symbol's notional so a multi-symbol universe spreads a
fixed capital budget across independent positions (design §"Risk Management").
Orders route through ``self.ctx.submit_order`` only (ADR 0002).

Multi-symbol (design §"Top 3–5 candidates"): ONE Range Trader can trade a universe of
candidate symbols. ``on_bar`` fires once per symbol, and **all per-day state — opening
range, VWAP, the trade counter, the stop-out halt, the in-flight flag — is kept PER SYMBOL**
(``self._sym[symbol]``), so each symbol has its own independent opening range / stop /
entry / exit / daily trade counter and they never collide. The strategy logic is identical
across symbols; it is simply applied to each independent opportunity. (Strategy-level risk —
gross exposure, concurrent-position caps — is enforced centrally by the risk engine, not
re-implemented here.)
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


class _SymState:
    """All per-symbol, per-day state for one candidate. A ``RangeTrader`` instance holds
    one of these per symbol so a multi-symbol universe trades each name independently —
    its own opening range, VWAP, stop-out halt, in-flight flag, and daily trade counter.

    A plain class (not a ``@dataclass``): strategy templates are loaded via ``exec`` without
    being registered in ``sys.modules``, and ``@dataclass`` crashes in that environment
    (it does ``sys.modules.get(cls.__module__).__dict__``)."""

    __slots__ = (
        "trade_day", "trades_today", "stopped_today", "pending", "invalid_logged_day",
        "or_high", "or_low", "dyn_levels", "cum_pv", "cum_v", "vwap", "scaled_out",
    )

    def __init__(self) -> None:
        self.trade_day: str | None = None       # ET date this state belongs to
        self.trades_today: int = 0
        self.stopped_today: bool = False        # hard stop fired today → range broken
        self.pending: str | None = None         # in-flight order: "entry" | "exit" | None
        self.invalid_logged_day: str | None = None
        self.scaled_out: bool = False           # H3: the partial profit-take has fired today
        # opening_range mode: today's range, built from the first N minutes then frozen.
        self.or_high: float | None = None
        self.or_low: float | None = None
        self.dyn_levels: tuple[float, float, float] | None = None
        # session VWAP accumulators (for the optional vwap_gate_pct filter).
        self.cum_pv: float = 0.0
        self.cum_v: float = 0.0
        self.vwap: float | None = None

    def roll_day(self, day_key: str) -> None:
        """Reset for a new ET day (DAY orders expired at the prior close; the opening
        range and VWAP rebuild from scratch)."""
        self.trade_day = day_key
        self.trades_today = 0
        self.stopped_today = False
        self.pending = None
        self.scaled_out = False
        self.or_high = None
        self.or_low = None
        self.dyn_levels = None
        self.cum_pv = 0.0
        self.cum_v = 0.0
        self.vwap = None


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
        # Support ZONE (design doc §8.2a): buy anywhere in the lowest `entry_zone_pct` of the
        # day's range — entry .. entry + pct×(exit−entry) — not only an exact touch of `entry`.
        # 0.0 (default) = exact-low behavior, so live behavior is UNCHANGED until set.
        "entry_zone_pct": 0.0,
        # ATR-scaled support zone (§8.2b / design Suggestion 2): size the zone to the symbol's
        # daily volatility instead of the day's range — ceiling = entry + mult×atr20_pct×entry.
        # Widens for high-ATR names, narrows for calm ones; robust across symbols. Takes
        # precedence over entry_zone_pct when both `entry_zone_atr_mult` and `atr20_pct` > 0.
        "entry_zone_atr_mult": 0.0,
        # Symbol's 20-day ATR as a fraction of price (prefilled from Range Insight on apply);
        # the per-symbol normalizer the ATR-scaled zone multiplies. 0.0 = unknown → ATR zone off.
        "atr20_pct": 0.0,
        # VWAP confirmation gate (§8.2c): skip a fade-support entry when price is more than
        # this fraction below session VWAP (a strong downtrend). 0.0 = gate off (default).
        "vwap_gate_pct": 0.0,
        "entry_price": 0.0,  # buy when price <= this (near support) — fixed mode
        "exit_price": 0.0,  # sell when price >= this (near resistance) — fixed mode
        "stop_price": 0.0,  # hard stop (below support) — fixed mode
        "risk_per_trade_pct": 0.01,
        # Per-position notional cap (design §"Risk Management"): with a multi-symbol universe,
        # spread a fixed strategy budget across independent positions — e.g. $4,000 each so 5
        # candidates fit a $20,000 sleeve. 0 (default) = no per-position cap (sizing uses only
        # risk_per_trade_pct + max_position_qty, the single-symbol behavior).
        "per_position_budget": 0.0,
        "initial_equity_estimate": 100_000,
        "max_position_qty": 100,
        "max_trades_per_day": 4,
        "no_trade_open_minutes": 5,
        "hard_exit_before_close_minutes": 5,
        # Scale-out partial exit (H3 exit research): take partial profit at a nearer target and
        # let the remainder run to resistance, instead of one all-or-nothing exit.
        # scale_out_pct = fraction of the position sold at the first target (0 = off, default →
        # single full exit, UNCHANGED). scale_out_target_pct = where that target sits as a
        # fraction from entry to exit (0.5 = midpoint of the range).
        "scale_out_pct": 0.0,
        "scale_out_target_pct": 0.5,
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
        "entry_zone_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.0,
            "description": "Support-zone width: buy anywhere in the lowest this-fraction of "
            "the range (entry … entry + pct×(exit−entry)). 0 = exact-low touch.",
        },
        "entry_zone_atr_mult": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "ATR-scaled support-zone width: buy from support up to "
            "entry + this × atr20_pct × entry (clamped to resistance). Takes precedence "
            "over entry_zone_pct. 0 = off.",
        },
        "atr20_pct": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "Symbol's 20-day ATR as a fraction of price (prefilled from Range "
            "Insight). The per-symbol normalizer for entry_zone_atr_mult. 0 = unknown.",
        },
        "vwap_gate_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.0,
            "description": "VWAP gate: skip an entry when price is more than this fraction "
            "below session VWAP (avoids fading a strong downtrend). 0 = gate off.",
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
        "per_position_budget": {
            "type": "number",
            "min": 0,
            "default": 0.0,
            "description": "Per-symbol notional cap ($). Spreads a fixed budget across a "
            "multi-symbol universe (e.g. 4000 → ~$4k/position). 0 = no per-position cap.",
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
        "scale_out_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.0,
            "description": "Scale-out: fraction of the position sold at the first profit target "
            "(the rest runs to resistance). 0 = off (single full exit).",
        },
        "scale_out_target_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.5,
            "description": "Scale-out target as a fraction from entry to exit (0.5 = midpoint). "
            "Only used when scale_out_pct > 0.",
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(
            str(self.params.get("initial_equity_estimate", 100_000))
        )
        # Per-symbol, per-day state — one _SymState per candidate the engine feeds us.
        # Multi-symbol safe: each symbol's opening range / VWAP / stop-out halt / trade
        # counter / in-flight flag are independent and never collide across the universe
        # (design §"Top 3–5 candidates"). Equity (sizing) is strategy-level (shared).
        self._sym: dict[str, _SymState] = {}

    async def on_bar(self, bar: Any) -> None:
        p = self.params
        price = float(bar.c)
        symbol = bar.symbol
        # This symbol's independent state (created on first sight of the symbol).
        st = self._sym.get(symbol)
        if st is None:
            st = self._sym[symbol] = _SymState()

        bar_et = bar.t.astimezone(_us_eastern())
        tod = bar_et.time()
        day_key = bar_et.date().isoformat()
        if st.trade_day != day_key:
            # New ET day for this symbol: reset its opening range, VWAP, counters and
            # in-flight flag (DAY orders expired at the prior close).
            st.roll_day(day_key)
            # Phase 0B funnel: this (symbol, ET-day) is now in the evaluated universe.
            self.ctx.record_opportunity(symbol, "universe", day_key)
            # Refresh the (strategy-level) sizing equity from the LIVE account balance,
            # falling back to the configured estimate when no broker snapshot exists yet.
            equity = await self.ctx.get_account_equity()
            if equity is not None and equity > 0:
                self._equity_estimate = equity

        # Update this symbol's session VWAP every bar (consulted only by vwap_gate_pct).
        typical = (float(bar.h) + float(bar.l) + float(bar.c)) / 3.0
        vol = float(bar.v) or 1.0
        st.cum_pv += typical * vol
        st.cum_v += vol
        st.vwap = st.cum_pv / st.cum_v if st.cum_v else None

        # Resolve this symbol's levels: fixed (params) or dynamic opening-range. In
        # opening_range mode this also accumulates the symbol's range while it forms.
        entry, exit_, stop = self._resolve_levels(p, bar, tod, st)
        if entry > 0:
            # Phase 0B funnel: OR levels resolved (qualified); price at/below support = touched.
            self.ctx.record_opportunity(symbol, "qualified", day_key)
            if price <= entry:
                self.ctx.record_opportunity(symbol, "touched", day_key)

        position = await self.ctx.get_position_for(symbol)
        in_long = (
            position is not None
            and getattr(position, "side", None) == "long"
            and position.qty > 0
        )

        # ---- reconcile pending flag against actual position state ----
        # Belt-and-braces alongside on_fill: if the position already reflects
        # the in-flight order, the fill landed and the flag is stale.
        if (st.pending == "exit" and not in_long) or (st.pending == "entry" and in_long):
            st.pending = None
        pend = st.pending

        # ---- hard exit near the close ----
        close_cutoff = _shift(SESSION_CLOSE, -int(p.get("hard_exit_before_close_minutes", 5)))
        if tod >= close_cutoff:
            # short-circuit: only submit when not already exiting (combined to
            # avoid a nested if; the submit's side effect runs only if accepted).
            if in_long and pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="time_exit"
            ):
                st.pending = "exit"
            return

        # ---- stop loss ----
        if in_long and stop > 0 and price <= stop:
            st.stopped_today = True  # range broken — halt entries for the day
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="stop_loss"
            ):
                st.pending = "exit"
            return

        # ---- exit at resistance ----
        if in_long and exit_ > 0 and price >= exit_:
            if pend != "exit" and await self._submit(
                symbol, OrderSide.SELL, position.qty, reason="range_exit"
            ):
                st.pending = "exit"
            return

        # ---- scale-out partial exit (H3 exit research) ----
        # Take partial profit at a nearer target (between entry and resistance), letting the
        # remainder run to the full exit above. Fires at most once per symbol per day. Price is
        # strictly below `exit_` here (the full exit already returned), so the partial only ever
        # lands in the [target, exit_) band. Off by default (scale_out_pct = 0).
        scale_pct = float(p.get("scale_out_pct", 0.0))
        if (
            in_long
            and not st.scaled_out
            and pend != "exit"
            and 0.0 < scale_pct < 1.0
            and exit_ > entry > 0
        ):
            target = entry + float(p.get("scale_out_target_pct", 0.5)) * (exit_ - entry)
            if price >= target:
                partial = int(float(position.qty) * scale_pct)
                if partial > 0 and await self._submit(
                    symbol, OrderSide.SELL, Decimal(partial), reason="scale_out"
                ):
                    st.scaled_out = True  # don't re-trim the same leg; remainder runs to exit
                return

        # ---- no-trade window after the open ----
        open_cutoff = _shift(SESSION_OPEN, int(p.get("no_trade_open_minutes", 5)))
        if tod < open_cutoff:
            return

        # ---- entry near support (fade the range) ----
        if in_long or pend is not None:
            return
        if entry <= 0:
            return
        # Support ZONE — buy anywhere from `entry` up to a ceiling above support, not only an
        # exact touch. Two ways to size the zone (ATR-scaled takes precedence, design §8.2):
        #   • §8.2b ATR-scaled (cross-symbol robust): ceiling = entry + mult × atr20_pct × entry,
        #     so the band widens for high-ATR names and narrows for calm ones, independent of the
        #     day's range. Needs both `entry_zone_atr_mult` and `atr20_pct` (> 0).
        #   • §8.2a range-fraction (fallback): ceiling = entry + entry_zone_pct × (exit − entry).
        # At 0/0/0 the ceiling is exactly `entry`, reproducing the exact-low touch byte-for-byte.
        zone_atr_mult = float(p.get("entry_zone_atr_mult", 0.0))
        atr20_pct = float(p.get("atr20_pct", 0.0))
        zone_pct = float(p.get("entry_zone_pct", 0.0))
        buy_ceiling = entry
        if zone_atr_mult > 0.0 and atr20_pct > 0.0:
            buy_ceiling = entry + zone_atr_mult * atr20_pct * entry
        elif 0.0 < zone_pct <= 1.0 and exit_ > entry:
            buy_ceiling = entry + zone_pct * (exit_ - entry)
        # Never fade above resistance: clamp the ceiling to `exit_` when it's a valid level.
        if exit_ > entry:
            buy_ceiling = min(buy_ceiling, exit_)
        if price > buy_ceiling:
            return
        # Optional VWAP confirmation gate (design §8.2c): don't fade support when price is
        # far below session VWAP (a strong downtrend = catching a falling knife). 0.0 = off.
        vwap_gate = float(p.get("vwap_gate_pct", 0.0))
        if vwap_gate > 0.0 and st.vwap is not None and price < st.vwap * (1.0 - vwap_gate):
            return
        if not _levels_ok(entry=entry, exit_=exit_, stop=stop):
            await self._log_invalid_levels(
                symbol, day_key, st, entry=entry, exit_=exit_, stop=stop
            )
            return
        if st.stopped_today:
            return  # stopped out earlier today — do not re-enter a broken range
        if stop > 0 and price <= stop:
            st.stopped_today = True  # price already through the stop: range broken
            return
        if st.trades_today >= int(p.get("max_trades_per_day", 4)):
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
                st.trades_today += 1
                st.pending = "entry"

    async def on_fill(self, fill: Any) -> None:
        # Fix #2: clear the in-flight flag once the order fills. The on_bar
        # reconciliation covers any fills this misses. FillEvent.symbol is the
        # framework's confirmed attribute (app/strategies/context.py).
        sym = getattr(fill, "symbol", None)
        if sym:
            st = self._sym.get(sym)
            if st is not None:
                st.pending = None

    # ---- helpers ----

    def _resolve_levels(
        self, p: dict[str, Any], bar: Any, tod: time, st: _SymState
    ) -> tuple[float, float, float]:
        """Return this symbol's ``(entry, exit, stop)`` for today.

        ``fixed`` mode → the configured params (legacy behavior). ``opening_range``
        mode → derived from this symbol's first ``opening_range_minutes`` of price action:
        entry = range low (fade/buy support), exit = range high (sell resistance),
        stop = range_low × (1 − ``stop_buffer_pct``). Returns zeros while the range
        is still forming (so the existing ``entry <= 0`` gate blocks entries), and
        accumulates the range into ``st`` as a side effect during that window."""
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
            st.or_high = bar.h if st.or_high is None else max(st.or_high, bar.h)
            st.or_low = bar.l if st.or_low is None else min(st.or_low, bar.l)
            return (0.0, 0.0, 0.0)  # range still forming — no levels yet
        if (
            st.dyn_levels is None
            and st.or_high is not None
            and st.or_low is not None
            and st.or_high > st.or_low
        ):
            buf = float(p.get("stop_buffer_pct", 0.005))
            st.dyn_levels = (
                round(st.or_low, 4),
                round(st.or_high, 4),
                round(st.or_low * (1 - buf), 4),
            )
        return st.dyn_levels or (0.0, 0.0, 0.0)

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
        qty = min(raw, float(self.params.get("max_position_qty", 100)))
        # Per-position notional cap (multi-symbol budget allocation): keep each symbol's
        # position within ``per_position_budget`` dollars so a fixed sleeve spreads across
        # the candidate universe. 0 = no cap (single-symbol behavior preserved).
        budget = float(self.params.get("per_position_budget", 0.0))
        if budget > 0.0 and entry > 0.0:
            qty = min(qty, budget / entry)
        return int(qty)

    async def _log_invalid_levels(
        self, symbol: str, day_key: str, st: _SymState, *, entry: float, exit_: float, stop: float
    ) -> None:
        """Surface invalid level ordering once per ET day (per symbol) instead of failing
        silently (fix #4)."""
        if st.invalid_logged_day == day_key:
            return
        st.invalid_logged_day = day_key
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
