"""Sector rotation portfolio (P12 §4) — paper-only sector factor book.

A REGULAR deterministic Strategy file implementing sector-momentum (12-month cross-sectional
relative strength at the sector level), rebalanced weekly. It reaches factor data ONLY through
``ctx.factors`` (the sandboxed read-only accessor) and submits every rebalance order through
``ctx.submit_order`` → OrderRouter + risk engine (ADR 0002). No broker / DB / network access;
no LLM (ADR 0006 v2). No parameter tuning from research (K=3, 12-month lookback are frozen).

SEC-001 verdict: **Diversifier (B)** — Sharpe 0.51, DD −64.8%, corr 0.38 with momentum.
No standalone edge (V1 H1 +0.16, CI [−0.03, 0.366]); construction archived; research frozen.

Methodology: Rank sectors by 12-month momentum; hold top-K strongest sectors as sector-neutral
equal-weight baskets (each sector gets a 1/K sleeve; within a sleeve, equal-weight across names).
This setup directly from SEC-001 V2 research (`apps/backend/scripts/sector_rotation_v2_research.py`),
which proved that (1) sector construction is the correct structural choice and (2) construction
was NOT the binding constraint on edge (H3 result).

Weekly rebalance: Monday 14:00 UTC ≈ 09:00 ET (matching Momentum portfolio cadence). Market-regime
filter + optional vol-scaling overlay inherited from MOM-001 discipline. Every sell precedes buys
(capital flow efficiency). Turnover damping via rank hysteresis + threshold.

**P12 §4 governance note:** This is a Methodology Transfer demonstration. SEC-001 promotion
proves that Evidence Engineering governance and operational architecture are REPEATABLE
across multiple strategies — not a one-off achievement. Success is operational correctness
(no crashes, clean rebalances, expected positions, proper risk gating), not P&L targets
(per ADR 0014; 4 weeks is too short for evidence).
"""

from __future__ import annotations

import asyncio
import math
from collections import defaultdict
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


