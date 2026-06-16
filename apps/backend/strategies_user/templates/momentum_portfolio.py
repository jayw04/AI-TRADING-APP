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
                  within a fixed top-N liquidity candidate universe (`symbols`);
                  optional per-sector cap (max_sector_pct, off by default) damps
                  single-sector concentration by capping names/sector + backfilling
  Entry/Exit     weekly rebalance — enter the target quintile, exit names that
                  fall out of it (with a rank-hysteresis buffer to damp churn)
  Position Sizing equal target notional = investable_equity / k, capped at
                  max_position_pct, market orders; whole shares by default, or
                  fractional (fractional_shares, opt-in) to deploy ~fully
  Stop Loss      none per-name (diversification + weekly turnover + risk engine)
  Bail-Out       no factor data → HOLD; bearish market regime (price < SPY 200d
                  MA) → risk-off to CASH; risk engine caps/breaker are the halt
  Risk Overlay   optional portfolio-level EWMA-vol targeting (off by default):
                  scales gross exposure DOWN when the market proxy's realized vol
                  exceeds vol_target_annual (no leverage; fails open)

Portfolio-level EWMA-vol targeting (v0.4.0, review Priority 1 — DEFAULT OFF):
  - when ``use_vol_scaling`` is on, gross exposure is multiplied by a scale in
    [0, 1] = min(1, vol_target_annual / realized_annual_vol), where the realized
    vol is the EWMA of the market proxy's (SPY) daily returns. High-vol regimes
    de-risk the book; the cap at 1.0 means no leverage. It fails OPEN (scale 1.0,
    logged) if the proxy series is unavailable, like the regime filter. Off by
    default so the deployed book's behavior is unchanged until a backtested opt-in.

Hardening (per the §4 strategy review):
  - the ISO week is marked at the START of a rebalance ATTEMPT, so the book
    rebalances at most once per week. The engine dispatches on_bar once per
    registered SYMBOL per cron tick (~200×), so marking after success would let a
    failing rebalance re-run on the next symbol in the same tick — a submission
    storm (observed live 2026-06-15). A failed attempt logs and waits for next
    week's tick rather than retrying within the same one;
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

