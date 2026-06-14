"""Cross-sectional price-momentum portfolio (P9 §4) — paper-only factor book.

A REGULAR deterministic Strategy file expressing the §2/§3 momentum book as a
weekly, long-only, equal-weight top-quintile portfolio. It reaches factor data
ONLY through ``ctx.factors`` (the §2 sandboxed read-only accessor) and submits
every rebalance order through ``ctx.submit_order`` → OrderRouter + the risk engine
(ADR 0002). No broker / DB / network access; no LLM (ADR 0006 v2).

MTG strategy-spec lens (Docs/Strategies/Trading+Plan+Clean.pdf):
  Style          systematic, cross-sectional equity factor
  Type           long-only momentum book
  Holding Period ~1 week (held until the next weekly rebalance)
  Stock Selection top quintile by 6-1 month momentum z-score (≥ min_score floor),
                  within a fixed top-N liquidity candidate universe (`symbols`)
  Entry/Exit     weekly rebalance — enter the target quintile, exit names that
                  fall out of it (with a rank-hysteresis buffer to damp churn)
  Position Sizing equal target notional = investable_equity / k, capped at
                  max_position_pct, whole shares, market orders
  Stop Loss      none per-name (diversification + weekly turnover + risk engine)
  Bail-Out       no factor data → HOLD; bearish market regime (price < SPY 200d
                  MA) → risk-off to CASH; risk engine caps/breaker are the halt

Hardening (per the §4 strategy review):
  - rebalance week is marked DONE only after a rebalance completes (a crash
    retries next tick, not next week);
  - sizing uses LIVE account equity (ctx.get_account_equity), falling back to a
    configured estimate only when no snapshot exists;
  - a turnover threshold (min_trade_pct) + rank-hysteresis buffer suppress churn;
  - a market-regime filter (SPY vs its 200d MA) moves the book to cash in
    downtrends; it fails OPEN (trades, loudly logged) if the market series is
    unavailable — so a data gap can't silently halt the book;
  - daily closes price the book for sizing (a Monday-open intraday bar is
    incomplete);
  - scores are sorted defensively before the quintile cut.

Rebalance cadence: the engine fires `on_bar` per symbol on the cron `schedule`
tick; this strategy rebalances ONCE per ISO week (first call of a new week) and
no-ops the rest — the framework has no portfolio/rebalance hook (§4 §3.1).
"""

from __future__ import annotations

import math
from decimal import Decimal
from typing import Any, ClassVar

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.risk import OrderRequest
from app.strategies import Strategy

