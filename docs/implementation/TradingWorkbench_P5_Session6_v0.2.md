# P5 Session 6 — Live Order Safety

| Field | Value |
|---|---|
| Document version | **v0.2** (updated in-place from v0.1; 14 drift corrections from Sessions 0–5 Results + 6 "execution-surfaced" issues categorized below) |
| Date | 2026-05-31 |
| Phase | **P5 — Live Trading**, **§6** (entirely) |
| Predecessor | `TradingWorkbench_P5_Session5_v0.2.md` (tag `p5-session5-complete`, PR #43) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Two friction layers that bound human and algorithmic error on the live path. Typed-ticker confirmation on manual LIVE orders (server-enforced, not just UI). 60-second per-strategy cooldown after any failed order submission. Every LIVE order submission audit-logged regardless of outcome. New `strategies.cooldown_until` column. New `confirmation_text` field on `POST /api/v1/orders`. New audit action `LIVE_ORDER_SUBMITTED`. New cooldown management endpoints. Single PR. |
| Estimated wall time | 4 hours |
| Stopping point | `git tag p5-session6-complete` |
| Out of scope | Two-factor confirmation on every order (the typed-ticker is the friction layer; we don't also require TOTP per order). Automatic cooldown escalation (60s every time, no doubling). Per-strategy daily order quotas distinct from the account-level cap from §5. Cooldown on fills (this is submission-only — partial fills, rejections-by-exchange, and cancellations don't trigger cooldown). Anti-replay protection on the confirmation token (the confirmation is the ticker, not a one-time code). Order amendment / modify flow (still submit-only in MVP). |

---

## Updated in v0.2 (drift corrections + candid acknowledgment of what we can't predict)

This file was updated 2026-05-31 against what Sessions 1–5 actually shipped (v0.1 was drafted 2026-05-23, before any of them executed). Sources: Session Zero Results, Session 2 Results, Session 2 v1.0, Session 3 Results, Session 4 Results, Session 5 Results.

### Part 1 — Drift corrections applied below (the knowable ones)

1. **`BrokerMode` → `AccountMode`.** Session Zero confirmed; the enum is `AccountMode` (lowercase values `paper` / `live`). Affects §6.4 OrderRouter integration and tests in §6.8.
2. **OrderRouter lives at `app/orders/router.py`**, not `app/orders/router.py`. Session Zero Results.
3. **`OrderSource` → `OrderSourceType`** (the enum), **`orders.source` → `orders.source_type`** (the column). Session Zero Results.
4. **`AuditLogger` is sync, lives in `app.audit`**, and `write()` does NOT take `await` — confirmed by Session 5's execution. The v0.1 code uses `AuditLogger.write(...)` with import from `app.services.audit_log`. Both wrong.
5. **`_router_token` discipline.** Session 2 v1.0: broker mutators (`submit_order`/`cancel_order`/`replace_order`) are `_router_token`-gated; only `OrderRouter` itself passes it. §6.4's existing `submit_order` call already lives inside the router, so this is preserved by location. But: the new `_maybe_set_cooldown` and `_maybe_audit_live_submission` helpers must NOT call adapter mutators in any way.
6. **Strategy→account mapping has no `account_id`** (Session 5 Results, "Deliberate deviations"). `strategies` has `user_id` + status (PAPER/LIVE), not a direct FK. §6.4's cooldown check uses `strategy_id` directly (no account mapping needed), so this drift doesn't bite here. But §6.5's "Clear cooldown" endpoint authorization needs to verify ownership via `Strategy.user_id == current_user_id`, not a join through `account`.
7. **Existing global daily-loss halt** (`app/risk/halt.py`, RiskEngine step 9) coexists with the account-scoped breaker from §5. §6.4's order pipeline inherits both — no §6 change needed; the RiskEngine call wraps both.
8. **Paths and tooling.** Windows working dir (`C:\LLM-RAG-APP\ai-trading-app`); `uv run` → `.\.venv\Scripts\python.exe`; pytest needs `--cov-branch`. Affects Prerequisites and §6.11.
9. **`check_adr0002.sh` removed from Prerequisites.** Doesn't exist; ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + `_router_token` tripwire.
10. **Eight invariants count is correct.** §6 adds no new invariant. The eight: `check_strategy_isolation.sh`, `check_mcp_readonly.sh`, `check_no_llm_in_order_path.sh`, `check_broker_isolation.sh` (P5 §2), `check_no_env_credentials.sh` (P5 §4), `check_risk_coverage.py`, `check_p2_coverage.py`, `check_p3_coverage.py`. Plus the ADR 0002 pytest invariant.
11. **`StrategyStatus.HALTED` already exists** (Session 5 Results) and follows the StrEnum convention. No enum changes needed in §6.
12. **API router wired via `app/api/v1/__init__.py`** with no extra prefix (Session 5 deviation note — `prefix="/api/v1"` would double it). Affects §6.5's cooldown endpoints and §6.2's order-submit schema additions.
13. **Frontend uses `apiFetch` + React Query**, not `apiClient.get/put`. The OrderForm intercept in §6.6 should wrap the existing form's submit handler, not rewrite the form.
14. **Shared `ensure_aware()` helper at `app/utils/time.py`** (introduced in Session 5 §5.0). `cooldown_until` is a SQLite-stored timezone-aware datetime; comparisons against `datetime.now(timezone.utc)` need coercion. Affects §6.3 `StrategyCooldownService.is_in_cooldown` and the §6.5 endpoint that surfaces remaining seconds.

### Part 2 — Candid acknowledgment of what this drift analysis CANNOT predict

Session 5 shipped only after the developer (with Claude Code) discovered ~6 issues during execution that the systematic drift analysis missed. These were items in the actual codebase that no Results document had previously documented because no prior session had needed to know about them. Specifically: `Fill` has no `signed_direction` (had to join with `Order`), `SQLEnum` stores names not values (the migration's lowercase `'global'` would have created an invisible row, caught only by ORM verification before merge), the existing `app/risk/halt.py` (the global daily-loss halt nobody planned for), and three other minor things.

**This drift analysis catches everything the Results documents have surfaced. It cannot catch what the Results documents have not yet surfaced. Specifically, the categories of unknown drift to verify against current code BEFORE relying on v0.1 / v0.2 code snippets in §6:**

- **`OrderSubmitRequest` / `OrderSubmissionResult` shape.** §6.2 adds `confirmation_text: str | None`. Verify the actual schema in `apps/backend/app/api/v1/schemas/orders.py` — does it use Pydantic v1 or v2, where do related types live, what other fields exist that might affect the patch.
- **`OrderRouter.submit()` actual current signature.** §6.4's code shows `async def submit(self, request: OrderSubmitRequest, *, current_user_id: int)`. Verify the actual signature in `app/orders/router.py` — does it take `current_user_id` keyword, return type, what does `_load_account` actually look like.
- **`OrderRouter` already has helpers like `_reject`, `_record_rejection`, `_record_broker_error`, `_record_success`, `_record_no_adapter`.** v0.1 calls these as if they exist. Verify the actual API. If the naming or signatures differ, the integration is a small refactor, not a paste-in.
- **`Strategy` model shape.** §6.1 adds `cooldown_until: Mapped[datetime | None]`. Verify the Mapped/Column conventions match — Session 5 Results noted `SQLEnum` stores names not values; check whether `Strategy` uses any SQLEnum columns whose values would be referenced in tests.
- **Audit payload schema for `LIVE_ORDER_SUBMITTED`.** §6.4 sketches a payload `{ symbol, side, qty, type, order_id, source, strategy_id, outcome, reason_code }`. Verify what shape existing audit calls use (especially after Session 5's three new audit actions). Match the convention.
- **`broker_registry.get()` return type.** §6.4 treats `adapter is None` as "no adapter available." Confirm — Session 2 v1.0 said yes, but if Session 5's RiskEngine changed how the registry is accessed, the pattern may have evolved.
- **`OrderStatus` enum values.** §6.4 uses `OrderStatus.REJECTED` and `OrderStatus.ERROR`. Verify these are the actual values (not `OrderStatusType.REJECTED` or similar).
- **The `outcome.status` and `outcome.reason_code` fields on `OrderSubmissionResult`.** Used in `_maybe_set_cooldown`. Verify the result type's actual fields.

**Process recommendation for implementation:** before pasting any §6.4 OrderRouter code into the actual router file, do a grep+read pass on `app/orders/router.py` and `app/api/v1/schemas/orders.py` to confirm the actual shape. If the shape differs from v0.2's sketches, adjust the integration to match — don't force the v0.2 shape onto the code. This is what Session 5's execution did (and produced the Session 5 Results "Deliberate deviations" list). Expect a similar list for Session 6.

---

## ⚠ Real-money posture (recap)

This session is the "humans and algos both make mistakes" layer. It assumes two things you'd want to fail safely:

1. **The user clicks Submit on a live order they didn't mean to send.** Defense: typed-ticker confirmation. Even if a script auto-submits, even if the modal flashes by, the user types the ticker — and a wrong ticker means the order doesn't go.

2. **An algorithm submits an order, gets rejected, and retries immediately.** Defense: 60-second per-strategy cooldown after any failed submission. A buggy strategy can lose money, but it can't lose money at high frequency.

Neither defense is sufficient on its own. Both together create the "loud failure modes are loud, quiet failure modes are slow" posture that §6 is meant to establish.

The load-bearing assertion for §6: **the P1-§5 paper smoke is byte-identical.** The new code paths fire only for `MANUAL` source on LIVE accounts (confirmation) or for `STRATEGY` source after a failed submission (cooldown). Paper smoke is all-success and source=MANUAL on PAPER accounts — neither path fires.

---

## Session Goal

After this session:
- New `strategies.cooldown_until` column (nullable `DateTime(timezone=True)`). When set and `> now()`, the strategy is in cooldown and cannot submit orders.
- New `POST /api/v1/orders` field `confirmation_text` (optional string). For `source=MANUAL` orders on `LIVE` accounts the field is **required** and must equal the symbol after normalization (uppercase, stripped whitespace). For all other cases the field is ignored.
- New service `app/services/strategy_cooldown.py`: `StrategyCooldownService` with `is_in_cooldown(strategy_id) → tuple[bool, datetime | None]`, `set_cooldown(strategy_id, duration_seconds=60, reason="")`, `clear_cooldown(strategy_id, user_id)`.
- `OrderRouter` integration order: (1) BrokerModeError guard from §1, (2) confirmation_text for MANUAL+LIVE, (3) cooldown for STRATEGY source, (4) risk engine (§5), (5) broker adapter submit, (6) if STRATEGY source AND outcome=failure → set 60s cooldown, (7) if LIVE → audit `LIVE_ORDER_SUBMITTED`.
- New audit action `LIVE_ORDER_SUBMITTED` recorded for every LIVE order submission regardless of outcome. Payload: `{ symbol, side, qty, type, order_id, source, strategy_id, outcome, reason_code }`.
- New endpoints:
  - `GET /api/v1/strategies/{id}/cooldown` — returns `{ in_cooldown, cooldown_until, seconds_remaining }`
  - `POST /api/v1/strategies/{id}/cooldown/clear` — manually clear, audit-logged
- Frontend:
  - `LiveOrderConfirmModal.tsx`: typed-ticker modal that intercepts the OrderForm submit when account is LIVE and source is MANUAL. Submit disabled until typed text matches symbol (case-insensitive).
  - `CooldownIndicator.tsx`: badge on strategy detail page showing remaining cooldown seconds and a "Clear cooldown" button.
- Tests: 22 backend tests across confirmation, cooldown, and audit; 8 CI invariants pass; P1-§5 paper smoke byte-identical.
- Runbook: `docs/runbook/live-order-safety.md` covering both layers and the "what if I typed the wrong ticker" flow.

What does NOT happen this session:
- **No TOTP-per-order.** The typed-ticker is the friction layer. Requiring TOTP on every live order is too much friction in fast markets, and it doesn't really add safety once you've already typed the ticker.
- **No cooldown escalation.** 60s every time. A strategy that's stuck in a fail-cool-retry-fail loop will spin at 60s intervals indefinitely; the operator notices via the LIVE_ORDER_SUBMITTED audit stream and intervenes. P5+ polish could escalate (60s → 5min → HALT) but the simple version is enough.
- **No order amendment / modification flow.** Submit-only. To change an order, cancel and resubmit. The amend code path is its own complexity nest and isn't needed for MVP.
- **No anti-replay protection on confirmation_text.** Someone with the user's session cookie could replay a submission. The session cookie is already the authentication boundary; the confirmation is friction, not crypto.
- **No live orders yet.** P5 §1's BrokerModeError still active. §6 wires the safety so that when §7 opens up live order submission, all the gates are in place from day one.

---

## Prerequisites Check

```powershell
# from repo root; uv is not on PATH — use the venv python
cd C:\LLM-RAG-APP\ai-trading-app
git checkout main; git pull origin main
git describe --tags --abbrev=0           # expect: p5-session5-complete

# All eight CI invariants pass (no new invariant this session)
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_no_env_credentials.sh
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_risk_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p2_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p3_coverage.py

# ADR 0002 invariant test (pytest-driven, not shell)
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q

# Baseline backend suite green
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=xml
cd ..\..

# Confirm OrderSourceType enum has STRATEGY value (from P4 §5)
cd apps\backend
.\.venv\Scripts\python.exe -c "from app.db.enums import OrderSourceType; print([s.value for s in OrderSourceType])"
# Expect: includes 'manual', 'strategy', 'agent_strategy', 'agent_proposal', 'pine'

# Confirm strategies table doesn't already have cooldown_until
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(strategies)').fetchall()])"
# Expect: NO 'cooldown_until' in the list

# Confirm there's no existing confirmation_text in OrderSubmitRequest
findstr /S /R "confirmation_text" app\api\v1\schemas\orders.py
# Expect: no match
cd ..\..

# Confirm shared ensure_aware helper from Session 5 §5.0 exists
findstr /S /R "ensure_aware" apps\backend\app\utils\time.py
# Expect: matches (Session 5 introduced this)
```

Live runtime gates are **deferred** per the standing Norton SSL + no-Docker posture. The in-suite tests in §6.8 stand in for the load-bearing assertions; the live diff runs in WSL/CI before the tag is promoted to a release.

```bash
git checkout -b feat/p5-session6-live-safety
```

- [ ] On `main`, at `p5-session5-complete`.
- [ ] All eight CI invariants pass; ADR 0002 pytest invariant green.
- [ ] Baseline backend suite green.
- [ ] `OrderSourceType` (not `OrderSource`) enum present.
- [ ] `strategies.cooldown_until` not yet present.
- [ ] `app/utils/time.py::ensure_aware` available for import.

---

## §6.1 — Schema: `strategies.cooldown_until` + New Audit Action

### 6.1.1 — Column

Edit `apps/backend/app/db/models/strategy.py`:

```python
# Short-term automatic pause after a failed order submission. When set
# and > now(), this strategy cannot submit orders. Distinct from
# status=HALTED (indefinite, manual restart only) and status=ERROR
# (engine-side crash). Cooldown is a self-clearing time-based block.
cooldown_until: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True,
)
```

### 6.1.2 — Audit Action

Edit `apps/backend/app/db/enums.py`:

```python
class AuditAction(str, Enum):
    # ... existing ...
    LIVE_ORDER_SUBMITTED = "live_order_submitted"
    STRATEGY_COOLDOWN_CLEARED = "strategy_cooldown_cleared"
```

> Why `LIVE_ORDER_SUBMITTED` rather than `ORDER_SUBMITTED`? Paper order submissions are high-volume during smoke tests and strategy backtests-replay; auditing all of them would bloat the audit log. The LIVE prefix narrows the audit-log signal to "things that touched real money." The existing per-order DB row (in `orders`) carries the full paper-order trail.

### 6.1.3 — Migration

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "P5: strategies.cooldown_until"
```

Open the migration. Verify:

```python
def upgrade():
    op.add_column("strategies", sa.Column(
        "cooldown_until", sa.DateTime(timezone=True), nullable=True,
    ))


def downgrade():
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("cooldown_until")
```

Apply and round-trip:

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m alembic upgrade head

# Verify cooldown_until column added
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(strategies)').fetchall()])"
# Expect: list including 'cooldown_until'

# Round-trip
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..\..
```

- [ ] Column added.
- [ ] Audit action added.
- [ ] Migration round-trips.

---

## §6.2 — Request Schema: `confirmation_text`

Edit `apps/backend/app/api/v1/schemas/orders.py`. Add the field to `OrderSubmitRequest`:

```python
class OrderSubmitRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    account_id: int
    symbol: str = Field(min_length=1, max_length=16)
    side: OrderSide
    type: OrderType
    qty: Decimal = Field(gt=0)
    limit_price: Optional[Decimal] = Field(default=None, gt=0)
    stop_price: Optional[Decimal] = Field(default=None, gt=0)
    tif: TimeInForce
    source: OrderSourceType = OrderSourceType.MANUAL
    strategy_id: Optional[int] = None
    # NEW in P5 §6: required for MANUAL orders on LIVE accounts. Server
    # enforces match against symbol after normalization. Ignored for all
    # other (source, account.mode) combinations.
    confirmation_text: Optional[str] = Field(default=None, max_length=32)
```

The schema permits the field on every request (it's optional at the schema level). The OrderRouter enforces the "required for MANUAL+LIVE" rule (§6.4).

> **Why not enforce at the Pydantic schema level?** The schema can't see the account's broker_mode — that's a DB lookup. Pulling account lookup into schema validation would couple Pydantic to the DB session. Putting the check in the OrderRouter keeps the schema simple and the rule co-located with the rest of the order routing decisions.

- [ ] `confirmation_text` field added.
- [ ] Optional at schema level; required only at OrderRouter.

---

## §6.3 — `StrategyCooldownService`

Create `apps/backend/app/services/strategy_cooldown.py`:

```python
"""Per-strategy cooldown after failed order submissions.

When a strategy submits an order that doesn't make it to the broker
(risk rejection, broker adapter error, validation error, anything that's
not 'accepted by Alpaca'), the strategy enters a 60-second cooldown.

During cooldown:
  - Subsequent strategy-sourced orders for this strategy_id are rejected
    with COOLDOWN_ACTIVE.
  - Other strategies on the same account are unaffected.
  - Manual orders (source=MANUAL) are NOT subject to strategy cooldown.

After cooldown expires (60s elapsed):
  - The strategy can submit again automatically. No manual intervention.

The user can manually clear the cooldown if they want to retry sooner.
This is a normal user action (no special confirmation) since it doesn't
unlock any new capability — just compresses the wait.

The cooldown is persisted on strategies.cooldown_until, so it survives
backend restarts.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

import structlog
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import AuditAction, AuditActorType
from app.db.models.strategy import Strategy
from app.audit.logger import AuditLogger
from app.utils.time import ensure_aware


logger = structlog.get_logger(__name__)


DEFAULT_COOLDOWN_SECONDS = 60


@dataclass
class CooldownStatus:
    strategy_id: int
    in_cooldown: bool
    cooldown_until: Optional[datetime]
    seconds_remaining: int   # 0 if not in cooldown


class StrategyCooldownService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def status(self, strategy_id: int) -> CooldownStatus:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        now = datetime.now(timezone.utc)
        # SQLite returns DateTime(timezone=True) as naive; coerce
        cooldown_until = ensure_aware(strategy.cooldown_until)
        if cooldown_until is None or cooldown_until <= now:
            return CooldownStatus(
                strategy_id=strategy_id,
                in_cooldown=False,
                cooldown_until=None,
                seconds_remaining=0,
            )
        seconds = int((cooldown_until - now).total_seconds())
        return CooldownStatus(
            strategy_id=strategy_id,
            in_cooldown=True,
            cooldown_until=cooldown_until,
            seconds_remaining=max(0, seconds),
        )

    async def is_in_cooldown(self, strategy_id: int) -> tuple[bool, Optional[datetime]]:
        """Fast check used by the OrderRouter pre-trade.

        Returns (in_cooldown, cooldown_until). The session is short-lived;
        callers should not hold this across awaits with other DB writes.
        """
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return (False, None)
        now = datetime.now(timezone.utc)
        # SQLite naive-datetime coercion (Session 5 §5.0)
        cooldown_until = ensure_aware(strategy.cooldown_until)
        if cooldown_until is None or cooldown_until <= now:
            return (False, None)
        return (True, cooldown_until)

    async def set_cooldown(
        self,
        strategy_id: int,
        *,
        duration_seconds: int = DEFAULT_COOLDOWN_SECONDS,
        reason: str = "",
    ) -> None:
        """Set or extend the cooldown.

        If the strategy is already in cooldown, the new cooldown_until
        replaces the existing one (essentially extending it to now+60s).
        This is the 'each failure resets the window' semantics — a
        strategy that keeps failing every 30s will never escape.
        """
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            logger.warning("cooldown_set_missing_strategy", strategy_id=strategy_id)
            return
        now = datetime.now(timezone.utc)
        new_until = now + timedelta(seconds=duration_seconds)
        strategy.cooldown_until = new_until
        await self._session.commit()
        logger.info(
            "strategy_cooldown_set",
            strategy_id=strategy_id,
            cooldown_until=new_until.isoformat(),
            duration_seconds=duration_seconds,
            reason=reason,
        )

    async def clear_cooldown(
        self,
        strategy_id: int,
        *,
        user_id: int,
    ) -> None:
        """Manual user clear. Audit-logged.

        Returns silently if the strategy isn't in cooldown — idempotent."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ValueError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(f"Strategy {strategy_id} does not belong to user {user_id}")
        if strategy.cooldown_until is None:
            return
        prior_until = strategy.cooldown_until
        strategy.cooldown_until = None
        AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.STRATEGY_COOLDOWN_CLEARED,
            target_type="strategy",
            target_id=strategy_id,
            payload={
                "prior_cooldown_until": prior_until.isoformat(),
                "cleared_by_user_id": user_id,
            },
            user_id=user_id,
        )
        await self._session.commit()
        logger.info("strategy_cooldown_cleared",
                    strategy_id=strategy_id, user_id=user_id)
```

- [ ] Service with status / is_in_cooldown / set_cooldown / clear_cooldown.
- [ ] Each failure resets the 60s window (no "first-failure" semantics).
- [ ] Clear is permission-checked + audit-logged.

---

## §6.4 — `OrderRouter` Integration

This is the load-bearing change. The OrderRouter gains:
- Confirmation-text check (between BrokerModeError and RiskEngine).
- Cooldown check (after confirmation, before RiskEngine).
- Cooldown set on failure (after submission outcome resolved).
- LIVE_ORDER_SUBMITTED audit (after every LIVE submission).

Edit `apps/backend/app/orders/router.py`. The relevant section:

```python
from app.db.enums import (
    AuditAction, AuditActorType, AccountMode, OrderSourceType, OrderStatus,
)
from app.services.strategy_cooldown import StrategyCooldownService


class OrderRouter:
    # ... existing __init__ ...

    async def submit(
        self,
        request: OrderSubmitRequest,
        *,
        current_user_id: int,
    ) -> OrderSubmissionResult:
        account = await self._load_account(request.account_id, current_user_id)

        # ============================================================
        # P5 §1: BrokerModeError guard (LIVE still rejected entirely)
        # ============================================================
        if account.mode == AccountMode.live:
            # P5 §7 will lift this guard. Until then: §6 still validates
            # the confirmation_text path so the wiring is correct on
            # day one of §7.
            pass    # the guard fires below; see existing code

        # ============================================================
        # P5 §6 (NEW): MANUAL+LIVE requires confirmation_text == symbol
        # ============================================================
        if (
            request.source == OrderSourceType.MANUAL
            and account.mode == AccountMode.live
        ):
            if not request.confirmation_text:
                return self._reject(
                    request, account,
                    reason_code="CONFIRMATION_REQUIRED",
                    detail=(
                        "Manual LIVE orders require confirmation_text "
                        "matching the symbol."
                    ),
                )
            normalized_confirmation = request.confirmation_text.strip().upper()
            normalized_symbol = request.symbol.strip().upper()
            if normalized_confirmation != normalized_symbol:
                return self._reject(
                    request, account,
                    reason_code="CONFIRMATION_MISMATCH",
                    detail=(
                        f"confirmation_text does not match symbol "
                        f"(got '{normalized_confirmation}', expected "
                        f"'{normalized_symbol}')."
                    ),
                )

        # ============================================================
        # P5 §6 (NEW): STRATEGY source — check cooldown
        # ============================================================
        if request.source == OrderSourceType.STRATEGY and request.strategy_id:
            async with self._session_factory() as session:
                cooldown_svc = StrategyCooldownService(session)
                in_cooldown, until = await cooldown_svc.is_in_cooldown(
                    request.strategy_id,
                )
            if in_cooldown:
                # Don't audit-log this (it would create a tight loop of
                # audit entries for spinning strategies). The logger.warning
                # is the operational signal.
                logger.warning(
                    "order_rejected_cooldown",
                    strategy_id=request.strategy_id,
                    account_id=account.id,
                    cooldown_until=until.isoformat() if until else None,
                )
                return self._reject(
                    request, account,
                    reason_code="STRATEGY_COOLDOWN",
                    detail=(
                        f"Strategy in cooldown until "
                        f"{until.isoformat() if until else 'unknown'}."
                    ),
                )

        # ============================================================
        # P5 §1 (existing): BrokerModeError if LIVE — §7 lifts this
        # ============================================================
        # ... existing BrokerModeError guard ...

        # ============================================================
        # P5 §5 (existing): RiskEngine — circuit breaker, per-day, BP
        # ============================================================
        risk_decision = await self._risk_engine.check(
            request, account=account, current_user_id=current_user_id,
        )
        if risk_decision.rejected:
            outcome = await self._record_rejection(
                request, account, risk_decision,
            )
            # P5 §6 (NEW): set cooldown for failed strategy submissions
            await self._maybe_set_cooldown(request, account, outcome)
            # P5 §6 (NEW): audit LIVE submissions
            await self._maybe_audit_live_submission(
                request, account, outcome, current_user_id,
            )
            return outcome

        # ============================================================
        # Broker adapter submit
        # ============================================================
        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            outcome = await self._record_no_adapter(request, account)
            await self._maybe_set_cooldown(request, account, outcome)
            await self._maybe_audit_live_submission(
                request, account, outcome, current_user_id,
            )
            return outcome

        try:
            submission = await adapter.submit_order(request)
        except Exception as exc:
            outcome = await self._record_broker_error(
                request, account, exc,
            )
            await self._maybe_set_cooldown(request, account, outcome)
            await self._maybe_audit_live_submission(
                request, account, outcome, current_user_id,
            )
            return outcome

        outcome = await self._record_success(request, account, submission)
        # Success: do NOT set cooldown (the order made it to the broker).
        await self._maybe_audit_live_submission(
            request, account, outcome, current_user_id,
        )
        return outcome

    async def _maybe_set_cooldown(
        self,
        request: OrderSubmitRequest,
        account: Account,
        outcome: OrderSubmissionResult,
    ) -> None:
        """If a STRATEGY-sourced order failed, set the 60s cooldown.
        Idempotent — sets cooldown_until = now + 60s every time, which
        is the 'each failure resets the window' semantics."""
        if request.source != OrderSourceType.STRATEGY:
            return
        if request.strategy_id is None:
            return
        if outcome.status not in (OrderStatus.REJECTED, OrderStatus.ERROR):
            # Order accepted by broker or pending — not a submission failure.
            return
        async with self._session_factory() as session:
            cooldown_svc = StrategyCooldownService(session)
            await cooldown_svc.set_cooldown(
                request.strategy_id,
                duration_seconds=60,
                reason=outcome.reason_code or "submission_failed",
            )

    async def _maybe_audit_live_submission(
        self,
        request: OrderSubmitRequest,
        account: Account,
        outcome: OrderSubmissionResult,
        current_user_id: int,
    ) -> None:
        """LIVE_ORDER_SUBMITTED for every LIVE attempt. Paper not audited."""
        if account.mode != AccountMode.live:
            return
        async with self._session_factory() as session:
            AuditLogger.write(
                session,
                actor_type=(
                    AuditActorType.USER if request.source == OrderSourceType.MANUAL
                    else AuditActorType.SYSTEM
                ),
                actor_id=str(current_user_id),
                action=AuditAction.LIVE_ORDER_SUBMITTED,
                target_type="order",
                target_id=outcome.order_id if outcome.order_id else 0,
                payload={
                    "symbol": request.symbol,
                    "side": request.side.value,
                    "qty": str(request.qty),
                    "type": request.type.value,
                    "limit_price": (
                        str(request.limit_price) if request.limit_price else None
                    ),
                    "stop_price": (
                        str(request.stop_price) if request.stop_price else None
                    ),
                    "source": request.source.value,
                    "strategy_id": request.strategy_id,
                    "outcome": outcome.status.value,
                    "reason_code": outcome.reason_code,
                    "account_id": account.id,
                },
                user_id=current_user_id,
            )
            await session.commit()
```

> **Order matters**. The confirmation check happens BEFORE the cooldown check — a user trying to submit a manual order shouldn't be told "the strategy is in cooldown." Confirmation comes before risk engine because confirmation is cheap (no DB query beyond what we've already done loading the account) and risk engine is the most expensive gate.

> **Why not audit when source=STRATEGY and outcome rejected for cooldown?** The cooldown's purpose is to throttle spinning strategies. If every rejection were audited, we'd have a tight loop of audit entries for a stuck strategy — defeating the cooldown's signal-vs-noise benefit. The `logger.warning` is the right place for that signal (it goes to structured logs, not audit log).

- [ ] Confirmation check between BrokerModeError and Risk.
- [ ] Cooldown check after confirmation, before Risk.
- [ ] Cooldown set on STRATEGY+failure outcomes.
- [ ] Audit LIVE submissions regardless of outcome.

---

## §6.5 — Cooldown Management Endpoints

Edit `apps/backend/app/api/v1/strategies.py`. Add two endpoints:

```python
from app.services.strategy_cooldown import StrategyCooldownService


class CooldownStatusResponse(BaseModel):
    strategy_id: int
    in_cooldown: bool
    cooldown_until: Optional[datetime]
    seconds_remaining: int


@router.get("/{strategy_id}/cooldown", response_model=CooldownStatusResponse)
async def strategy_cooldown_status(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    svc = StrategyCooldownService(session)
    status = await svc.status(strategy_id)
    return CooldownStatusResponse(
        strategy_id=status.strategy_id,
        in_cooldown=status.in_cooldown,
        cooldown_until=status.cooldown_until,
        seconds_remaining=status.seconds_remaining,
    )


@router.post("/{strategy_id}/cooldown/clear")
async def clear_strategy_cooldown(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = StrategyCooldownService(session)
    try:
        await svc.clear_cooldown(strategy_id, user_id=current_user.id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found")
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    return {"ok": True, "strategy_id": strategy_id}
```

- [ ] GET cooldown status.
- [ ] POST clear cooldown (audit-logged via the service).

---

## §6.6 — Frontend: `LiveOrderConfirmModal`

Create `apps/frontend/src/components/orders/LiveOrderConfirmModal.tsx`:

```tsx
import { useEffect, useState } from "react";


interface Props {
  symbol: string;
  side: "buy" | "sell";
  qty: string;
  type: string;
  limitPrice?: string | null;
  stopPrice?: string | null;
  accountLabel: string;
  onConfirm: (confirmationText: string) => void;
  onCancel: () => void;
  submitting: boolean;
  error: string | null;
}


export function LiveOrderConfirmModal(props: Props) {
  const [confirmation, setConfirmation] = useState("");

  // Auto-focus the input when the modal opens.
  const inputRef = (el: HTMLInputElement | null) => { if (el) el.focus(); };

  const symbolUpper = props.symbol.trim().toUpperCase();
  const confirmationUpper = confirmation.trim().toUpperCase();
  const matches = confirmationUpper === symbolUpper && confirmationUpper.length > 0;

  // ESC cancels.
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape") props.onCancel();
      if (e.key === "Enter" && matches && !props.submitting) {
        props.onConfirm(confirmation);
      }
    }
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [matches, confirmation, props.submitting]);

  const priceLine = (() => {
    if (props.limitPrice) return `LIMIT @ $${props.limitPrice}`;
    if (props.stopPrice) return `STOP @ $${props.stopPrice}`;
    return "MARKET";
  })();

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[28rem] space-y-3 rounded-lg border-2 border-red-700 bg-gray-950 p-5">
        <div className="flex items-center gap-2">
          <span className="rounded bg-red-700 px-2 py-0.5 text-[10px] font-bold text-white">
            LIVE
          </span>
          <h2 className="text-lg font-semibold text-red-100">
            Confirm live order
          </h2>
        </div>

        <div className="rounded border border-red-800 bg-red-950/40 p-3 text-sm">
          <div className="flex items-baseline gap-2">
            <span className="text-xs text-red-300">Account:</span>
            <span className="font-mono text-red-100">{props.accountLabel}</span>
          </div>
          <div className="mt-2 font-mono text-base text-white">
            {props.side.toUpperCase()} {props.qty} {symbolUpper}
          </div>
          <div className="mt-1 font-mono text-xs text-red-200">{priceLine}</div>
        </div>

        <p className="text-xs text-amber-200">
          This will send a real order to the broker. Type the symbol{" "}
          <code className="rounded bg-gray-800 px-1 font-mono text-amber-100">
            {symbolUpper}
          </code>{" "}
          to confirm.
        </p>

        <input
          ref={inputRef}
          type="text"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          placeholder="symbol"
          className="w-full rounded bg-gray-800 px-2 py-1.5 font-mono text-sm text-white"
          autoComplete="off"
          spellCheck={false}
          disabled={props.submitting}
        />

        {props.error && (
          <div className="rounded border border-red-700 bg-red-950/60 p-2 text-xs text-red-100">
            {props.error}
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button
            onClick={props.onCancel}
            disabled={props.submitting}
            className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200 hover:bg-gray-600"
          >
            Cancel
          </button>
          <button
            onClick={() => props.onConfirm(confirmation)}
            disabled={!matches || props.submitting}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-gray-700"
          >
            {props.submitting ? "Submitting…" : "Submit LIVE order"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

Now edit the existing `OrderForm.tsx` (or equivalent) to gate manual LIVE submits through this modal:

```tsx
// In OrderForm.tsx, on submit:

async function handleSubmit() {
  const isLive = selectedAccount.mode === "live";
  const isManual = source === "manual";

  if (isLive && isManual) {
    // Show confirmation modal; actual submit happens in the modal's callback.
    setLiveConfirmOpen(true);
    return;
  }

  // Paper or strategy: submit directly.
  await doSubmit(/* confirmationText = */ null);
}

async function doSubmit(confirmationText: string | null) {
  setSubmitting(true);
  setError(null);
  try {
    const body: any = {
      account_id: selectedAccount.id,
      symbol, side, type, qty, tif, source,
      strategy_id: source === "strategy" ? selectedStrategyId : null,
    };
    if (limitPrice) body.limit_price = limitPrice;
    if (stopPrice) body.stop_price = stopPrice;
    if (confirmationText) body.confirmation_text = confirmationText;

    const result = await ordersApi.submit(body);
    onSubmitted(result);
    setLiveConfirmOpen(false);
  } catch (e: any) {
    setError(e.detail || String(e));
  } finally {
    setSubmitting(false);
  }
}

// In the JSX:
{liveConfirmOpen && (
  <LiveOrderConfirmModal
    symbol={symbol}
    side={side}
    qty={qty}
    type={type}
    limitPrice={limitPrice}
    stopPrice={stopPrice}
    accountLabel={selectedAccount.label}
    onConfirm={doSubmit}
    onCancel={() => setLiveConfirmOpen(false)}
    submitting={submitting}
    error={error}
  />
)}
```

> The modal is only shown for manual LIVE submissions. Paper orders bypass entirely; strategy-sourced submissions never go through the order form. The `confirmation_text` is forwarded to the API; for paper or strategy paths, it's `null` and the server ignores it.

- [ ] Modal renders order summary clearly.
- [ ] Submit disabled until typed text matches symbol.
- [ ] ESC cancels; Enter submits.
- [ ] Paper submit bypasses modal.

---

## §6.7 — Frontend: `CooldownIndicator`

Create `apps/frontend/src/components/strategies/CooldownIndicator.tsx`:

```tsx
import { useEffect, useState } from "react";
import { strategiesApi } from "@/api/strategies";


interface Props {
  strategyId: number;
}


export function CooldownIndicator({ strategyId }: Props) {
  const [status, setStatus] = useState<{
    in_cooldown: boolean;
    cooldown_until: string | null;
    seconds_remaining: number;
  } | null>(null);
  const [clearing, setClearing] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const s = await strategiesApi.cooldownStatus(strategyId);
        if (!cancelled) setStatus(s);
      } catch { /* silent */ }
    }
    refresh();
    // While in cooldown, refresh every second to count down. Otherwise
    // every 30s is enough.
    const interval = status?.in_cooldown ? 1_000 : 30_000;
    const id = setInterval(refresh, interval);
    return () => { cancelled = true; clearInterval(id); };
  }, [strategyId, status?.in_cooldown]);

  async function handleClear() {
    setClearing(true);
    try {
      await strategiesApi.clearCooldown(strategyId);
      const s = await strategiesApi.cooldownStatus(strategyId);
      setStatus(s);
    } finally {
      setClearing(false);
    }
  }

  if (!status || !status.in_cooldown) return null;

  return (
    <div className="rounded border border-amber-700 bg-amber-950/30 p-2">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-xs font-semibold text-amber-100">
            ⏸ Cooldown active
          </div>
          <div className="mt-0.5 text-[10px] text-amber-300">
            {status.seconds_remaining}s remaining — automatic resume.
            Triggered by a failed order submission.
          </div>
        </div>
        <button
          onClick={handleClear}
          disabled={clearing}
          className="rounded border border-amber-700 px-2 py-1 text-[10px] text-amber-100 hover:bg-amber-900/30 disabled:opacity-50"
        >
          {clearing ? "Clearing…" : "Clear now"}
        </button>
      </div>
    </div>
  );
}
```

Extend `apps/frontend/src/api/strategies.ts`:

```typescript
export const strategiesApi = {
  // ... existing ...
  cooldownStatus: (strategyId: number) =>
    apiFetch<{
      strategy_id: number;
      in_cooldown: boolean;
      cooldown_until: string | null;
      seconds_remaining: number;
    }>(`/api/v1/strategies/${strategyId}/cooldown`),
  clearCooldown: (strategyId: number) =>
    apiFetch<{ ok: boolean }>(
      `/api/v1/strategies/${strategyId}/cooldown/clear`,
      { method: "POST" },
    ),
};
```

Mount on the strategy detail page above the orders table: `<CooldownIndicator strategyId={strategy.id} />`. The component returns null when not in cooldown, so it doesn't add layout noise in the common case.

- [ ] Cooldown indicator renders countdown.
- [ ] Polls every 1s while in cooldown, 30s otherwise.
- [ ] Clear button works and refreshes immediately.

---

## §6.8 — Tests

Create `apps/backend/tests/api/test_p5_live_order_confirmation.py`:

```python
"""Manual LIVE orders require typed-ticker confirmation."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.db.enums import AccountMode, OrderSourceType
from app.db.models.account import Account


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def live_account(session_factory):
    async with session_factory() as session:
        acc = Account(
            user_id=1, broker="alpaca", mode=AccountMode.live,
            label="MyLive", created_at=_now(),
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc.id


@pytest.fixture
async def paper_account(session_factory):
    async with session_factory() as session:
        acc = Account(
            user_id=1, broker="alpaca", mode=AccountMode.paper,
            label="MyPaper", created_at=_now(),
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc.id


@pytest.mark.asyncio
async def test_manual_live_without_confirmation_returns_rejected(
    auth_client, live_account,
):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
    })
    # The order is recorded as REJECTED with reason_code=CONFIRMATION_REQUIRED.
    # API returns 200 with the rejected order in the body (this is the
    # existing OrderRouter contract; rejections are not HTTP errors).
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "CONFIRMATION_REQUIRED"


@pytest.mark.asyncio
async def test_manual_live_with_wrong_confirmation_rejected(
    auth_client, live_account,
):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "MSFT",
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_manual_live_with_correct_confirmation_passes_check(
    auth_client, live_account,
):
    """Confirmation passes; order still rejected by P5 §1 BrokerModeError
    (LIVE not yet enabled). What we're checking is that confirmation
    doesn't reject it FIRST."""
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "AAPL",
    })
    assert r.status_code == 200
    body = r.json()
    # Rejection reason should be from later gate, not confirmation
    assert body["reason_code"] != "CONFIRMATION_REQUIRED"
    assert body["reason_code"] != "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_confirmation_case_insensitive(auth_client, live_account):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "aapl",
    })
    body = r.json()
    assert body["reason_code"] != "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_confirmation_whitespace_stripped(auth_client, live_account):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "  AAPL  ",
    })
    body = r.json()
    assert body["reason_code"] != "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_manual_paper_does_not_require_confirmation(
    auth_client, paper_account,
):
    """Paper accounts don't need confirmation_text."""
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": paper_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
    })
    body = r.json()
    assert body["reason_code"] != "CONFIRMATION_REQUIRED"
    assert body["reason_code"] != "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_strategy_live_does_not_require_confirmation(
    auth_client, live_account, session_factory,
):
    """STRATEGY-sourced orders never need confirmation_text."""
    from app.db.models.strategy import Strategy as StrategyRow
    from app.db.enums import StrategyType, StrategyStatus
    async with session_factory() as session:
        strat = StrategyRow(
            user_id=1, account_id=live_account, name="s", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.LIVE,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        )
        session.add(strat)
        await session.commit()
        await session.refresh(strat)
        strategy_id = strat.id

    r = await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "strategy",
        "strategy_id": strategy_id,
    })
    body = r.json()
    assert body["reason_code"] != "CONFIRMATION_REQUIRED"
    assert body["reason_code"] != "CONFIRMATION_MISMATCH"
