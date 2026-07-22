"""momentum-daily — Workstream B: daily-evaluation, condition-driven momentum book (proposal v1.1 §5).

The NEW strategy of the v1.1 split (§2.2). It shares the corrected v0.9 signal (A1 dual momentum
filter, A2 absolute-rank bands, A3 12-1 window, A5 bounded regime) but replaces the weekly forced
rebalance with the Stage-2 policy: EVALUATE every trading day after the close, and TRADE only when a
pre-registered condition fires. Monday is a mandatory REVIEW, not a mandatory trade.

It is deployed as a separate registration on its own paper account, alongside the corrected v0.9
baseline, and must pass the full Stage 1-4 validation and the promotion gates before any status
change. It never overwrites or outranks the baseline by incumbency ("discovery is not deployment").

WHY A SEPARATE, SELF-CONTAINED FILE. The loader execs a template by file path, so template-to-
template subclassing is fragile; and §2.2 requires a NEW strategy row, not a mutation of the v0.9
one. So the selection logic is reproduced here rather than imported from `momentum_portfolio`. The
two must not drift; a future refactor may lift the shared selection into an app-level core once both
have validated.

THE SIX TRIGGERS (§5.1) — trade only when one fires; log WHICH one (attribution is mechanical):
  exit_rank_breach       a holding ranks worse than hold_rank on `exit_confirm_closes` closes
  candidate_displacement a name at rank <= entry_rank beats the weakest holding by >= 0.30 z
  raw_momentum_negative  a holding's RAW momentum turns <= 0  -> immediate reduce/exit
  regime_change          the market-regime state flips        -> follow regime rules immediately
  weight_drift           a position's weight drifts > drift_pct from target
  scheduled_backstop     no completed review in `backstop_max_days` trading days

DURABLE STATE (the Workstream B prerequisite, ctx.get_state/set_state). The daily latch, the
rebalance lifecycle (signal_date / attempted_at / completed_at — A4) and the last-review date all
live in `strategy_state`, so they survive a restart or reload. An in-memory counter would be silently
reset by a reload, and the exit-confirmation and backstop discipline would misfire exactly when the
book is active enough to warrant one.

STORM GUARD. The engine dispatches per symbol per tick (~200x). A durable once-per-day latch keyed on
the tick date makes at most one evaluation per day; a failed evaluation is retried a bounded number
of times WITHIN the day rather than re-run on the next symbol in the same tick.

CONSTRUCTION / REGIME / UNIVERSE knobs (§6/§7/§8) are parameters DEFAULTED TO THE STAGE 2-4 VALIDATED
CONFIG (5 names, equal weight, no sector cap, GRADUATED regime, fixed universe) — see
`docs/implementation/evidence/momentum_daily_stage2_4/`. Stage 3 REFUTED both widening priors (8-10
names and the sector cap each cost Sharpe), so those defaults are unchanged from the baseline by
EVIDENCE, not by inertia; Stage 4 replaced the binary regime default with `graduated` (binary scored
worse than no filter at all — whipsaw). The losing variants stay wired and off. Defaults move only
when a stage says so; validation is not activation (promotion is separately gated).

No broker/DB/network access beyond the sandboxed ctx; no LLM (ADR 0006 v2). Every order flows through
ctx.submit_order -> OrderRouter + the risk engine (ADR 0002).
"""

from __future__ import annotations

import asyncio
import math
from dataclasses import replace
from decimal import Decimal
from typing import Any, ClassVar

from app.db.enums import OrderSide, OrderSourceType, OrderType, SignalType, TimeInForce
from app.factor_data.accessor import FactorDataUnavailable
from app.factor_data.factors.engine import FactorUnavailable
from app.factor_data.universe import UniverseUnavailable
from app.risk import OrderRequest
from app.strategies import Strategy
from app.strategies.deployment_state import (
    DeploymentBlob,
    DeploymentStateInvalid,
    DeploymentStateUninitialized,
    load_deployment_blob,
    seed_attempt_to_dict,
)
from app.strategies.seed_reconciliation import (
    DeploymentState,
    SeedAttempt,
    SeedAttemptStatus,
    reconcile_seed_attempt,
)

_HOLD_ON = (FactorDataUnavailable, FactorUnavailable, UniverseUnavailable)
_TERMINAL_ATTEMPT = frozenset({SeedAttemptStatus.FILLED, SeedAttemptStatus.TERMINALLY_UNFILLED})

# Durable-state keys.
_K_LAST_EVAL = "last_eval_date"          # ISO date of the last completed daily evaluation (the latch)
_K_LAST_REVIEW = "last_review_date"      # ISO date of the last completed review (backstop clock)
_K_LIFECYCLE = "rebalance_lifecycle"     # {signal_date, attempted_at, completed_at, attempts}
_K_REGIME = "prev_regime"                # {"gross": float} | {"below": bool} — last regime state seen
_K_DEPLOYMENT = "deployment"             # P7 §7-A: the atomic _rev-versioned deployment-lifecycle blob


