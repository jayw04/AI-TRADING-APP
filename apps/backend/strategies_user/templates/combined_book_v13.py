"""Combined Book (PORT-001 §4) — "Risk-Balanced Multi-Asset Portfolio", paper-only.

The live deployment of PORT-001, the multi-sleeve capability ONBOARDED from the sibling
claude-trading-view system (Onboarding Gate PASSED 2026-06-27, construction-verification,
Lifecycle Fidelity 98.8% — see ``docs/implementation/evidence/port_001/``). A REGULAR
deterministic Strategy file: it reaches factor data ONLY through ``ctx.factors`` (the
sandboxed read-only accessor) and submits every rebalance order through ``ctx.submit_order``
→ OrderRouter + risk engine (ADR 0002). No broker / DB / network access; no LLM (ADR 0006 v2).

Two sleeves blended at a **fixed 0.40 equity / 0.60 cross-asset** weight (the production live
config — ERC was used once to *derive* ~40/60, then pinned). Faithful to the validated engines:

  * **Equity sleeve** — crash-protected 12-1 momentum: the top-quantile of the momentum
    cross-section (``ctx.factors.momentum_scores``), equal-weight, per-name capped. The
    crash-protection is the market-regime filter (de-risk the equity sleeve to cash below the
    market MA — the live analogue of the sibling's vol-target/VIX crash engine, ADR 0020).
  * **Cross-asset sleeve** — the validated ``cross_asset_tsmom`` (PORT-001 §1/§5.6): a **9-ETF**
    12-1 TSMOM (the 8 asset classes + **KMLM managed futures**, added 2026-07-03 as the missing
    rate-crisis hedge), risk-parity, vol-targeted (de-risk-only; gross ≤ 1, rotates to
    cash/bonds/gold in the absence of trends — its own crash protection), now with the
    **correlation-aware tilt ON (λ=0.5)** — down-weights whatever is currently equity-correlated,
    leans into the live hedges (PORT-001 §11 #1; sibling has run this live since 2026-06-25).

**Look-through equity-beta-cap governor (lever #2, PORT-001 §11 #2 / §6.2) — de-risk only,
ENFORCED BY DEFAULT in governance v1.3.** After the blend, trim the equity-beta names (stocks +
SPY/EFA/EEM) down when their look-through risk contribution exceeds a budget (0.80), raising cash
— the non-equity legs (bonds / gold / commodities / USD / KMLM) untouched, the released allocation
retained as explicit cash (never auto-redistributed). Enforcement is the governed v1.3/C40 policy
(the 2026-07-07 owner activation, CF-1-adjudicated, is baked in as the default so a registration
path that omits the param cannot silently recreate the WS-1 governor-registration ambiguity);
``beta_cap_report_only=True`` keeps the telemetry logging alongside enforcement. See
``app/research/factor_lab/beta_cap.py`` and ADR 0049.

HONEST VERDICT (carried on every artifact): crash-protected BETA + diversification, NOT alpha
(combined alpha t=0.82 insignificant; stock-selection alpha refuted under PIT). The product's
value is drawdown reduction + diversification.

Weekly rebalance: Monday 14:00 UTC ≈ 09:00 ET (matching Momentum / Sector / Low-Vol cadence).
Every sell precedes buys (capital-flow efficiency); turnover damped by a trade threshold.

**Scope note:** this template's cross-asset sleeve prices off daily *close* bars
(``ctx.get_recent_bars``), a small price-return approximation of the research path's total-return
panel (distributions are immaterial intra-rebalance for sizing). KMLM (managed futures, larger
distributions) inherits the same approximation already accepted for TLT/IEF/GLD/DBC; a true
total-return live pricing path is a separate design item. Activation is owner-gated (a
provisioned Alpaca paper account + the ADR-0005 24h cooldown), like SEC-001 / LOW-001.
"""

from __future__ import annotations

import asyncio
import math
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any, ClassVar

import pandas as pd

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.total_return import total_return_index
from app.factor_data.universe import UniverseUnavailable
from app.market_data.alpaca_distributions import AlpacaDistributionsProvider
from app.observability import metrics
from app.research.factor_lab.beta_cap import cap_equity_beta, default_equity_names
from app.research.factor_lab.cross_asset import CROSS_ASSET_UNIVERSE, cross_asset_tsmom
from app.risk import OrderRequest
from app.strategies import Strategy

# The three "no factor data this week" signals → HOLD the book, not crash.
_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)