```

Create `apps/backend/tests/services/test_p5_strategy_cooldown.py`:

```python
"""StrategyCooldownService tests."""
import pytest
from datetime import datetime, timedelta, timezone

from app.db.enums import (
    BrokerMode, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.services.strategy_cooldown import (
    DEFAULT_COOLDOWN_SECONDS, StrategyCooldownService,
)


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.paper,
            label="Paper", created_at=_now(),
        ))
        session.add(StrategyRow(
            id=10, user_id=1, account_id=1, name="s10", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_status_not_in_cooldown_initially(session_factory, seeded):
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        status = await svc.status(10)
    assert status.in_cooldown is False
    assert status.seconds_remaining == 0


@pytest.mark.asyncio
async def test_set_cooldown_then_status(session_factory, seeded):
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10, duration_seconds=60, reason="test")
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        status = await svc.status(10)
    assert status.in_cooldown is True
    assert 55 <= status.seconds_remaining <= 60


@pytest.mark.asyncio
async def test_is_in_cooldown_returns_true_and_until(session_factory, seeded):
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10)
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        in_cd, until = await svc.is_in_cooldown(10)
    assert in_cd is True
    assert until is not None
    assert until > _now()


@pytest.mark.asyncio
async def test_cooldown_expires_naturally(session_factory, seeded):
    """Backdate the cooldown to test expiration logic."""
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.cooldown_until = _now() - timedelta(seconds=10)
        await session.commit()
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        in_cd, until = await svc.is_in_cooldown(10)
    assert in_cd is False
    assert until is None


