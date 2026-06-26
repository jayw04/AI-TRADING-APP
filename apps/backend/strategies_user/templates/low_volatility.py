"""Low-volatility portfolio (LOW-001 promotion) — paper-only defensive factor book.

A REGULAR deterministic Strategy file implementing the low-volatility anomaly: hold the
lowest-realized-volatility names, rebalanced weekly. It reaches factor data ONLY through
``ctx.factors`` (the sandboxed read-only accessor) and submits every rebalance order through
``ctx.submit_order`` → OrderRouter + risk engine (ADR 0002). No broker / DB / network access;
no LLM (ADR 0006 v2). No parameter tuning from research (252-day vol window, top-quintile are
frozen).

LOW-001 verdict: **Diversifier / Defensive (B)** — Sharpe 0.59 (vs MOM 0.39), maxDD −39.0%
(vs MOM −76.4%), corr −0.153 with momentum. No standalone edge (H1 ΔSharpe +0.24, CI
[−0.029, 0.53] spans zero); but the signature low-vol downside protection holds (shallower
drawdown than equal-weight in 5/5 walk-forward windows, H3). Construction frozen; research
complete (full-cycle survivorship-free 2000–2026 — the proper test that reverses the narrow
2016–2026 mega-cap negative of PR #142).

Methodology: score each name by −(trailing 252-day realized volatility); hold the top-quintile
(lowest-vol 20%), equal-weight. Identical top-quantile-equal-weight harness as Momentum and the
factor-agnostic backtest — only the *score* changes (the clean A/B the research used). Directly
from the validated LOW-001 V1 research (``apps/backend/scripts/low_vol_research.py`` ::
``low_vol_score``).

Low Volatility ≠ Volatility Targeting: this changes **stock selection** (which names to hold);
the vol-scaling overlay changes **position sizing** (how much). They are complementary — one can
run a low-vol *selection* and *also* vol-target its exposure. The overlay here is OFF by default
so the selection signal is proven in isolation.

Weekly rebalance: Monday 14:00 UTC ≈ 09:00 ET (matching Momentum / Sector cadence). Market-regime
filter + optional vol-scaling overlay inherited from MOM-001 discipline. Every sell precedes buys
(capital flow efficiency). Turnover damping via a trade threshold.

**Phase 2 governance note:** This is a Methodology Transfer demonstration (after SEC-001). LOW-001
promotion proves Evidence Engineering governance + operational architecture are REPEATABLE across
*multiple* strategies — not a one-off. Success is operational correctness (no crashes, clean
rebalances, expected positions, proper risk gating, corr direction holds), not P&L targets
(per ADR 0014; 4 weeks is too short for evidence).
"""

from __future__ import annotations

import asyncio
import math
from decimal import Decimal
from typing import Any, ClassVar

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.risk import OrderRequest
from app.strategies import Strategy