class CombinedBook(Strategy):
    name: ClassVar[str] = "combined-book"
    version: ClassVar[str] = "1.4.0"  # the governed "Strategy 9 v1.3" construction (C40, sealed spec
    # 2026-07-28 sha 8445fa8a…). The 1.3.0 version STRING was already used by the TR-pricing revision,
    # so this file carries 1.4.0 while the governance name of the construction remains "v1.3"/C40.
    symbols: ClassVar[list[str]] = []  # set at registration: equity universe + the 8 cross-asset ETFs
    # Weekly, Monday 14:00 UTC ≈ 09:00 ET. Day names avoid APScheduler's off-by-one.
    schedule: ClassVar[str] = "0 14 * * mon"

    # ⚠ DECLARED factor consumption (2026-08-27). This book ranks on ``ctx.factors``, so the
    # factor-readiness interlock governs both its dispatch and its IDLE->PAPER/LIVE activation.
    # Declared rather than inferred because AST introspection of the LOADED INSTANCE failed in
    # production on 2026-08-10 and silently disarmed the veto for this class of strategy.
    requires_factor_readiness: ClassVar[bool] = True

    default_params: ClassVar[dict[str, Any]] = {
        # --- sleeve blend (fixed 40/60 — production live config, λ=0; plan §locked) ---
        "equity_sleeve_weight": 0.40,
        "cross_asset_weight": 0.60,
        # --- equity sleeve (crash-protected 12-1 momentum) ---
        "momentum_lookback_days": 252,   # 12-month
        "momentum_skip_days": 21,        # skip the most recent month
        "equity_top_quantile": 0.40,     # hold the top 40% of the momentum cross-section
        # --- cross-asset sleeve (validated cross_asset_tsmom, PORT-001 §1/§5.6; 9 ETFs incl KMLM) ---
        "cross_asset_symbols": list(CROSS_ASSET_UNIVERSE),
        "ca_lookback_days": 252, "ca_skip_days": 21,
        "ca_vol_lookback_days": 60, "ca_vol_target": 0.10,
        # --- correlation-aware tilt (PORT-001 §5.6/§11 #1; ON, λ=0.5 — sibling live since 2026-06-25) ---
        "ca_corr_aware": True,
        "ca_corr_lambda": 0.5,
        "ca_corr_lookback": 60,
        "ca_corr_floor": 0.0,
        "ca_corr_cap": 2.0,
        "ca_corr_proxy": "SPY",
        # --- look-through equity-beta-cap governor (PORT-001 lever #2; DE-RISK ONLY;
        # --- v1.3/C40: ENFORCED BY DEFAULT — the governed policy, ADR 0049) ---
        "enforce_beta_cap": True,       # v1.3 spec: governor ENFORCED (CF-1-adjudicated policy)
        "beta_cap_report_only": True,   # when not enforcing, still LOG the would-be haircut (dry-run)
        "beta_cap_max_rc": 0.80,        # max equity-beta risk-contribution share
        "beta_cap_lookback": 120,       # covariance window (trading days; live 1Day history ~1yr cap)
        "beta_cap_shrink": 0.15,        # off-diagonal covariance shrinkage λ
        # --- total-return live pricing for the cross-asset sleeve (PORT-001 #3; default OFF) ---
        "use_total_return_pricing": False,   # price the cross-asset sleeve on total-return closes (Alpaca corp-actions)
        "tr_pricing_report_only": False,     # log the TR-vs-raw divergence without changing the panel (dry-run)
        # --- crash protection for the equity sleeve (market-regime filter) ---
        "use_market_regime_filter": True,
        "market_filter_symbol": "SPY",   # proxy for the MA filter (also a held cross-asset ETF)
        "market_ma_days": 200,
        # --- governance & sizing ---
        "equity_fixed_n": 40,            # v1.3: fixed top-N equity sleeve (supersedes the quantile)
        "ca_book_cap": 0.20,             # v1.3: cross-asset per-name cap, BOOK-level, applied PRE-BLEND
                                         # inside the sleeve as min(w, ca_book_cap / cross_asset_weight)
        "max_position_pct": 0.04,        # EQUITY-SLEEVE-INTERNAL per-name cap (CF-2 corrected scope:
                                         # applied inside _equity_sleeve_weights, NEVER post-blend)
        "fractional_shares": True,  # fractional deploys ~fully; whole shares under-deploy (default ON)
        "cash_buffer_pct": 0.02,
        "initial_equity_estimate": 100_000,
        "pricing_timeframe": "1Day",
        "timeframe": "1Day",
        "order_pacing_seconds": 1.0,
        # v1.3 bounded hybrid threshold (C40): max(floor, min(rel*target, ceiling*account_equity))
        "trade_floor_usd": 50.0,
        "trade_rel_pct": 0.03,
        "trade_ceiling_equity_pct": 0.0010,
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
        "ca_corr_aware": {
            "type": "boolean", "default": True,
            "description": "Correlation-aware tilt: down-weight assets correlated to the equity proxy, lean into hedges (PORT-001 §5.6)."
        },
        "ca_corr_lambda": {
            "type": "number", "min": 0, "max": 2, "default": 0.5,
            "description": "Tilt strength λ in clip(1 − λ·corr(asset, proxy), floor, cap). 0.5 = the sibling live setting."
        },
        "ca_corr_lookback": {
            "type": "integer", "min": 3, "default": 60,
            "description": "Trailing window (trading days) for the asset-vs-proxy correlation used by the tilt."
        },
        "ca_corr_floor": {
            "type": "number", "min": 0, "max": 2, "default": 0.0,
            "description": "Lower clip on the tilt multiplier."
        },
        "ca_corr_cap": {
            "type": "number", "min": 0, "max": 5, "default": 2.0,
            "description": "Upper clip on the tilt multiplier."
        },
        "ca_corr_proxy": {
            "type": "string", "default": "SPY",
            "description": "Equity proxy the tilt correlates each asset against (skipped if absent from the panel)."
        },
        "enforce_beta_cap": {
            "type": "boolean", "default": True,
            "description": "Apply the look-through equity-beta-cap governor (de-risk only). "
                           "ENFORCED BY DEFAULT under governance v1.3/C40 (ADR 0049): the "
                           "governor is the ruled policy, and the default guarantees a "
                           "registration that omits the param cannot silently disable it."
        },
        "beta_cap_report_only": {
            "type": "boolean", "default": True,
            "description": "Keep the per-rebalance governor telemetry (the beta_cap signal) "
                           "logging. With enforcement on this is logging continuity, not a "
                           "dry-run; dry-run mode is enforce_beta_cap=False + report_only=True."
        },
        "beta_cap_max_rc": {
            "type": "number", "min": 0.1, "max": 1.0, "default": 0.80,
            "description": "Max share of total risk from the equity-beta names before the governor trims them."
        },
        "beta_cap_lookback": {
            "type": "integer", "min": 20, "default": 120,
            "description": "Covariance window (trading days) for the governor. Live 1Day history is ~1yr-capped."
        },
        "beta_cap_shrink": {
            "type": "number", "min": 0.0, "max": 1.0, "default": 0.15,
            "description": "Off-diagonal covariance shrinkage (Ledoit-Wolf-lite) for the governor."
        },
        "use_total_return_pricing": {
            "type": "boolean", "default": False,
            "description": "Price the cross-asset sleeve on TOTAL-RETURN closes (raw + Alpaca corp-actions). False = raw closes (PORT-001 #3)."
        },
        "tr_pricing_report_only": {
            "type": "boolean", "default": False,
            "description": "When not enforcing TR pricing, still compute + log the TR-vs-raw divergence (the live dry-run)."
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
            "description": "Per-name cap INSIDE the equity sleeve (sleeve-internal; v1.3 corrected scope)."
        },
        "equity_fixed_n": {
            "type": "number", "min": 1, "max": 200, "default": 40,
            "description": "Fixed number of equity-momentum names (v1.3; supersedes equity_top_quantile)."
        },
        "ca_book_cap": {
            "type": "number", "min": 0, "max": 1, "default": 0.20,
            "description": "Cross-asset per-name cap as a fraction of the BOOK, applied pre-blend inside the sleeve (min(w, cap/cross_asset_weight); truncation, no redistribution)."
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
            "description": "Delay between rebalance order submissions (spreads the burst under the order-rate cap)."
        },
        "trade_floor_usd": {
            "type": "number", "min": 0, "default": 50.0,
            "description": "Absolute minimum order notional (bounded hybrid threshold; exits exempt)."
        },
        "trade_rel_pct": {
            "type": "number", "min": 0, "max": 1, "default": 0.03,
            "description": "Relative arm of the bounded hybrid threshold (fraction of target notional)."
        },
        "trade_ceiling_equity_pct": {
            "type": "number", "min": 0, "max": 0.01, "default": 0.0010,
            "description": "Ceiling arm: the relative threshold never exceeds this fraction of account equity (prevents large capped positions from accumulating skipped deltas — the F2/F3 interaction fix)."
        },
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        self._last_rebalance_week: tuple[int, int] | None = None  # backtest cadence
        self._last_dispatch_seq: int | None = None  # live cadence: one rebalance per dispatch
        # Set per-rebalance by _maybe_prefetch_distributions when TR pricing is on; None = raw closes.
        self._dist_provider: AlpacaDistributionsProvider | None = None
        # Operational-debt telemetry state (v1.3): in-memory only, resets on reload.
        self._skipped_cum: dict[str, Decimal] = {}
        self._skipped_streak: dict[str, int] = {}

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
        """Build the two-sleeve target book (fixed 40/60 blend) and trade the diff toward it."""
        await self._maybe_prefetch_distributions()       # PORT-001 #3 total-return pricing (default OFF)
        eq_w = await self._equity_sleeve_weights()       # {ticker: weight in [0,1]}, sums ≤ 1
        ca_w = await self._cross_asset_sleeve_weights()   # {etf: weight}, sums ≤ 1 (de-risked)

        e = float(self.params.get("equity_sleeve_weight", 0.40))
        c = float(self.params.get("cross_asset_weight", 0.60))
        target: dict[str, float] = {}
        for sym, w in eq_w.items():
            target[sym.upper()] = target.get(sym.upper(), 0.0) + e * w
        for sym, w in ca_w.items():
            target[sym.upper()] = target.get(sym.upper(), 0.0) + c * w

        target = await self._maybe_beta_cap(target)  # PORT-001 lever #2 (de-risk only; default OFF)

        held = await self._current_holdings()
        await self._apply_targets(target, held=held, reason="rebalance")

    async def _maybe_beta_cap(self, target: dict[str, float]) -> dict[str, float]:
        """Look-through equity-beta-cap governor (PORT-001 lever #2, spec §11 #2 / §6.2). De-risk-only:
        if the book's equity-beta risk contribution exceeds ``beta_cap_max_rc``, scale the equity-beta
        names down (raising cash). When ``enforce_beta_cap`` is False but ``beta_cap_report_only`` is True
        the would-be haircut is LOGGED but NOT applied — the live dry-run. Fail-open (any error / thin
        panel → book unchanged)."""
        enforce = bool(self.params.get("enforce_beta_cap", False))
        report_only = bool(self.params.get("beta_cap_report_only", True))
        if not (enforce or report_only):
            return target
        names = [s for s in target if target[s] > 0]
        if len(names) < 3:
            return target
        try:
            lookback = int(self.params.get("beta_cap_lookback", 120))
            panel = await self._close_panel(names, lookback + 10)
            rets = None if panel is None else panel.pct_change().dropna(how="any")
            if rets is None or rets.shape[0] < 3:
                await self.ctx.log_signal(
                    "PORTFOLIO", SignalType.INFO,
                    payload={"reason": "beta_cap_skip", "note": "insufficient return panel"})
                return target
            new_target, report = cap_equity_beta(
                target, rets, equity_names=default_equity_names(names),
                cap=float(self.params.get("beta_cap_max_rc", 0.80)),
                lookback=lookback,
                shrink=float(self.params.get("beta_cap_shrink", 0.15)))
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.INFO,
                payload={"reason": "beta_cap", "enforced": enforce, **report})
            return new_target if enforce else target
        except Exception as exc:
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.INFO,
                payload={"reason": "beta_cap_failopen", "error": str(exc)[:160]})
            return target

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
        n_fixed = self.params.get("equity_fixed_n")
        if n_fixed:
            k = min(int(n_fixed), len(eligible))
        else:
            q = float(self.params.get("equity_top_quantile", 0.40))
            k = max(1, math.ceil(len(eligible) * q))
        names = [str(t) for t in eligible.sort_values("score", ascending=False).index[:k]]
        # v1.3 (CF-2 corrected scope): the 4% per-name cap applies INSIDE the sleeve.
        cap = float(self.params.get("max_position_pct", 0.04))
        w = min(1.0 / len(names), cap)
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
            vol_target=float(self.params.get("ca_vol_target", 0.10)),
            corr_aware=bool(self.params.get("ca_corr_aware", False)),
            corr_lambda=float(self.params.get("ca_corr_lambda", 0.5)),
            corr_lookback=int(self.params.get("ca_corr_lookback", 60)),
            corr_floor=float(self.params.get("ca_corr_floor", 0.0)),
            corr_cap=float(self.params.get("ca_corr_cap", 2.0)),
            corr_proxy=str(self.params.get("ca_corr_proxy", "SPY")))
        if sleeve.status != "ok":
            return {}
        w = {k.upper(): float(v) for k, v in sleeve.weights.items() if v > 0}
        # v1.3 (C40): cross-asset per-name cap, BOOK-level, applied PRE-BLEND inside
        # the sleeve: min(w, ca_book_cap / cross_asset_weight). Truncation — never a
        # post-blend global cap (settled spec, parity-proven semantics).
        cap_book = self.params.get("ca_book_cap")
        if cap_book:
            c = float(self.params.get("cross_asset_weight", 0.60)) or 1.0
            cap_i = float(cap_book) / c
            w = {s: min(x, cap_i) for s, x in w.items()}
        return w

    async def _maybe_prefetch_distributions(self) -> None:
        """PORT-001 #3 — total-return live pricing (DEFAULT OFF). When enabled (or in report-only), fetch
        the cross-asset ETFs' distributions once for this rebalance, log an evidence signal (pricing
        method + provider metadata + raw-vs-TR divergence), and — only when *enabled* — arm
        ``_close_panel`` to price on total-return closes. Fail-open: any provider error ⇒ raw closes."""
        self._dist_provider = None
        use_tr = bool(self.params.get("use_total_return_pricing", False))
        report_only = bool(self.params.get("tr_pricing_report_only", False))
        sid = str(self.ctx.strategy_id)
        metrics.pricing_mode.labels(strategy_id=sid).set(1 if use_tr else 0)
        if not (use_tr or report_only):
            return

        symbols = self._cross_asset_symbols()
        need = int(self.params.get("ca_lookback_days", 252)) + int(self.params.get("ca_skip_days", 21)) \
            + max(int(self.params.get("ca_vol_lookback_days", 60)), int(self.params.get("beta_cap_lookback", 120))) + 5
        end = datetime.now(UTC)
        start = end - timedelta(days=int(need * 1.5) + 40)
        provider = AlpacaDistributionsProvider()
        summary = await provider.prefetch(symbols, start, end)
        if summary.fallback:
            metrics.total_return_fail_open_total.labels(strategy_id=sid).inc()
        elif use_tr:
            self._dist_provider = provider  # arm the panel only when enabled and the fetch succeeded

        divergence = {} if summary.fallback else await self._tr_divergence_bps(provider, symbols, need)
        await self.ctx.log_signal(
            "PORTFOLIO", SignalType.INFO,
            payload={
                "reason": "total_return_pricing",
                "pricing_method": "TOTAL_RETURN" if (use_tr and not summary.fallback) else "RAW",
                "report_only": report_only and not use_tr,
                "provider": summary.provider, "provider_sdk": summary.provider_sdk,
                "fetched_at": summary.fetched_at, "window": list(summary.window),
                "symbols": summary.symbols, "dividends": summary.dividends, "splits": summary.splits,
                "rejected": summary.rejected, "fallback": summary.fallback,
                "elapsed_ms": summary.elapsed_ms, "divergence_bps": divergence,
            })

    async def _tr_divergence_bps(
        self, provider: AlpacaDistributionsProvider, symbols: list[str], n: int
    ) -> dict[str, float]:
        """Per-symbol trailing-return delta (total-return − raw), in basis points — the report-only
        evidence of what enabling TR pricing would change. Read-only; skips symbols without bars."""
        out: dict[str, float] = {}
        for sym in symbols:
            bars = await self.ctx.get_recent_bars(sym, "1Day", n=n)
            if bars is None or bars.empty or len(bars) < 2:
                continue
            raw = pd.Series(bars["c"].astype(float).to_numpy(),
                            index=pd.to_datetime(bars["t"]).dt.tz_localize(None).dt.normalize())
            div, spl = provider.distributions(sym, raw.index[0], raw.index[-1])
            tri = total_return_index(raw, div, spl)
            if raw.iloc[0] > 0 and tri.iloc[0] > 0:
                raw_ret = raw.iloc[-1] / raw.iloc[0] - 1.0
                tr_ret = tri.iloc[-1] / tri.iloc[0] - 1.0
                out[sym.upper()] = round((tr_ret - raw_ret) * 1e4, 2)
        return out

    async def _close_panel(self, symbols: list[str], n: int) -> pd.DataFrame | None:
        """Daily-close price panel (index = date, cols = symbol) over the common dates, for the
        cross-asset sleeve. None if no symbol has bars. When TR pricing is armed
        (``_maybe_prefetch_distributions``), each priced series is a total-return index instead of the
        raw close (raw + distributions); symbols absent from the distributions cache stay raw."""
        series: dict[str, pd.Series] = {}
        for sym in symbols:
            bars = await self.ctx.get_recent_bars(sym, "1Day", n=n)
            if bars is None or bars.empty:
                continue
            s = pd.Series(bars["c"].astype(float).to_numpy(),
                          index=pd.to_datetime(bars["t"]).dt.tz_localize(None).dt.normalize())
            if self._dist_provider is not None:
                div, spl = self._dist_provider.distributions(sym, s.index[0], s.index[-1])
                if len(div) or len(spl):
                    s = total_return_index(s, div, spl)
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

        equity = await self._investable_equity()  # investable = account * (1 - buffer)
        buffer = Decimal(str(self.params.get("cash_buffer_pct", 0.02)))
        account_equity = equity / (Decimal(1) - buffer)
        floor_usd = Decimal(str(self.params.get("trade_floor_usd", 50.0)))
        rel = Decimal(str(self.params.get("trade_rel_pct", 0.03)))
        ceil_pct = Decimal(str(self.params.get("trade_ceiling_equity_pct", 0.0010)))
        fractional = bool(self.params.get("fractional_shares", True))

        buys: list[tuple[str, Decimal, float, Decimal]] = []
        skipped: list[tuple[str, Decimal, float]] = []  # operational-debt telemetry
        for sym, weight in sorted(target.items()):
            # v1.3 (CF-2 remediation): NO global post-blend cap — caps live inside
            # the sleeves. Sizing is the raw blended weight.
            notional = equity * Decimal(str(weight))
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
            # v1.3 bounded hybrid threshold (C40): applies to entries AND held-name
            # deltas. Structural exemption is EXITS ONLY (phase 1 above) — the exact
            # behavior the sealed C40 walk-forward and parity proof validated; governor-
            # and cap-driven PARTIAL trims remain thresholded. Mandatory account-level
            # risk actions (circuit breakers, daily-loss, operator de-risking) are
            # enforced OUTSIDE this template via the risk engine and OrderRouter and
            # cannot be suppressed here (owner ruling 2026-07-28).
            threshold = max(floor_usd, min(rel * notional, ceil_pct * account_equity))
            if abs(delta) * price_d < threshold:
                skipped.append((sym, delta * price_d, weight))
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

        # Operational-debt telemetry (owner requirement 2026-07-28): sub-threshold partial
        # deltas are ACCUMULATED in-memory (streak + cumulative reset when the name trades
        # or its residual clears; state resets on reload — telemetry, not evidence) and
        # logged every rebalance with symbol, notional, account weight, sleeve, risk
        # direction, and persistence. Residuals are REPORTED operational debt, never a
        # silent loss of target fidelity.
        ca_set = {s.upper() for s in self._cross_asset_symbols()}
        seen: set[str] = set()
        for sym, delta_usd, _w in skipped:
            seen.add(sym)
            self._skipped_streak[sym] = self._skipped_streak.get(sym, 0) + 1
            self._skipped_cum[sym] = self._skipped_cum.get(sym, Decimal(0)) + abs(delta_usd)
        for sym in list(self._skipped_streak):
            if sym not in seen:
                self._skipped_streak.pop(sym, None)
                self._skipped_cum.pop(sym, None)
        if skipped:
            await self.ctx.log_signal(
                "PORTFOLIO", SignalType.INFO,
                payload={
                    "reason": "trade_threshold_operational_debt",
                    "total_abs_usd": float(round(sum(abs(d) for _, d, _ in skipped), 2)),
                    "skipped": [
                        {"symbol": s, "delta_usd": float(round(d, 2)),
                         "pct_equity": float(round(d / account_equity * 100, 4)),
                         "sleeve": "cross_asset" if s in ca_set else "equity",
                         "direction": "risk_reducing" if d < 0 else "risk_increasing",
                         "consecutive_rebalances": self._skipped_streak.get(s, 1),
                         "cum_abs_usd": float(round(self._skipped_cum.get(s, Decimal(0)), 2))}
                        for s, d, _w in skipped],
                })

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
