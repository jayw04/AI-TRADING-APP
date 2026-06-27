"""Combined Book (PORT-001 §4) — "Risk-Balanced Multi-Asset Portfolio", paper-only.

The live deployment of PORT-001, the multi-sleeve capability ONBOARDED from the sibling
claude-trading-view system (Onboarding Gate PASSED 2026-06-27, construction-verification,
Lifecycle Fidelity 98.8% — see ``docs/implementation/evidence/port_001/``). A REGULAR
deterministic Strategy file: it reaches factor data ONLY through ``ctx.factors`` (the
sandboxed read-only accessor) and submits every rebalance order through ``ctx.submit_order``
→ OrderRouter + risk engine (ADR 0002). No broker / DB / network access; no LLM (ADR 0006 v2).

Two sleeves blended at a **fixed 0.40 equity / 0.60 cross-asset** weight (the production live
config, λ=0 — ERC was used once to *derive* ~40/60, then pinned; the correlation-aware tilt is
deferred, plan §locked-decisions). Faithful to the validated engines:

  * **Equity sleeve** — crash-protected 12-1 momentum: the top-quantile of the momentum
    cross-section (``ctx.factors.momentum_scores``), equal-weight, per-name capped. The
    crash-protection is the market-regime filter (de-risk the equity sleeve to cash below the
    market MA — the live analogue of the sibling's vol-target/VIX crash engine, ADR 0020).
  * **Cross-asset sleeve** — the validated ``cross_asset_tsmom`` (PORT-001 §1): 8-ETF 12-1
    TSMOM, risk-parity, vol-targeted (de-risk-only; gross ≤ 1, rotates to cash/bonds/gold in
    the absence of trends — its own crash protection).

HONEST VERDICT (carried on every artifact): crash-protected BETA + diversification, NOT alpha
(combined alpha t=0.82 insignificant; stock-selection alpha refuted under PIT). The product's
value is drawdown reduction + diversification.

Weekly rebalance: Monday 14:00 UTC ≈ 09:00 ET (matching Momentum / Sector / Low-Vol cadence).
Every sell precedes buys (capital-flow efficiency); turnover damped by a trade threshold.

**Scope note:** this template's cross-asset sleeve prices off daily *close* bars
(``ctx.get_recent_bars``), a small price-return approximation of the research path's total-return
panel (distributions are immaterial intra-rebalance for sizing). Activation is owner-gated (a
provisioned Alpaca paper account + the ADR-0005 24h cooldown), like SEC-001 / LOW-001.
"""

from __future__ import annotations

import asyncio
import math
from decimal import Decimal
from typing import Any, ClassVar

import pandas as pd

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE, cross_asset_tsmom
from app.risk import OrderRequest
from app.strategies import Strategy