@pytest.mark.asyncio
async def test_set_cooldown_extends_existing(session_factory, seeded):
    """Calling set_cooldown twice replaces the deadline; second call wins."""
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10, duration_seconds=10)
    first_until = (await _read_until(session_factory, 10))

    import asyncio
    await asyncio.sleep(0.05)

    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10, duration_seconds=60)
    second_until = (await _read_until(session_factory, 10))

    assert second_until > first_until


async def _read_until(session_factory, strategy_id):
    async with session_factory() as session:
        strat = await session.get(StrategyRow, strategy_id)
        return strat.cooldown_until


@pytest.mark.asyncio
async def test_clear_cooldown_resets_state(session_factory, seeded):
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10)
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.clear_cooldown(10, user_id=1)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.cooldown_until is None


@pytest.mark.asyncio
async def test_clear_cooldown_audits(session_factory, seeded):
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10)
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.clear_cooldown(10, user_id=1)

    from app.db.models.audit_log import AuditLog
    from sqlalchemy import select
    async with session_factory() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "strategy_cooldown_cleared")
        )).scalars().all()
    assert len(audits) == 1
    assert audits[0].target_id == 10


@pytest.mark.asyncio
async def test_clear_cooldown_other_user_raises_permission(session_factory, seeded):
    async with session_factory() as session:
        session.add(User(id=2, email="other@local"))
        await session.commit()

    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.set_cooldown(10)
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        with pytest.raises(PermissionError):
            await svc.clear_cooldown(10, user_id=2)


