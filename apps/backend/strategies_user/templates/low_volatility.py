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

Weekly rebalance: Monday (live cron may stagger the minute). LOW-001 V1 is **always invested** —
the SPY 200-day cash gate was a MOM-001 copy and contradicted the research; it is not applied.
Optional vol-scaling overlay remains OFF by default. Every sell precedes buys. Turnover damping
via a trade threshold. Factor store must be session-fresh or the week HOLDs. Rebalance
started→completed is durable (signal-backed) so a restart retries an incomplete week.

**Phase 2 governance note:** This is a Methodology Transfer demonstration (after SEC-001). LOW-001
promotion proves Evidence Engineering governance + operational architecture are REPEATABLE across
*multiple* strategies — not a one-off. Success is operational correctness (no crashes, clean
rebalances, expected positions, proper risk gating, corr direction holds), not P&L targets
(per ADR 0014; 4 weeks is too short for evidence).
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, date, timedelta
from decimal import Decimal
from typing import Any, ClassVar
from zoneinfo import ZoneInfo

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.market.session import default_market_session
from app.risk import OrderRequest
from app.strategies import Strategy

# The three "no factor data this week" signals → HOLD the book, not crash
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)

# Frozen from LOW-001 V1 research (`low_vol_research.py --n 200`).
RESEARCH_UNIVERSE_N = 200
# Ingest slack: HOLD only if the store lags more than one *completed NYSE session*
# behind the previous trading day. Holidays are not counted as missing sessions.
MAX_FACTOR_LAG_SESSIONS = 1


def expected_last_session(as_of: date) -> date:
    """Previous completed NYSE session before ``as_of`` (weekends and holidays)."""
    return default_market_session().previous_trading_day(as_of)


def session_lag(latest: date, expected: date) -> int:
    """Count completed NYSE sessions in (latest, expected]. 0 if latest ≥ expected."""
    if latest >= expected:
        return 0
    ms = default_market_session()
    n = 0
    d = latest
    while d < expected:
        d += timedelta(days=1)
        if ms.is_trading_day(d):
            n += 1
    return n