# The three "no factor data this week" signals → HOLD the book, not crash.
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class CombinedBook(Strategy):
    name: ClassVar[str] = "combined-book"
    version: ClassVar[str] = "1.0.0"  # PORT-001 Gate-Passed (construction-verification); first deploy
    symbols: ClassVar[list[str]] = []  # set at registration: equity universe + the 8 cross-asset ETFs
    # Weekly, Monday 14:00 UTC ≈ 09:00 ET. Day names avoid APScheduler's off-by-one.
    schedule: ClassVar[str] = "0 14 * * mon"

    default_params: ClassVar[dict[str, Any]] = {
        # --- sleeve blend (fixed 40/60 — production live config, λ=0; plan §locked) ---
        "equity_sleeve_weight": 0.40,
        "cross_asset_weight": 0.60,
        # --- equity sleeve (crash-protected 12-1 momentum) ---
        "momentum_lookback_days": 252,   # 12-month
        "momentum_skip_days": 21,        # skip the most recent month
        "equity_top_quantile": 0.40,     # hold the top 40% of the momentum cross-section
        # --- cross-asset sleeve (validated cross_asset_tsmom, PORT-001 §1) ---
        "cross_asset_symbols": list(CROSS_ASSET_UNIVERSE),
        "ca_lookback_days": 252, "ca_skip_days": 21,
        "ca_vol_lookback_days": 60, "ca_vol_target": 0.10,
        # --- crash protection for the equity sleeve (market-regime filter) ---
        "use_market_regime_filter": True,
        "market_filter_symbol": "SPY",   # proxy for the MA filter (also a held cross-asset ETF)
        "market_ma_days": 200,
        # --- governance & sizing ---
        "max_position_pct": 0.04,        # per-name cap (the sibling equity sleeve's 4%)
        "fractional_shares": False,
        "cash_buffer_pct": 0.02,
        "initial_equity_estimate": 100_000,
        "pricing_timeframe": "1Day",
        "timeframe": "1Day",
        "order_pacing_seconds": 1.0,
        "min_trade_pct": 0.03,
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "equity_sleeve_weight": {
            "type": "number", "min": 0, "max": 1, "default": 0.40,
            "description": "Fixed weight of the equity-momentum sleeve (production 40/60; λ=0)."
        },
        "cross_asset_weight": {
            "type": "number", "min": 0, "max": 1, "default": 0.60,
            "description": "Fixed weight of the cross-asset TSMOM sleeve (production 40/60; λ=0)."
        },
        "momentum_lookback_days": {
            "type": "integer", "min": 2, "default": 252,
            "description": "Equity-sleeve momentum lookback (trading days). 252 = 12-month."
        },
        "momentum_skip_days": {
            "type": "integer", "min": 0, "default": 21,
            "description": "Equity-sleeve momentum skip (trading days). 21 = skip the recent month."
        },
        "equity_top_quantile": {
            "type": "number", "min": 0.01, "max": 1.0, "default": 0.40,
            "description": "Fraction of the momentum cross-section held, equal-weight (top 40%)."
        },
        "cross_asset_symbols": {
            "type": "list", "default": list(CROSS_ASSET_UNIVERSE),
            "description": "The 8 asset-class ETFs for the cross-asset TSMOM sleeve (validated set)."
        },
        "ca_lookback_days": {
            "type": "integer", "min": 2, "default": 252,
            "description": "Cross-asset 12-1 momentum lookback (trading days)."
        },
        "ca_skip_days": {
            "type": "integer", "min": 0, "default": 21,
            "description": "Cross-asset momentum skip (trading days)."
        },
        "ca_vol_lookback_days": {
            "type": "integer", "min": 2, "default": 60,
            "description": "Cross-asset risk-parity volatility lookback (trading days)."
        },
        "ca_vol_target": {
            "type": "number", "min": 0, "max": 2, "default": 0.10,
            "description": "Cross-asset sleeve annualized vol target (de-risk only; gross ≤ 1)."
        },
        "use_market_regime_filter": {
            "type": "boolean", "default": True,
            "description": "De-risk the EQUITY sleeve to cash when the market is below its MA (crash protection)."
        },
        "market_filter_symbol": {
            "type": "string", "default": "SPY",
            "description": "Market proxy for the equity-sleeve regime filter (also a held cross-asset ETF)."
        },
        "market_ma_days": {
            "type": "integer", "min": 20, "default": 200,
            "description": "Moving-average window (trading days) for the regime filter."
        },
        "max_position_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.04,
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
            "description": "Delay between rebalance order submissions (spreads the burst under the order-rate cap)."
        },
        "min_trade_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.03,
            "description": "Skip adjustments to existing positions smaller than this fraction of target notional."
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
        """Build the two-sleeve target book (fixed 40/60 blend) and trade the diff toward it."""
        eq_w = await self._equity_sleeve_weights()       # {ticker: weight in [0,1]}, sums ≤ 1
        ca_w = await self._cross_asset_sleeve_weights()   # {etf: weight}, sums ≤ 1 (de-risked)

        e = float(self.params.get("equity_sleeve_weight", 0.40))
        c = float(self.params.get("cross_asset_weight", 0.60))
        target: dict[str, float] = {}
        for sym, w in eq_w.items():
            target[sym.upper()] = target.get(sym.upper(), 0.0) + e * w
        for sym, w in ca_w.items():
            target[sym.upper()] = target.get(sym.upper(), 0.0) + c * w

        held = await self._current_holdings()
        await self._apply_targets(target, held=held, reason="rebalance")

    async def _equity_sleeve_weights(self) -> dict[str, float]:
        """Crash-protected equity-momentum sleeve → equal-weight target weights (sum ≤ 1).
        Below-MA market regime → the sleeve goes to cash (the live crash-protection analogue)."""
        if self.params.get("use_market_regime_filter", True):
            below = await self._market_below_ma()
            if below is True:
                await self.ctx.log_signal(
                    "PORTFOLIO", SignalType.EXIT, payload={"reason": "equity_sleeve_regime_cash"})
                return {}
        try:
            n = len(self.ctx.symbols) or None
            kw = {"lookback_days": int(self.params.get("momentum_lookback_days", 252)),
                  "skip_days": int(self.params.get("momentum_skip_days", 21))}
            scores = (self.ctx.factors.momentum_scores(n=n, **kw) if n
                      else self.ctx.factors.momentum_scores(**kw))
        except _HOLD_ON as exc:
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "equity_factor_unavailable_hold", "error": str(exc)[:120]})
            return {}

        ca_set = {s.upper() for s in self._cross_asset_symbols()}
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        # Eligible equity names = registered symbols that are NOT cross-asset ETFs (avoid double-
        # counting SPY etc.) and not the bare market proxy.
        allowed = {s.upper() for s in self.ctx.symbols} - ca_set - {market_sym}
        eligible = scores[scores.index.isin(allowed)]
        if eligible.empty:
            return {}
        q = float(self.params.get("equity_top_quantile", 0.40))
        k = max(1, math.ceil(len(eligible) * q))
        names = [str(t) for t in eligible.sort_values("score", ascending=False).index[:k]]
        w = 1.0 / len(names)
        return {t.upper(): w for t in names}

    async def _cross_asset_sleeve_weights(self) -> dict[str, float]:
        """Validated cross-asset TSMOM sleeve over the ETF close panel → de-risked weights
        (sum = gross ≤ 1). Insufficient history → all cash (empty)."""
        symbols = self._cross_asset_symbols()
        lookback = int(self.params.get("ca_lookback_days", 252))
        skip = int(self.params.get("ca_skip_days", 21))
        vol_lb = int(self.params.get("ca_vol_lookback_days", 60))
        need = lookback + skip + max(vol_lb, 5) + 5
        panel = await self._close_panel(symbols, need)
        if panel is None or panel.shape[0] < lookback + skip + 1:
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "cross_asset_insufficient_history",
                         "have": 0 if panel is None else int(panel.shape[0]), "need": need})
            return {}
        sleeve = cross_asset_tsmom(
            panel, lookback=lookback, skip=skip, vol_lookback=vol_lb,
            vol_target=float(self.params.get("ca_vol_target", 0.10)))
        if sleeve.status != "ok":
            return {}
        return {k.upper(): float(v) for k, v in sleeve.weights.items() if v > 0}

    async def _close_panel(self, symbols: list[str], n: int) -> pd.DataFrame | None:
        """Daily-close price panel (index = date, cols = symbol) over the common dates, for the
        cross-asset sleeve. None if no symbol has bars."""
        series: dict[str, pd.Series] = {}
        for sym in symbols:
            bars = await self.ctx.get_recent_bars(sym, "1Day", n=n)
            if bars is None or bars.empty:
                continue
            s = pd.Series(bars["c"].astype(float).to_numpy(),
                          index=pd.to_datetime(bars["t"]).dt.tz_localize(None).dt.normalize())
            series[sym.upper()] = s
        if not series:
            return None
        return pd.DataFrame(series).sort_index().dropna(how="any")

    def _cross_asset_symbols(self) -> list[str]:
        raw = self.params.get("cross_asset_symbols") or list(CROSS_ASSET_UNIVERSE)
        return [str(s).upper() for s in raw]

    async def _apply_targets(
        self, target: dict[str, float], *, held: dict[str, Decimal], reason: str
    ) -> None:
        """Trade the diff from `held` toward the WEIGHTED `target` book (symbol → fraction of
        equity). Sells precede buys (capital-flow efficiency); rejections are logged and skipped."""
        target = {k: v for k, v in target.items() if v > 0}
        target_set = set(target)

        for sym, qty in held.items():
            if sym not in target_set:
                await self._submit(sym, OrderSide.SELL, qty, reason=f"{reason}_exit")

        if not target:
            return

        equity = await self._investable_equity()
        cap = Decimal(str(self.params.get("max_position_pct", 0.04)))
        min_trade = Decimal(str(self.params.get("min_trade_pct", 0.03)))
        fractional = bool(self.params.get("fractional_shares", False))

        buys: list[tuple[str, Decimal, float, Decimal]] = []
        for sym, weight in sorted(target.items()):
            notional = min(equity * Decimal(str(weight)), equity * cap)
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(sym, SignalType.ENTRY,
                                          payload={"reason": f"{reason}_skip_no_price"})
                continue
            price_d = Decimal(str(price))
            if fractional:
                target_qty = (notional / price_d).quantize(Decimal("0.000001"))
            else:
                target_qty = Decimal(math.floor(notional / price_d))
            cur = held.get(sym, Decimal(0))
            delta = target_qty - cur
            if delta == 0:
                continue
            if cur > 0 and abs(delta) * price_d < notional * min_trade:
                continue
            if delta < 0:
                await self._submit(sym, OrderSide.SELL, -delta, reason=f"{reason}_trim",
                                   payload={"price": price, "weight": round(weight, 4),
                                            "target_qty": str(target_qty)})
            else:
                buys.append((sym, delta, price, target_qty))

        for sym, qty, price, target_qty in buys:
            await self._submit(sym, OrderSide.BUY, qty, reason=f"{reason}_entry",
                               payload={"price": price, "target_qty": str(target_qty)})

    async def _current_holdings(self) -> dict[str, Decimal]:
        """Long quantities currently held across every registered symbol (equity + ETFs)."""
        held: dict[str, Decimal] = {}
        for sym in self.ctx.symbols:
            pos = await self.ctx.get_position_for(sym)
            qty = getattr(pos, "qty", None) if pos is not None else None
            if qty is not None and Decimal(qty) > 0 and getattr(pos, "side", "long") == "long":
                held[sym.upper()] = Decimal(qty)
        return held

    async def _investable_equity(self) -> Decimal:
        """Live account equity minus the cash buffer; falls back to the estimate."""
        try:
            live = await self.ctx.get_account_equity()
        except Exception:
            live = None
        equity = Decimal(str(live)) if live is not None else self._equity_estimate
        buffer = Decimal(str(self.params.get("cash_buffer_pct", 0.02)))
        return equity * (Decimal(1) - buffer)

    async def _market_below_ma(self) -> bool | None:
        """True/False if the market proxy is below/above its MA; None (fail-open) if unavailable."""
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        days = int(self.params.get("market_ma_days", 200))
        bars = await self.ctx.get_recent_bars(sym, "1Day", n=days + 1)
        if bars is None or bars.empty or len(bars) < days + 1:
            await self.ctx.log_signal(
                sym, SignalType.EXIT,
                payload={"reason": "regime_filter_unavailable_failopen",
                         "have_bars": 0 if bars is None else int(len(bars)), "need": days + 1})
            return None
        ma = float(bars["c"].iloc[:-1].mean())
        last = float(bars["c"].iloc[-1])
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
        """Dispatch one order through OrderRouter (ADR 0002) and log the outcome. The context
        stamps ``user_id`` / ``account_id`` / ``source_id``. Rejections are returned, not raised."""
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
        pacing = float(self.params.get("order_pacing_seconds", 0.0) or 0.0)
        if pacing > 0:
            await asyncio.sleep(pacing)
        return result is not None and not rejection