@pytest.mark.asyncio
async def test_clear_cooldown_when_not_in_cooldown_is_noop(session_factory, seeded):
    """Clearing when no cooldown set should not raise and should not audit."""
    async with session_factory() as session:
        svc = StrategyCooldownService(session)
        await svc.clear_cooldown(10, user_id=1)

    from app.db.models.audit_log import AuditLog
    from sqlalchemy import select
    async with session_factory() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "strategy_cooldown_cleared")
        )).scalars().all()
    assert len(audits) == 0
```

Create `apps/backend/tests/api/test_p5_live_order_audit.py`:

```python
"""LIVE_ORDER_SUBMITTED audit logging tests."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.db.enums import AccountMode
from app.db.models.account import Account
from app.db.models.audit_log import AuditLog
from sqlalchemy import select


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def live_account(session_factory):
    async with session_factory() as session:
        acc = Account(
            user_id=1, broker="alpaca", mode=AccountMode.live,
            label="MyLive", created_at=_now(),
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc.id


@pytest.fixture
async def paper_account(session_factory):
    async with session_factory() as session:
        acc = Account(
            user_id=1, broker="alpaca", mode=AccountMode.paper,
            label="Paper", created_at=_now(),
        )
        session.add(acc)
        await session.commit()
        await session.refresh(acc)
        return acc.id


@pytest.mark.asyncio
async def test_live_order_submitted_audits_on_attempt(
    auth_client, live_account, session_factory,
):
    """Even a rejected LIVE order audits."""
    await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "AAPL",
    })

    async with session_factory() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "live_order_submitted")
        )).scalars().all()
    assert len(audits) >= 1
    payload = audits[0].payload
    assert payload["symbol"] == "AAPL"
    assert payload["side"] == "buy"
    assert payload["source"] == "manual"


@pytest.mark.asyncio
async def test_live_confirmation_failure_still_audits(
    auth_client, live_account, session_factory,
):
    """A wrong-confirmation rejection still audits — every LIVE attempt."""
    await auth_client.post("/api/v1/orders", json={
        "account_id": live_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
        "confirmation_text": "MSFT",   # wrong
    })

    async with session_factory() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "live_order_submitted")
        )).scalars().all()
    assert len(audits) >= 1
    payload = audits[0].payload
    assert payload["outcome"] == "rejected"
    assert payload["reason_code"] == "CONFIRMATION_MISMATCH"


@pytest.mark.asyncio
async def test_paper_orders_do_not_audit_live_submitted(
    auth_client, paper_account, session_factory,
):
    """Paper submissions don't create LIVE_ORDER_SUBMITTED entries."""
    await auth_client.post("/api/v1/orders", json={
        "account_id": paper_account,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day", "source": "manual",
    })

    async with session_factory() as session:
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "live_order_submitted")
        )).scalars().all()
    assert len(audits) == 0


