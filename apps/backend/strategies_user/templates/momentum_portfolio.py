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
  Stock Selection top quintile by 6-1 month momentum z-score, within a fixed
                  top-N liquidity candidate universe (`symbols`)
  Entry/Exit     weekly rebalance — enter the target quintile, exit names that
                  fall out of it (no per-name price target / stop)
  Position Sizing equal target notional = equity / k, whole shares, market orders
  Bail-Out       on FactorDataUnavailable → HOLD (never trade blind); the
                  centralized risk engine (caps / circuit breaker) is the halt

Rebalance cadence: the engine fires `on_bar` per symbol on the cron `schedule`
tick; this strategy rebalances ONCE per ISO week (on the first call of a new
week) and no-ops the rest — the framework has no portfolio/rebalance hook (§4 §3.1).
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
# crash the rebalance tick (P9 §3/§4 review, Finding 1).
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class MomentumPortfolio(Strategy):
    name: ClassVar[str] = "momentum-portfolio"
    version: ClassVar[str] = "0.1.0"
    symbols: ClassVar[list[str]] = []  # set at registration = top-200 liquidity candidates (§4 §3.3)
    schedule: ClassVar[str] = "0 14 * * 1"  # weekly, Mon 14:00 UTC ≈ 09:00 ET (§4 §3.2)

    default_params: ClassVar[dict[str, Any]] = {
        "top_quantile": 0.20,  # hold the top 20% by momentum score…
        "max_names": 10,  # …capped at this many names
        "min_score": None,  # optional z-score floor (None = no floor)
        "pricing_timeframe": "1Hour",  # bar timeframe used to price names for sizing
        "initial_equity_estimate": 100_000,  # equity used for equal-weight sizing
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "top_quantile": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.20,
            "description": "Hold the top fraction of the universe by momentum score.",
        },
        "max_names": {
            "type": "integer",
            "min": 1,
            "default": 10,
            "description": "Hard cap on the number of names held.",
        },
        "min_score": {
            "type": "number",
            "nullable": True,
            "default": None,
            "description": "Optional z-score floor; names below it are not held. Empty/None = no floor.",
        },
        "pricing_timeframe": {
            "type": "enum",
            "choices": ["5Min", "15Min", "1Hour", "1Day"],
            "default": "1Hour",
            "description": "Bar timeframe used to price names for equal-weight sizing.",
        },
        "initial_equity_estimate": {
            "type": "number",
            "min": 0,
            "default": 100_000,
            "description": "Equity estimate used for equal-weight position sizing.",
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(
            str(self.params.get("initial_equity_estimate", 100_000))
        )
        # (ISO year, ISO week) of the last rebalance — guards rebalance-once-per-week.
        self._last_rebalance_week: tuple[int, int] | None = None

    async def on_bar(self, bar: Any) -> None:
        wk = bar.t.isocalendar()[:2]  # (iso_year, iso_week)
        if wk == self._last_rebalance_week:
            return  # already rebalanced this week; ignore the per-symbol tick calls
        self._last_rebalance_week = wk
        await self._rebalance()

    # ---- rebalance ----

    async def _rebalance(self) -> None:
        """Compute the target top-quintile book and trade the diff toward it."""
        try:
            # Standardize z-scores over the registered candidate universe (not the
            # accessor's broad n=500 default), so the quintile cut and the z-scores
            # share one cross-section (P9 §3/§4 review, Finding 2).
            n = len(self.ctx.symbols) or None
            scores = self.ctx.factors.momentum_scores(n=n) if n else self.ctx.factors.momentum_scores()
        except _HOLD_ON as exc:  # not provisioned / thin / below floor → HOLD (Finding 1)
            # Bail-out row of the MTG spec: never trade blind. Hold the book.
            await self.ctx.log_signal(
                self.ctx.symbols[0] if self.ctx.symbols else "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return

        target = self._select_targets(scores)
        held = await self._current_holdings()

        # Exits: held names no longer in the target book → sell to flat.
        for sym, qty in held.items():
            if sym not in target:
                await self._submit(sym, OrderSide.SELL, qty, reason="rebalance_exit")

        # Entries / adjustments: move each target name toward equity/k notional.
        k = len(target)
        if k == 0:
            return
        per_name = self._equity_estimate / Decimal(k)
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(
                    sym, SignalType.ENTRY,
                    payload={"reason": "rebalance_skip_no_price"},
                )
                continue
            target_qty = int(math.floor(float(per_name) / price))
            cur = int(held.get(sym, Decimal(0)))
            delta = target_qty - cur
            if delta > 0:
                await self._submit(sym, OrderSide.BUY, Decimal(delta), reason="rebalance_entry",
                                   payload={"price": price, "target_qty": target_qty})
            elif delta < 0:
                await self._submit(sym, OrderSide.SELL, Decimal(-delta), reason="rebalance_trim",
                                   payload={"price": price, "target_qty": target_qty})

    def _select_targets(self, scores: Any) -> list[str]:
        """Top-quintile tickers within this strategy's candidate universe.

        `scores` is the §2 momentum_scores frame (indexed by ticker, sorted by
        `score` desc). We can only trade names in `self.ctx.symbols` (the
        registered allowed-list StrategyContext enforces), so select the top
        quintile *within* it.
        """
        allowed = {s.upper() for s in self.ctx.symbols}
        eligible = scores[scores.index.isin(allowed)]
        floor = self.params.get("min_score")
        if floor is not None and floor != "":
            eligible = eligible[eligible["score"] >= float(floor)]
        if eligible.empty:
            return []
        q = float(self.params.get("top_quantile", 0.20))
        cap = int(self.params.get("max_names", 10))
        k = min(cap, max(1, math.ceil(len(eligible) * q)))
        # eligible is already sorted by score desc (engine guarantees it).
        return list(eligible.index[:k])

    async def _current_holdings(self) -> dict[str, Decimal]:
        """Long quantities currently held, keyed by ticker, over the candidate set."""
        held: dict[str, Decimal] = {}
        for sym in self.ctx.symbols:
            pos = await self.ctx.get_position_for(sym)
            qty = getattr(pos, "qty", None) if pos is not None else None
            if qty is not None and Decimal(qty) > 0 and getattr(pos, "side", "long") == "long":
                held[sym.upper()] = Decimal(qty)
        return held

    async def _price(self, symbol: str) -> float | None:
        """Latest close for sizing, from the pricing timeframe; None if unavailable."""
        tf = str(self.params.get("pricing_timeframe", "1Hour"))
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
        if rejection:
            log_payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig, payload=log_payload)
        return result is not None and not rejection
