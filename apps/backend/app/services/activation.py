"""ActivationService: orchestrates the paper → live transition (P5 §7, ADR 0005).

State machine:
  IDLE / PAPER ── initiate ──►  PENDING_LIVE
  PENDING_LIVE ── cancel ─────►  IDLE
  PENDING_LIVE ── (24h) ──────►  LIVE   (via scheduler)
  LIVE / HALTED ── deactivate ►  IDLE   (with optional liquidation)

Prerequisites for initiate (all must be satisfied):
  0. LIVE account exists (the user has an Alpaca live account)
  1. Live broker credentials configured (alpaca_live_key + alpaca_live_secret)
  2. TOTP enrolled (users.totp_verified_at set)
  3. Recent backtest (a backtest_results row in the last 7 days)
  4. LIVE risk limits configured (GLOBAL risk_limits row, broker_mode=LIVE)
  5. No active circuit breaker on the LIVE account

initiate requires TOTP re-entry + typed strategy name. Cancellation during
PENDING_LIVE requires only authentication (frictionless escape hatch, ADR 0005).

Drift notes vs the v0.2 doc (reconciled to live schema):
  - There is no `backtests` table / Backtest model — "recent backtest" queries
    `backtest_results` (a result row means a backtest completed).
  - `strategies` has no account_id — `_resolve_strategy_account(user_id, mode)`
    maps via user_id + mode (Session 5 pattern). A 6th `live_account_exists`
    prereq surfaces the "no live account yet" case.
  - get_positions() is sync and returns list[dict]; liquidation reads dict keys.
  - Liquidation submits MANUAL+LIVE orders (confirmation_text=symbol) via the
    OrderRouter, NOT STRATEGY source: MANUAL bypasses the §6 cooldown and the §7
    strategy-status guard, so it works for both LIVE and HALTED strategies.
    submit(req) returns an Order (no OrderSubmissionResult; rejections carry
    rejection_reason).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.audit import AuditAction, AuditActorType, AuditLogger
from app.db.enums import (
    OrderSide,
    OrderSourceType,
    OrderType,
    RiskScopeType,
    StrategyStatus,
    TimeInForce,
)
from app.db.models.account import Account, AccountMode
from app.db.models.backtest_result import BacktestResult
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.utils.time import ensure_aware

logger = structlog.get_logger(__name__)


ACTIVATION_COOLDOWN_HOURS = 24
RECENT_BACKTEST_WINDOW_DAYS = 7


@dataclass
class Prerequisite:
    name: str
    satisfied: bool
    detail: str


@dataclass
class ActivationStatus:
    strategy_id: int
    status: StrategyStatus
    prerequisites: list[Prerequisite]
    all_satisfied: bool
    initiated_at: datetime | None
    completes_at: datetime | None
    seconds_remaining: int


class ActivationError(RuntimeError):
    pass


class ActivationService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        broker_registry: Any = None,
        order_router: Any = None,
        bus: Any = None,
    ) -> None:
        self._session = session
        self._broker_registry = broker_registry
        self._order_router = order_router
        self._bus = bus

    # ---------------- read-side ----------------

    async def _resolve_strategy_account(
        self, strategy: Strategy, mode: AccountMode
    ) -> Account | None:
        """Resolve the account this strategy uses for the given mode. strategies
        has no account_id FK; the mapping is user_id + mode (a user has at most
        one Alpaca account per mode in the MVP). None if none exists."""
        return (
            await self._session.execute(
                select(Account)
                .where(Account.user_id == strategy.user_id)
                .where(Account.mode == mode)
            )
        ).scalars().first()

    async def check_prerequisites(self, strategy_id: int) -> list[Prerequisite]:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        account = await self._resolve_strategy_account(strategy, AccountMode.live)
        store = CredentialStore(self._session)
        prereqs: list[Prerequisite] = []

        # 0. LIVE account exists.
        prereqs.append(Prerequisite(
            name="live_account_exists",
            satisfied=account is not None,
            detail=(
                f"LIVE account {account.id} configured." if account is not None
                else "Create a LIVE account via Settings → Accounts before activating."
            ),
        ))

        # 1. Live broker credentials.
        live_key = await store.get(strategy.user_id, CredentialKind.ALPACA_LIVE_KEY)
        live_secret = await store.get(strategy.user_id, CredentialKind.ALPACA_LIVE_SECRET)
        prereqs.append(Prerequisite(
            name="live_broker_credentials",
            satisfied=bool(live_key and live_secret),
            detail=(
                "Configured." if (live_key and live_secret)
                else "Set via Settings → Credentials → Alpaca Live API Key/Secret."
            ),
        ))

        # 2. TOTP enrolled.
        user = await self._session.get(User, strategy.user_id)
        totp_ok = user is not None and user.totp_verified_at is not None
        prereqs.append(Prerequisite(
            name="totp_enrolled",
            satisfied=totp_ok,
            detail=(
                "Enrolled." if totp_ok
                else "TOTP not enrolled. Run scripts/create_user.py or /auth/totp/setup."
            ),
        ))

        # 3. Recent backtest (backtest_results row in the window).
        cutoff = datetime.now(UTC) - timedelta(days=RECENT_BACKTEST_WINDOW_DAYS)
        recent = (
            await self._session.execute(
                select(BacktestResult)
                .where(BacktestResult.strategy_id == strategy_id)
                .where(BacktestResult.created_at >= cutoff)
                .order_by(BacktestResult.created_at.desc())
                .limit(1)
            )
        ).scalars().first()
        prereqs.append(Prerequisite(
            name="recent_backtest",
            satisfied=recent is not None,
            detail=(
                "Recent backtest found." if recent is not None
                else f"Run a backtest (none in last {RECENT_BACKTEST_WINDOW_DAYS} days)."
            ),
        ))

        # 4. LIVE risk limits.
        live_limits = (
            await self._session.execute(
                select(RiskLimits)
                .where(RiskLimits.user_id == strategy.user_id)
                .where(RiskLimits.broker_mode == AccountMode.live)
                .where(RiskLimits.scope_type == RiskScopeType.GLOBAL)
            )
        ).scalars().first()
        prereqs.append(Prerequisite(
            name="live_risk_limits",
            satisfied=live_limits is not None,
            detail=(
                f"Configured (max_daily_loss=${live_limits.max_daily_loss})."
                if live_limits is not None
                else "Configure via Settings → Risk Limits (LIVE)."
            ),
        ))

        # 5. Circuit breaker clear on the LIVE account.
        if account is None:
            breaker_ok = True
            breaker_detail = "Pending LIVE account creation."
        else:
            tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
            breaker_ok = tripped_at is None
            breaker_detail = (
                "No active trip." if tripped_at is None
                else f"Circuit breaker tripped at {tripped_at.isoformat()}. Reset first."
            )
        prereqs.append(Prerequisite(
            name="circuit_breaker_clear",
            satisfied=breaker_ok,
            detail=breaker_detail,
        ))

        return prereqs

    async def status(self, strategy_id: int) -> ActivationStatus:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        prereqs = await self.check_prerequisites(strategy_id)
        all_ok = all(p.satisfied for p in prereqs)
        completes_at: datetime | None = None
        seconds_remaining = 0
        initiated_at = ensure_aware(strategy.live_activation_initiated_at)
        if strategy.status == StrategyStatus.PENDING_LIVE and initiated_at is not None:
            completes_at = initiated_at + timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
            now = datetime.now(UTC)
            seconds_remaining = max(0, int((completes_at - now).total_seconds()))
        return ActivationStatus(
            strategy_id=strategy_id,
            status=strategy.status,
            prerequisites=prereqs,
            all_satisfied=all_ok,
            initiated_at=initiated_at,
            completes_at=completes_at,
            seconds_remaining=seconds_remaining,
        )

    # ---------------- write-side ----------------

    async def initiate(
        self,
        *,
        strategy_id: int,
        user_id: int,
        confirmation_name: str,
        totp_code: str,
    ) -> ActivationStatus:
        """Wizard completion: verify ownership + status + typed name + TOTP +
        all prerequisites, then set PENDING_LIVE and start the 24h cooldown."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}"
            )
        if strategy.status not in (StrategyStatus.IDLE, StrategyStatus.PAPER):
            raise ActivationError(
                f"Cannot activate strategy in status {strategy.status.value}. "
                f"Required: IDLE or PAPER."
            )
        if confirmation_name != strategy.name:
            raise ActivationError(
                f"Confirmation name does not match strategy name. "
                f"Expected '{strategy.name}'."
            )

        # TOTP re-verification (defense against session hijack — ADR 0005 note).
        from app.auth.totp import verify_code

        store = CredentialStore(self._session)
        totp_secret = await store.get(user_id, CredentialKind.TOTP_SECRET)
        if totp_secret is None or not verify_code(totp_secret, totp_code):
            raise ActivationError("Invalid TOTP code.")

        # Re-check all prerequisites at the last moment (they may have changed
        # while the wizard was open).
        prereqs = await self.check_prerequisites(strategy_id)
        unsatisfied = [p for p in prereqs if not p.satisfied]
        if unsatisfied:
            raise ActivationError(
                f"Prerequisites not satisfied: {', '.join(p.name for p in unsatisfied)}"
            )

        now = datetime.now(UTC)
        strategy.status = StrategyStatus.PENDING_LIVE
        strategy.live_activation_initiated_at = now

        live_account = await self._resolve_strategy_account(strategy, AccountMode.live)
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_ACTIVATION_INITIATED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "strategy_name": strategy.name,
                "account_id": live_account.id if live_account else None,
                "initiated_at": now.isoformat(),
                "completes_at": (
                    now + timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
                ).isoformat(),
            },
            user_id=user_id,
        )
        await self._session.commit()
        logger.info(
            "strategy_activation_initiated",
            strategy_id=strategy_id, user_id=user_id,
            cooldown_hours=ACTIVATION_COOLDOWN_HOURS,
        )
        return await self.status(strategy_id)

    async def cancel(self, *, strategy_id: int, user_id: int) -> None:
        """Cancel a pending activation. Always permitted during PENDING_LIVE; no
        TOTP — cancellation is the safe direction (ADR 0005)."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}"
            )
        if strategy.status != StrategyStatus.PENDING_LIVE:
            raise ActivationError(
                f"Cannot cancel — strategy is in status {strategy.status.value}, "
                f"not PENDING_LIVE."
            )

        prior = ensure_aware(strategy.live_activation_initiated_at)
        strategy.status = StrategyStatus.IDLE
        strategy.live_activation_initiated_at = None
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_ACTIVATION_CANCELED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "strategy_name": strategy.name,
                "prior_initiated_at": prior.isoformat() if prior else None,
            },
            user_id=user_id,
        )
        await self._session.commit()
        logger.info("strategy_activation_canceled", strategy_id=strategy_id, user_id=user_id)

    async def complete_pending(self, strategy_id: int) -> bool:
        """Scheduler entry point. Transition PENDING_LIVE → LIVE if 24h elapsed.
        Idempotent: returns False (no change) if the strategy is no longer
        PENDING_LIVE or the window hasn't elapsed."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return False
        if strategy.status != StrategyStatus.PENDING_LIVE:
            return False
        if strategy.live_activation_initiated_at is None:
            logger.error("complete_pending_missing_initiated_at", strategy_id=strategy_id)
            strategy.status = StrategyStatus.IDLE
            await self._session.commit()
            return False

        now = datetime.now(UTC)
        initiated_at = ensure_aware(strategy.live_activation_initiated_at)
        assert initiated_at is not None  # guarded above
        if now - initiated_at < timedelta(hours=ACTIVATION_COOLDOWN_HOURS):
            return False

        strategy.status = StrategyStatus.LIVE
        live_account = await self._resolve_strategy_account(strategy, AccountMode.live)
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="activation_scheduler",
            action=AuditAction.STRATEGY_LIVE_ACTIVATED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "strategy_name": strategy.name,
                "account_id": live_account.id if live_account else None,
                "activated_at": now.isoformat(),
                "initiated_at": initiated_at.isoformat(),
            },
            user_id=strategy.user_id,
        )
        await self._session.commit()

        if self._bus is not None:
            try:
                await self._bus.publish(
                    "strategy.live_activated",
                    {"strategy_id": strategy_id, "activated_at": now.isoformat()},
                )
            except Exception:
                logger.exception("strategy_live_activated_publish_failed")

        logger.info("strategy_live_activated", strategy_id=strategy_id)
        return True

    async def deactivate(
        self, *, strategy_id: int, user_id: int, liquidate: bool
    ) -> dict[str, Any]:
        """Deactivate a LIVE/HALTED strategy (immediate; no cooldown). If
        liquidate=True, enqueue market-order closes for open positions in the
        strategy's symbols BEFORE flipping to IDLE."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}"
            )
        if strategy.status not in (StrategyStatus.LIVE, StrategyStatus.HALTED):
            raise ActivationError(
                f"Cannot deactivate — strategy is in status {strategy.status.value}, "
                f"not LIVE or HALTED."
            )

        liquidation_orders: list[int] = []
        if liquidate:
            liquidation_orders = await self._enqueue_liquidation(strategy)

        prior_status = strategy.status
        strategy.status = StrategyStatus.IDLE
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_DEACTIVATED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "strategy_name": strategy.name,
                "prior_status": prior_status.value,
                "liquidate": liquidate,
                "liquidation_order_ids": liquidation_orders,
            },
            user_id=user_id,
        )
        await self._session.commit()
        logger.info(
            "strategy_deactivated", strategy_id=strategy_id, liquidate=liquidate,
            liquidation_count=len(liquidation_orders),
        )
        return {
            "strategy_id": strategy_id,
            "new_status": StrategyStatus.IDLE.value,
            "liquidation_orders": liquidation_orders,
        }

    async def _enqueue_liquidation(self, strategy: Strategy) -> list[int]:
        """Close open positions in the strategy's symbols via the OrderRouter.

        Uses MANUAL source with confirmation_text=symbol: MANUAL bypasses the §6
        cooldown and the §7 strategy-status guard, so liquidation works for both
        LIVE and HALTED strategies. Orders still pass the §5 risk gates (incl. the
        circuit breaker) and are audited. Best-effort: broker errors are logged,
        not retried."""
        if self._broker_registry is None or self._order_router is None:
            logger.warning("liquidation_no_broker_or_router", strategy_id=strategy.id)
            return []
        live_account = await self._resolve_strategy_account(strategy, AccountMode.live)
        if live_account is None:
            logger.warning("liquidation_no_live_account", strategy_id=strategy.id)
            return []
        adapter = self._broker_registry.get(live_account.id)
        if adapter is None:
            logger.warning("liquidation_no_adapter", strategy_id=strategy.id)
            return []
        try:
            positions = adapter.get_positions()  # sync, list[dict]
        except Exception:
            logger.exception("liquidation_position_fetch_failed", strategy_id=strategy.id)
            return []

        from app.risk.types import OrderRequest

        strategy_symbols = set(strategy.symbols_json or [])
        order_ids: list[int] = []
        for pos in positions:
            symbol = pos.get("symbol") if isinstance(pos, dict) else None
            qty_raw = pos.get("qty") if isinstance(pos, dict) else None
            if symbol is None or qty_raw is None or symbol not in strategy_symbols:
                continue
            qty = Decimal(str(qty_raw))
            if qty == 0:
                continue
            side = OrderSide.SELL if qty > 0 else OrderSide.BUY
            req = OrderRequest(
                user_id=strategy.user_id,
                account_id=live_account.id,
                symbol_ticker=symbol,
                side=side,
                qty=abs(qty),
                type=OrderType.MARKET,
                tif=TimeInForce.DAY,
                source_type=OrderSourceType.MANUAL,
                confirmation_text=symbol,  # auto-confirm: MANUAL+LIVE gate
            )
            try:
                order = await self._order_router.submit(req)
                if getattr(order, "id", None):
                    order_ids.append(order.id)
            except Exception:
                logger.exception(
                    "liquidation_submit_failed", strategy_id=strategy.id, symbol=symbol
                )
        return order_ids