@pytest.mark.asyncio
async def test_cooldown_endpoints(
    auth_client, paper_account, session_factory,
):
    """GET cooldown → POST clear → audit."""
    from app.db.models.strategy import Strategy as StrategyRow
    from app.db.enums import StrategyType, StrategyStatus
    async with session_factory() as session:
        strat = StrategyRow(
            user_id=1, account_id=paper_account, name="s", version="0.1.0",
            type=StrategyType.PYTHON, status=StrategyStatus.PAPER,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        )
        from datetime import timedelta
        strat.cooldown_until = _now() + timedelta(seconds=60)
        session.add(strat)
        await session.commit()
        await session.refresh(strat)
        strategy_id = strat.id

    # GET status
    r = await auth_client.get(f"/api/v1/strategies/{strategy_id}/cooldown")
    assert r.status_code == 200
    body = r.json()
    assert body["in_cooldown"] is True
    assert body["seconds_remaining"] > 0

    # POST clear
    r = await auth_client.post(f"/api/v1/strategies/{strategy_id}/cooldown/clear")
    assert r.status_code == 200

    # GET status → now clear
    r = await auth_client.get(f"/api/v1/strategies/{strategy_id}/cooldown")
    assert r.json()["in_cooldown"] is False
```

Run:

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m pytest tests/api/test_p5_live_order_confirmation.py \
              tests/api/test_p5_live_order_audit.py \
              tests/services/test_p5_strategy_cooldown.py -v
.\.venv\Scripts\python.exe -m pytest -q --cov-branch

# All eight invariants
bash scripts/check_adr0002.sh
bash scripts/check_strategy_isolation.sh
bash scripts/check_mcp_readonly.sh
bash scripts/check_broker_isolation.sh
bash scripts/check_no_env_credentials.sh
.\.venv\Scripts\python.exe scripts\check_risk_coverage.py
.\.venv\Scripts\python.exe scripts\check_p2_coverage.py
.\.venv\Scripts\python.exe scripts\check_p3_coverage.py
cd ../..
```