class SectorRotation(Strategy):
    name: ClassVar[str] = "sector-rotation"
    version: ClassVar[str] = "1.0.0"  # research-frozen SEC-001 V2, first operational deployment
    symbols: ClassVar[list[str]] = []  # set at registration (same 201 as Momentum: top-200 + SPY)
    # Weekly, Monday 14:00 UTC ≈ 09:00 ET. Day names avoid APScheduler's off-by-one.
    schedule: ClassVar[str] = "0 14 * * mon"

    default_params: ClassVar[dict[str, Any]] = {
        # SEC-001 research-frozen parameters (V2 headline; all from sector_rotation_v2_research.py)
        "sector_momentum_lookback_days": 252,  # 12-month, matching Momentum 252/0
        "sector_momentum_skip_days": 0,        # no skip (matching Momentum)
        "top_k_sectors": 3,                    # frozen from V2 research; {2,4} are robustness band
        # Governance & risk (inherited from Momentum discipline)
        "use_market_regime_filter": True,      # risk-off to cash in downtrends
        "market_filter_symbol": "SPY",         # market proxy (must be in symbols)
        "market_ma_days": 200,                 # MA window for regime filter
        "max_position_pct": 0.10,              # hard cap on any single position
        "fractional_shares": True,             # fractional deploys ~fully; whole shares under-deploy
        "cash_buffer_pct": 0.02,               # hold 2% cash
        "initial_equity_estimate": 100_000,    # fallback when live equity unavailable
        "pricing_timeframe": "1Day",           # price by daily close (not intraday bar)
        "timeframe": "1Day",                   # engine dispatch bar timeframe
        "order_pacing_seconds": 1.0,           # spread rebalance orders under rate cap
        "min_trade_pct": 0.03,                 # skip tiny adjustments to existing positions
        # Portfolio-level EWMA-vol targeting (default OFF to prove the core signal in
        # isolation). When on, gross exposure scales down in high-vol regimes (no
        # leverage; fails open). The daily-overlay machinery from Momentum is
        # deliberately NOT carried here — it is out of scope for v1.0 (the session doc
        # defers it post-validation), so the param surface stays in sync with behavior.
        "use_vol_scaling": False,
        "vol_target_annual": 0.15,
        "vol_ewma_span": 20,
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "sector_momentum_lookback_days": {
            "type": "integer", "min": 1, "default": 252,
            "description": "Sector momentum lookback (trading days). 252 = 12-month; frozen from research."
        },
        "sector_momentum_skip_days": {
            "type": "integer", "min": 0, "default": 0,
            "description": "Trading days skipped before lookback. 0 = 12m total return; frozen from research."
        },
        "top_k_sectors": {
            "type": "integer", "min": 1, "max": 11, "default": 3,
            "description": "Number of top sectors to hold (equal-weight baskets). 3 = research frozen; {2,4} = robustness band."
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
            "type": "boolean", "default": True,
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
        self._last_rebalance_week: tuple[int, int] | None = None  # backtest cadence
        self._last_dispatch_seq: int | None = None  # live cadence: one rebalance per dispatch

    async def on_bar(self, bar: Any) -> None:
        """The engine calls this ONCE PER SYMBOL on every cron tick (200+ calls per slot), so
        the first thing on_bar must do is decide whether this tick's rebalance already ran.

        Live: key on the DISPATCH (``ctx.dispatch_seq``), not on the bar. The cron schedule
        already IS the weekly cadence, and a bar-derived key is unsafe here: each call carries
        that symbol's own latest bar, and symbols routinely disagree on how recent it is (a
        stale cached month-bucket, a thin ETF that has not printed yet). Friday is ISO week 28
        and Monday is week 29, so ONE lagging symbol flips a week-keyed guard back and re-runs
        the whole rebalance against stale holdings. That fired the combined book 5x in a single
        slot on 2026-07-13: it double-bought and then double-sold the same names.

        Backtest: there is no engine dispatch (``dispatch_seq is None``) and bars are replayed
        one at a time, so the bar's ISO week IS the correct cadence signal. Keep it there.
        """
        seq = getattr(self.ctx, "dispatch_seq", None)
        if isinstance(seq, int):  # a real engine dispatch id; absent in backtests
            if seq == self._last_dispatch_seq:
                return  # already offered this dispatch; ignore the other N-1 symbol ticks
            self._last_dispatch_seq = seq
        else:
            wk = bar.t.isocalendar()[:2]
            if wk == self._last_rebalance_week:
                return
            self._last_rebalance_week = wk
        try:
            await self._rebalance()
        except Exception as exc:  # noqa: BLE001 - contain user-path failures
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "rebalance_failed", "error": str(exc)[:160]},
            )

    # ---- rebalance ----

    async def _rebalance(self) -> None:
        """Compute the target sector baskets and trade the diff toward them."""
        if self.params.get("use_market_regime_filter", True):
            below = await self._market_below_ma()
            if below is True:
                await self._apply_targets([], reason="regime_bear_cash")
                return

        try:
            n = len(self.ctx.symbols) or None
            mom_kw = {
                "lookback_days": int(self.params.get("sector_momentum_lookback_days", 252)),
                "skip_days": int(self.params.get("sector_momentum_skip_days", 0)),
            }
            scores = (self.ctx.factors.momentum_scores(n=n, **mom_kw) if n
                      else self.ctx.factors.momentum_scores(**mom_kw))
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
        """Top-K strongest sectors, each held as a full equal-weight basket.

        Reproduces the SEC-001 V2 construction (``basket_weights`` in
        ``scripts/sector_rotation_v2_research.py``): rank sectors by the average
        12-month momentum of their names, take the top-K, and hold *every* name in
        each chosen sector. The downstream equal-weight sizing in ``_apply_targets``
        gives each name ≈ (1/K)·(1/n_sector) of the book — the sector-neutral
        baskets that earned the verdict. Excludes the market proxy (SPY).

        No per-sector name cap or pruning is applied: that is a construction change
        from the validated research, and this deployment runs the validated strategy
        unchanged (the Methodology-Transfer discipline — no parameter tuning)."""
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        allowed = {s.upper() for s in self.ctx.symbols if s.upper() != market_sym}
        eligible = scores[scores.index.isin(allowed)]
        if eligible.empty:
            return []

        try:
            sectors = self.ctx.factors.sectors(list(eligible.index))
        except Exception:  # noqa: BLE001 — no sector data → can't build baskets → HOLD
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "sector_data_unavailable_hold"},
            )
            return []

        # Group eligible names by sector, carrying each name's momentum score.
        by_sector: dict[str, list[tuple[str, float]]] = defaultdict(list)
        for ticker in eligible.index:
            sector = sectors.get(ticker)
            if sector is not None:  # unknown-sector names can't be placed in a basket
                by_sector[sector].append((str(ticker), float(eligible.loc[ticker, "score"])))
        if not by_sector:
            return []

        # Rank sectors by mean momentum, strong → weak; take the top-K.
        sector_mom = {s: sum(m for _, m in names) / len(names) for s, names in by_sector.items()}
        ranked_sectors = sorted(sector_mom, key=lambda s: sector_mom[s], reverse=True)
        k = int(self.params.get("top_k_sectors", 3))
        selected_sectors = ranked_sectors[:k]

        # Hold every name in each chosen sector (the full basket, V2 construction).
        target: list[str] = []
        for sector in selected_sectors:
            target.extend(ticker for ticker, _ in by_sector[sector])
        return target

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

        fractional = bool(self.params.get("fractional_shares", True))
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