# The three "no factor data this week" signals (accessor not provisioned, thin
# cross-section, below the price floor) — any of them means HOLD the book, not
# crash the rebalance tick (§4 review, Finding 1).
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class MomentumPortfolio(Strategy):
    name: ClassVar[str] = "momentum-portfolio"
    version: ClassVar[str] = "0.6.0"  # + optional fractional-share sizing (P10 §7, default off)
    # Set at registration = top-200 liquidity candidates (§4 §3.3). Include the
    # market_filter_symbol (SPY) here too, or the regime filter fails open.
    symbols: ClassVar[list[str]] = []
    # Weekly, Mon 14:00 UTC ≈ 09:00 ET. Use the day NAME, not "1": APScheduler's
    # CronTrigger numbers dow 0=Mon (cron is 1=Mon), so "0 14 * * 1" fires TUESDAY.
    # The engine also normalizes numeric dow now, but the name is unambiguous.
    schedule: ClassVar[str] = "0 14 * * mon"

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
        "max_sector_pct": None,  # cap per-sector book weight (None = disabled; P10 §3, opt-in)
        "fractional_shares": False,  # size fractional qty (deploys ~fully on a small acct; P10 §7, opt-in)
        "cash_buffer_pct": 0.02,  # keep this fraction in cash (deploy the rest)
        "initial_equity_estimate": 100_000,  # FALLBACK only when live equity is unavailable
        # Engine dispatch timeframe: StrategyEngine._dispatch_bar_tick fetches a bar
        # of THIS timeframe per symbol to fire on_bar. Daily matches the book's
        # daily sizing/regime data (the engine default is "1Min", which is wrong here).
        "timeframe": "1Day",
        # Delay between rebalance order submissions, to spread a burst under the
        # per-strategy order-rate cap (rolling max_orders_per_minute). 0 = no pacing.
        "order_pacing_seconds": 1.0,
        "use_vol_scaling": False,  # portfolio EWMA-vol targeting (review Priority 1) — opt-in
        "vol_target_annual": 0.15,  # target annualized portfolio vol when vol-scaling is on
        "vol_ewma_span": 20,  # EWMA span (trading days) for the market-proxy vol estimate
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
        "fractional_shares": {"type": "boolean", "default": False,
                              "description": "Size fractional share quantities (deploys ~fully vs whole-share rounding). Alpaca fractional MARKET/DAY only."},
        "max_sector_pct": {"type": "number", "min": 0, "max": 1, "nullable": True, "default": None,
                           "description": "Cap on any one sector's share of the book (≈names, equal-weight). Empty/None = no sector cap."},
        "cash_buffer_pct": {"type": "number", "min": 0, "max": 1, "default": 0.02,
                            "description": "Fraction of equity held back as cash."},
        "initial_equity_estimate": {"type": "number", "min": 0, "default": 100_000,
                                    "description": "Fallback equity estimate when no live account snapshot exists."},
        "timeframe": {"type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"],
                      "default": "1Day", "description": "Engine dispatch bar timeframe that fires the weekly on_bar tick."},
        "order_pacing_seconds": {"type": "number", "min": 0, "max": 60, "default": 1.0,
                                 "description": "Delay between rebalance order submissions (spreads the burst under the order-rate cap)."},
        "use_vol_scaling": {"type": "boolean", "default": False,
                            "description": "Scale gross exposure to a target volatility using the market proxy's EWMA vol."},
        "vol_target_annual": {"type": "number", "min": 0, "max": 2, "default": 0.15,
                              "description": "Target annualized portfolio volatility when vol-scaling is enabled."},
        "vol_ewma_span": {"type": "integer", "min": 2, "default": 20,
                          "description": "EWMA span (trading days) for the market-proxy volatility estimate."},
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        # (ISO year, ISO week) of the last ATTEMPTED rebalance — guards once/week.
        self._last_rebalance_week: tuple[int, int] | None = None

    async def on_bar(self, bar: Any) -> None:
        wk = bar.t.isocalendar()[:2]  # (iso_year, iso_week)
        if wk == self._last_rebalance_week:
            return  # already attempted this week; ignore the per-symbol tick calls
        # ★ Mark the week BEFORE rebalancing. The engine dispatches on_bar PER SYMBOL
        # (once for each of the ~200 registered symbols) on every cron tick, so a
        # rebalance that raises would otherwise re-run on the *next symbol in the
        # same tick* — up to 200× — flooding the OrderRouter (this caused a live
        # cooldown storm 2026-06-15). Marking first guarantees at most one attempt
        # per ISO week; a failure logs and waits for next week's tick, not next symbol.
        self._last_rebalance_week = wk
        try:
            await self._rebalance()
        except Exception as exc:  # noqa: BLE001 — contain user-path failures; retry is next week
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.EXIT,
                payload={"reason": "rebalance_failed", "error": str(exc)[:160]},
            )

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
        fractional = bool(self.params.get("fractional_shares", False))
        buys: list[tuple[str, Decimal, float, Decimal]] = []
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(sym, SignalType.ENTRY, payload={"reason": f"{reason}_skip_no_price"})
                continue
            price_d = Decimal(str(price))
            # Fractional sizing deploys ~fully — no whole-share floor that zeroes out
            # names priced above the per-name budget (the ~67%-deployment problem on a
            # small account). Alpaca fills fractional MARKET/DAY orders on fractionable
            # names; a non-fractionable name simply rejects (logged, like any rejection).
            if fractional:
                target_qty = (per_name / price_d).quantize(Decimal("0.000001"))
            else:
                target_qty = Decimal(math.floor(per_name / price_d))
            cur = held.get(sym, Decimal(0))  # Decimal — never int-cast (fractional holdings)
            delta = target_qty - cur
            if delta == 0:
                continue
            # Turnover threshold: skip adjustments to EXISTING positions that are
            # smaller than min_trade_pct of the target notional (new entries pass).
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
        final = [t for t in ranked if t in chosen][:cap]
        return self._apply_sector_cap(final, ranked, cap)

    def _apply_sector_cap(self, final: list[str], ranked: list[str], cap: int) -> list[str]:
        """Enforce a per-sector cap on the selected book (review #7, P10 §3).

        Keeps at most ``floor(max_sector_pct * max_names)`` names per Sharadar
        sector (≥1), preferring the highest-scored, then BACKFILLS the slots freed
        by dropped over-concentrated names with the next-best names from other
        sectors — so the book diversifies without shrinking. Disabled when
        ``max_sector_pct`` is unset/≥1; FAILS OPEN (returns ``final`` unchanged) if
        sector data is unavailable, so a data gap can't silently halt selection."""
        max_pct = self.params.get("max_sector_pct")
        if not max_pct or float(max_pct) >= 1.0 or not final:
            return final
        try:
            sectors = self.ctx.factors.sectors(ranked)
        except Exception:  # noqa: BLE001 — no sector data → fail open (no cap applied)
            return final

        max_per = max(1, int(math.floor(float(max_pct) * cap)))
        target_n = len(final)
        book: list[str] = []
        sec_count: dict[Any, int] = {}

        def _try_add(t: str) -> None:
            sec = sectors.get(t)  # None (unknown sector) is never capped
            if sec is not None and sec_count.get(sec, 0) >= max_per:
                return
            book.append(t)
            sec_count[sec] = sec_count.get(sec, 0) + 1

        for t in final:  # keep original picks that fit the cap (best-first preserved)
            if len(book) >= target_n:
                break
            _try_add(t)
        if len(book) < target_n:  # backfill freed slots from the broader ranked list
            for t in ranked:
                if len(book) >= target_n:
                    break
                if t not in book:
                    _try_add(t)
        return book

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
        base = equity * (Decimal(1) - buffer)
        # Portfolio-level vol targeting (review Priority 1): scale gross exposure
        # down in high-vol regimes. min(1.0, ...) caps at full investment (no
        # leverage); 1.0 when disabled or the proxy series is unavailable.
        scale = await self._gross_scale()
        return base * Decimal(str(scale))

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

    async def _gross_scale(self) -> float:
        """Portfolio gross-exposure multiplier in [0, 1] from EWMA-vol targeting.

        Returns min(1.0, vol_target_annual / realized_annual_vol), where the
        realized vol is the EWMA (span ``vol_ewma_span``) of the market proxy's
        daily returns annualized by √252. So a high-vol regime scales the book
        down; the cap at 1.0 means the overlay never adds leverage. Returns 1.0
        when disabled, and FAILS OPEN (1.0, logged) if the proxy series is
        unavailable — consistent with the regime filter (review-praised design)."""
        if not self.params.get("use_vol_scaling", False):
            return 1.0
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        span = int(self.params.get("vol_ewma_span", 20))
        target = float(self.params.get("vol_target_annual", 0.15))
        # Fetch enough daily closes to warm the EWMA (≈3 spans of returns).
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
        if not (ewma_var > 0):  # zero / NaN variance → can't scale → full exposure
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
        # Pace submissions so a multi-name rebalance burst stays under the
        # per-strategy rolling order-rate cap (a 0 value disables pacing).
        pacing = float(self.params.get("order_pacing_seconds", 0.0) or 0.0)
        if pacing > 0:
            await asyncio.sleep(pacing)
        return result is not None and not rejection