- [ ] 7 confirmation tests pass.
- [ ] 9 cooldown service tests pass.
- [ ] 6 audit / endpoint tests pass.
- [ ] Full suite green; eight CI invariants green.

---

## §6.9 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30
./scripts/login_helper.sh    # session cookie in /tmp/cookies.txt

PAPER_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[0].id')

# 1. Paper smoke — byte-identical to baseline (no confirmation, no cooldown)
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, reason_code}'
# Expect: status=accepted, reason_code=null

# 2. Confirm no LIVE_ORDER_SUBMITTED audit was written
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*) FROM audit_log WHERE action='live_order_submitted';"
# Expect: 0

# 3. Create a LIVE account directly via DB (P5 §1 blocks the API path)
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "INSERT INTO accounts (user_id, broker, mode, label, created_at) VALUES (1, 'alpaca', 'live', 'TestLive', datetime('now'));"
LIVE_ACC_ID=$(docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT id FROM accounts WHERE mode='live' ORDER BY id DESC LIMIT 1;" | tr -d '\r')
echo "LIVE_ACC_ID=${LIVE_ACC_ID}"

# 4. Manual LIVE order with NO confirmation → CONFIRMATION_REQUIRED
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${LIVE_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, reason_code}'
# Expect: status=rejected, reason_code=CONFIRMATION_REQUIRED

# 5. Manual LIVE with WRONG ticker → CONFIRMATION_MISMATCH
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${LIVE_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\",
    \"confirmation_text\": \"MSFT\"
  }" | jq '{status, reason_code}'
# Expect: status=rejected, reason_code=CONFIRMATION_MISMATCH

# 6. Manual LIVE with correct ticker → confirmation passes, BrokerModeError follows
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${LIVE_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\",
    \"confirmation_text\": \"AAPL\"
  }" | jq '{status, reason_code}'
# Expect: status=rejected, reason_code != CONFIRMATION_* (P5 §1 guard fires)

# 7. Confirm three LIVE_ORDER_SUBMITTED audits (one per LIVE attempt above)
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "SELECT count(*), MAX(payload) FROM audit_log WHERE action='live_order_submitted';"
# Expect: 3, with payload showing the last attempt

# 8. Cooldown smoke — set cooldown directly, verify GET reflects it
STRATEGY_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies | jq -r '.items[0].id')
if [ -z "$STRATEGY_ID" ] || [ "$STRATEGY_ID" == "null" ]; then
  echo "No strategy; skipping cooldown smoke"
else
  docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
    "UPDATE strategies SET cooldown_until=datetime('now', '+60 seconds') WHERE id=${STRATEGY_ID};"

  curl -s -b /tmp/cookies.txt \
    http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/cooldown | jq
  # Expect: in_cooldown=true, seconds_remaining ≈ 60

  # 9. Clear cooldown via API
  curl -s -b /tmp/cookies.txt -X POST \
    http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/cooldown/clear | jq
  # Expect: ok=true

  # 10. Re-check
  curl -s -b /tmp/cookies.txt \
    http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/cooldown | jq
  # Expect: in_cooldown=false

  # 11. Audit recorded
  docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
    "SELECT action, target_id FROM audit_log WHERE action='strategy_cooldown_cleared' ORDER BY id DESC LIMIT 1;"