# The three "no factor data this week" signals → HOLD the book, not crash
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class LowVolatility(Strategy):
    name: ClassVar[str] = "low-volatility"
    version: ClassVar[str] = "1.0.0"  # research-frozen LOW-001 V1, first operational deployment
    symbols: ClassVar[list[str]] = []  # set at registration (same 201 as Momentum: top-200 + SPY)
    # Weekly, Monday 14:00 UTC ≈ 09:00 ET. Day names avoid APScheduler's off-by-one.
    schedule: ClassVar[str] = "0 14 * * mon"

    default_params: ClassVar[dict[str, Any]] = {
        # LOW-001 research-frozen parameters (V1 headline; from low_vol_research.py)
        "vol_lookback_days": 252,   # 12-month trailing realized vol; frozen from research
        "top_quantile": 0.20,       # hold the lowest-vol quintile, equal-weight; frozen from research
        # Governance & risk (inherited from Momentum discipline)
        "use_market_regime_filter": True,      # risk-off to cash in downtrends
        "market_filter_symbol": "SPY",         # market proxy (must be in symbols)
        "market_ma_days": 200,                 # MA window for regime filter
        "max_position_pct": 0.10,              # hard cap on any single position
        "fractional_shares": False,            # size whole shares unless opted in
        "cash_buffer_pct": 0.02,               # hold 2% cash
        "initial_equity_estimate": 100_000,    # fallback when live equity unavailable
        "pricing_timeframe": "1Day",           # price by daily close (not intraday bar)
        "timeframe": "1Day",                   # engine dispatch bar timeframe
        "order_pacing_seconds": 1.0,           # spread rebalance orders under rate cap
        "min_trade_pct": 0.03,                 # skip tiny adjustments to existing positions
        # Portfolio-level EWMA-vol targeting (default OFF to prove the selection signal in
        # isolation — low-vol *selection* is distinct from vol-*targeting* sizing). When on,
        # gross exposure scales down in high-vol regimes (no leverage; fails open). The
        # daily-overlay machinery from Momentum is deliberately NOT carried here — out of
        # scope for v1.0 (the session doc defers it post-validation), so the param surface
        # stays in sync with behavior.
        "use_vol_scaling": False,
        "vol_target_annual": 0.15,
        "vol_ewma_span": 20,
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "vol_lookback_days": {
            "type": "integer", "min": 2, "default": 252,
            "description": "Trailing realized-volatility window (trading days). 252 = 12-month; frozen from research."
        },
        "top_quantile": {
            "type": "number", "min": 0.01, "max": 1.0, "default": 0.20,
            "description": "Fraction of the universe held (lowest-vol names, equal-weight). 0.20 = top-quintile; frozen from research."
        },
        "use_market_regime_filter": {
            "type": "boolean", "default": True,
            "description": "Move the book to cash when the market is below its MA."
        },
        "market_filter_symbol": {
            "type": "string", "default": "SPY",
            "description": "Market proxy for the regime filter (must be in registered symbols)."
        },
        "market_ma_days": {
            "type": "integer", "min": 20, "default": 200,
            "description": "Moving-average window (trading days) for the regime filter."
        },
        "max_position_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.10,
            "description": "Hard cap on any single position as a fraction of equity."
        },
        "fractional_shares": {
            "type": "boolean", "default": False,
            "description": "Size fractional share quantities (deploys ~fully vs whole-share rounding)."
        },
        "cash_buffer_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.02,
            "description": "Fraction of equity held back as cash."
        },
        "initial_equity_estimate": {
            "type": "number", "min": 0, "default": 100_000,
            "description": "Fallback equity estimate when no live account snapshot exists."
        },
        "pricing_timeframe": {
            "type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"], "default": "1Day",
            "description": "Bar timeframe used to price names for sizing."
        },
        "timeframe": {
            "type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"], "default": "1Day",
            "description": "Engine dispatch bar timeframe that fires the weekly on_bar tick."
        },
        "order_pacing_seconds": {
            "type": "number", "min": 0, "max": 60, "default": 1.0,
            "description": "Delay between rebalance order submissions (spreads the burst under order-rate cap)."
        },
        "min_trade_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.03,
            "description": "Skip adjustments to existing positions smaller than this fraction of target notional."
        },
        "use_vol_scaling": {
            "type": "boolean", "default": False,
            "description": "Scale gross exposure to a target volatility (inherited from Momentum; opt-in)."
        },
        "vol_target_annual": {
            "type": "number", "min": 0, "max": 2, "default": 0.15,
            "description": "Target annualized portfolio volatility when vol-scaling is enabled."
        },
        "vol_ewma_span": {
            "type": "integer", "min": 2, "default": 20,
            "description": "EWMA span (trading days) for market-proxy volatility estimate."
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        self._last_rebalance_week: tuple[int, int] | None = None

    async def on_bar(self, bar: Any) -> None:
        wk = bar.t.isocalendar()[:2]
        if wk == self._last_rebalance_week:
            return
        self._last_rebalance_week = wk
        try:
            await self._rebalance()
        except Exception as exc:
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "rebalance_failed", "error": str(exc)[:160]},
            )

    # ---- rebalance ----

    async def _rebalance(self) -> None:
        """Compute the lowest-vol target book and trade the diff toward it."""
        if self.params.get("use_market_regime_filter", True):
            below = await self._market_below_ma()
            if below is True:
                await self._apply_targets([], reason="regime_bear_cash")
                return

        try:
            n = len(self.ctx.symbols) or None
            lv_kw = {"lookback_days": int(self.params.get("vol_lookback_days", 252))}
            scores = (self.ctx.factors.low_vol_scores(n=n, **lv_kw) if n
                      else self.ctx.factors.low_vol_scores(**lv_kw))
        except _HOLD_ON as exc:
            await self.ctx.log_signal(
                self.ctx.symbols[0] if self.ctx.symbols else "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return

        held = await self._current_holdings()
        target = await self._select_targets(scores, held)
        await self._apply_targets(target, held=held, reason="rebalance")

    async def _select_targets(self, scores: Any, held: dict[str, Decimal]) -> list[str]:
        """Top-quintile lowest-volatility names, equal-weight.

        Reproduces the validated LOW-001 V1 selection (``run_momentum_backtest`` with
        ``score_fn=low_vol_score``, ``top_quantile=0.20``): rank the universe by
        −(trailing realized vol) — lowest vol first, already the order ``low_vol_scores``
        returns — and hold the top ``ceil(len(eligible) * top_quantile)`` names. The
        downstream equal-weight sizing in ``_apply_targets`` gives each name ≈ 1/k of the
        book. Excludes the market proxy (SPY).

        The held-count uses the same ``max(1, ceil(N · top_quantile))`` rule as the
        research harness (``backtest.py``); no extra pruning — that would be a
        construction change from the validated research (the Methodology-Transfer
        discipline forbids tuning)."""
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        allowed = {s.upper() for s in self.ctx.symbols if s.upper() != market_sym}
        eligible = scores[scores.index.isin(allowed)]
        if eligible.empty:
            return []

        # eligible is already sorted by score desc (lowest vol first) by low_vol_scores.
        q = float(self.params.get("top_quantile", 0.20))
        k = max(1, math.ceil(len(eligible) * q))
        return [str(t) for t in eligible.index[:k]]

    async def _apply_targets(
        self, target: list[str], *, held: dict[str, Decimal] | None = None, reason: str
    ) -> None:
        """Trade the diff from `held` toward the equal-weight `target` basket.

        Sells precede buys (capital flow efficiency). Rejection on any order is logged and continues."""
        if held is None:
            held = await self._current_holdings()
        target_set = set(target)

        for sym, qty in held.items():
            if sym not in target_set:
                await self._submit(sym, OrderSide.SELL, qty, reason=f"{reason}_exit")

        if not target:
            return

        equity = await self._investable_equity()
        k = len(target)
        per_name = min(equity / Decimal(k), equity * Decimal(str(self.params.get("max_position_pct", 0.10))))
        min_trade = Decimal(str(self.params.get("min_trade_pct", 0.03)))

        fractional = bool(self.params.get("fractional_shares", False))
        buys: list[tuple[str, Decimal, float, Decimal]] = []
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(sym, SignalType.ENTRY, payload={"reason": f"{reason}_skip_no_price"})
                continue
            price_d = Decimal(str(price))
            if fractional:
                target_qty = (per_name / price_d).quantize(Decimal("0.000001"))
            else:
                target_qty = Decimal(math.floor(per_name / price_d))
            cur = held.get(sym, Decimal(0))
            delta = target_qty - cur
            if delta == 0:
                continue
            if cur > 0 and abs(delta) * price_d < per_name * min_trade:
                continue
            if delta < 0:
                await self._submit(sym, OrderSide.SELL, -delta, reason=f"{reason}_trim",
                                   payload={"price": price, "target_qty": str(target_qty)})
            else:
                buys.append((sym, delta, price, target_qty))

        for sym, qty, price, target_qty in buys:
            await self._submit(sym, OrderSide.BUY, qty, reason=f"{reason}_entry",
                               payload={"price": price, "target_qty": str(target_qty)})

    async def _current_holdings(self) -> dict[str, Decimal]:
        """Long quantities currently held, excluding the market proxy."""
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
        """Live account equity minus cash buffer; falls back to estimate."""
        try:
            live = await self.ctx.get_account_equity()
        except Exception:
            live = None
        equity = Decimal(str(live)) if live is not None else self._equity_estimate
        buffer = Decimal(str(self.params.get("cash_buffer_pct", 0.02)))
        base = equity * (Decimal(1) - buffer)
        scale = await self._gross_scale()
        return base * Decimal(str(scale))

    async def _market_below_ma(self) -> bool | None:
        """True/False if the market proxy is below/above its MA; None if unavailable."""
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        days = int(self.params.get("market_ma_days", 200))
        bars = await self.ctx.get_recent_bars(sym, "1Day", n=days + 1)
        if bars is None or bars.empty or len(bars) < days + 1:
            await self.ctx.log_signal(
                sym, SignalType.EXIT,
                payload={"reason": "regime_filter_unavailable_failopen",
                         "have_bars": 0 if bars is None else int(len(bars)), "need": days + 1},
            )
            return None
        ma = float(bars["c"].iloc[:-1].mean())
        last = float(bars["c"].iloc[-1])
        return last < ma

    async def _gross_scale(self) -> float:
        """Portfolio gross-exposure multiplier from vol targeting; 1.0 if disabled or unavailable."""
        if not self.params.get("use_vol_scaling", False):
            return 1.0
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        span = int(self.params.get("vol_ewma_span", 20))
        target = float(self.params.get("vol_target_annual", 0.15))
        bars = await self.ctx.get_recent_bars(sym, "1Day", n=span * 3 + 1)
        if bars is None or bars.empty or len(bars) < span + 1:
            await self.ctx.log_signal(
                sym, SignalType.EXIT,
                payload={"reason": "vol_scaling_unavailable_failopen",
                         "have_bars": 0 if bars is None else int(len(bars)), "need": span + 1},
            )
            return 1.0
        rets = bars["c"].astype(float).pct_change().dropna()
        if rets.empty:
            return 1.0
        ewma_var = float(rets.ewm(span=span).var().iloc[-1])
        if not (ewma_var > 0):
            return 1.0
        realized_annual = math.sqrt(ewma_var) * math.sqrt(252.0)
        if realized_annual <= 0:
            return 1.0
        return min(1.0, target / realized_annual)

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
        """Dispatch one order through OrderRouter (ADR 0002) and log the outcome.

        The context stamps ``user_id`` / ``account_id`` / ``source_id`` (passed as 0
        / None here). Rejections are returned, not raised — they are logged as info
        signals so a rejected order doesn't take the rebalance down."""
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
            log_payload["submit_returned_none"] = True
        elif rejection:
            log_payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig, payload=log_payload)
        # Pace submissions so a multi-name rebalance burst stays under the
        # per-strategy rolling order-rate cap (a 0 value disables pacing).
        pacing = float(self.params.get("order_pacing_seconds", 0.0) or 0.0)
        if pacing > 0:
            await asyncio.sleep(pacing)
        return result is not None and not rejection