class LowVolatility(Strategy):
    name: ClassVar[str] = "low-volatility"
    version: ClassVar[str] = "1.0.1"  # V1 economics frozen; implementation-drift repairs only
    symbols: ClassVar[list[str]] = []  # set at registration (same 201 as Momentum: top-200 + SPY)
    # Weekly, Monday 14:00 UTC ≈ 09:00 ET. Day names avoid APScheduler's off-by-one.
    schedule: ClassVar[str] = "0 14 * * mon"

    default_params: ClassVar[dict[str, Any]] = {
        # LOW-001 research-frozen parameters (V1 headline; from low_vol_research.py)
        "vol_lookback_days": 252,  # 12-month trailing realized vol; frozen from research
        "top_quantile": 0.20,  # hold the lowest-vol quintile, equal-weight; frozen from research
        # Market proxy is used only by the optional vol-scaling overlay (default OFF).
        # The SPY 200-day cash gate is NOT part of LOW-001 V1 (research is always invested).
        "market_filter_symbol": "SPY",
        "market_ma_days": 200,
        "max_position_pct": 0.10,  # hard cap on any single position
        "fractional_shares": True,  # fractional deploys ~fully; whole shares under-deploy
        "cash_buffer_pct": 0.02,  # hold 2% cash
        "initial_equity_estimate": 100_000,  # fallback when live equity unavailable
        "pricing_timeframe": "1Day",  # price by daily close (not intraday bar)
        "timeframe": "1Day",  # engine dispatch bar timeframe
        "order_pacing_seconds": 1.0,  # spread rebalance orders under rate cap
        "min_trade_pct": 0.03,  # skip tiny adjustments to existing positions
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
            "type": "integer",
            "min": 2,
            "default": 252,
            "description": "Trailing realized-volatility window (trading days). 252 = 12-month; frozen from research.",
        },
        "top_quantile": {
            "type": "number",
            "min": 0.01,
            "max": 1.0,
            "default": 0.20,
            "description": "Fraction of the universe held (lowest-vol names, equal-weight). 0.20 = top-quintile; frozen from research.",
        },
        "market_filter_symbol": {
            "type": "string",
            "default": "SPY",
            "description": "Market proxy for optional vol-scaling (must be in registered symbols). Not a cash gate.",
        },
        "market_ma_days": {
            "type": "integer",
            "min": 20,
            "default": 200,
            "description": "Moving-average window (trading days) unused unless vol-scaling is on.",
        },
        "max_position_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.10,
            "description": "Hard cap on any single position as a fraction of equity.",
        },
        "fractional_shares": {
            "type": "boolean",
            "default": True,
            "description": "V1 always sizes fractionally (this cannot disable it). Non-fractionable names are floored to whole shares by OrderRouter.",
        },
        "cash_buffer_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.02,
            "description": "Fraction of equity held back as cash.",
        },
        "initial_equity_estimate": {
            "type": "number",
            "min": 0,
            "default": 100_000,
            "description": "Fallback equity estimate when no live account snapshot exists.",
        },
        "pricing_timeframe": {
            "type": "enum",
            "choices": ["5Min", "15Min", "1Hour", "1Day"],
            "default": "1Day",
            "description": "Bar timeframe used to price names for sizing.",
        },
        "timeframe": {
            "type": "enum",
            "choices": ["5Min", "15Min", "1Hour", "1Day"],
            "default": "1Day",
            "description": "Engine dispatch bar timeframe that fires the weekly on_bar tick.",
        },
        "order_pacing_seconds": {
            "type": "number",
            "min": 0,
            "max": 60,
            "default": 1.0,
            "description": "Delay between rebalance order submissions (spreads the burst under order-rate cap).",
        },
        "min_trade_pct": {
            "type": "number",
            "min": 0,
            "max": 1,
            "default": 0.03,
            "description": "Skip adjustments to existing positions smaller than this fraction of target notional.",
        },
        "use_vol_scaling": {
            "type": "boolean",
            "default": False,
            "description": "Scale gross exposure to a target volatility (inherited from Momentum; opt-in).",
        },
        "vol_target_annual": {
            "type": "number",
            "min": 0,
            "max": 2,
            "default": 0.15,
            "description": "Target annualized portfolio volatility when vol-scaling is enabled.",
        },
        "vol_ewma_span": {
            "type": "integer",
            "min": 2,
            "default": 20,
            "description": "EWMA span (trading days) for market-proxy volatility estimate.",
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        # Same-process storm skip. Live uses ctx.dispatch_seq (201-symbol loop +
        # 2026-07-13 stale-bar incident). Backtest uses ISO week. Durable
        # ``rebalance_completed`` is what survives a restart.
        self._last_rebalance_week: tuple[int, int] | None = None
        self._last_dispatch_seq: int | None = None

    def _as_of_date(self, bar: Any) -> date:
        """Live: ET date of this engine dispatch, not the symbol bar.

        The engine calls on_bar once per symbol; those bars can disagree on
        recency. A bar-derived ISO week re-fired the combined book 5× in one
        slot on 2026-07-13. Backtests have no dispatch_seq and use bar.t.
        """
        seq = getattr(self.ctx, "dispatch_seq", None)
        if isinstance(seq, int):
            instant = getattr(getattr(self.ctx, "session", None), "as_of", None)
            if instant is not None:
                if getattr(instant, "tzinfo", None) is None:
                    instant = instant.replace(tzinfo=UTC)
                return instant.astimezone(ZoneInfo("America/New_York")).date()
        t = bar.t
        return t.date() if hasattr(t, "date") else t

    async def on_bar(self, bar: Any) -> None:
        as_of = self._as_of_date(bar)
        wk = as_of.isocalendar()[:2]
        if await self._week_completed(wk):
            return
        seq = getattr(self.ctx, "dispatch_seq", None)
        if isinstance(seq, int):
            if seq == getattr(self, "_last_dispatch_seq", None):
                return
            self._last_dispatch_seq = seq
        elif getattr(self, "_last_rebalance_week", None) == wk:
            return
        else:
            self._last_rebalance_week = wk
        try:
            await self._mark("rebalance_started", wk)
            if await self._rebalance(as_of=as_of):
                await self._mark("rebalance_completed", wk)
        except Exception as exc:
            await self.ctx.log_signal(
                "PORTFOLIO",
                SignalType.EXIT,
                payload={
                    "reason": "rebalance_failed",
                    "error": str(exc)[:160],
                    "iso_week": [wk[0], wk[1]],
                },
            )

    async def _week_completed(self, wk: tuple[int, int]) -> bool:
        """True if a durable rebalance_completed signal exists for this ISO week."""
        try:
            payloads = await self.ctx.recent_payloads(limit=80)
        except Exception:
            return False
        for p in payloads:
            if p.get("reason") != "rebalance_completed":
                continue
            marked = p.get("iso_week")
            if (
                isinstance(marked, (list, tuple))
                and len(marked) >= 2
                and int(marked[0]) == wk[0]
                and int(marked[1]) == wk[1]
            ):
                return True
        return False

    async def _mark(self, reason: str, wk: tuple[int, int]) -> None:
        await self.ctx.log_signal(
            "PORTFOLIO",
            SignalType.EXIT,
            payload={"reason": reason, "iso_week": [wk[0], wk[1]]},
        )

    # ---- rebalance ----

    async def _rebalance(self, *, as_of: date) -> bool:
        """Compute the lowest-vol target book and trade the diff toward it.

        Returns True when the week should be marked completed. HOLD (stale or
        missing factors) returns False so a later dispatch — typically a
        restart — can retry the incomplete week.
        """
        if not await self._factor_is_fresh(as_of):
            return False

        try:
            lv_kw = {"lookback_days": int(self.params.get("vol_lookback_days", 252))}
            scores = self.ctx.factors.low_vol_scores(n=RESEARCH_UNIVERSE_N, **lv_kw)
        except _HOLD_ON as exc:
            await self.ctx.log_signal(
                self.ctx.symbols[0] if self.ctx.symbols else "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return False

        held = await self._current_holdings()
        target = await self._select_targets(scores)
        await self._apply_targets(target, held=held, reason="rebalance")
        return True

    async def _factor_is_fresh(self, as_of: date) -> bool:
        """HOLD when the factor store lags more than MAX_FACTOR_LAG_SESSIONS
        completed NYSE sessions behind the previous trading day."""
        try:
            latest = self.ctx.factors.latest_price_date()
        except _HOLD_ON as exc:
            await self.ctx.log_signal(
                "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return False
        except Exception as exc:
            await self.ctx.log_signal(
                "PORTFOLIO",
                SignalType.EXIT,
                payload={"reason": "factor_unavailable_hold", "error": str(exc)[:120]},
            )
            return False
        expected = expected_last_session(as_of)
        lag = session_lag(latest, expected)
        if lag > MAX_FACTOR_LAG_SESSIONS:
            await self.ctx.log_signal(
                "PORTFOLIO",
                SignalType.EXIT,
                payload={
                    "reason": "factor_stale_hold",
                    "latest": str(latest),
                    "expected": str(expected),
                    "lag_sessions": lag,
                },
            )
            return False
        return True

    async def _select_targets(self, scores: Any) -> list[str]:
        """Top-quintile lowest-volatility names from the research PIT universe.

        Rank ``universe_asof(n=200)`` by −(trailing realized vol), take
        ``ceil(N · top_quantile)``, drop the market proxy. Names in that PIT
        quintile that are not in the registered symbol list cannot be ordered
        (strategy-universe isolation); they are logged and omitted from
        execution. Equal-weight sizing then fully deploys among the executable
        subset.
        """
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        allowed = {s.upper() for s in self.ctx.symbols if s.upper() != market_sym}
        if scores is None or getattr(scores, "empty", True):
            return []

        ordered = [str(t).upper() for t in scores.index if str(t).upper() != market_sym]
        if not ordered:
            return []
        q = float(self.params.get("top_quantile", 0.20))
        k = max(1, math.ceil(len(ordered) * q))
        pit = ordered[:k]
        executable = [t for t in pit if t in allowed]
        dropped = [t for t in pit if t not in allowed]
        if dropped:
            await self.ctx.log_signal(
                "PORTFOLIO",
                SignalType.EXIT,
                payload={
                    "reason": "pit_name_not_registered",
                    "n": len(dropped),
                    "sample": dropped[:12],
                },
            )
        return executable

    async def _apply_targets(
        self, target: list[str], *, held: dict[str, Decimal] | None = None, reason: str
    ) -> None:
        """Trade the diff from `held` toward the equal-weight `target` basket.

        Sells precede buys. Names without a price are dropped before sizing so
        leftover cash is not reserved for unexecutable legs. Qty is always
        fractional; OrderRouter floors non-fractionable assets. In-flight buys
        are netted so a retry does not stack a second basket.
        """
        if held is None:
            held = await self._current_holdings()
        target_set = set(target)

        for sym, qty in held.items():
            if sym not in target_set:
                await self._submit(sym, OrderSide.SELL, qty, reason=f"{reason}_exit")

        if not target:
            return

        priced: list[tuple[str, Decimal]] = []
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(
                    sym, SignalType.ENTRY, payload={"reason": f"{reason}_skip_no_price"}
                )
                continue
            priced.append((sym, Decimal(str(price))))
        if not priced:
            return

        equity = await self._investable_equity()
        k = len(priced)
        per_name = min(
            equity / Decimal(k), equity * Decimal(str(self.params.get("max_position_pct", 0.10)))
        )
        min_trade = Decimal(str(self.params.get("min_trade_pct", 0.03)))
        try:
            pending_buys = await self.ctx.pending_buy_qty()
        except Exception:
            pending_buys = {}

        buys: list[tuple[str, Decimal, float, Decimal]] = []
        for sym, price_d in priced:
            target_qty = (per_name / price_d).quantize(Decimal("0.000001"))
            cur = held.get(sym, Decimal(0))
            inflight = pending_buys.get(sym, Decimal(0))
            delta = target_qty - cur - inflight
            if delta == 0:
                continue
            if cur > 0 and abs(delta) * price_d < per_name * min_trade:
                continue
            price = float(price_d)
            if delta < 0:
                await self._submit(
                    sym,
                    OrderSide.SELL,
                    -delta,
                    reason=f"{reason}_trim",
                    payload={"price": price, "target_qty": str(target_qty)},
                )
            else:
                buys.append((sym, delta, price, target_qty))

        for sym, qty, price, target_qty in buys:
            await self._submit(
                sym,
                OrderSide.BUY,
                qty,
                reason=f"{reason}_entry",
                payload={"price": price, "target_qty": str(target_qty)},
            )

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
                sym,
                SignalType.EXIT,
                payload={
                    "reason": "vol_scaling_unavailable_failopen",
                    "have_bars": 0 if bars is None else int(len(bars)),
                    "need": span + 1,
                },
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
        self,
        symbol: str,
        side: OrderSide,
        qty: Decimal,
        *,
        reason: str,
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