fi

# 12. UI check (manual): paper account → no confirmation modal.
#     Switch to LIVE account in the order form → modal appears on Submit.
#     Type wrong symbol → submit disabled. Type correct symbol → submit enabled.
#     ESC dismisses; Enter submits when matched.

docker compose down
```

- [ ] Paper baseline unchanged.
- [ ] Manual LIVE without confirmation rejected with CONFIRMATION_REQUIRED.
- [ ] Manual LIVE with wrong text rejected with CONFIRMATION_MISMATCH.
- [ ] Manual LIVE with correct text passes confirmation gate.
- [ ] Three LIVE_ORDER_SUBMITTED audits recorded.
- [ ] Cooldown GET/clear endpoints work.
- [ ] **UI modal appears only for manual LIVE submissions.**

---

## §6.10 — Runbook

Create `docs/runbook/live-order-safety.md`:

```markdown
# Live Order Safety (P5 §6)

Two layers, both narrow in scope:

| Layer | Scope | What it catches |
|---|---|---|
| Typed-ticker confirmation | Manual LIVE orders | "I clicked the wrong button" |
| Per-strategy cooldown | Strategy orders that fail | Runaway retry loops |

## Typed-ticker confirmation

For manual orders on LIVE accounts, the workbench requires the user to
type the order's ticker in a confirmation modal. The server re-validates
the typed text matches the symbol (case-insensitive, whitespace
stripped). Mismatches reject with `CONFIRMATION_MISMATCH`. Missing
confirmation_text rejects with `CONFIRMATION_REQUIRED`.

Strategy-sourced orders and all paper orders bypass this layer.

### What if I typed the wrong ticker?

The order rejects with `CONFIRMATION_MISMATCH` and is recorded in the
audit log as a LIVE_ORDER_SUBMITTED with outcome=rejected. No order was
sent to the broker. Re-submit with the correct text.

### Can I disable this?

No. The check is server-enforced and applies to every direct API call
as well. If you need automated LIVE submissions, use a strategy
(source=STRATEGY) — strategies are authenticated by their identity and
don't need per-order confirmation.

## Per-strategy cooldown

When a strategy submits an order that doesn't reach the broker (risk
rejection, broker adapter error, validation error), that strategy
enters a 60-second cooldown. Subsequent orders from the same strategy
during the window reject with `STRATEGY_COOLDOWN`.

The cooldown:
- Is per-strategy (not per-account, not global).
- Resets to 60s on each failed submission (a strategy failing every 30s
  will stay in cooldown indefinitely).
- Self-clears after 60s if no further failures.
- Survives backend restart (persisted on `strategies.cooldown_until`).

### What if my strategy got stuck in cooldown?

Two options:
1. Wait 60s. Self-clearing.
2. Settings → Strategy detail page → "Clear cooldown" button. Audit-logged.

### When does cooldown NOT fire?

- Successful order submissions (the order reached the broker).
- Manual (source=MANUAL) orders. Manual cooldown would frustrate the
  user without much safety benefit; the typed-ticker layer is the
  manual defense.
- Post-acceptance failures (partial fills, broker-side cancels, etc.).
  Cooldown is about submission attempts only.

## LIVE_ORDER_SUBMITTED audit

Every LIVE order submission writes an audit_log row with action
`live_order_submitted`, regardless of outcome. Payload:

```json
{
  "symbol": "AAPL",
  "side": "buy",
  "qty": "100",
  "type": "market",
  "limit_price": null,
  "stop_price": null,
  "source": "manual",
  "strategy_id": null,
  "outcome": "accepted",
  "reason_code": null,
  "account_id": 2
}
```

Paper submissions do NOT generate live_order_submitted audits. The
existing per-order row in the `orders` table is the paper trail; for
live, the audit log provides an immutable record independent of the
orders table.

## Inspecting

### Recent LIVE order audit trail

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT created_at, payload
FROM audit_log
WHERE action='live_order_submitted'
ORDER BY id DESC LIMIT 20;
"
```

### Strategies currently in cooldown

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT id, name, cooldown_until
FROM strategies
WHERE cooldown_until IS NOT NULL AND cooldown_until > datetime('now')
ORDER BY cooldown_until;
"
```

### Strategies that hit cooldown recently

The audit log only records manual cooldown clears. To find strategies
that ENTERED cooldown, search the structured logs for `strategy_cooldown_set`:

```bash
grep strategy_cooldown_set /var/log/workbench/backend.log | tail -20
```
```

- [ ] Runbook committed at `docs/runbook/live-order-safety.md`.

---

## §6.11 — Commit and PR

```bash
git add apps/backend/app/db/models/strategy.py
git add apps/backend/app/db/enums.py
git add apps/backend/alembic/versions/
git add apps/backend/app/api/v1/schemas/orders.py
git add apps/backend/app/services/strategy_cooldown.py
git add apps/backend/app/orders/router.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/tests/api/test_p5_live_order_confirmation.py
git add apps/backend/tests/api/test_p5_live_order_audit.py
git add apps/backend/tests/services/test_p5_strategy_cooldown.py
git add apps/frontend/src/components/orders/LiveOrderConfirmModal.tsx
git add apps/frontend/src/components/orders/OrderForm.tsx
git add apps/frontend/src/components/strategies/CooldownIndicator.tsx
git add apps/frontend/src/api/strategies.ts
git add docs/runbook/live-order-safety.md

git commit -m "feat(p5): live order safety — typed-ticker + strategy cooldown (P5 §6)

- New strategies.cooldown_until column (nullable datetime). Survives
  backend restart.
- New OrderSubmitRequest.confirmation_text field (optional at schema).
  Required by OrderRouter when source=MANUAL && account.mode=LIVE;
  server-side check (case-insensitive, whitespace-stripped match against
  symbol). Reject codes: CONFIRMATION_REQUIRED, CONFIRMATION_MISMATCH.
- New StrategyCooldownService (status, is_in_cooldown, set_cooldown,
  clear_cooldown). 60s default duration; each failure resets the window
  (no 'first-failure' semantics). Clear is permission-checked + audit-logged.
- OrderRouter integration: confirmation check after BrokerModeError,
  cooldown check after confirmation, both before RiskEngine. Cooldown
  set on STRATEGY-sourced rejections/errors (not on success, not on
  partial fills). LIVE_ORDER_SUBMITTED audit every LIVE attempt.
- New endpoints: GET /api/v1/strategies/{id}/cooldown,
  POST /api/v1/strategies/{id}/cooldown/clear.
- New audit actions: LIVE_ORDER_SUBMITTED, STRATEGY_COOLDOWN_CLEARED.
- Frontend LiveOrderConfirmModal — intercepts manual LIVE submits;
  typed text must match symbol; ESC cancels, Enter submits when matched.
- Frontend CooldownIndicator — countdown badge on strategy detail page
  with manual-clear button. Polls every 1s while in cooldown.
- 22 backend tests; 8 CI invariants all green.

NOT in this PR:
- TOTP-per-order. Typed-ticker is the friction layer.
- Cooldown escalation. 60s every time; operator notices stuck strategies
  via LIVE_ORDER_SUBMITTED audit stream.
- Order amend / modify flow.

Load-bearing: P1-§5 paper smoke produces byte-identical chains
(neither new path fires for paper+manual or paper+strategy with no failures)."

git push -u origin feat/p5-session6-order-safety

gh pr create \
  --title "feat(p5): live order safety (P5 §6)" \
  --body "P5 Session 6 — typed-ticker confirmation + strategy cooldown.

Two friction layers:
1. Manual LIVE orders require server-validated typed-ticker confirmation.
2. Strategy orders that fail to submit set a 60s per-strategy cooldown.

Load-bearing: P1-§5 paper smoke byte-identical.

PLEASE: do not merge in flow. Re-read the OrderRouter integration with
attention to the order of operations (confirmation BEFORE cooldown
BEFORE risk engine) and the audit fire-points (every LIVE attempt,
including pre-broker rejections)."

gh pr checks

# Walk away ≥1 hour. Re-read with attention to:
# - The OrderRouter integration — every code path through submit() ends
#   with both _maybe_set_cooldown and _maybe_audit_live_submission.
# - The confirmation matching is case-insensitive + whitespace-stripped
#   on both sides. Wrong assumption: 'must be exact-case match' would
#   reject 'aapl' when symbol is 'AAPL'.
# - Cooldown does NOT fire on success — successful order submissions
#   should not penalize subsequent submissions from the same strategy.