# The three "no factor data this week" signals (accessor not provisioned, thin
# cross-section, below the price floor) — any of them means HOLD the book, not
# crash the rebalance tick (§4 review, Finding 1).
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class MomentumPortfolio(Strategy):
    name: ClassVar[str] = "momentum-portfolio"
    version: ClassVar[str] = "0.3.0"  # §4 review hardening (rounds 1 + 2)
    # Set at registration = top-200 liquidity candidates (§4 §3.3). Include the
    # market_filter_symbol (SPY) here too, or the regime filter fails open.
    symbols: ClassVar[list[str]] = []
    schedule: ClassVar[str] = "0 14 * * 1"  # weekly, Mon 14:00 UTC ≈ 09:00 ET (§4 §3.2)

    default_params: ClassVar[dict[str, Any]] = {
        "top_quantile": 0.20,  # hold the top 20% by momentum score…
        "max_names": 10,  # …capped at this many names
        "min_score": 0.0,  # z-score floor — default 0 avoids buying negative momentum
        "min_trade_pct": 0.03,  # skip adjustments smaller than this fraction of target notional
        "rebalance_buffer_rank_pct": 0.05,  # keep a held name within (q + this) of the cut (hysteresis)
        "pricing_timeframe": "1Day",  # daily close for sizing (intraday open bar is incomplete)
        "use_market_regime_filter": True,  # risk-off to cash when the market is below its MA
        "market_filter_symbol": "SPY",  # must be in `symbols` for the filter to work
        "market_ma_days": 200,  # MA window for the regime filter
        "max_position_pct": 0.10,  # hard cap on any one name's weight
        "cash_buffer_pct": 0.02,  # keep this fraction in cash (deploy the rest)
        "initial_equity_estimate": 100_000,  # FALLBACK only when live equity is unavailable
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "top_quantile": {"type": "number", "min": 0, "max": 1, "default": 0.20,
                         "description": "Hold the top fraction of the universe by momentum score."},
        "max_names": {"type": "integer", "min": 1, "default": 10,
                      "description": "Hard cap on the number of names held."},
        "min_score": {"type": "number", "nullable": True, "default": 0.0,
                      "description": "z-score floor; names below it are not held. Empty/None = no floor."},
        "min_trade_pct": {"type": "number", "min": 0, "max": 1, "default": 0.03,
                          "description": "Skip rebalance adjustments smaller than this fraction of target notional."},
        "rebalance_buffer_rank_pct": {"type": "number", "min": 0, "max": 1, "default": 0.05,
                                      "description": "Keep a held name if still within (top_quantile + this) of the cut."},
        "pricing_timeframe": {"type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"],
                              "default": "1Day", "description": "Bar timeframe used to price names for sizing."},
        "use_market_regime_filter": {"type": "boolean", "default": True,
                                     "description": "Move the book to cash when the market is below its MA."},
        "market_filter_symbol": {"type": "string", "default": "SPY",
                                 "description": "Market proxy for the regime filter (must be in the registered symbols)."},
        "market_ma_days": {"type": "integer", "min": 20, "default": 200,
                           "description": "Moving-average window (trading days) for the regime filter."},
        "max_position_pct": {"type": "number", "min": 0, "max": 1, "default": 0.10,
                             "description": "Hard cap on any single position as a fraction of equity."},
        "cash_buffer_pct": {"type": "number", "min": 0, "max": 1, "default": 0.02,
                            "description": "Fraction of equity held back as cash."},
        "initial_equity_estimate": {"type": "number", "min": 0, "default": 100_000,
                                    "description": "Fallback equity estimate when no live account snapshot exists."},
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        # (ISO year, ISO week) of the last SUCCESSFUL rebalance — guards once/week.
        self._last_rebalance_week: tuple[int, int] | None = None

    async def on_bar(self, bar: Any) -> None:
        wk = bar.t.isocalendar()[:2]  # (iso_year, iso_week)
        if wk == self._last_rebalance_week:
            return  # already rebalanced this week; ignore the per-symbol tick calls
        try:
            await self._rebalance()
        except Exception as exc:  # noqa: BLE001 — an unexpected failure must retry, not skip the week
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "rebalance_failed", "error": str(exc)[:160]},
            )
            return  # do NOT mark the week → the next tick retries
        self._last_rebalance_week = wk  # mark DONE only on a completed rebalance (incl. deliberate holds)

    # ---- rebalance ----

    async def _rebalance(self) -> None:
        """Compute the target book and trade the diff toward it."""
        # 1. Market-regime gate: risk-off to cash in a downtrend.
        if self.params.get("use_market_regime_filter", True):
            below = await self._market_below_ma()  # None = unavailable → fail open (trade)
            if below is True:
                await self._apply_targets([], reason="regime_bear_cash")
                return

        # 2. Factor scores over the registered universe (Finding 2: standardize over
        #    the tradeable candidate set, not the accessor's broad n=500 default).
        try:
            n = len(self.ctx.symbols) or None
            scores = self.ctx.factors.momentum_scores(n=n) if n else self.ctx.factors.momentum_scores()
        except _HOLD_ON as exc:  # not provisioned / thin / below floor → HOLD (the bail-out row)
            await self.ctx.log_signal(
                self.ctx.symbols[0] if self.ctx.symbols else "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return

        held = await self._current_holdings()
        target = self._select_targets(scores, held)
        await self._apply_targets(target, held=held, reason="rebalance")

    async def _apply_targets(
        self, target: list[str], *, held: dict[str, Decimal] | None = None, reason: str
    ) -> None:
        """Trade the diff from `held` toward the equal-weight `target` book.

        Sells (exits + trims) are submitted BEFORE buys so capital is freed first
        (Finding 6); a rejection on any one order is log-and-continue."""
        if held is None:
            held = await self._current_holdings()
        target_set = set(target)

        # Exits: held names not in the target → sell to flat (never thresholded).
        for sym, qty in held.items():
            if sym not in target_set:
                await self._submit(sym, OrderSide.SELL, qty, reason=f"{reason}_exit")

        if not target:
            return

        equity = await self._investable_equity()
        k = len(target)
        per_name = min(equity / Decimal(k), equity * Decimal(str(self.params.get("max_position_pct", 0.10))))
        min_trade = Decimal(str(self.params.get("min_trade_pct", 0.03)))

        # First pass sells (trims) so they precede buys; collect buys, submit after.
        buys: list[tuple[str, Decimal, float, int]] = []
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(sym, SignalType.ENTRY, payload={"reason": f"{reason}_skip_no_price"})
                continue
            target_qty = int(math.floor(float(per_name) / price))
            cur = int(held.get(sym, Decimal(0)))
            delta = target_qty - cur
            if delta == 0:
                continue
            # Turnover threshold: skip adjustments to EXISTING positions that are
            # smaller than min_trade_pct of the target notional (new entries pass).
            if cur > 0 and abs(delta) * price < float(per_name) * float(min_trade):
                continue
            if delta < 0:
                await self._submit(sym, OrderSide.SELL, Decimal(-delta), reason=f"{reason}_trim",
                                   payload={"price": price, "target_qty": target_qty})
            else:
                buys.append((sym, Decimal(delta), price, target_qty))

        for sym, qty, price, target_qty in buys:
            await self._submit(sym, OrderSide.BUY, qty, reason=f"{reason}_entry",
                               payload={"price": price, "target_qty": target_qty})

    def _select_targets(self, scores: Any, held: dict[str, Decimal]) -> list[str]:
        """Top-quintile tickers within the candidate universe, with rank hysteresis.

        Selects the top `top_quantile` by score (≥ min_score, capped at max_names);
        additionally KEEPS a currently-held name if it is still within
        (top_quantile + rebalance_buffer_rank_pct) of the cut, to damp churn from
        names hovering at the boundary."""
        # Exclude the market proxy (SPY) — it may be registered ONLY so the regime
        # filter can read it; it must never be selected as a portfolio holding.
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        allowed = {s.upper() for s in self.ctx.symbols if s.upper() != market_sym}
        eligible = scores[scores.index.isin(allowed)]
        floor = self.params.get("min_score")
        if floor is not None and floor != "":
            eligible = eligible[eligible["score"] >= float(floor)]
        if eligible.empty:
            return []
        eligible = eligible.sort_values("score", ascending=False)  # defensive (Finding 6/sort)

        q = float(self.params.get("top_quantile", 0.20))
        cap = int(self.params.get("max_names", 10))
        buf = float(self.params.get("rebalance_buffer_rank_pct", 0.05))
        ranked = list(eligible.index)

        core_k = min(cap, max(1, math.ceil(len(ranked) * q)))
        core = ranked[:core_k]
        buf_k = min(len(ranked), max(core_k, math.ceil(len(ranked) * (q + buf))))
        buffer_zone = set(ranked[:buf_k])

        keep_held = [h for h in held if h in buffer_zone and h not in core]
        chosen = set(core) | set(keep_held)
        # Order by score, cap at max_names.
        return [t for t in ranked if t in chosen][:cap]

    async def _current_holdings(self) -> dict[str, Decimal]:
        """Long quantities currently held, keyed by ticker, over the candidate set.

        The market proxy is excluded — the strategy never manages a SPY position
        (it may exist only for the regime filter, or be held by another path)."""
        held: dict[str, Decimal] = {}
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        for sym in self.ctx.symbols:
            if sym.upper() == market_sym:
                continue
            pos = await self.ctx.get_position_for(sym)
            qty = getattr(pos, "qty", None) if pos is not None else None
            if qty is not None and Decimal(qty) > 0 and getattr(pos, "side", "long") == "long":
                held[sym.upper()] = Decimal(qty)
        return held

    async def _investable_equity(self) -> Decimal:
        """Live account equity (cache snapshot) minus the cash buffer; falls back to
        the configured estimate when no snapshot exists."""
        try:
            live = await self.ctx.get_account_equity()
        except Exception:  # noqa: BLE001 — any equity-read failure → fall back to the estimate, never block sizing
            live = None
        equity = Decimal(str(live)) if live is not None else self._equity_estimate
        buffer = Decimal(str(self.params.get("cash_buffer_pct", 0.02)))
        return equity * (Decimal(1) - buffer)

    async def _market_below_ma(self) -> bool | None:
        """True/False if the market proxy is below/above its MA; None if the series
        is unavailable (→ fail open: trade). The proxy must be in `ctx.symbols`."""
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        days = int(self.params.get("market_ma_days", 200))
        # Fetch days+1 bars: the MA is over the `days` COMPLETED bars (iloc[:-1]),
        # compared against the latest bar (iloc[-1]) — so the current/forming bar
        # never contaminates its own MA.
        bars = await self.ctx.get_recent_bars(sym, "1Day", n=days + 1)
        if bars is None or bars.empty or len(bars) < days + 1:
            await self.ctx.log_signal(
                sym, SignalType.EXIT,
                payload={"reason": "regime_filter_unavailable_failopen",
                         "have_bars": 0 if bars is None else int(len(bars)), "need": days + 1},
            )
            return None
        ma = float(bars["c"].iloc[:-1].mean())  # the `days` completed bars
        last = float(bars["c"].iloc[-1])        # the latest bar
        return last < ma

    async def _price(self, symbol: str) -> float | None:
        """Latest close for sizing, from the pricing timeframe; None if unavailable."""
        tf = str(self.params.get("pricing_timeframe", "1Day"))
        bars = await self.ctx.get_recent_bars(symbol, tf, n=1)
        if bars is None or bars.empty:
            return None
        return float(bars.iloc[-1]["c"])

    async def _submit(
        self, symbol: str, side: OrderSide, qty: Decimal, *, reason: str,
        payload: dict[str, Any] | None = None,
    ) -> bool:
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
        sig = SignalType.ENTRY if side == OrderSide.BUY else SignalType.EXIT
        log_payload: dict[str, Any] = {"reason": reason, **(payload or {})}
        rejection = getattr(result, "rejection_reason", None)
        if result is None:
            log_payload["submit_returned_none"] = True  # router gave no order back — surface it
        elif rejection:
            log_payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig, payload=log_payload)
        return result is not None and not rejection