class MomentumDaily(Strategy):
    name: ClassVar[str] = "momentum-daily"
    version: ClassVar[str] = "0.2.0"     # Workstream B — Stage 2-4 validated config (graduated regime); paper, promotion-gated
    symbols: ClassVar[list[str]] = []
    # Post-close daily evaluation. Day names (the dow off-by-one bites numeric cron). ~16:10 ET.
    schedule: ClassVar[str] = "10 21 * * mon-fri"

    default_params: ClassVar[dict[str, Any]] = {
        # ---- signal (shared with v0.9: A1 dual filter, A3 12-1 window) ----
        "momentum_lookback_days": 252,
        "momentum_skip_days": 21,
        "min_score": 0.0,                # z-score floor (relative)
        "min_raw_momentum": 0.0,         # A1 raw floor (absolute)
        # ---- absolute-rank bands (A2) + replacement ----
        "entry_rank": 5,
        "hold_rank": 10,
        "exit_confirm_closes": 2,
        "replace_score_advantage": 0.30,
        # ---- the six triggers (§5.1) ----
        "weight_drift_pct": 0.04,        # trigger a weight-maintenance trade past this drift
        "backstop_max_days": 10,         # force a review after this many trading days without one
        "max_daily_retries": 3,          # bounded same-day retries on a failed evaluation (A4)
        # ---- construction (§6 — Stage 3, defaulted to baseline) ----
        "max_names": 5,
        "max_position_pct": 0.20,
        "max_sector_pct": None,          # sector cap OFF (Stage 3 turns it on under test)
        # SIZING IS EQUAL WEIGHT AND ONLY EQUAL WEIGHT (owner adjudication 2026-07-22). At N=5 a
        # hard 20% per-name cap makes equal weight the ONLY feasible fully-invested portfolio, so
        # the Stage-3 "hybrid_50_50" arm was never a distinct feasible strategy here — its
        # 19.2-20.6% weights are the residual of a clamp loop that stops before satisfying its own
        # constraint. See the weighting-defect erratum. `invvol_hybrid` is NOT a supported value.
        "weighting": "equal",            # "equal" ONLY — any other value fails closed in on_init
        "min_weight_pct": 0.075,
        # ---- regime (§7 — Stage-4 VALIDATED: graduated wins decisively; binary is worst) ----
        "use_market_regime_filter": True,
        "market_filter_symbol": "SPY",
        "market_ma_days": 200,
        "regime_mode": "graduated",      # "graduated" (Stage-4 winner) | "binary" (variant A/B)
        "regime_graduated_band_pct": 0.02,   # ±band around the MA (graduated)
        "regime_gross_above": 0.98,      # gross clearly above the MA
        "regime_gross_mid": 0.60,        # gross inside the ±band
        "regime_gross_below": 0.15,      # gross clearly below the MA
        "regime_buffer_pct": 0.0,        # binary mode only: 0 = plain binary; >0 = §7 variant B buffer
        "regime_confirm_days": 1,        # binary mode only
        "regime_stale_max_days": 2,      # A5 bounded fallback (both modes)
        "regime_degraded_gross": 0.50,
        "regime_degraded_max_days": 4,
        # ---- cold-start inception (§7-A) ----
        "initial_seed_investable_gross": 0.60,   # LOCKED: seed a NEVER_DEPLOYED book only at regime gross >= this
        # ---- universe (§8 — Stage, fixed baseline) ----
        "monthly_universe_refresh": False,
        # ---- execution ----
        "min_trade_pct": 0.03,
        "pricing_timeframe": "1Day",
        "fractional_shares": True,
        "cash_buffer_pct": 0.02,
        "initial_equity_estimate": 100_000,
        "order_pacing_seconds": 1.0,
        "timeframe": "1Day",
    }

    params_schema: ClassVar[dict[str, Any]] = {
        "momentum_lookback_days": {"type": "integer", "min": 1, "default": 252,
                                   "description": "Momentum lookback (trading days). 252 = 12 months."},
        "momentum_skip_days": {"type": "integer", "min": 0, "default": 21,
                               "description": "Days skipped before the lookback. 21 = the 12-1 skip."},
        "min_score": {"type": "number", "nullable": True, "default": 0.0,
                      "description": "z-score floor (relative). A positive z does not imply positive absolute momentum — see min_raw_momentum."},
        "min_raw_momentum": {"type": "number", "nullable": True, "default": 0.0,
                             "description": "Raw trailing-return floor (absolute). Empty/None = no floor (not recommended)."},
        "entry_rank": {"type": "integer", "min": 1, "default": 5,
                       "description": "Enter a name only at rank <= this."},
        "hold_rank": {"type": "integer", "min": 1, "default": 10,
                      "description": "Keep a held name while rank <= this. Must be >= entry_rank."},
        "exit_confirm_closes": {"type": "integer", "min": 1, "default": 2,
                                "description": "Exit only after rank > hold_rank on this many consecutive closes."},
        "replace_score_advantage": {"type": "number", "min": 0, "default": 0.30,
                                    "description": "A challenger at rank <= entry_rank displaces a holding only with at least this z-score edge."},
        "weight_drift_pct": {"type": "number", "min": 0, "max": 1, "default": 0.04,
                             "description": "Trigger a weight-maintenance trade when a position drifts past this fraction from target."},
        "backstop_max_days": {"type": "integer", "min": 1, "default": 10,
                              "description": "Force a review after this many trading days without a completed one."},
        "max_daily_retries": {"type": "integer", "min": 1, "default": 3,
                              "description": "Bounded same-day retries on a failed evaluation (A4)."},
        "max_names": {"type": "integer", "min": 1, "default": 5,
                      "description": "Names held. Stage 3 sweeps 5/8/10."},
        "max_position_pct": {"type": "number", "min": 0, "max": 1, "default": 0.20,
                             "description": "Hard cap on any single position."},
        "max_sector_pct": {"type": "number", "min": 0, "max": 1, "nullable": True, "default": None,
                           "description": "Per-sector cap (Stage 3). Empty/None = off."},
        "weighting": {"type": "enum", "choices": ["equal"], "default": "equal",
                      "description": "Sizing. EQUAL WEIGHT ONLY: at max_names=5 with a 20% per-name "
                                     "cap, equal weight is the only feasible fully-invested "
                                     "portfolio, so no inverse-vol tilt is expressible. Any other "
                                     "value is rejected at startup."},
        "min_weight_pct": {"type": "number", "min": 0, "max": 1, "default": 0.075,
                           "description": "Unused while weighting is equal-only; retained for "
                                          "schema stability. Has no effect on sizing."},
        "use_market_regime_filter": {"type": "boolean", "default": True,
                                     "description": "Apply the market-trend regime filter (de-gross in a downtrend)."},
        "market_filter_symbol": {"type": "string", "default": "SPY",
                                 "description": "Market proxy (must be in the registered symbols)."},
        "market_ma_days": {"type": "integer", "min": 20, "default": 200,
                           "description": "Regime moving-average window."},
        "regime_mode": {"type": "enum", "choices": ["graduated", "binary"], "default": "graduated",
                        "description": "graduated (Stage-4 winner: gross steps with distance from MA) | binary (100/0 above/below; whipsaws — Stage-4 worst)."},
        "regime_graduated_band_pct": {"type": "number", "min": 0, "max": 1, "default": 0.02,
                                      "description": "Graduated: ±band around the MA defining the mid-gross zone."},
        "regime_gross_above": {"type": "number", "min": 0, "max": 1, "default": 0.98,
                               "description": "Graduated gross when clearly above the MA."},
        "regime_gross_mid": {"type": "number", "min": 0, "max": 1, "default": 0.60,
                             "description": "Graduated gross inside the ±band."},
        "regime_gross_below": {"type": "number", "min": 0, "max": 1, "default": 0.15,
                               "description": "Graduated gross when clearly below the MA."},
        "regime_buffer_pct": {"type": "number", "min": 0, "max": 1, "default": 0.0,
                              "description": "Binary mode only: crossing buffer (§7 variant B). 0 = plain binary."},
        "regime_confirm_days": {"type": "integer", "min": 1, "default": 1,
                                "description": "Consecutive closes required to flip regime (§7 variant B). 1 = baseline."},
        "regime_stale_max_days": {"type": "integer", "min": 0, "default": 2,
                                  "description": "Reuse the last regime for this many days on missing data before stepping gross down (A5)."},
        "regime_degraded_gross": {"type": "number", "min": 0, "max": 1, "default": 0.50,
                                  "description": "Gross multiplier once regime data is staler than regime_stale_max_days."},
        "regime_degraded_max_days": {"type": "integer", "min": 1, "default": 4,
                                     "description": "Beyond this staleness, gross goes to zero."},
        "initial_seed_investable_gross": {"type": "number", "min": 0, "max": 1, "default": 0.60,
                                          "description": "Inception eligibility ONLY (LOCKED 0.60): seed a never-deployed book when regime_target_gross >= this. Not a warm-book regime control."},
        "monthly_universe_refresh": {"type": "boolean", "default": False,
                                     "description": "Refresh the registered universe monthly (§8). Baseline = fixed."},
        "min_trade_pct": {"type": "number", "min": 0, "max": 1, "default": 0.03,
                          "description": "Skip order legs smaller than this fraction of target notional."},
        "pricing_timeframe": {"type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"],
                              "default": "1Day", "description": "Bar timeframe used to price names."},
        "fractional_shares": {"type": "boolean", "default": True,
                              "description": "Size fractional quantities (deploys ~fully)."},
        "cash_buffer_pct": {"type": "number", "min": 0, "max": 1, "default": 0.02,
                            "description": "Fraction of equity held back as cash."},
        "initial_equity_estimate": {"type": "number", "min": 0, "default": 100_000,
                                    "description": "Fallback equity when no live snapshot exists."},
        "order_pacing_seconds": {"type": "number", "min": 0, "max": 60, "default": 1.0,
                                 "description": "Delay between order submissions (spreads the burst under the rate cap)."},
        "timeframe": {"type": "enum", "choices": ["5Min", "15Min", "1Hour", "1Day"],
                      "default": "1Day", "description": "Engine dispatch bar timeframe."},
    }

    async def on_init(self) -> None:
        self._equity_estimate = Decimal(str(self.params.get("initial_equity_estimate", 100_000)))
        entry = int(self.params.get("entry_rank", 5))
        hold = int(self.params.get("hold_rank", 10))
        if hold < entry:
            raise ValueError(
                f"incoherent rank bands: hold_rank={hold} < entry_rank={entry} — a name would be "
                f"sold the day it is bought"
            )
        # FAIL CLOSED on any sizing this template does not implement. A stored param row from
        # before the weighting-defect adjudication could still carry "invvol_hybrid"; silently
        # ignoring it would be exactly the schema/code drift this repo treats as a defect class.
        weighting = str(self.params.get("weighting", "equal"))
        if weighting != "equal":
            raise ValueError(
                f"unsupported weighting={weighting!r}: momentum-daily sizes equal-weight only. "
                f"At max_names=5 with max_position_pct=0.20 equal weight is the only feasible "
                f"fully-invested portfolio; an inverse-vol tilt is not expressible and is not "
                f"implemented. Rejecting rather than silently sizing equal-weight anyway."
            )
        await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
            "reason": "effective_params", "version": self.version,
            "window": f"{self.params.get('momentum_lookback_days')}/"
                      f"{self.params.get('momentum_skip_days')}",
            "entry_rank": entry, "hold_rank": hold,
            "schedule": self.schedule, "policy": "daily_evaluation_conditional_trading",
        })

    # ---- daily evaluation ----

    async def on_bar(self, bar: Any) -> None:
        """One post-close daily evaluation. The engine calls this per symbol per tick; a DURABLE
        once-per-day latch makes at most one evaluation per calendar day, surviving restarts."""
        day = (bar.t.date() if hasattr(bar.t, "date") else bar.t).isoformat()
        self._tick_date = bar.t.date() if hasattr(bar.t, "date") else bar.t
        self._tick_ts = bar.t  # datetime — the deterministic clock for a seed attempt (sub-step 2)

        # P7 §7-A.2b: load+validate the deployment blob and reconcile any active seed
        # attempt BEFORE the daily latch — a fill can land after today's evaluation or
        # on a same-day restart, and lifecycle state must still advance. Fail closed on
        # uninitialized/invalid/ambiguous state (submit nothing).
        dep = await self._load_and_validate_deployment()
        if dep is None:
            return
        dep = await self._reconcile_active_seed_attempt(dep)
        if dep is None:
            return

        if await self.ctx.get_state(_K_LAST_EVAL) == day:
            return  # already evaluated today (durable latch — not an in-memory flag)

        lifecycle = await self.ctx.get_state(_K_LIFECYCLE, {}) or {}
        attempts = int(lifecycle.get("attempts", 0)) if lifecycle.get("signal_date") == day else 0
        if attempts >= int(self.params.get("max_daily_retries", 3)):
            await self.ctx.set_state(_K_LAST_EVAL, day)   # give up for today; the backstop still runs
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "daily_eval_retries_exhausted", "date": day, "attempts": attempts})
            return

        # A4 — record the ATTEMPT before evaluating, so a crash mid-evaluation is a bounded retry,
        # not a silent skip until tomorrow.
        await self.ctx.set_state(_K_LIFECYCLE, {
            "signal_date": day, "attempted_at": day, "attempts": attempts + 1,
            "completed_at": lifecycle.get("completed_at"),
        })
        try:
            await self._evaluate(day, dep)
        except Exception as exc:  # noqa: BLE001 — contain; the same-day retry budget covers it
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "daily_eval_failed", "date": day, "error": str(exc)[:160]})
            return
        # completed: mark the latch + lifecycle + review clock.
        await self.ctx.set_state(_K_LAST_EVAL, day)
        await self.ctx.set_state(_K_LAST_REVIEW, day)
        await self.ctx.set_state(_K_LIFECYCLE, {
            "signal_date": day, "attempted_at": day, "completed_at": day,
            "attempts": attempts + 1})

    # ---- P7 §7-A.2b: deployment lifecycle (read-side) ----

    async def _load_and_validate_deployment(self) -> DeploymentBlob | None:
        """Load + FAIL-CLOSED-validate the deployment blob. Returns None (and logs the
        reason) on an uninitialized or invalid/impossible state — the caller submits
        nothing this tick. 7-B performs the authoritative first init."""
        raw = await self.ctx.get_state(_K_DEPLOYMENT)
        try:
            return load_deployment_blob(raw)
        except DeploymentStateUninitialized:
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "deployment_state_uninitialized"})
            return None
        except DeploymentStateInvalid as exc:
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "deployment_state_invalid", "error": str(exc)[:160]})
            return None

    async def _reconcile_active_seed_attempt(self, dep: DeploymentBlob) -> DeploymentBlob | None:
        """Reconcile an active NON-TERMINAL seed attempt from live observations and
        CAS-apply the result. Returns the fresh blob to evaluate against, or None to
        block normal evaluation (CAS lost, or a blocking reconciliation-required)."""
        attempt = dep.active_seed_attempt
        if attempt is None or attempt.status in _TERMINAL_ATTEMPT:
            return await self._detect_unexpected_flatten(dep)

        fills = await self.ctx.recent_fills(
            since=attempt.last_reconciled_fill_at or attempt.created_at,
            after_fill_id=attempt.last_reconciled_fill_id,
            client_order_id_prefix=attempt.client_order_id_prefix,
        )
        open_orders = await self.ctx.open_orders(
            client_order_id_prefix=attempt.client_order_id_prefix)
        positions = await self._current_holdings()
        result = reconcile_seed_attempt(attempt, fills, open_orders, positions)

        cursor = result.committed_cursor
        new_attempt = replace(
            attempt, status=result.seed_attempt_status,
            last_reconciled_fill_at=cursor[0] if cursor else attempt.last_reconciled_fill_at,
            last_reconciled_fill_id=cursor[1] if cursor else attempt.last_reconciled_fill_id,
        )
        # first_deployed_at is monotonic (preserve once set); has_ever_deployed one-shot.
        first_dep = dep.first_deployed_at or result.first_deployed_at
        has_ever = dep.has_ever_deployed or (result.deployment_state == DeploymentState.DEPLOYED)
        if result.should_clear_attempt:
            last = seed_attempt_to_dict(new_attempt)  # ARCHIVE terminal attempt (not delete)
            active = None
        else:
            last, active = dep.last_seed_attempt, new_attempt
        new_blob = DeploymentBlob(
            rev=dep.rev + 1, state=result.deployment_state, has_ever_deployed=has_ever,
            first_deployed_at=first_dep, active_seed_attempt=active, last_seed_attempt=last)

        ok = await self.ctx.compare_and_set_state(
            _K_DEPLOYMENT, expected_rev=dep.rev, new_value=new_blob.to_dict())
        if not ok:
            # Concurrency loss: another writer advanced the blob. Reload next tick; do
            # NOT evaluate against stale state now.
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "reconcile_cas_lost"})
            return None
        for alert in result.alerts:
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "seed_alert", "alert": alert})
        if result.seed_attempt_status == SeedAttemptStatus.RECONCILIATION_REQUIRED:
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "seed_reconciliation_required", "alerts": list(result.alerts)})
            return None
        return new_blob

    async def _detect_unexpected_flatten(self, dep: DeploymentBlob) -> DeploymentBlob | None:
        """A DEPLOYED book observed flat with no active attempt is an anomaly the
        template cannot attribute (risk liquidation / manual flatten / account
        intervention are 7-B's to classify). Alert and fail closed — never INVENT an
        INTENTIONALLY_FLAT cause the template cannot prove."""
        if dep.state == DeploymentState.DEPLOYED and not await self._current_holdings():
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "unexpected_flatten_detected"})
            return None
        return dep

    async def _maybe_initial_seed(self, day: str, dep: DeploymentBlob, regime_gross: float,
                                  scores: Any, held: dict[str, Decimal]) -> None:
        """Evaluate the six inception gates (each traced); on all-pass, CAS a PREPARED
        attempt (write-ahead) BEFORE any submission, then submit incrementally. A CAS
        loss is a normal concurrency loss — reload next tick, submit nothing."""
        eligible = self._eligible(scores)
        pending = await self.ctx.open_orders(
            client_order_id_prefix=f"seed:{self.ctx.strategy_id}:")
        threshold = float(self.params.get("initial_seed_investable_gross", 0.60))
        gates = {
            "no_holdings": not held,
            "no_pending_entries": not pending,
            "never_deployed": (dep.state == DeploymentState.NEVER_DEPLOYED
                               and not dep.has_ever_deployed),
            "regime_investable": regime_gross >= threshold,
            "scores_available": True,
            "eligible_candidates": len(eligible) >= 1,
        }
        await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
            "reason": "initial_seed_eval", "date": day, "gates": gates,
            "regime_target_gross": regime_gross, "candidates": int(len(eligible))})
        if not all(gates.values()):
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "reviewed_no_trigger", "date": day, "held": sorted(held),
                "seed_gates_failed": [k for k, v in gates.items() if not v]})
            return

        target = self._select_targets(scores, held)
        if not target:
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "reviewed_no_trigger", "date": day, "seed_no_targets": True})
            return
        attempt_number = int((dep.last_seed_attempt or {}).get("attempt_number", 0)) + 1
        attempt_id = f"{day}-{attempt_number}"
        prefix = f"seed:{self.ctx.strategy_id}:{attempt_id}:"
        if any(len(f"{prefix}{s.upper()}") > 64 for s in target):  # broker/DB client-id cap
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "initial_seed_prefix_too_long", "prefix": prefix})
            return
        attempt = SeedAttempt(
            attempt_id=attempt_id, created_at=self._tick_ts, intended_symbols=tuple(target),
            client_order_id_prefix=prefix, status=SeedAttemptStatus.PREPARED)
        prepared = DeploymentBlob(
            rev=dep.rev + 1, state=DeploymentState.DEPLOYMENT_PENDING, has_ever_deployed=False,
            first_deployed_at=None, active_seed_attempt=attempt,
            last_seed_attempt=dep.last_seed_attempt)
        if not await self.ctx.compare_and_set_state(
                _K_DEPLOYMENT, expected_rev=dep.rev, new_value=prepared.to_dict()):
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "initial_seed_cas_lost", "date": day})
            return
        await self._submit_seed(prepared, target, scores, held, attempt_number)

    async def _submit_seed(self, blob: DeploymentBlob, target: list[str], scores: Any,
                           held: dict[str, Decimal], attempt_number: int) -> None:
        """Incremental CAS-persisted submission. Every status update is a CAS. The
        durable submission LEDGER (not open_orders emptiness) decides the terminal
        outcome: any accepted order -> ORDERS_OPEN; every intended order rejected/
        skipped -> TERMINALLY_UNFILLED -> ARCHIVE -> NEVER_DEPLOYED (retry). Ongoing
        reconciliation (on_bar; prefix recovery over fills AND open orders) advances
        ORDERS_OPEN thereafter. The client_order_id tag makes a crash between submit
        and status-persist recoverable by prefix."""
        attempt = blob.active_seed_attempt
        submitting = replace(attempt, status=SeedAttemptStatus.SUBMITTING)
        b_sub = DeploymentBlob(
            rev=blob.rev + 1, state=DeploymentState.DEPLOYMENT_PENDING, has_ever_deployed=False,
            first_deployed_at=None, active_seed_attempt=submitting,
            last_seed_attempt=blob.last_seed_attempt)
        if not await self.ctx.compare_and_set_state(
                _K_DEPLOYMENT, expected_rev=blob.rev, new_value=b_sub.to_dict()):
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "initial_seed_cas_lost"})
            return

        outcomes: list[dict[str, Any]] = []
        await self._apply_targets(target, held=held, reason="initial_seed",
                                  attempt=attempt, outcomes=outcomes)
        accepted = [o for o in outcomes if o.get("ok")]

        if accepted:
            final = replace(submitting, status=SeedAttemptStatus.ORDERS_OPEN)
            b_fin = DeploymentBlob(
                rev=b_sub.rev + 1, state=DeploymentState.DEPLOYMENT_PENDING,
                has_ever_deployed=False, first_deployed_at=None, active_seed_attempt=final,
                last_seed_attempt=blob.last_seed_attempt)
        else:
            archived = seed_attempt_to_dict(
                replace(submitting, status=SeedAttemptStatus.TERMINALLY_UNFILLED))
            archived["attempt_number"] = attempt_number
            archived["previous_attempt_id"] = (blob.last_seed_attempt or {}).get("attempt_id")
            b_fin = DeploymentBlob(
                rev=b_sub.rev + 1, state=DeploymentState.NEVER_DEPLOYED, has_ever_deployed=False,
                first_deployed_at=None, active_seed_attempt=None, last_seed_attempt=archived)
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "initial_seed_all_rejected", "attempt_id": attempt.attempt_id})
        await self.ctx.compare_and_set_state(
            _K_DEPLOYMENT, expected_rev=b_sub.rev, new_value=b_fin.to_dict())

    async def _evaluate(self, day: str, dep: DeploymentBlob) -> None:
        """Score, decide which triggers fire, and trade ONLY if one does."""
        regime_below, regime_gross, regime_flipped = await self._regime()
        self._regime_gross = regime_gross

        # A regime flip to risk-off is itself a trigger — act immediately.
        if regime_below is True or regime_gross <= 0.0:
            await self._apply_targets([], reason="regime_change" if regime_flipped
                                      else "regime_bear_cash")
            return

        try:
            n = len(self.ctx.symbols) or None
            mom_kw = {"lookback_days": int(self.params.get("momentum_lookback_days", 252)),
                      "skip_days": int(self.params.get("momentum_skip_days", 21))}
            scores = (self.ctx.factors.momentum_scores(n=n, **mom_kw) if n
                      else self.ctx.factors.momentum_scores(**mom_kw))
        except _HOLD_ON as exc:
            await self.ctx.log_signal("PORTFOLIO", SignalType.EXIT, payload={
                "reason": "factor_unavailable_hold", "error": str(exc)[:120]})
            return

        held = await self._current_holdings()
        self._current_order = {t: i + 1 for i, t in enumerate(self._eligible(scores).index)}
        await self._load_prior_closes()

        # P7 §7-A.2b: cold-start seed path — ONLY for a never-deployed flat book. Regime
        # risk-off and data-unavailable outcomes above still take precedence; the seed
        # gates can only be reached with a risk-on regime and available scores.
        # A seed in flight (DEPLOYMENT_PENDING) is owned by reconciliation (on_bar,
        # before the latch); do not warm-trade while awaiting fills.
        if dep.state == DeploymentState.DEPLOYMENT_PENDING:
            return
        # Cold-start: a never-deployed flat book seeds via initial_seed.
        if dep.state == DeploymentState.NEVER_DEPLOYED and not dep.has_ever_deployed:
            await self._maybe_initial_seed(day, dep, regime_gross, scores, held)
            return

        triggers = await self._fired_triggers(scores, held, regime_flipped)
        backstop_due = await self._backstop_due(day)
        if not triggers and not backstop_due:
            await self.ctx.log_signal("PORTFOLIO", SignalType.INFO, payload={
                "reason": "reviewed_no_trigger", "date": day, "held": sorted(held)})
            return

        target = self._select_targets(scores, held)
        await self._apply_targets(
            target, held=held,
            reason=("+".join(sorted(triggers)) if triggers else "scheduled_backstop"))

    async def _fired_triggers(self, scores: Any, held: dict[str, Decimal],
                              regime_flipped: bool) -> set[str]:
        """Which of the six §5.1 conditions fire this close. Names, so the signals log records WHY a
        trade happened rather than leaving it to be reconstructed."""
        fired: set[str] = set()
        if regime_flipped:
            fired.add("regime_change")
        elig = self._eligible(scores)
        pos = {t: i + 1 for i, t in enumerate(elig.index)}
        score_of = elig["score"].to_dict()
        raw_of = elig["momentum"].to_dict()
        hold_rank = int(self.params.get("hold_rank", 10))
        entry_rank = int(self.params.get("entry_rank", 5))
        advantage = float(self.params.get("replace_score_advantage", 0.30))

        for h in held:
            r = pos.get(h)
            if r is None or raw_of.get(h, 1.0) <= 0.0:
                fired.add("raw_momentum_negative")     # fell out of eligibility (A1) or raw turned <= 0
            elif r > hold_rank and self._exit_confirmed(h, hold_rank):
                fired.add("exit_rank_breach")

        # displacement: a fresh entry-band name that beats the weakest holding by the advantage
        weakest = min((score_of.get(h, 0.0) for h in held), default=None)
        if weakest is not None and len(held) >= int(self.params.get("max_names", 5)):
            for t in list(elig.index)[:entry_rank]:
                if t not in held and score_of.get(t, 0.0) >= weakest + advantage:
                    fired.add("candidate_displacement")
                    break

        if await self._weight_drift_exceeded(held):
            fired.add("weight_drift")
        return fired

    async def _weight_drift_exceeded(self, held: dict[str, Decimal]) -> bool:
        """True if any holding's weight has drifted past weight_drift_pct from the equal target.

        The drift trigger decides WHETHER a maintenance trade happens; `min_trade_pct` then filters
        the individual legs, so a drift trigger never produces a flurry of sub-threshold trims
        (§5.3 ordering). Fails CLOSED on a missing price — no spurious trigger."""
        drift = float(self.params.get("weight_drift_pct", 0.04))
        if not held or drift <= 0:
            return False
        prices: dict[str, float] = {}
        for sym in held:
            p = await self._price(sym)
            if p is None or p <= 0:
                return False
            prices[sym] = p
        values = {s: float(held[s]) * prices[s] for s in held}
        total = sum(values.values())
        if total <= 0:
            return False
        # Target weights come from the sizing seam, not a restated 1/N — drift must be measured
        # against what the order path would actually size. Renormalized over the held names so
        # the comparison is like-for-like against realized weights-of-book (the gross multiplier
        # and cash buffer cancel; they scale both sides).
        seam = {s: float(self._per_name_notional(Decimal(1), len(held))) for s in held}
        seam_total = sum(seam.values())
        if seam_total <= 0:
            return False
        target_w = {s: seam[s] / seam_total for s in held}
        return any(abs(values[s] / total - target_w[s]) > drift for s in held)

    async def _backstop_due(self, day: str) -> bool:
        """§5.1 #6 — force a review if none has completed within backstop_max_days trading days."""
        last = await self.ctx.get_state(_K_LAST_REVIEW)
        if not last:
            return False  # first review sets the clock; not itself overdue
        from datetime import date as _date
        try:
            gap = (_date.fromisoformat(day) - _date.fromisoformat(last)).days
        except Exception:  # noqa: BLE001
            return False
        # trading days ~ calendar days * 5/7; compare generously in calendar days
        return gap >= int(self.params.get("backstop_max_days", 10)) * 7 // 5

    # ---- selection (A1 + A2, shared semantics with v0.9) ----

    def _eligible(self, scores: Any) -> Any:
        market_sym = str(self.params.get("market_filter_symbol", "SPY")).upper()
        allowed = {s.upper() for s in self.ctx.symbols if s.upper() != market_sym}
        e = scores[scores.index.isin(allowed)]
        floor = self.params.get("min_score")
        if floor is not None and floor != "":
            e = e[e["zscore"] >= float(floor)]
        raw = self.params.get("min_raw_momentum")
        if raw is not None and raw != "":
            e = e[e["momentum"] > float(raw)]
        return e.sort_values("score", ascending=False)

    def _select_targets(self, scores: Any, held: dict[str, Decimal]) -> list[str]:
        eligible = self._eligible(scores)
        if eligible.empty:
            return []
        cap = int(self.params.get("max_names", 5))
        entry_rank = int(self.params.get("entry_rank", 5))
        hold_rank = int(self.params.get("hold_rank", 10))
        advantage = float(self.params.get("replace_score_advantage", 0.30))
        ranked = list(eligible.index)
        pos = {t: i + 1 for i, t in enumerate(ranked)}
        score_of = eligible["score"].to_dict()

        keep = [h for h in held if pos.get(h) is not None
                and (pos[h] <= hold_rank or not self._exit_confirmed(h, hold_rank))]
        book = list(keep)
        for t in ranked[:entry_rank]:
            if len(book) >= cap:
                break
            if t not in book:
                book.append(t)
        for t in ranked[:entry_rank]:
            if t in book:
                continue
            weakest = max((b for b in book if b in score_of), key=lambda b: -score_of[b],
                          default=None)
            if weakest is None:
                break
            if score_of[t] >= score_of[weakest] + advantage:
                book[book.index(weakest)] = t
        return [t for t in ranked if t in set(book)][:cap]

    def _exit_confirmed(self, ticker: str, hold_rank: int) -> bool:
        need = int(self.params.get("exit_confirm_closes", 2))
        if need <= 1:
            return True
        frames = getattr(self, "_prior_frames", None)
        if not frames or len(frames) < need - 1:
            return False
        for order in frames[: need - 1]:
            r = order.get(ticker)
            if r is None or r <= hold_rank:
                return False
        return True

    async def _load_prior_closes(self) -> None:
        self._prior_frames: list[dict[str, int]] = []
        need = int(self.params.get("exit_confirm_closes", 2))
        if need <= 1:
            return
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        bars = await self.ctx.get_recent_bars(sym, "1Day", n=need + 4)
        if bars is None or bars.empty or len(bars) < 2:
            return
        try:
            idx = bars.index if getattr(bars.index, "name", None) == "t" else bars["t"]
            dates = [d.date() if hasattr(d, "date") else d for d in list(idx)]
        except Exception:  # noqa: BLE001
            return
        prior = list(dates[:-1])[::-1]
        mom_kw = {"lookback_days": int(self.params.get("momentum_lookback_days", 252)),
                  "skip_days": int(self.params.get("momentum_skip_days", 21))}
        n = len(self.ctx.symbols) or None
        current = getattr(self, "_current_order", None)
        for as_of in prior[: need - 1]:
            try:
                prev = (self.ctx.factors.momentum_scores(as_of=as_of, n=n, **mom_kw) if n
                        else self.ctx.factors.momentum_scores(as_of=as_of, **mom_kw))
            except _HOLD_ON:
                return
            order = {t: i + 1 for i, t in enumerate(self._eligible(prev).index)}
            if current is not None and order == current:
                return  # not a distinct close -> fail closed (no exit confirmed)
            self._prior_frames.append(order)

    # ---- regime (A5 bounded fallback + §7 buffer/confirmation) ----

    async def _regime(self) -> tuple[bool | None, float, bool]:
        """(below_ma, gross_multiplier, flipped_since_last_eval). Never fails open.

        Two modes (§7, Stage-4-validated). ``binary`` (variant A): 100% above the MA, cash below
        (optional buffer/confirmation = variant B). ``graduated`` (variant C — the Stage-4 winner,
        `Stage4_Evidence_Report_v1.0`): gross steps with distance from the MA — ``regime_gross_above``
        clearly above, ``regime_gross_mid`` inside the ±``regime_graduated_band_pct`` band,
        ``regime_gross_below`` clearly below — so the book de-grosses (via ``_investable_equity``)
        rather than flipping fully to cash, avoiding the binary filter's whipsaw. A gross-level change
        is itself a ``regime_change`` trigger. The A5 staleness fallback caps gross in both modes.

        The previous regime lives in DURABLE state (``_K_REGIME``), not on the instance. Graduated has
        no equivalent of binary's ``below is True`` re-entry — that branch re-flattens on every eval
        regardless of ``flipped``, so binary self-corrects after a restart for free. Graduated only
        re-grosses when ``flipped`` fires, so an in-memory latch would read ``None`` after a reload,
        report ``flipped=False``, and strand the book at its pre-restart gross until an unrelated
        trigger or the ``backstop_max_days`` review. A deep bear hides this (``raw_momentum_negative``
        fires anyway); a mild 0.98 -> 0.60 pullback does not.
        """
        if not self.params.get("use_market_regime_filter", True):
            return False, 1.0, False
        sym = str(self.params.get("market_filter_symbol", "SPY"))
        days = int(self.params.get("market_ma_days", 200))
        stale_max = int(self.params.get("regime_stale_max_days", 2))
        degraded_gross = float(self.params.get("regime_degraded_gross", 0.50))
        degraded_max = int(self.params.get("regime_degraded_max_days", 4))

        bars = await self.ctx.get_recent_bars(sym, "1Day", n=days + 1)
        if bars is None or bars.empty or len(bars) < days + 1:
            await self.ctx.log_signal(sym, SignalType.EXIT, payload={
                "reason": "regime_data_unavailable_flat", "gross": 0.0})
            return None, 0.0, False
        ma = float(bars["c"].iloc[:-1].mean())
        last = float(bars["c"].iloc[-1])

        prev_state = await self.ctx.get_state(_K_REGIME, {}) or {}
        mode = str(self.params.get("regime_mode", "graduated"))
        if mode == "graduated":
            # Variant C: distance-from-MA sets gross; never fully to cash while data is fresh.
            band = float(self.params.get("regime_graduated_band_pct", 0.02))
            rel = last / ma - 1.0
            gross = (float(self.params.get("regime_gross_above", 0.98)) if rel > band
                     else float(self.params.get("regime_gross_below", 0.15)) if rel < -band
                     else float(self.params.get("regime_gross_mid", 0.60)))
            below = False  # graduated de-grosses via the multiplier, not a hard cash flip
            prev = prev_state.get("gross")
            flipped = prev is not None and abs(float(prev) - gross) > 1e-9
            await self.ctx.set_state(_K_REGIME, {"gross": gross})
        else:
            # Variant A/B: binary (optional buffer + confirmation).
            buffer_pct = float(self.params.get("regime_buffer_pct", 0.0))
            if buffer_pct > 0:
                below = last < ma * (1.0 - buffer_pct)
                if last > ma * (1.0 + buffer_pct):
                    below = False
            else:
                below = last < ma
            gross = 1.0
            prev = prev_state.get("below")
            flipped = prev is not None and bool(prev) != below
            await self.ctx.set_state(_K_REGIME, {"below": below})

        stale = self._staleness_days(bars)
        if stale is None or stale <= stale_max:
            return below, gross, flipped
        if stale <= degraded_max:
            await self.ctx.log_signal(sym, SignalType.INFO, payload={
                "reason": "regime_stale_degraded_gross", "stale_days": stale,
                "gross": min(gross, degraded_gross)})
            return below, min(gross, degraded_gross), flipped
        await self.ctx.log_signal(sym, SignalType.EXIT, payload={
            "reason": "regime_stale_blind_flat", "stale_days": stale, "gross": 0.0})
        return below, 0.0, flipped

    def _staleness_days(self, bars: Any) -> int | None:
        now = getattr(self, "_tick_date", None)
        if now is None:
            return None
        try:
            last_t = (bars.index[-1] if getattr(bars.index, "name", None) == "t"
                      else bars["t"].iloc[-1])
            last_date = last_t.date() if hasattr(last_t, "date") else last_t
        except Exception:  # noqa: BLE001
            return None
        return max(0, (now - last_date).days)

    # ---- sizing seam (§6 — THE single source of truth for position size) ----
    #
    # Both the order path (`_apply_targets`), the weight-drift trigger, and the §8 drift-audit
    # harness read sizing from here. The harness must OBSERVE this function, never restate its
    # rule — a harness that recomputes "equal weight" independently would report agreement even
    # if production sizing changed underneath it, which is precisely the blind spot the census
    # hit. Equal weight only (owner adjudication 2026-07-22); see `_evaluate` docstring refs.

    def _per_name_notional(self, equity: Decimal, k: int) -> Decimal:
        """Target notional per name given ``k`` targets and gross-scaled investable ``equity``.

        Equal weight, hard-capped at ``max_position_pct``. The cap binds only when k < 1/cap
        (i.e. fewer than 5 names at the default 0.20), in which case the book runs partly in
        cash rather than concentrating past the limit."""
        if k <= 0:
            return Decimal(0)
        return min(equity / Decimal(k),
                   equity * Decimal(str(self.params.get("max_position_pct", 0.20))))

    def target_weights(self, target: list[str]) -> dict[str, float]:
        """The production sizing seam as per-name fractions of TOTAL equity (ex cash buffer),
        gross-scaled by the current regime — the observable form of `_per_name_notional`.

        Derived by evaluating the same function at unit equity, so this can never drift from
        what the order path actually sizes. Consumed by the §8 drift-audit driver."""
        if not target:
            return {}
        unit = float(self._per_name_notional(Decimal(1), len(target)))
        gross = float(getattr(self, "_regime_gross", 1.0) or 0.0)
        return {t: unit * gross for t in target}

    # ---- execution (sells before buys; regime gross; storm-safe via the daily latch) ----

    async def _apply_targets(self, target: list[str], *, held: dict[str, Decimal] | None = None,
                             reason: str, attempt: SeedAttempt | None = None,
                             outcomes: list | None = None) -> None:
        if held is None:
            held = await self._current_holdings()

        def _coid(sym: str) -> str | None:
            # P7 §7-A: tag seed orders so fills/orders are attributable to the attempt.
            return f"{attempt.client_order_id_prefix}{sym.upper()}" if attempt is not None else None

        target_set = set(target)
        for sym, qty in held.items():
            if sym not in target_set:
                await self._submit(sym, OrderSide.SELL, qty, reason=f"{reason}_exit",
                                   client_order_id=_coid(sym), outcomes=outcomes)
        if not target:
            return
        equity = await self._investable_equity()
        per_name = self._per_name_notional(equity, len(target))
        min_trade = Decimal(str(self.params.get("min_trade_pct", 0.03)))
        fractional = bool(self.params.get("fractional_shares", True))
        pending = await self.ctx.pending_buy_qty()
        buys: list[tuple[str, Decimal, float]] = []
        for sym in target:
            price = await self._price(sym)
            if price is None or price <= 0:
                await self.ctx.log_signal(sym, SignalType.ENTRY,
                                          payload={"reason": f"{reason}_skip_no_price"})
                if outcomes is not None:
                    outcomes.append({"symbol": sym.upper(), "ok": False, "reason": "skip_no_price"})
                continue
            price_d = Decimal(str(price))
            target_qty = ((per_name / price_d).quantize(Decimal("0.000001")) if fractional
                          else Decimal(math.floor(per_name / price_d)))
            cur = held.get(sym, Decimal(0))
            delta = target_qty - cur
            if delta == 0:
                continue
            if cur > 0 and abs(delta) * price_d < per_name * min_trade:
                continue
            if delta < 0:
                await self._submit(sym, OrderSide.SELL, -delta, reason=f"{reason}_trim",
                                   ref_price=price, client_order_id=_coid(sym), outcomes=outcomes)
            else:
                buy_qty = delta - pending.get(sym.upper(), Decimal(0))
                if buy_qty > 0:
                    buys.append((sym, buy_qty, price))
        for sym, qty, price in buys:
            await self._submit(sym, OrderSide.BUY, qty, reason=f"{reason}_entry", ref_price=price,
                               client_order_id=_coid(sym), outcomes=outcomes)

    async def _current_holdings(self) -> dict[str, Decimal]:
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
        try:
            live = await self.ctx.get_account_equity()
        except Exception:  # noqa: BLE001
            live = None
        equity = Decimal(str(live)) if live is not None else self._equity_estimate
        buffer = Decimal(str(self.params.get("cash_buffer_pct", 0.02)))
        regime = float(getattr(self, "_regime_gross", 1.0))
        return equity * (Decimal(1) - buffer) * Decimal(str(regime))

    async def _price(self, symbol: str) -> float | None:
        tf = str(self.params.get("pricing_timeframe", "1Day"))
        bars = await self.ctx.get_recent_bars(symbol, tf, n=1)
        if bars is None or bars.empty:
            return None
        return float(bars.iloc[-1]["c"])

    async def _submit(self, symbol: str, side: OrderSide, qty: Decimal, *, reason: str,
                      ref_price: float | None = None, client_order_id: str | None = None,
                      outcomes: list | None = None) -> bool:
        if qty <= 0:
            if outcomes is not None:
                outcomes.append({"symbol": symbol.upper(), "ok": False, "reason": "zero_qty"})
            return False
        req = OrderRequest(
            user_id=0, account_id=0, symbol_ticker=symbol, side=side, qty=qty,
            type=OrderType.MARKET, tif=TimeInForce.DAY, source_type=OrderSourceType.STRATEGY,
            source_id=None, client_order_id=client_order_id,
            reference_price=(Decimal(str(ref_price)) if ref_price and ref_price > 0 else None),
        )
        result = await self.ctx.submit_order(req)
        sig = SignalType.ENTRY if side == OrderSide.BUY else SignalType.EXIT
        payload: dict[str, Any] = {"reason": reason}
        rejection = getattr(result, "rejection_reason", None)
        if result is None:
            payload["submit_returned_none"] = True
        elif rejection:
            payload["rejected"] = rejection
        await self.ctx.log_signal(symbol, sig, payload=payload)
        pacing = float(self.params.get("order_pacing_seconds", 0.0) or 0.0)
        if pacing > 0:
            await asyncio.sleep(pacing)
        ok = result is not None and not rejection
        if outcomes is not None:
            outcomes.append({"symbol": symbol.upper(), "ok": ok, "reason": rejection})
        return ok