# Squash-merge convention (matches Sessions 4 + 5)
gh pr merge --squash --subject "feat(p5): live order safety (P5 §6) (#NN)" --delete-branch
git checkout main && git pull
git tag -a p5-session6-complete -m "P5 §6 live order safety complete"
git push origin p5-session6-complete
```

- [ ] PR opened; CI green incl. all eight invariants + ADR 0002 test.
- [ ] Walked away ≥1 hour (Session 4 skipped this; Session 5 honored it).
- [ ] All eight invariants pass.
- [ ] PR merged.
- [ ] Tag pushed.

---

## Verification Checklist (full session)

- [ ] §6.1 cooldown_until column + LIVE_ORDER_SUBMITTED audit action.
- [ ] §6.2 confirmation_text field on OrderSubmitRequest.
- [ ] §6.3 StrategyCooldownService with status/set/clear semantics.
- [ ] §6.4 OrderRouter integration: confirmation + cooldown + audit hooks.
- [ ] §6.5 Cooldown management endpoints.
- [ ] §6.6 LiveOrderConfirmModal renders only for manual LIVE.
- [ ] §6.7 CooldownIndicator countdown + manual clear.
- [ ] §6.8 22 backend tests pass.
- [ ] §6.9 Smoke: paper unchanged, LIVE rejected at correct gates, audits fire.
- [ ] §6.10 Runbook covers both layers + inspection queries.
- [ ] §6.11 PR merged, tag pushed.
- [ ] Eight CI invariants green.

---

## Notes & Gotchas

1. **Server-side enforces confirmation; the modal is just UX.** Gotcha-of-record: someone bypassing the frontend (direct API call, browser inspector, curl) still hits the OrderRouter rule. The modal is convenience. The defense is the server check.

2. **Confirmation is case-insensitive and whitespace-stripped on both sides.** Gotcha at §6.4: `confirmation_text.strip().upper() == request.symbol.strip().upper()`. "aapl" matches "AAPL". " AAPL " matches "AAPL". "AAPL.US" does NOT match "AAPL" (the dot is part of the ticker). Test coverage: §6.8 includes both case-insensitivity and whitespace-stripping cases.

3. **Cooldown only fires on submission failure.** Gotcha at §6.4: post-acceptance events (partial fills, broker-side cancellations, exchange rejections) do NOT trigger cooldown. The reasoning: those failures happen at the broker after we successfully submitted; they're not a sign that the strategy is in a tight retry loop. If the broker keeps rejecting orders for "invalid symbol" or similar, the strategy IS in a tight loop and will cool down naturally on the next submission attempt.

4. **Cooldown does not fire for manual orders.** Gotcha at §6.4 + §6.10 runbook: `_maybe_set_cooldown` early-returns if `request.source != STRATEGY`. The reasoning: a user fat-fingering a manual order doesn't need a 60s timeout to prevent loops; that's not how humans submit orders. The typed-ticker is the manual defense; cooldown is the algorithmic defense.

5. **Each failure resets the cooldown window.** Gotcha at §6.3: `set_cooldown` overwrites `cooldown_until` unconditionally. A strategy that fails every 30s stays in cooldown forever. This is intentional — the operator sees the spinning strategy via the structured-log `strategy_cooldown_set` events and the lack of progress in the orders table, then manually HALTs or fixes the strategy. P5+ polish could add escalation (60s → 5min → HALT) but the simple version is sufficient.

6. **Cooldown is per-strategy, not per-account.** Gotcha §6.3: two strategies on the same account are independent. One can be in cooldown while the other submits orders freely. This is correct — a bug in strategy A shouldn't block strategy B's legitimate trades.

7. **LIVE_ORDER_SUBMITTED audits even rejections.** Gotcha at §6.4: every LIVE order attempt writes an audit row, even if it never reaches the broker. The audit log is the immutable record of "what live trade attempts happened." A rejection-by-risk-engine and a rejection-by-broker look the same from the audit's perspective; both are recorded with their `reason_code`.

8. **Paper orders never write LIVE_ORDER_SUBMITTED audits.** Gotcha at §6.4: `_maybe_audit_live_submission` early-returns if `account.mode != LIVE`. The orders table itself is the paper audit trail. Auditing every paper order to the audit log would dwarf the live entries we actually care about.

9. **The cooldown check happens BEFORE the risk engine.** Gotcha at §6.4: this is intentional. The risk engine is the most expensive gate (broker round-trip for buying power, DB queries for circuit breaker). Skipping it for a cooled-down strategy is the right optimization. The order is: BrokerModeError (cheapest, in-memory) → confirmation (string compare) → cooldown (one DB read) → risk engine (potentially broker call) → broker submit.

10. **The cooldown check uses a fresh session for the DB read.** Gotcha at §6.4: `async with self._session_factory() as session` for the cooldown lookup. The OrderRouter doesn't hold a long-lived session — each phase uses its own session. This avoids the "I read cooldown 200ms ago and the value changed before I rejected" race. The race is still possible (between read and reject) but acceptable; the worst case is one extra order slipping through during the millisecond window.

11. **Manual cooldown clear is normal user authority.** Gotcha at §6.3 + §6.5: no typed-confirmation, no TOTP re-check. The reasoning: clearing a cooldown doesn't unlock any new capability — it just lets the user retry sooner. If they were going to retry in 60s anyway, allowing them to retry now isn't an escalation of privilege. The audit captures who and when.

12. **The `LIVE_ORDER_SUBMITTED` payload includes prices as strings.** Gotcha at §6.4: `str(request.limit_price)` not `float()`. Decimals serialize to strings in JSON to preserve precision; the audit log is the durable record and we never want to lose decimal precision to float rounding. The orders table itself uses Decimal columns; the audit payload mirrors that as strings.

13. **The cooldown indicator polls 1Hz while in cooldown.** Gotcha at §6.7: the React component runs `setInterval(refresh, 1000)` while in cooldown to update the countdown display. At 30 strategies × 1Hz = 30 polls/second across the UI, that's still trivial. But: if you scale to hundreds of strategies in cooldown simultaneously, switch to a WebSocket-pushed countdown. P5+ polish; not in §6 scope.

14. **Don't bundle P5 §7 (activation wizard) into this PR.** Each P5 session is its own tag. §7 is the session that finally lifts the BrokerModeError guard and lets the LIVE order path execute end-to-end.

15. **Two daily-loss mechanisms now coexist** (Session 5 Results punch list inherited here). The existing global daily-loss halt at `app/risk/halt.py` (RiskEngine step 9) and the account-scoped circuit breaker from Session 5 both fire as separate gates in the risk engine. §6's OrderRouter integration sits *above* the RiskEngine, so it sees both halts uniformly — no §6 change needed, but worth flagging during walk-away review: a Live order rejection in §6 might come from either halt mechanism, and the `reason_code` in the audit payload identifies which.

16. **Shared `ensure_aware()` is the canonical SQLite datetime fix** (introduced in Session 5 §5.0). Session 6 inherits this discipline: `cooldown_until` is `DateTime(timezone=True)` but SQLite returns it naive on read. `StrategyCooldownService.is_in_cooldown` and `.status` both call `ensure_aware()` before comparing against `datetime.now(timezone.utc)`. Without this coercion: a strategy could appear "not in cooldown" because the naive comparison silently returns False instead of raising TypeError. Silent-correctness bug risk, not a crash.

17. **`_router_token` discipline preserved.** Session 2's load-bearing invariant: broker mutators (`submit_order`/`cancel_order`/`replace_order`) are `_router_token`-gated; only `OrderRouter` itself passes it. §6.4's existing `submit_order` call already lives inside the router and passes the token; the new `_maybe_set_cooldown` and `_maybe_audit_live_submission` helpers do NOT call adapter mutators (they only write to the DB). `tests/test_adr_0002_invariant.py` stays green without edit.

18. **Strategy→account mapping is via `user_id` + status↔mode, not a direct FK** (Session 5 Results deviation). §6's cooldown service uses `strategy_id` directly, so it doesn't need this mapping. But §6.5's "Clear cooldown" endpoint authorization uses `Strategy.user_id == current_user.id` for ownership verification (the right check; do NOT try to join through `account` — that's the same pattern Session 5's HALT cascade established).

19. **Expect execution-surfaced drift.** This v0.2 catches the knowable drift from Sessions 0–5 Results. It cannot catch unknown drift in the actual codebase that no prior session needed to surface. Session 5's execution found ~6 such items (`Fill.signed_direction` missing, `SQLEnum` stores names, `app/risk/halt.py` existing, etc.). Session 6 will likely find a similar list. Before pasting any §6.4 OrderRouter code, do a grep+read pass on `app/orders/router.py` and `app/api/v1/schemas/orders.py` to confirm the actual shape. Adjust the integration to match the code; don't force the v0.2 shape onto code that's different. Capture deviations in Session 6 Results as Session 5 did.

---

*End of P5 Session 6 v0.2. Updated in-place from v0.1 (2026-05-23) with 14 drift corrections from Sessions 0–5 Results, the shared `ensure_aware()` helper integration from Session 5 §5.0, and a candid acknowledgment of the unknown drift that this analysis cannot predict.*
