# P5 Session 5 — Live-Mode Risk Gates

| Field | Value |
|---|---|
| Document version | **v0.2** (updated in-place from v0.1; 13 drift corrections from `TradingWorkbench_P5_Session5_DriftAnalysis_v0.1.md`) |
| Date | 2026-05-31 |
| Phase | **P5 — Live Trading**, **§5** (entirely) |
| Predecessor | `TradingWorkbench_P5_Session4_v1.0.md` (tag `p5-session4-complete`, PR #40 @ `b5b37da`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | Live-mode risk hardening: tighter LIVE-scoped risk-limit defaults, daily-loss circuit breaker as hard halt (ADR 0004), per-day order cap, PDT warning surfaces, pre-trade buying-power check. New `accounts.circuit_breaker_tripped_at`. New `risk_limits.max_orders_per_day`. Manual reset endpoint with audit. New `StrategyStatus.HALTED`. Endpoints + UI for risk-limits management and PDT banner. **No live orders are yet possible** (P5 §1 BrokerModeError still active). Single PR. |
| Estimated wall time | 5 hours |
| Stopping point | `git tag p5-session5-complete` |
| Out of scope | Background PnL polling (we check on order submission only — open-position drift between checks doesn't trip). Auto-reset of circuit breaker. Auto-restart of HALTED strategies. PDT auto-detection that blocks trading. Margin / day-trading buying power. Stop-loss enforcement at the workbench level (broker handles it). Liquidation of open positions when breaker trips. Per-symbol limits or per-strategy gross exposure caps. |

---

## Updated in v0.2 (drift corrections from shipped Sessions 1–4)

This file was updated 2026-05-31 to reconcile against what Sessions 1, 2, 3, 4 actually shipped (the original v0.1 dated 2026-05-23 was drafted before any of them executed). Full rationale in `TradingWorkbench_P5_Session5_DriftAnalysis_v0.1.md`. The corrections applied below:

1. **`BrokerMode` → `AccountMode`.** Session Zero confirmed `BrokerMode` doesn't exist; the enum is `AccountMode` (values `paper` / `live`, lowercase). Affects §5.4, §5.5, §5.6, §5.9.
2. **`BrokerAccountSnapshot` → `dict[str, Any]`.** Session 2 v1.0 rejected typed DTOs; `BrokerAdapter.get_account()` returns a dict. Affects §5.3 `_fetch_equity` and §5.4 `BuyingPowerChecker.check()`.
3. **`adapter.get_account()` is sync, not async.** Drop `await`. Same root cause as #2.
4. **Shared `ensure_aware()` helper at `app/utils/time.py`.** Session 3 added `_aware()` to `stub.py`; Session 4 added `_ensure_aware()` to `credential_store.py`. Session 5 is the third site needing this; extracting to a shared module avoids three more copies. Affects §5.2, §5.3, §5.5.
5. **Paths and tooling.** Windows working dir (`C:\LLM-RAG-APP\ai-trading-app`); `uv run` → `.\.venv\Scripts\python.exe`; pytest needs `--cov-branch` flag. Affects Prerequisites and §5.13.
6. **`check_adr0002.sh` removed from Prerequisites.** Doesn't exist; ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + `_router_token`.
7. **Eight invariants count is correct.** Sessions 2 + 4 added `check_broker_isolation.sh` and `check_no_env_credentials.sh`. Session 5 adds none.
8. **API router wired via `app/api/v1/__init__.py`** (Session 4 deviation note), not directly in `main.py`. Affects §5.6 closing.
9. **Frontend uses `apiFetch` + React Query**, not `apiClient.get/put` sketch. Affects §5.8 (no body changes here; the patterns are conventional but documented for the implementer).
10. **`StrategyStatus` follows project enum convention.** Verify whether it's `(str, Enum)` or `StrEnum` in current `app/db/enums.py` and match. Both work functionally; convention matters for ruff `UP042`.
11. **Migration acquires precondition state before DDL** (Session 4 deviation pattern). For §5.1.4 this is mild (no master key needed) but follow the discipline: any precondition checks happen before column adds.
12. **Confirm `_router_token` discipline preserved.** The new risk gates call only adapter *read* methods (`get_account()`); no mutator calls. `tests/test_adr_0002_invariant.py` stays green without edit.
13. **`BuyingPowerChecker` fail-open on adapter errors** is the chosen posture (matches v0.1's implicit choice). A future hardening pass could switch to fail-closed or trip-the-breaker; explicitly out of §5 scope.

**One small addition this session needs**: create `apps/backend/app/utils/time.py` with `ensure_aware(dt)`. Then refactor `app/auth/stub.py::_aware` and `app/security/credential_store.py::_ensure_aware` to import the shared helper. New code in §5.2 / §5.3 / §5.5 uses the shared helper.

---

## ⚠ Real-money posture (recap)

Three principles from the P5 checklist drive the design of every gate in this session:

1. **Failure modes that could cost money default to halting, not retrying.** The circuit breaker is a hard stop — not a "reduce position size" or "warn and continue." When it trips, every live order is rejected and every live strategy is HALTED until a human resets it.

2. **Live actions require irrecoverable affirmative steps.** Resetting the circuit breaker is not a one-click "are you sure?" — it's a typed confirmation. The user must understand that resetting means resuming trading.

3. **Paper and live are sibling code paths.** The risk gates apply to both, but LIVE-scoped `risk_limits` rows hold the tighter defaults. Paper continues to work with its existing limits; live gets the conservative set.

This session's load-bearing assertion: **paper smoke from P1-§4 still produces byte-identical order chains.** New code paths only fire under conditions paper accounts don't reach.

---

## Session Goal

After this session:
- New `StrategyStatus.HALTED` enum value. Distinct from ERROR (crashed) and IDLE (user-stopped). HALTED strategies are paused by system policy; restart requires explicit user action.
- New `risk_limits.max_orders_per_day` column. Default per mode: PAPER 200, LIVE 20.
- New `accounts.circuit_breaker_tripped_at` column (nullable datetime). NULL means "currently OK."
- Migration creates a default LIVE-scoped `risk_limits` row for user_id=1 with the tight defaults: `max_position_qty=10`, `max_position_notional=$5,000`, `max_gross_exposure=$25,000`, `max_daily_loss=$500`, `max_orders_per_minute=3`, `max_orders_per_day=20`.
- New `app/risk/circuit_breaker.py`: `CircuitBreakerService` with `check(account_id) → CircuitBreakerStatus`, `trip(account_id, reason, payload)`, `reset(account_id, user_id)`. Trip halts all strategies on the account, rejects pending orders, persists state, audit-logs.
- New `app/risk/pdt_analyzer.py`: `PdtAnalyzer.compute(account_id) → PdtStatus`. Identifies day trades from `fills` in last 5 trading days (US/Eastern), returns count and is_at_risk flag.
- New `app/risk/buying_power.py`: `BuyingPowerChecker.check_sufficient(account, request) → BuyingPowerDecision`. For LIVE: calls `BrokerAdapter.get_account()` for live buying power. For PAPER: skipped (Alpaca paper enforces it on the broker side).
- RiskEngine extended: daily-loss check, per-day order count check, pre-trade buying-power check (LIVE only).
- New endpoints:
  - `GET /api/v1/accounts/{id}/risk-state` — circuit breaker + PDT + daily PnL summary
  - `POST /api/v1/accounts/{id}/risk/reset-circuit-breaker` — manual reset, typed-name confirmation server-side
  - `GET /api/v1/risk-limits` — list user's risk limits
  - `PUT /api/v1/risk-limits/{id}` — update risk limits (audit-logged)
- New audit actions: `CIRCUIT_BREAKER_TRIPPED`, `CIRCUIT_BREAKER_RESET`, `RISK_LIMITS_UPDATED`.
- Frontend: PDT warning banner on account dashboard; circuit-breaker state indicator; Settings → Risk Limits page; reset modal with typed account-name confirmation.
- ADR 0004 documented: daily-loss circuit breaker as hard halt.
- P1-§4 paper smoke produces byte-identical chains. Eight CI invariants pass.

What does NOT happen this session:
- **No background PnL polling.** The breaker checks on order submission only. A held position that drifts into a deep loss with no order activity will NOT trip until the next attempted order. Documented as a known limitation; P5+ polish if real users hit it.
- **No auto-reset of the breaker.** It stays tripped until manually reset. "Reset at midnight" sounds reasonable but encodes the assumption that the trader has had time to look at what happened — and the whole point is for the trader to look at what happened.
- **No auto-restart of HALTED strategies after reset.** Reset re-enables order submission for the account; each strategy must be started manually. This forces the user to confirm each strategy is still appropriate before resuming.
- **No liquidation when the breaker trips.** Existing positions stay. The user decides whether to close them. Auto-liquidation would itself be a series of orders that the breaker is supposed to prevent.
- **No PDT auto-block.** PDT is a warning surface only.
- **No live orders yet.** P5 §1's `BrokerModeError` still fires; this session's gates apply to LIVE accounts in principle but live order submission is opened up by P5 §7's wizard.

---

## Prerequisites Check

```powershell
# from repo root; uv is not on PATH — use the venv python
cd C:\LLM-RAG-APP\ai-trading-app
git checkout main; git pull origin main
git describe --tags --abbrev=0           # expect: p5-session4-complete

# All eight CI invariants pass (no new invariant this session)
bash apps/backend/scripts/check_strategy_isolation.sh
bash apps/backend/scripts/check_mcp_readonly.sh
bash apps/backend/scripts/check_no_llm_in_order_path.sh
bash apps/backend/scripts/check_broker_isolation.sh
bash apps/backend/scripts/check_no_env_credentials.sh
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_risk_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p2_coverage.py
.\apps\backend\.venv\Scripts\python.exe apps\backend\scripts\check_p3_coverage.py

# ADR 0002 invariant test (not a shell script — see Session Zero Results)
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
cd ..\..

# Baseline backend suite green
cd apps\backend
.\.venv\Scripts\python.exe -m pytest -q --cov=app --cov-branch --cov-report=xml
cd ..\..
```

Live runtime gates (paper smoke + new trip/reset flow) are **deferred** per the standing Norton SSL + no-Docker posture. The in-suite tests in §5.9 stand in for the load-bearing assertions; the live diff runs in WSL/CI before the tag is promoted to a release.

```powershell
# Confirm existing risk_limits scope (Windows / venv equivalent)
.\apps\backend\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'apps\backend\data\workbench.sqlite'); print(list(c.execute('SELECT id, user_id, broker_mode, max_position_qty, max_daily_loss FROM risk_limits')))"

# Confirm StrategyStatus enum values
.\apps\backend\.venv\Scripts\python.exe -c "from app.db.enums import StrategyStatus; print([s.value for s in StrategyStatus])"
# May or may not include 'halted' — we'll add it if missing (§5.1.3)
```

```bash
git checkout -b feat/p5-session5-risk-gates
```

- [ ] On `main`, at `p5-session4-complete`.
- [ ] All eight invariants pass; ADR 0002 invariant test green.
- [ ] Baseline backend suite green.

---

## §5.0 — One small piece of new code: shared `ensure_aware()` helper

Session 5 introduces three new modules that compare SQLite-returned datetimes against `datetime.now(timezone.utc)`. The SQLite gotcha (already handled by `_aware()` in Session 3's `app/auth/stub.py` and `_ensure_aware()` in Session 4's `app/security/credential_store.py`): SQLite returns timezone-aware columns as naive, breaking comparisons.

Rather than copy the helper a third time, extract it.

Create `apps/backend/app/utils/time.py`:

```python
"""Shared time/datetime helpers.

ensure_aware: coerce a possibly-naive datetime to aware-UTC. SQLite returns
DateTime(timezone=True) columns without tzinfo; comparisons against
datetime.now(timezone.utc) raise TypeError ("can't compare naive and
aware") if not coerced. This helper is the single canonical fix.
"""
from __future__ import annotations

from datetime import datetime, timezone


def ensure_aware(dt: datetime | None) -> datetime | None:
    """Coerce a possibly-naive datetime to aware-UTC. None passes through."""
    if dt is None:
        return None
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt
```

Then refactor the two existing copies to import this helper (small, mechanical, three-line changes each):

- `apps/backend/app/auth/stub.py`: replace `_aware()` body with `from app.utils.time import ensure_aware` and `_aware = ensure_aware`. Or rename callers to use `ensure_aware` directly — both fine.
- `apps/backend/app/security/credential_store.py`: same — replace `_ensure_aware()` with the imported `ensure_aware`.

New code in §5.2 (`CircuitBreakerService`), §5.3 (`PdtAnalyzer`), §5.5 (`RiskEngine`) imports from `app.utils.time` and uses `ensure_aware()` directly.

- [ ] `app/utils/time.py` created with `ensure_aware`.
- [ ] `stub.py` and `credential_store.py` refactored to import the shared helper.
- [ ] New §5.2 / §5.3 / §5.5 code imports `ensure_aware` from the shared location.

---

## §5.1 — Schema Changes

Three changes: new column on `accounts`, new column on `risk_limits`, new enum value.

### 5.1.1 — `accounts.circuit_breaker_tripped_at`

Edit `apps/backend/app/db/models/account.py`. Add:

```python
# Circuit breaker state. NULL means "not currently tripped." When tripped,
# the timestamp records when. Full history is in audit_log
# (CIRCUIT_BREAKER_TRIPPED / CIRCUIT_BREAKER_RESET actions).
circuit_breaker_tripped_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True,
)
```

### 5.1.2 — `risk_limits.max_orders_per_day`

Edit `apps/backend/app/db/models/risk_limits.py`. Add:

```python
# Daily order cap. NULL means unlimited.
max_orders_per_day: Mapped[int | None] = mapped_column(
    Integer, nullable=True,
)
```

### 5.1.3 — `StrategyStatus.HALTED`

Edit `apps/backend/app/db/enums.py`. If `HALTED` doesn't exist, add to `StrategyStatus`:

```python
class StrategyStatus(str, Enum):
    IDLE = "idle"
    PAPER = "paper"
    LIVE = "live"
    ERROR = "error"
    HALTED = "halted"     # NEW: paused by system policy (e.g. circuit breaker)
```

If HALTED is already present (some implementations may have it from P2), no schema change — just verify the existing values.

`ACTIVE_STRATEGY_STATUSES` should NOT include HALTED. Verify in the enum module:

```python
ACTIVE_STRATEGY_STATUSES = frozenset([
    StrategyStatus.PAPER, StrategyStatus.LIVE,
])    # HALTED, ERROR, IDLE are inactive
```

### 5.1.4 — Migration

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "P5: circuit_breaker + max_orders_per_day + HALTED"
```

Open the migration. Verify:

- [ ] `op.add_column("accounts", sa.Column("circuit_breaker_tripped_at", sa.DateTime(timezone=True), nullable=True))`
- [ ] `op.add_column("risk_limits", sa.Column("max_orders_per_day", sa.Integer(), nullable=True))`
- [ ] No alter on `strategies.status` — we use a string column with non-native enum (per P1), so adding the HALTED string requires no DDL.
- [ ] `downgrade()` drops both new columns.

**Append a data migration step** to seed the LIVE-scoped default risk limits for user_id=1:

```python
def upgrade():
    # ... autogenerated column adds ...
    op.add_column("accounts", sa.Column("circuit_breaker_tripped_at",
                                        sa.DateTime(timezone=True), nullable=True))
    op.add_column("risk_limits", sa.Column("max_orders_per_day",
                                           sa.Integer(), nullable=True))

    # Data migration: tighten LIVE defaults if no LIVE-scoped row exists.
    conn = op.get_bind()
    from datetime import datetime, timezone
    now = datetime.now(timezone.utc).isoformat()

    users = conn.execute(sa.text("SELECT id FROM users")).fetchall()
    for u in users:
        existing = conn.execute(sa.text(
            "SELECT id FROM risk_limits WHERE user_id=:uid AND broker_mode='live'"
        ), {"uid": u.id}).fetchone()
        if existing is None:
            conn.execute(sa.text("""
                INSERT INTO risk_limits (
                    user_id, broker_mode, scope_type, scope_id,
                    max_position_qty, max_position_notional, max_gross_exposure,
                    max_daily_loss, max_orders_per_minute, max_orders_per_day,
                    allow_short, created_at, updated_at
                ) VALUES (
                    :uid, 'live', 'global', NULL,
                    10, 5000.0, 25000.0,
                    500.0, 3, 20,
                    0, :ts, :ts
                )
            """), {"uid": u.id, "ts": now})

    # Also: top up existing PAPER rows with a default max_orders_per_day of 200
    # (was implicitly unlimited). Per P5 ethos: per-day cap is a defense in depth
    # for paper too — runaway algos shouldn't burn through 50,000 paper orders.
    conn.execute(sa.text(
        "UPDATE risk_limits SET max_orders_per_day=200 "
        "WHERE broker_mode='paper' AND max_orders_per_day IS NULL"
    ))
```

> The PAPER default of 200/day is a meaningful change to existing behavior — previously paper had no per-day cap. Justification: 200/day is generous enough that no normal strategy hits it; if one does, that's a useful signal that something is wrong. If a real workflow legitimately needs more, the user edits the risk limits.

Apply and verify:

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m alembic upgrade head

# Confirm new columns (PowerShell-friendly inline Python)
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(accounts)').fetchall()])"
# Expect: list including 'circuit_breaker_tripped_at'

.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(risk_limits)').fetchall()])"
# Expect: list including 'max_orders_per_day'

# Confirm LIVE default row created
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print(list(c.execute(\"SELECT user_id, broker_mode, max_position_qty, max_daily_loss, max_orders_per_day FROM risk_limits WHERE broker_mode='live'\")))"
# Expect: one row per user, broker_mode='live', tight defaults

# Confirm PAPER rows have max_orders_per_day=200
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print(list(c.execute(\"SELECT user_id, broker_mode, max_orders_per_day FROM risk_limits WHERE broker_mode='paper'\")))"

# Round-trip
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..\..
```

- [ ] Two columns added.
- [ ] LIVE-scoped risk_limits row created for each user.
- [ ] PAPER rows backfilled with max_orders_per_day=200.

---

## §5.2 — `CircuitBreakerService`

Create `apps/backend/app/risk/circuit_breaker.py`:

```python
"""Circuit breaker: account-scoped hard halt on daily loss limit.

State model:
  - accounts.circuit_breaker_tripped_at is the source of truth for
    "is this account currently tripped?"
  - audit_log carries the history (CIRCUIT_BREAKER_TRIPPED with the PnL
    snapshot, CIRCUIT_BREAKER_RESET with the actor).

Trip preconditions (any one is sufficient):
  - realized_pnl_today + unrealized_pnl_now <= -max_daily_loss

Trip actions (all happen atomically before the rejecting order returns):
  1. Set accounts.circuit_breaker_tripped_at = now()
  2. Transition every PAPER/LIVE strategy attached to this account to HALTED
  3. Write CIRCUIT_BREAKER_TRIPPED audit row
  4. Publish system.circuit_breaker bus event

Reset actions (atomic, audit-logged):
  1. Clear accounts.circuit_breaker_tripped_at
  2. Write CIRCUIT_BREAKER_RESET audit row with reset_by_user_id
  3. Publish system.circuit_breaker bus event
  4. Do NOT auto-restart HALTED strategies — user does each manually
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time as dtime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    ACTIVE_STRATEGY_STATUSES, AuditAction, AuditActorType,
    StrategyStatus,
)
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy
from app.services.audit_log import AuditLogger
from app.utils.time import ensure_aware


logger = structlog.get_logger(__name__)


# US/Eastern: market open / close times. We compute "today's PnL" as the
# UTC-converted window from this morning's open to now.
# Fixed -5h offset (EST); the 1-hour DST drift is acceptable for MVP.


@dataclass
class CircuitBreakerStatus:
    account_id: int
    tripped: bool
    tripped_at: Optional[datetime]
    realized_pnl_today: Decimal
    unrealized_pnl_now: Decimal
    max_daily_loss: Decimal
    headroom: Decimal


class CircuitBreakerError(RuntimeError):
    """Raised by the OrderRouter when the breaker is tripped and an
    order is attempted."""


class CircuitBreakerService:
    def __init__(
        self,
        *,
        session: AsyncSession,
        bus: Any = None,
        broker_registry: Any = None,
    ) -> None:
        self._session = session
        self._bus = bus
        self._broker_registry = broker_registry

    async def status(self, account_id: int) -> CircuitBreakerStatus:
        """Compute the current status. Used by the risk-state endpoint
        and the OrderRouter check."""
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")
        limits = await self._get_active_limits(account)
        realized = await self._compute_realized_pnl_today(account_id)
        unrealized = await self._compute_unrealized_pnl(account)
        max_loss = Decimal(str(limits.max_daily_loss)) if limits else Decimal("0")
        net = realized + unrealized
        headroom = max_loss - abs(net) if net < 0 else max_loss
        # SQLite returns DateTime(timezone=True) as naive; coerce
        tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
        return CircuitBreakerStatus(
            account_id=account_id,
            tripped=tripped_at is not None,
            tripped_at=tripped_at,
            realized_pnl_today=realized,
            unrealized_pnl_now=unrealized,
            max_daily_loss=max_loss,
            headroom=headroom,
        )

    async def check(self, account_id: int) -> None:
        """Pre-trade check: raise CircuitBreakerError if tripped OR if
        about to trip. Called by RiskEngine on every order."""
        account = await self._session.get(Account, account_id)
        if account is None:
            raise CircuitBreakerError(f"Account {account_id} not found")
        tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
        if tripped_at is not None:
            raise CircuitBreakerError(
                f"Circuit breaker tripped at {tripped_at.isoformat()}. "
                f"Reset via Settings → Risk to resume trading."
            )

        limits = await self._get_active_limits(account)
        if limits is None or limits.max_daily_loss is None:
            return    # No daily-loss limit configured

        max_loss = Decimal(str(limits.max_daily_loss))
        realized = await self._compute_realized_pnl_today(account_id)
        unrealized = await self._compute_unrealized_pnl(account)
        net_pnl = realized + unrealized
        if net_pnl <= -max_loss:
            await self.trip(
                account_id=account_id,
                reason="daily_loss_exceeded",
                payload={
                    "realized_pnl_today": str(realized),
                    "unrealized_pnl_now": str(unrealized),
                    "net_pnl": str(net_pnl),
                    "max_daily_loss": str(max_loss),
                },
            )
            raise CircuitBreakerError(
                f"Daily loss limit reached (net PnL {net_pnl} ≤ -{max_loss}). "
                f"All strategies on this account are now HALTED."
            )

    async def trip(self, *, account_id: int, reason: str, payload: dict[str, Any]) -> None:
        """Atomically: set the trip timestamp, HALT all active strategies
        on this account, audit-log, publish."""
        now = datetime.now(timezone.utc)
        account = await self._session.get(Account, account_id)
        if account is None or account.circuit_breaker_tripped_at is not None:
            return    # Already tripped or missing; idempotent
        account.circuit_breaker_tripped_at = now

        strategies = (await self._session.execute(
            select(Strategy).where(
                Strategy.account_id == account_id,
                Strategy.status.in_([s.value for s in ACTIVE_STRATEGY_STATUSES]),
            )
        )).scalars().all()
        halted_ids = []
        for s in strategies:
            s.status = StrategyStatus.HALTED
            halted_ids.append(s.id)

        await AuditLogger.write(
            self._session,
            actor_type=AuditActorType.SYSTEM,
            actor_id="circuit_breaker",
            action=AuditAction.CIRCUIT_BREAKER_TRIPPED,
            target_type="account",
            target_id=account_id,
            payload={
                "reason": reason,
                "halted_strategy_ids": halted_ids,
                **payload,
            },
            user_id=account.user_id,
        )
        await self._session.commit()

        if self._bus is not None:
            try:
                await self._bus.publish("system.circuit_breaker", {
                    "account_id": account_id,
                    "state": "tripped",
                    "reason": reason,
                    "halted_strategy_ids": halted_ids,
                    "at": now.isoformat(),
                })
            except Exception:
                logger.exception("circuit_breaker_publish_failed")

        logger.warning("circuit_breaker_tripped",
                       account_id=account_id, reason=reason,
                       halted_strategies=halted_ids)

    async def reset(
        self, *, account_id: int, user_id: int, confirmation_text: str,
    ) -> None:
        """Manual reset by the account owner. confirmation_text must
        equal the account's label — server-side defense in depth."""
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")
        if account.user_id != user_id:
            raise PermissionError(f"Account {account_id} does not belong to user {user_id}")
        if confirmation_text != account.label:
            raise ValueError(
                f"Confirmation text does not match account label. "
                f"Type '{account.label}' to confirm reset."
            )
        if account.circuit_breaker_tripped_at is None:
            return    # Idempotent

        prior_trip_at = account.circuit_breaker_tripped_at
        account.circuit_breaker_tripped_at = None

        await AuditLogger.write(
            self._session,
            actor_type=AuditActorType.USER,
            actor_id=str(user_id),
            action=AuditAction.CIRCUIT_BREAKER_RESET,
            target_type="account",
            target_id=account_id,
            payload={
                "reset_by_user_id": user_id,
                "prior_trip_at": prior_trip_at.isoformat(),
            },
            user_id=user_id,
        )
        await self._session.commit()

        if self._bus is not None:
            try:
                await self._bus.publish("system.circuit_breaker", {
                    "account_id": account_id,
                    "state": "reset",
                    "reset_by_user_id": user_id,
                    "at": datetime.now(timezone.utc).isoformat(),
                })
            except Exception:
                logger.exception("circuit_breaker_publish_failed")

        logger.info("circuit_breaker_reset",
                    account_id=account_id, user_id=user_id)

    async def _get_active_limits(self, account: Account) -> Optional[RiskLimits]:
        from app.db.enums import RiskScopeType
        result = await self._session.execute(
            select(RiskLimits).where(
                RiskLimits.user_id == account.user_id,
                RiskLimits.broker_mode == account.mode,
                RiskLimits.scope_type == RiskScopeType.GLOBAL,
            )
        )
        return result.scalars().first()

    async def _compute_realized_pnl_today(self, account_id: int) -> Decimal:
        """Sum signed cash flow from today's fills.

        signed_direction on Fill is +1 for buys, -1 for sells. The signed
        cash flow is qty * price * signed_direction; positive means cash
        out (buy), negative means cash in (sell). Realized PnL is
        approximately -sum(signed_cash) for the day if positions opened
        today are also closed today; for open positions it over-counts loss,
        which the unrealized calc corrects."""
        market_open_utc = self._market_open_utc_today()

        from sqlalchemy import func
        result = await self._session.execute(
            select(func.coalesce(func.sum(
                Fill.qty * Fill.price * Fill.signed_direction
            ), 0))
            .join(Order, Fill.order_id == Order.id)
            .where(Order.account_id == account_id)
            .where(Fill.filled_at >= market_open_utc)
        )
        net_cash = result.scalar() or Decimal("0")
        return Decimal(str(-net_cash))

    async def _compute_unrealized_pnl(self, account: Account) -> Decimal:
        if self._broker_registry is None:
            return Decimal("0")
        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            return Decimal("0")
        try:
            positions = await adapter.get_positions()
        except Exception:
            logger.exception("circuit_breaker_unrealized_fetch_failed",
                             account_id=account.id)
            return Decimal("0")
        return sum((p.unrealized_pl for p in positions), Decimal("0"))

    def _market_open_utc_today(self) -> datetime:
        """09:30 US/Eastern today → UTC. Fixed -5h offset (EST). The
        1-hour DST drift is acceptable for MVP; P5+ uses zoneinfo."""
        now = datetime.now(timezone.utc)
        market_open = now.replace(hour=14, minute=30, second=0, microsecond=0)
        if now < market_open:
            market_open = market_open - timedelta(days=1)
        return market_open
```

> The realized-PnL computation is intentionally conservative — it sums signed cash flow today, which over-counts loss when positions opened today are still open (they look like cash out, but they're also unrealized assets). The companion `_compute_unrealized_pnl` adds positions' unrealized P&L back via the broker, which corrects for this. The net `(realized + unrealized)` is the right quantity to compare against `max_daily_loss`.

- [ ] `CircuitBreakerService` with status / check / trip / reset.
- [ ] Trip is atomic: timestamp + HALT all active strategies + audit + publish.
- [ ] Reset requires typed account label as confirmation.

---

## §5.3 — `PdtAnalyzer`

Create `apps/backend/app/risk/pdt_analyzer.py`:

```python
"""Pattern Day Trader detection.

FINRA defines a Pattern Day Trader as one who executes 4+ day trades in a
rolling 5-business-day period in a margin account with equity < $25,000.
A "day trade" is opening and closing the same position (same symbol)
within the same trading session.

The workbench surfaces a warning when:
  - Account equity < $25,000, AND
  - 3+ day trades in the rolling 5-business-day window

We DO NOT block trading. The user owns the FINRA decision.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import OrderSide
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.utils.time import ensure_aware


logger = structlog.get_logger(__name__)


PDT_EQUITY_THRESHOLD = Decimal("25000.00")
PDT_DAY_TRADE_THRESHOLD = 3       # we warn at 3 — FINRA's trigger is 4
PDT_WINDOW_BUSINESS_DAYS = 5


@dataclass
class PdtStatus:
    account_id: int
    is_at_risk: bool
    day_trade_count: int
    threshold: int
    window_days: int
    account_equity: Optional[Decimal]
    equity_threshold: Decimal
    detected_day_trades: list[dict[str, Any]]


class PdtAnalyzer:
    def __init__(
        self, *, session: AsyncSession, broker_registry: Any = None,
    ) -> None:
        self._session = session
        self._broker_registry = broker_registry

    async def compute(self, account_id: int) -> PdtStatus:
        account = await self._session.get(Account, account_id)
        if account is None:
            raise ValueError(f"Account {account_id} not found")

        cutoff = self._business_days_ago(PDT_WINDOW_BUSINESS_DAYS)
        fills = (await self._session.execute(
            select(Fill, Order)
            .join(Order, Fill.order_id == Order.id)
            .where(Order.account_id == account_id)
            .where(Fill.filled_at >= cutoff)
            .order_by(Fill.filled_at)
        )).all()

        day_trades = self._identify_day_trades(fills)
        equity = await self._fetch_equity(account)

        is_at_risk = (
            len(day_trades) >= PDT_DAY_TRADE_THRESHOLD
            and (equity is None or equity < PDT_EQUITY_THRESHOLD)
        )

        return PdtStatus(
            account_id=account_id,
            is_at_risk=is_at_risk,
            day_trade_count=len(day_trades),
            threshold=PDT_DAY_TRADE_THRESHOLD,
            window_days=PDT_WINDOW_BUSINESS_DAYS,
            account_equity=equity,
            equity_threshold=PDT_EQUITY_THRESHOLD,
            detected_day_trades=day_trades,
        )

    def _identify_day_trades(self, fill_rows) -> list[dict[str, Any]]:
        """Walk fills in time order; track per-symbol per-day position state.
        Emit a day_trade when position goes 0 → non-zero → 0 within one day."""
        per_day_per_symbol: dict[tuple[date, str], list[tuple[datetime, OrderSide, Decimal]]] = \
            defaultdict(list)
        for fill, order in fill_rows:
            eastern_date = self._utc_to_eastern_date(fill.filled_at)
            per_day_per_symbol[(eastern_date, order.symbol)].append(
                (fill.filled_at, order.side, fill.qty)
            )

        day_trades = []
        for (eastern_date, symbol), events in per_day_per_symbol.items():
            position = Decimal("0")
            opened_at = None
            for ts, side, qty in events:
                signed = qty if side == OrderSide.BUY else -qty
                prev = position
                position += signed
                if prev == 0 and position != 0:
                    opened_at = ts
                elif prev != 0 and position == 0 and opened_at is not None:
                    day_trades.append({
                        "date": eastern_date.isoformat(),
                        "symbol": symbol,
                        "opened_at": opened_at.isoformat(),
                        "closed_at": ts.isoformat(),
                    })
                    opened_at = None
        return day_trades

    async def _fetch_equity(self, account: Account) -> Optional[Decimal]:
        if self._broker_registry is None:
            return None
        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            return None
        try:
            # Sync adapter call (Session 2 v1.0: BrokerAdapter is sync, dict return)
            snapshot = adapter.get_account()
            eq = snapshot.get("equity") if isinstance(snapshot, dict) else None
            return Decimal(str(eq)) if eq is not None else None
        except Exception:
            logger.exception("pdt_equity_fetch_failed", account_id=account.id)
            return None

    def _business_days_ago(self, n: int) -> datetime:
        d = datetime.now(timezone.utc)
        days_back = 0
        while days_back < n:
            d = d - timedelta(days=1)
            if d.weekday() < 5:
                days_back += 1
        return d

    def _utc_to_eastern_date(self, ts: datetime) -> date:
        # SQLite returns DateTime(timezone=True) as naive; coerce
        ts = ensure_aware(ts)
        eastern = ts - timedelta(hours=5)
        return eastern.date()
```

- [ ] PdtAnalyzer with `compute(account_id)`.
- [ ] Day-trade detection via position-walk across same-day fills.
- [ ] Equity fetched from broker.

---

## §5.4 — `BuyingPowerChecker`

Create `apps/backend/app/risk/buying_power.py`:

```python
"""Pre-trade buying-power check.

For LIVE: calls BrokerAdapter.get_account() to read live buying power.
For PAPER: skipped (Alpaca paper enforces buying power on the broker side;
adding a round-trip on every paper order would slow paper smoke without
benefit).
"""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Optional

import structlog

# Note: BrokerAdapter.get_account() returns dict[str, Any] (Session 2 v1.0
# rejected typed DTOs). We read fields by key + Decimal coercion.
from app.db.enums import AccountMode, OrderSide, OrderType
from app.db.models.account import Account


logger = structlog.get_logger(__name__)


# How much more than the limit/stop price we estimate market orders might
# actually fill at. 1% is generous for liquid US equities.
MARKET_SLIPPAGE_BUFFER = Decimal("0.01")


@dataclass
class BuyingPowerDecision:
    sufficient: bool
    required_notional: Decimal
    available_buying_power: Decimal
    rejection_reason: Optional[str] = None


class BuyingPowerChecker:
    def __init__(self, *, broker_registry: Any, bar_cache: Any = None) -> None:
        self._broker_registry = broker_registry
        self._bar_cache = bar_cache

    async def check(self, account: Account, request: Any) -> BuyingPowerDecision:
        # Sells exempt
        if request.side == OrderSide.SELL:
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=Decimal("0"),
                available_buying_power=Decimal("0"),
            )

        required = await self._estimate_worst_case_notional(request)
        adapter = self._broker_registry.get(account.id)
        if adapter is None:
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=required,
                available_buying_power=Decimal("0"),
                rejection_reason="No broker adapter — deferred to broker",
            )
        try:
            # Sync call (Session 2 v1.0): adapter.get_account() returns
            # dict[str, Any]. Fail-open on any exception (matches v0.1's
            # implicit choice; see Notes & Gotchas #14 for the alternatives
            # considered and why we kept fail-open for §5).
            snap = adapter.get_account()
        except Exception as exc:
            logger.warning("buying_power_check_failed_open",
                           account_id=account.id, error=str(exc))
            return BuyingPowerDecision(
                sufficient=True,
                required_notional=required,
                available_buying_power=Decimal("0"),
                rejection_reason=f"Broker unreachable for buying-power check: {exc}",
            )

        # dict access; Alpaca returns string fields, coerce to Decimal
        available = Decimal(str(snap.get("buying_power", "0")))
        if available < required:
            return BuyingPowerDecision(
                sufficient=False,
                required_notional=required,
                available_buying_power=available,
                rejection_reason=(
                    f"INSUFFICIENT_BUYING_POWER: need ${required} "
                    f"(worst-case estimate), have ${available}."
                ),
            )
        return BuyingPowerDecision(
            sufficient=True,
            required_notional=required,
            available_buying_power=available,
        )

    async def _estimate_worst_case_notional(self, request: Any) -> Decimal:
        qty = Decimal(str(request.qty))
        if request.type == OrderType.LIMIT:
            return Decimal(str(request.limit_price)) * qty
        if request.type == OrderType.STOP_LIMIT:
            return Decimal(str(request.limit_price)) * qty
        if request.type == OrderType.STOP:
            buffer = (Decimal("1") + MARKET_SLIPPAGE_BUFFER)
            return Decimal(str(request.stop_price)) * qty * buffer
        # MARKET: use latest bar close
        last_price = await self._fetch_latest_price(request.symbol)
        if last_price is None:
            return Decimal("0")    # fail open
        buffer = (Decimal("1") + MARKET_SLIPPAGE_BUFFER)
        return last_price * qty * buffer

    async def _fetch_latest_price(self, symbol: str) -> Optional[Decimal]:
        if self._bar_cache is None:
            return None
        try:
            bar = await self._bar_cache.get_latest_bar(symbol)
            if bar is None:
                return None
            return Decimal(str(bar.get("c") if isinstance(bar, dict) else bar.close))
        except Exception:
            return None
```

> The "fail open" pattern (return `sufficient=True` when broker is unreachable) is debated. Argument for: the broker will reject if it really doesn't have buying power; our check is redundant. Argument against: the broker reject leaves us in a confused local state (we submitted, got a 422, now what?). For MVP we fail open and rely on the broker as the ultimate authority — but log loudly when this happens.

- [ ] `BuyingPowerChecker.check(account, request)`.
- [ ] Sells exempt.
- [ ] Worst-case notional per order type.
- [ ] Fail-open with logging when broker unreachable.

---

## §5.5 — RiskEngine Integration

Edit `apps/backend/app/risk/engine.py`. Add the new gates to the existing check pipeline:

```python
from app.risk.circuit_breaker import CircuitBreakerError, CircuitBreakerService
from app.risk.buying_power import BuyingPowerChecker
from app.db.enums import AccountMode


class RiskEngine:
    def __init__(
        self, *, session_factory, broker_registry, bar_cache=None, **kwargs,
    ) -> None:
        # ... existing init ...
        self._broker_registry = broker_registry
        self._bar_cache = bar_cache

    async def check(self, request, *, account, current_user_id):
        # NEW in P5 §5: order matters. Cheap checks first.
        async with self._session_factory() as session:
            cb = CircuitBreakerService(
                session=session,
                broker_registry=self._broker_registry,
                bus=getattr(self, "_bus", None),
            )
            try:
                # This raises CircuitBreakerError for both "already tripped"
                # and "just tripped this order"
                await cb.check(account.id)
            except CircuitBreakerError as exc:
                return self._reject(request, account, reason_code="CIRCUIT_BREAKER",
                                    detail=str(exc))

            # Per-day order cap
            limits = await self._resolve_limits(session, account)
            if limits and limits.max_orders_per_day is not None:
                from app.db.models.order import Order
                from sqlalchemy import func, select
                # SQL-side comparison: SQLite stores ISO strings; an
                # aware cutoff formats to ISO with offset and compares
                # correctly against naive-stored values. No Python-side
                # comparison happens here, so ensure_aware not needed.
                cutoff = self._market_open_utc_today()
                count = (await session.execute(
                    select(func.count(Order.id))
                    .where(Order.account_id == account.id)
                    .where(Order.created_at >= cutoff)
                )).scalar() or 0
                if count >= limits.max_orders_per_day:
                    return self._reject(
                        request, account, reason_code="MAX_ORDERS_PER_DAY",
                        detail=f"Daily order cap reached ({count}/{limits.max_orders_per_day})",
                    )

        # Pre-trade buying power — LIVE only.
        if account.mode == AccountMode.live:
            bp_checker = BuyingPowerChecker(
                broker_registry=self._broker_registry,
                bar_cache=self._bar_cache,
            )
            bp_decision = await bp_checker.check(account, request)
            if not bp_decision.sufficient:
                return self._reject(
                    request, account,
                    reason_code="INSUFFICIENT_BUYING_POWER",
                    detail=bp_decision.rejection_reason,
                )

        # Existing checks (P1 Session 5): position_qty, notional, gross, per-minute rate
        return await self._existing_checks(request, account, current_user_id, limits)
```

> The order matters. Circuit breaker first (cheap DB read + maybe-trip), then per-day cap (one COUNT query), then per-trade buying power (broker round-trip — slowest). Skip whatever you can.

- [ ] CircuitBreakerService called first.
- [ ] Per-day order cap.
- [ ] Pre-trade buying power LIVE-only.

---

## §5.6 — Endpoints

Create `apps/backend/app/api/v1/risk.py`:

```python
"""/api/v1/risk-limits and /api/v1/accounts/{id}/risk/* endpoints."""
from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.enums import (
    AuditAction, AuditActorType, AccountMode, RiskScopeType,
)
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.session import get_session
from app.risk.circuit_breaker import CircuitBreakerService
from app.risk.pdt_analyzer import PdtAnalyzer
from app.services.audit_log import AuditLogger


router = APIRouter(tags=["risk"])


# ---------------- schemas ----------------


class RiskLimitsResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    user_id: int
    broker_mode: AccountMode
    scope_type: str
    scope_id: Optional[int]
    max_position_qty: Optional[int]
    max_position_notional: Optional[Decimal]
    max_gross_exposure: Optional[Decimal]
    max_daily_loss: Optional[Decimal]
    max_orders_per_minute: Optional[int]
    max_orders_per_day: Optional[int]
    allow_short: bool


class RiskLimitsListResponse(BaseModel):
    items: list[RiskLimitsResponse]
    count: int


class UpdateRiskLimitsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_position_qty: Optional[int] = Field(default=None, ge=0)
    max_position_notional: Optional[Decimal] = Field(default=None, ge=0)
    max_gross_exposure: Optional[Decimal] = Field(default=None, ge=0)
    max_daily_loss: Optional[Decimal] = Field(default=None, ge=0)
    max_orders_per_minute: Optional[int] = Field(default=None, ge=0)
    max_orders_per_day: Optional[int] = Field(default=None, ge=0)
    allow_short: Optional[bool] = None


class CircuitBreakerStatusResponse(BaseModel):
    account_id: int
    tripped: bool
    tripped_at: Optional[datetime]
    realized_pnl_today: Decimal
    unrealized_pnl_now: Decimal
    max_daily_loss: Decimal
    headroom: Decimal


class PdtStatusResponse(BaseModel):
    account_id: int
    is_at_risk: bool
    day_trade_count: int
    threshold: int
    window_days: int
    account_equity: Optional[Decimal]
    equity_threshold: Decimal


class RiskStateResponse(BaseModel):
    circuit_breaker: CircuitBreakerStatusResponse
    pdt: PdtStatusResponse


class ResetCircuitBreakerRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_text: str = Field(min_length=1, max_length=64)


# ---------------- endpoints ----------------


@router.get("/risk-limits", response_model=RiskLimitsListResponse)
async def list_risk_limits(
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    rows = (await session.execute(
        select(RiskLimits)
        .where(RiskLimits.user_id == current_user.id)
        .order_by(RiskLimits.broker_mode, RiskLimits.scope_type)
    )).scalars().all()
    return RiskLimitsListResponse(
        items=[RiskLimitsResponse.model_validate(r, from_attributes=True) for r in rows],
        count=len(rows),
    )


@router.put("/risk-limits/{limits_id}", response_model=RiskLimitsResponse)
async def update_risk_limits(
    limits_id: int,
    body: UpdateRiskLimitsRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    row = await session.get(RiskLimits, limits_id)
    if row is None or row.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Risk limits not found")

    audit_payload = {"old": {}, "new": {}}
    for field, new_val in body.model_dump(exclude_unset=True).items():
        old_val = getattr(row, field)
        if old_val != new_val:
            audit_payload["old"][field] = str(old_val) if old_val is not None else None
            audit_payload["new"][field] = str(new_val) if new_val is not None else None
            setattr(row, field, new_val)
    await session.commit()

    await AuditLogger.write(
        session,
        actor_type=AuditActorType.USER,
        actor_id=str(current_user.id),
        action=AuditAction.RISK_LIMITS_UPDATED,
        target_type="risk_limits",
        target_id=limits_id,
        payload={"changes": audit_payload, "broker_mode": row.broker_mode.value},
        user_id=current_user.id,
    )
    await session.commit()
    return RiskLimitsResponse.model_validate(row, from_attributes=True)


@router.get("/accounts/{account_id}/risk-state", response_model=RiskStateResponse)
async def account_risk_state(
    account_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    account = await session.get(Account, account_id)
    if account is None or account.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Account not found")

    broker_registry = getattr(request.app.state, "broker_registry", None)
    cb = CircuitBreakerService(session=session, broker_registry=broker_registry)
    pdt = PdtAnalyzer(session=session, broker_registry=broker_registry)
    cb_status = await cb.status(account_id)
    pdt_status = await pdt.compute(account_id)

    return RiskStateResponse(
        circuit_breaker=CircuitBreakerStatusResponse(
            account_id=cb_status.account_id,
            tripped=cb_status.tripped,
            tripped_at=cb_status.tripped_at,
            realized_pnl_today=cb_status.realized_pnl_today,
            unrealized_pnl_now=cb_status.unrealized_pnl_now,
            max_daily_loss=cb_status.max_daily_loss,
            headroom=cb_status.headroom,
        ),
        pdt=PdtStatusResponse(
            account_id=pdt_status.account_id,
            is_at_risk=pdt_status.is_at_risk,
            day_trade_count=pdt_status.day_trade_count,
            threshold=pdt_status.threshold,
            window_days=pdt_status.window_days,
            account_equity=pdt_status.account_equity,
            equity_threshold=pdt_status.equity_threshold,
        ),
    )


@router.post("/accounts/{account_id}/risk/reset-circuit-breaker")
async def reset_circuit_breaker(
    account_id: int,
    body: ResetCircuitBreakerRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    broker_registry = getattr(request.app.state, "broker_registry", None)
    bus = getattr(request.app.state, "event_bus", None)
    cb = CircuitBreakerService(session=session, broker_registry=broker_registry, bus=bus)
    try:
        await cb.reset(
            account_id=account_id,
            user_id=current_user.id,
            confirmation_text=body.confirmation_text,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Account not found")
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "account_id": account_id}
```

Wire via the central router registry in `apps/backend/app/api/v1/__init__.py`
(the codebase's actual pattern, as confirmed by Session 4 Results — credentials
router followed this; Session 5's risk router follows the same):

```python
# in app/api/v1/__init__.py — add to the existing include list
from app.api.v1 import risk as risk_router
api_router.include_router(risk_router.router, prefix="/api/v1")
```

The full endpoint paths are `/api/v1/risk-limits`, `/api/v1/risk-limits/{id}`,
`/api/v1/accounts/{id}/risk-state`, and
`/api/v1/accounts/{id}/risk/reset-circuit-breaker`.

- [ ] List + update risk limits.
- [ ] Account risk-state (circuit breaker + PDT).
- [ ] Reset endpoint with typed confirmation.

---

## §5.7 — Audit Actions + WS Routing

Edit `apps/backend/app/db/enums.py`. Add to `AuditAction`:

```python
class AuditAction(str, Enum):
    # ... existing ...
    CIRCUIT_BREAKER_TRIPPED = "circuit_breaker_tripped"
    CIRCUIT_BREAKER_RESET = "circuit_breaker_reset"
    RISK_LIMITS_UPDATED = "risk_limits_updated"
```

WS gateway routes the breaker event. Per Session Zero Results, the actual
WS topic map is `_BUS_TOPICS` + `_bus_to_ws_topic()` in
`apps/backend/app/ws/gateway.py` (not `bus_to_ws_map`). Add the new bus topic
to that map so `system.circuit_breaker` events route to the `system` WS topic:

```python
# in app/ws/gateway.py — add to _BUS_TOPICS
_BUS_TOPICS = {
    # ... existing entries ...
    "system.circuit_breaker": "system",
}
```

The `_bus_to_ws_topic()` helper uses this map; no other change needed.

- [ ] Three audit actions added.
- [ ] `system.circuit_breaker` routed to `system` topic.

---

## §5.8 — Frontend: Risk State Display

Create `apps/frontend/src/components/risk/RiskStateBanner.tsx`:

```tsx
import { useEffect, useState } from "react";
import { riskApi } from "@/api/risk";
import type { RiskState } from "@/api/risk";


interface Props {
  accountId: number;
}


export function RiskStateBanner({ accountId }: Props) {
  const [state, setState] = useState<RiskState | null>(null);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const s = await riskApi.accountRiskState(accountId);
        if (!cancelled) setState(s);
      } catch { /* silent — banner is best-effort */ }
    }
    refresh();
    const id = setInterval(refresh, 60_000);
    return () => { cancelled = true; clearInterval(id); };
  }, [accountId]);

  if (!state) return null;

  return (
    <div className="space-y-2">
      {state.circuit_breaker.tripped && (
        <CircuitBreakerTrippedBanner accountId={accountId} state={state} />
      )}
      {state.pdt.is_at_risk && (
        <PdtWarningBanner state={state} />
      )}
    </div>
  );
}


function CircuitBreakerTrippedBanner({ accountId, state }: { accountId: number; state: RiskState }) {
  const [resetOpen, setResetOpen] = useState(false);
  return (
    <>
      <div className="rounded border-2 border-red-700 bg-red-950/40 p-3">
        <div className="flex items-center justify-between">
          <div>
            <div className="text-sm font-bold text-red-100">⚠ CIRCUIT BREAKER TRIPPED</div>
            <div className="mt-1 text-xs text-red-200">
              Daily loss limit reached on {new Date(state.circuit_breaker.tripped_at!).toLocaleString()}.
              All strategies on this account have been HALTED. Order submission is rejected.
            </div>
            <div className="mt-1 text-[10px] text-red-300">
              Net PnL today: ${state.circuit_breaker.realized_pnl_today} realized +
              ${state.circuit_breaker.unrealized_pnl_now} unrealized.
              Daily loss limit: ${state.circuit_breaker.max_daily_loss}.
            </div>
          </div>
          <button
            onClick={() => setResetOpen(true)}
            className="rounded border border-red-700 px-3 py-1.5 text-xs font-semibold text-red-100 hover:bg-red-900/30"
          >
            Reset…
          </button>
        </div>
      </div>
      {resetOpen && (
        <ResetCircuitBreakerModal
          accountId={accountId}
          onClose={() => setResetOpen(false)}
        />
      )}
    </>
  );
}


function PdtWarningBanner({ state }: { state: RiskState }) {
  return (
    <div className="rounded border border-amber-700 bg-amber-950/30 p-3">
      <div className="text-sm font-semibold text-amber-100">
        ⚠ Pattern Day Trader warning
      </div>
      <div className="mt-1 text-xs text-amber-200">
        {state.pdt.day_trade_count} day trades detected in the last {state.pdt.window_days} business days
        (threshold: {state.pdt.threshold}). Account equity ${state.pdt.account_equity ?? "?"}
        {" "}vs FINRA threshold ${state.pdt.equity_threshold}.
      </div>
      <div className="mt-1 text-[10px] text-amber-300">
        FINRA flags accounts at 4+ day trades / 5 business days with equity {"<"} $25,000.
        You own this decision; the workbench will not block trading.
      </div>
    </div>
  );
}


function ResetCircuitBreakerModal({ accountId, onClose }: { accountId: number; onClose: () => void }) {
  const [accountLabel, setAccountLabel] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    riskApi.getAccount(accountId).then((a) => setAccountLabel(a.label)).catch(() => {});
  }, [accountId]);

  async function handleReset() {
    setError(null); setSubmitting(true);
    try {
      await riskApi.resetCircuitBreaker(accountId, confirmation);
      onClose();
      window.location.reload();
    } catch (e: any) {
      setError(e.detail || String(e));
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-96 space-y-3 rounded-lg border-2 border-red-700 bg-gray-950 p-5">
        <h2 className="text-lg font-semibold text-red-100">Reset circuit breaker</h2>
        <p className="text-sm text-gray-300">
          Resetting re-enables order submission for this account. Strategies remain HALTED;
          you must start each one manually.
        </p>
        <p className="text-xs text-amber-200">
          Type the account label{" "}
          <code className="rounded bg-gray-800 px-1 font-mono">{accountLabel}</code>{" "}
          to confirm.
        </p>
        <input
          type="text"
          value={confirmation}
          onChange={(e) => setConfirmation(e.target.value)}
          placeholder="account label"
          className="w-full rounded bg-gray-800 px-2 py-1 font-mono text-sm text-white"
        />
        {error && (
          <div className="rounded border border-red-700 bg-red-950/40 p-2 text-xs text-red-200">
            {error}
          </div>
        )}
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
            Cancel
          </button>
          <button
            onClick={handleReset}
            disabled={submitting || confirmation !== accountLabel}
            className="rounded bg-red-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-red-600 disabled:bg-gray-700"
          >
            {submitting ? "Resetting…" : "Reset"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

Create `apps/frontend/src/api/risk.ts`:

```typescript
import { apiFetch } from "./client";


export interface RiskState {
  circuit_breaker: {
    account_id: number;
    tripped: boolean;
    tripped_at: string | null;
    realized_pnl_today: string;
    unrealized_pnl_now: string;
    max_daily_loss: string;
    headroom: string;
  };
  pdt: {
    account_id: number;
    is_at_risk: boolean;
    day_trade_count: number;
    threshold: number;
    window_days: number;
    account_equity: string | null;
    equity_threshold: string;
  };
}


export interface RiskLimits {
  id: number;
  user_id: number;
  broker_mode: "paper" | "live";
  scope_type: string;
  scope_id: number | null;
  max_position_qty: number | null;
  max_position_notional: string | null;
  max_gross_exposure: string | null;
  max_daily_loss: string | null;
  max_orders_per_minute: number | null;
  max_orders_per_day: number | null;
  allow_short: boolean;
}


export const riskApi = {
  accountRiskState: (accountId: number) =>
    apiFetch<RiskState>(`/api/v1/accounts/${accountId}/risk-state`),
  resetCircuitBreaker: (accountId: number, confirmationText: string) =>
    apiFetch<{ ok: boolean }>(
      `/api/v1/accounts/${accountId}/risk/reset-circuit-breaker`,
      { method: "POST", body: { confirmation_text: confirmationText } },
    ),
  listLimits: () =>
    apiFetch<{ items: RiskLimits[]; count: number }>("/api/v1/risk-limits"),
  updateLimits: (id: number, changes: Partial<RiskLimits>) =>
    apiFetch<RiskLimits>(`/api/v1/risk-limits/${id}`, {
      method: "PUT", body: changes,
    }),
  getAccount: (accountId: number) =>
    apiFetch<{ id: number; label: string }>(`/api/v1/accounts/${accountId}`),
};
```

Mount the banner on the account dashboard page (`pages/Accounts/AccountDetail.tsx` or similar): render `<RiskStateBanner accountId={account.id} />` near the top of the layout.

Also add a Risk Limits settings page at `apps/frontend/src/pages/Settings/RiskLimits.tsx` (mirrors the Credentials page from §4 — one card per (broker_mode) row, edit fields inline, save calls `riskApi.updateLimits`). Route it as `/settings/risk-limits` and add a sidebar link.

- [ ] RiskStateBanner renders breaker + PDT warnings.
- [ ] Reset modal requires typed account label.
- [ ] Risk limits page lets user edit paper + live limits.

---

## §5.9 — Tests

Create `apps/backend/tests/risk/test_p5_circuit_breaker.py`:

```python
"""CircuitBreakerService tests."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.db.enums import (
    AccountMode, RiskScopeType, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.risk.circuit_breaker import (
    CircuitBreakerError, CircuitBreakerService,
)


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper",
            created_at=_now(),
        ))
        session.add(RiskLimits(
            id=1, user_id=1, broker_mode=AccountMode.paper,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        ))
        for sid in (10, 11):
            session.add(StrategyRow(
                id=sid, user_id=1, account_id=1, name=f"s{sid}",
                version="0.1.0", type=StrategyType.PYTHON,
                status=StrategyStatus.PAPER, code_path="x.py",
                params_json={}, symbols_json=[], schedule="event",
                created_at=_now(), updated_at=_now(),
            ))
        await session.commit()


@pytest.fixture
def broker_registry_mock():
    reg = MagicMock()
    adapter = MagicMock()
    adapter.get_positions = AsyncMock(return_value=[])
    reg.get.return_value = adapter
    return reg


@pytest.mark.asyncio
async def test_status_not_tripped_initially(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        status = await cb.status(1)
    assert status.tripped is False
    assert status.tripped_at is None


@pytest.mark.asyncio
async def test_check_passes_when_no_loss(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.check(1)


@pytest.mark.asyncio
async def test_trip_halts_all_active_strategies(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={"x": "y"})

    async with session_factory() as session:
        account = await session.get(Account, 1)
        s10 = await session.get(StrategyRow, 10)
        s11 = await session.get(StrategyRow, 11)
    assert account.circuit_breaker_tripped_at is not None
    assert s10.status == StrategyStatus.HALTED
    assert s11.status == StrategyStatus.HALTED


@pytest.mark.asyncio
async def test_check_when_tripped_raises(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})

    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        with pytest.raises(CircuitBreakerError) as exc:
            await cb.check(1)
        assert "tripped" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_reset_clears_tripped_state(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})

    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.reset(account_id=1, user_id=1, confirmation_text="Paper")

    async with session_factory() as session:
        account = await session.get(Account, 1)
    assert account.circuit_breaker_tripped_at is None


@pytest.mark.asyncio
async def test_reset_rejects_wrong_confirmation(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})

    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        with pytest.raises(ValueError) as exc:
            await cb.reset(account_id=1, user_id=1, confirmation_text="wrong")
        assert "label" in str(exc.value).lower()


@pytest.mark.asyncio
async def test_reset_does_not_restart_halted_strategies(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.reset(account_id=1, user_id=1, confirmation_text="Paper")
    async with session_factory() as session:
        s10 = await session.get(StrategyRow, 10)
        s11 = await session.get(StrategyRow, 11)
    assert s10.status == StrategyStatus.HALTED
    assert s11.status == StrategyStatus.HALTED


@pytest.mark.asyncio
async def test_reset_rejects_wrong_user(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        session.add(User(id=2, email="other@local"))
        await session.commit()

    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})

    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        with pytest.raises(PermissionError):
            await cb.reset(account_id=1, user_id=2, confirmation_text="Paper")


@pytest.mark.asyncio
async def test_trip_is_idempotent(session_factory, seeded, broker_registry_mock):
    async with session_factory() as session:
        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test", payload={})

    async with session_factory() as session:
        account_before = await session.get(Account, 1)
        first_trip_at = account_before.circuit_breaker_tripped_at

        cb = CircuitBreakerService(session=session, broker_registry=broker_registry_mock)
        await cb.trip(account_id=1, reason="test_again", payload={})

        account_after = await session.get(Account, 1)
    assert account_after.circuit_breaker_tripped_at == first_trip_at
```

Create `apps/backend/tests/risk/test_p5_pdt_analyzer.py`:

```python
"""PdtAnalyzer tests."""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.db.enums import AccountMode, OrderSide, OrderStatus, OrderType, TimeInForce
from app.db.models.account import Account
from app.db.models.fill import Fill
from app.db.models.order import Order
from app.db.models.user import User
from app.risk.pdt_analyzer import PdtAnalyzer


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def seeded(session_factory):
    async with session_factory() as session:
        session.add(User(id=1, email="t@local"))
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.paper, label="Paper",
            created_at=_now(),
        ))
        await session.commit()


@pytest.fixture
def broker_registry_factory():
    def _make(equity: Decimal):
        reg = MagicMock()
        adapter = MagicMock()
        # Sync return (Session 2 v1.0); dict shape matches what AlpacaAdapter returns
        adapter.get_account = MagicMock(return_value={
            "cash": str(Decimal("10000")),
            "equity": str(equity),
            "buying_power": str(equity),
        })
        reg.get.return_value = adapter
        return reg
    return _make


async def _add_day_trade(session, account_id, symbol, hours_ago: int):
    """Helper to seed a buy + sell of the same symbol within one day."""
    base_ts = _now() - timedelta(hours=hours_ago)
    buy_order = Order(
        account_id=account_id, symbol=symbol, side=OrderSide.BUY,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED, created_at=base_ts, updated_at=base_ts,
    )
    sell_order = Order(
        account_id=account_id, symbol=symbol, side=OrderSide.SELL,
        type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
        status=OrderStatus.FILLED,
        created_at=base_ts + timedelta(hours=2),
        updated_at=base_ts + timedelta(hours=2),
    )
    session.add_all([buy_order, sell_order])
    await session.flush()
    session.add_all([
        Fill(order_id=buy_order.id, qty=Decimal("10"),
             price=Decimal("100"), filled_at=base_ts,
             signed_direction=1),
        Fill(order_id=sell_order.id, qty=Decimal("10"),
             price=Decimal("101"), filled_at=base_ts + timedelta(hours=2),
             signed_direction=-1),
    ])


@pytest.mark.asyncio
async def test_no_day_trades_not_at_risk(session_factory, seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with session_factory() as session:
        analyzer = PdtAnalyzer(session=session, broker_registry=reg)
        status = await analyzer.compute(1)
    assert status.day_trade_count == 0
    assert status.is_at_risk is False


@pytest.mark.asyncio
async def test_two_day_trades_below_threshold(session_factory, seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with session_factory() as session:
        await _add_day_trade(session, 1, "AAPL", 24)
        await _add_day_trade(session, 1, "MSFT", 48)
        await session.commit()

    async with session_factory() as session:
        analyzer = PdtAnalyzer(session=session, broker_registry=reg)
        status = await analyzer.compute(1)
    assert status.day_trade_count == 2
    assert status.is_at_risk is False    # 2 < 3 threshold


@pytest.mark.asyncio
async def test_three_day_trades_low_equity_at_risk(session_factory, seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with session_factory() as session:
        await _add_day_trade(session, 1, "AAPL", 24)
        await _add_day_trade(session, 1, "MSFT", 48)
        await _add_day_trade(session, 1, "GOOG", 72)
        await session.commit()

    async with session_factory() as session:
        analyzer = PdtAnalyzer(session=session, broker_registry=reg)
        status = await analyzer.compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is True


@pytest.mark.asyncio
async def test_three_day_trades_high_equity_not_at_risk(session_factory, seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("50000"))
    async with session_factory() as session:
        await _add_day_trade(session, 1, "AAPL", 24)
        await _add_day_trade(session, 1, "MSFT", 48)
        await _add_day_trade(session, 1, "GOOG", 72)
        await session.commit()

    async with session_factory() as session:
        analyzer = PdtAnalyzer(session=session, broker_registry=reg)
        status = await analyzer.compute(1)
    assert status.day_trade_count == 3
    assert status.is_at_risk is False


@pytest.mark.asyncio
async def test_buy_only_not_a_day_trade(session_factory, seeded, broker_registry_factory):
    reg = broker_registry_factory(Decimal("10000"))
    async with session_factory() as session:
        buy = Order(
            account_id=1, symbol="AAPL", side=OrderSide.BUY,
            type=OrderType.MARKET, qty=Decimal("10"), tif=TimeInForce.DAY,
            status=OrderStatus.FILLED, created_at=_now(), updated_at=_now(),
        )
        session.add(buy)
        await session.flush()
        session.add(Fill(order_id=buy.id, qty=Decimal("10"),
                         price=Decimal("100"), filled_at=_now(),
                         signed_direction=1))
        await session.commit()

    async with session_factory() as session:
        analyzer = PdtAnalyzer(session=session, broker_registry=reg)
        status = await analyzer.compute(1)
    assert status.day_trade_count == 0
```

Create `apps/backend/tests/risk/test_p5_buying_power.py`:

```python
"""BuyingPowerChecker tests."""
import pytest
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.db.enums import AccountMode, OrderSide, OrderType
from app.risk.buying_power import BuyingPowerChecker


def _request(side=OrderSide.BUY, type=OrderType.MARKET, qty="10",
             limit=None, stop=None, symbol="AAPL"):
    req = MagicMock()
    req.side = side
    req.type = type
    req.qty = Decimal(qty)
    req.limit_price = Decimal(limit) if limit else None
    req.stop_price = Decimal(stop) if stop else None
    req.symbol = symbol
    return req


def _account():
    return MagicMock(id=1, mode=AccountMode.live)


def _registry(buying_power: Decimal):
    """Build a registry whose adapter returns a dict snapshot (sync).
    Matches the as-built BrokerAdapter (Session 2 v1.0)."""
    reg = MagicMock()
    adapter = MagicMock()
    # Sync return; dict shape matching what AlpacaAdapter actually produces
    adapter.get_account = MagicMock(return_value={
        "cash": "1000",
        "equity": "1000",
        "buying_power": str(buying_power),
    })
    reg.get.return_value = adapter
    return reg


@pytest.mark.asyncio
async def test_sell_orders_exempt():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("0")))
    decision = await checker.check(_account(), _request(side=OrderSide.SELL))
    assert decision.sufficient is True


@pytest.mark.asyncio
async def test_limit_buy_sufficient():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("10000")))
    decision = await checker.check(_account(), _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is True
    assert decision.required_notional == Decimal("1000")


@pytest.mark.asyncio
async def test_limit_buy_insufficient():
    checker = BuyingPowerChecker(broker_registry=_registry(Decimal("500")))
    decision = await checker.check(_account(), _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is False
    assert "INSUFFICIENT_BUYING_POWER" in decision.rejection_reason


@pytest.mark.asyncio
async def test_market_buy_uses_bar_cache_price():
    bar_cache = MagicMock()
    bar_cache.get_latest_bar = AsyncMock(return_value={"c": "100"})
    checker = BuyingPowerChecker(
        broker_registry=_registry(Decimal("10000")),
        bar_cache=bar_cache,
    )
    decision = await checker.check(_account(), _request(type=OrderType.MARKET, qty="10"))
    assert decision.required_notional == Decimal("1010.00")
    assert decision.sufficient is True


@pytest.mark.asyncio
async def test_broker_unreachable_fails_open():
    """Fail-open: any exception from the adapter → proceed without check
    (matches Notes & Gotchas #14)."""
    reg = MagicMock()
    adapter = MagicMock()
    adapter.get_account = MagicMock(side_effect=RuntimeError("broker down"))
    reg.get.return_value = adapter
    checker = BuyingPowerChecker(broker_registry=reg)
    decision = await checker.check(_account(),
                                    _request(type=OrderType.LIMIT, limit="100", qty="10"))
    assert decision.sufficient is True
    assert "Broker unreachable" in (decision.rejection_reason or "")
```

Create `apps/backend/tests/api/test_p5_risk_endpoints.py`:

```python
"""/api/v1/risk-limits and /accounts/{id}/risk/* tests."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.db.enums import AccountMode, RiskScopeType
from app.db.models.account import Account
from app.db.models.risk_limits import RiskLimits


def _now():
    return datetime.now(timezone.utc)


@pytest.mark.asyncio
async def test_list_risk_limits_returns_user_rows(auth_client, session_factory):
    async with session_factory() as session:
        session.add(RiskLimits(
            id=100, user_id=1, broker_mode=AccountMode.paper,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("2000"),
            created_at=_now(), updated_at=_now(),
        ))
        session.add(RiskLimits(
            id=101, user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        ))
        await session.commit()

    r = await auth_client.get("/api/v1/risk-limits")
    assert r.status_code == 200
    body = r.json()
    by_mode = {i["broker_mode"]: i for i in body["items"]}
    assert by_mode["paper"]["max_daily_loss"] == "2000"
    assert by_mode["live"]["max_daily_loss"] == "500"


@pytest.mark.asyncio
async def test_update_risk_limits_changes_value_and_audits(auth_client, session_factory):
    async with session_factory() as session:
        rl = RiskLimits(
            user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        )
        session.add(rl)
        await session.commit()
        await session.refresh(rl)
        limits_id = rl.id

    r = await auth_client.put(f"/api/v1/risk-limits/{limits_id}", json={
        "max_daily_loss": "400",
    })
    assert r.status_code == 200
    assert r.json()["max_daily_loss"] == "400"

    from app.db.models.audit_log import AuditLog
    async with session_factory() as session:
        from sqlalchemy import select
        audits = (await session.execute(
            select(AuditLog).where(AuditLog.action == "risk_limits_updated")
        )).scalars().all()
    assert len(audits) >= 1


@pytest.mark.asyncio
async def test_update_risk_limits_other_user_returns_404(auth_client, session_factory):
    from app.db.models.user import User
    async with session_factory() as session:
        session.add(User(id=2, email="other@local"))
        rl = RiskLimits(
            user_id=2, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        )
        session.add(rl)
        await session.commit()
        await session.refresh(rl)
        other_id = rl.id

    r = await auth_client.put(f"/api/v1/risk-limits/{other_id}",
                                json={"max_daily_loss": "1"})
    assert r.status_code == 404


@pytest.mark.asyncio
async def test_risk_state_returns_breaker_and_pdt(auth_client, session_factory):
    async with session_factory() as session:
        session.add(Account(id=1, user_id=1, broker="alpaca",
                            mode=AccountMode.paper, label="Paper",
                            created_at=_now()))
        await session.commit()

    r = await auth_client.get("/api/v1/accounts/1/risk-state")
    assert r.status_code == 200
    body = r.json()
    assert "circuit_breaker" in body
    assert "pdt" in body
    assert body["circuit_breaker"]["tripped"] is False


@pytest.mark.asyncio
async def test_reset_with_correct_confirmation(auth_client, session_factory):
    async with session_factory() as session:
        account = Account(user_id=1, broker="alpaca", mode=AccountMode.paper,
                          label="Paper", created_at=_now())
        account.circuit_breaker_tripped_at = _now()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        acc_id = account.id

    r = await auth_client.post(
        f"/api/v1/accounts/{acc_id}/risk/reset-circuit-breaker",
        json={"confirmation_text": "Paper"},
    )
    assert r.status_code == 200

    async with session_factory() as session:
        acc = await session.get(Account, acc_id)
    assert acc.circuit_breaker_tripped_at is None


@pytest.mark.asyncio
async def test_reset_with_wrong_confirmation_returns_400(auth_client, session_factory):
    async with session_factory() as session:
        account = Account(user_id=1, broker="alpaca", mode=AccountMode.paper,
                          label="Paper", created_at=_now())
        account.circuit_breaker_tripped_at = _now()
        session.add(account)
        await session.commit()
        await session.refresh(account)
        acc_id = account.id

    r = await auth_client.post(
        f"/api/v1/accounts/{acc_id}/risk/reset-circuit-breaker",
        json={"confirmation_text": "wrong-label"},
    )
    assert r.status_code == 400
```

Run:

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m pytest tests/risk/ tests/api/test_p5_risk_endpoints.py -v
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

- [ ] 8 circuit-breaker tests pass.
- [ ] 5 PDT analyzer tests pass.
- [ ] 5 buying-power tests pass.
- [ ] 6 endpoint tests pass.
- [ ] Full suite green.
- [ ] All eight CI invariants pass.

---

## §5.10 — ADR 0004

Create `docs/adr/0004-circuit-breaker-hard-halt.md`:

```markdown
# ADR 0004 — Daily-Loss Circuit Breaker as Hard Halt

| Field | Value |
|---|---|
| Date | 2026-05-23 |
| Status | Accepted |
| Phase | P5 §5 |
| Supersedes | — |
| Superseded by | — |

## Context

P5 introduces live trading. Live accounts can lose real money. The
workbench's existing P1 risk engine enforces per-order and per-minute
limits; it doesn't have an account-level "this isn't going well, stop"
state.

We need a way to bound account-level loss in a single day. Three
candidate designs were considered:

1. **Hard halt** — when daily PnL crosses a configured threshold, every
   live order is rejected; every active strategy is moved to a HALTED
   state; manual user action is required to resume.

2. **Soft warning** — surface a UI banner and an alert when daily PnL
   approaches the threshold, but continue trading.

3. **Adaptive sizing** — when daily PnL approaches the threshold, reduce
   subsequent order sizes proportionally to slow down further loss.

## Decision

**Hard halt.** Daily PnL ≤ -max_daily_loss → every live order rejected,
every active strategy transitions to HALTED, manual reset required.

## Rationale

The choice between hard halt and the alternatives turns on what kind of
loss day-trading bugs typically produce.

- **A strategy that has gone wrong tends to keep being wrong.** A flaw in
  signal generation, position sizing, or exit logic produces correlated
  losses across many orders, not a single bad trade. Soft warnings let the
  bug keep losing money while the user is reading the banner.

- **Adaptive sizing assumes the bug has graceful failure modes.** A
  strategy submitting 100-share orders at 60% loss rate is no safer at
  50-share orders — it's losing the same percentage of buying power per
  trade, just slightly slower. The math of "reduce size" doesn't help
  when the underlying logic is wrong.

- **Manual reset forces the user to look.** The whole point of a circuit
  breaker is to interrupt the flow of damage long enough for a human to
  evaluate what's happening. Auto-reset (at midnight, after a cooling
  period, etc.) defeats this — it encodes the assumption that whatever
  caused the loss was transient. We assume the opposite by default.

- **Halting strategies, not just rejecting orders.** A strategy that
  submits an order, gets a CIRCUIT_BREAKER rejection, and tries again on
  the next bar tick is not actually stopped — it's spinning at maximum
  rate. The HALTED status is the engine-level signal that the strategy
  should not be dispatched, even if it would otherwise be active.

## Consequences

**Positive:**
- A single bug cannot lose more than `max_daily_loss` in one day per
  account (modulo open positions that drift between order submissions).
- The manual reset step creates a checkpoint where the user examines
  what happened before resuming.
- Halted strategies stay halted across backend restarts (status is
  persisted), so a flapping backend doesn't accidentally restart broken
  strategies.

**Negative:**
- A genuine market move that briefly crosses the threshold halts trading
  for the rest of the day even if the strategy would have recovered.
  Mitigation: the limit is conservative on LIVE accounts ($500 default);
  users can edit it up if they have a higher risk tolerance.
- "Manual reset" friction during fast markets is a real cost. A trader
  who wants to resume immediately after a brief drawdown has to click
  through the reset modal. We consider this acceptable because the
  reset modal explicitly displays the loss state.
- Adds a code path on every order submission. The check is a single
  indexed query plus an optional broker round-trip; ~5-15ms overhead.

## Alternatives considered (not chosen)

- **Per-strategy circuit breakers.** Would localize the damage to one
  strategy. Rejected: in practice multiple strategies share the same
  account and the same buying power; protecting just one doesn't
  protect the account. Account-scope is the right unit.

- **Configurable: hard halt OR soft warning.** Adds complexity and a
  setting the user has to think about. Rejected: a single defensible
  default beats an adjustable one when the cost of the wrong choice
  is high.

- **Auto-restart strategies on reset.** Convenient but undoes the "force
  the user to look" principle. Rejected.

## Implementation notes

- `accounts.circuit_breaker_tripped_at` is the source of truth (NULL =
  not tripped).
- `CircuitBreakerService.trip()` atomically: sets the timestamp, HALTs
  strategies, writes audit, publishes bus event.
- `CircuitBreakerService.reset()` requires the user to type the account
  label (server re-checks against the value).
- Background PnL polling is out of scope. A position that drifts deep
  while no orders are being submitted will not trigger until the next
  order attempt. P5+ polish.
```

- [ ] ADR 0004 committed.

---

## §5.11 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30

# Log in (session cookie set in /tmp/cookies.txt)
./scripts/login_helper.sh

# 1. Risk state for the paper account: not tripped, no PDT, normal headroom
PAPER_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[0].id')
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID}/risk-state | jq

# 2. Verify the LIVE-scoped risk_limits row from the migration
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/risk-limits | jq '.items[] | select(.broker_mode == "live")'
# Expect: max_position_qty=10, max_daily_loss=500, max_orders_per_day=20

# 3. Tighten the paper limit so we can trip it
PAPER_LIMITS_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/risk-limits | jq -r '.items[] | select(.broker_mode == "paper") | .id')
curl -s -b /tmp/cookies.txt -X PUT http://127.0.0.1:8000/api/v1/risk-limits/${PAPER_LIMITS_ID} \
  -H "Content-Type: application/json" \
  -d '{"max_daily_loss": "1.00"}'   # absurdly tight for testing

# 4. Submit a market buy that will lose more than $1
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"5\", \"tif\": \"day\"
  }"
sleep 5

# After the order fills and the position drifts down even slightly:
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"5\", \"tif\": \"day\"
  }" | jq
# Expect: 400 with reason CIRCUIT_BREAKER

# 5. Check risk-state — should show tripped
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID}/risk-state | jq '.circuit_breaker'

# 6. UI check: Open the account dashboard — red CIRCUIT BREAKER TRIPPED banner.
#    Click Reset → typed-confirmation modal. Type the account label → reset succeeds.

# 7. Reset via API
ACC_LABEL=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID} | jq -r '.label')
curl -s -b /tmp/cookies.txt -X POST \
  http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID}/risk/reset-circuit-breaker \
  -H "Content-Type: application/json" \
  -d "{\"confirmation_text\":\"${ACC_LABEL}\"}" | jq

# 8. Verify reset
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts/${PAPER_ACC_ID}/risk-state \
  | jq '.circuit_breaker.tripped'
# Expect: false

# 9. But strategies remain HALTED — verify by listing
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies | jq '.items[].status'

# 10. Restore the limit to the migration default
curl -s -b /tmp/cookies.txt -X PUT http://127.0.0.1:8000/api/v1/risk-limits/${PAPER_LIMITS_ID} \
  -H "Content-Type: application/json" \
  -d '{"max_daily_loss": "2000.00"}'

# 11. THE LOAD-BEARING SMOKE: paper order works normally
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\", \"tif\": \"day\"
  }" | jq '{id, status, broker_order_id}'
# Expect: order routes; broker_order_id from Alpaca

docker compose down
```

- [ ] Risk-state endpoint works.
- [ ] LIVE-scoped risk_limits row exists with tight defaults.
- [ ] Tightening the limit then submitting trips the breaker.
- [ ] Subsequent orders rejected.
- [ ] Strategies HALTED after trip.
- [ ] Reset requires typed confirmation; succeeds.
- [ ] After reset, strategies remain HALTED.
- [ ] **Paper smoke at normal limits: byte-identical to baseline.**

---

## §5.12 — Runbook

Create `docs/runbook/risk-gates.md`:

```markdown
# Risk Gates

P5 §5 introduced four account-level risk gates on top of P1's per-order
checks:

| Gate | When checked | What happens on failure |
|---|---|---|
| Circuit breaker | Every order submission | Order rejected; strategies HALTED |
| Per-day order cap | Every order submission | Order rejected with MAX_ORDERS_PER_DAY |
| Pre-trade buying power (LIVE only) | Every LIVE order submission | Order rejected with INSUFFICIENT_BUYING_POWER |
| PDT warning | UI poll (60s) | Banner displayed; no blocking |

## Circuit breaker

**Trip condition:** `realized_pnl_today + unrealized_pnl_now ≤ -max_daily_loss`

When it trips:
1. `accounts.circuit_breaker_tripped_at` is set to NOW().
2. Every PAPER or LIVE strategy on this account transitions to HALTED.
3. An audit_log entry is written (action=circuit_breaker_tripped).
4. The system.circuit_breaker bus event is published.
5. The submitting order is rejected with `CIRCUIT_BREAKER`.

While tripped: every order to the account is rejected with the same code.

**Reset:** `POST /api/v1/accounts/{id}/risk/reset-circuit-breaker` with
the account label as `confirmation_text`. The UI's reset modal enforces
this; the server re-checks server-side.

The reset re-enables order submission BUT does NOT auto-restart HALTED
strategies. You must start each one manually.

**Known limitation:** the breaker checks only on order submission. A
held position that drifts deep while no orders are being submitted will
not trip until the next order attempt. We accept this — a position
losing money while no algos are active is a problem the trader should
notice without the breaker.

## Per-day order cap

`risk_limits.max_orders_per_day` (defaults: PAPER 200, LIVE 20). Orders
on the account since 09:30 US/Eastern today count. NULL means unlimited.

Edit at Settings → Risk Limits. Increases are audit-logged.

## Pre-trade buying power (LIVE only)

For LIVE order submissions, the workbench calls
`BrokerAdapter.get_account()` to fetch live buying power, computes the
worst-case notional, and rejects if insufficient.

Order types:
- MARKET: latest close × qty × 1.01
- LIMIT / STOP_LIMIT: limit_price × qty
- STOP: stop_price × qty × 1.01
- SELL: always passes

If the broker is unreachable, the check fails open (the broker would
reject if it really doesn't have buying power; we'd rather have a clean
broker reject than a half-baked local one).

## Pattern Day Trader warning

A "day trade" is opening and closing the same symbol within one trading
day (US/Eastern). The analyzer walks fills from the last 5 business
days and counts.

We warn at 3 day trades (FINRA flags at 4) when account equity <
$25,000. We DO NOT block. The user owns the FINRA decision.

## Editing risk limits

Settings → Risk Limits. Two rows per user (PAPER + LIVE). Editing fires
an audit_log entry with the old and new values.

## Strategy HALTED status

`StrategyStatus.HALTED` is distinct from ERROR (crashed) and IDLE
(user-stopped). Causes:
- Circuit breaker trip.
- (Future) Manual halt by a user.

To restart a HALTED strategy: go to its detail page and click Start.
The status transitions HALTED → IDLE → PAPER (or LIVE). No automatic
restart anywhere in the system.
```

- [ ] Runbook committed.

---

## §5.13 — Commit and PR

```bash
# New file (shared helper introduced in §5.0)
git add apps/backend/app/utils/time.py

# Refactored to import the shared helper (small mechanical edits)
git add apps/backend/app/auth/stub.py
git add apps/backend/app/security/credential_store.py

# Session 5 substance
git add apps/backend/app/db/models/account.py
git add apps/backend/app/db/models/risk_limits.py
git add apps/backend/app/db/enums.py
git add apps/backend/alembic/versions/
git add apps/backend/app/risk/circuit_breaker.py
git add apps/backend/app/risk/pdt_analyzer.py
git add apps/backend/app/risk/buying_power.py
git add apps/backend/app/risk/engine.py
git add apps/backend/app/api/v1/risk.py
git add apps/backend/app/api/v1/__init__.py
git add apps/backend/app/ws/gateway.py
git add apps/backend/tests/risk/
git add apps/backend/tests/api/test_p5_risk_endpoints.py
git add apps/frontend/src/api/risk.ts
git add apps/frontend/src/components/risk/RiskStateBanner.tsx
git add apps/frontend/src/pages/Settings/RiskLimits.tsx
git add apps/frontend/src/App.tsx
git add docs/adr/0004-circuit-breaker-hard-halt.md
git add docs/runbook/risk-gates.md

git commit -m "feat(p5): live-mode risk gates — circuit breaker, PDT, buying power (P5 §5)

- New StrategyStatus.HALTED for circuit-breaker policy halts.
- New columns: accounts.circuit_breaker_tripped_at, risk_limits.max_orders_per_day.
- Data migration seeds a LIVE-scoped risk_limits row per user with tight
  defaults (max_position_qty=10, max_daily_loss=\$500, max_orders_per_day=20).
  Existing PAPER rows backfilled with max_orders_per_day=200.
- CircuitBreakerService: account-scoped breaker. Trips on
  realized_pnl_today + unrealized_pnl_now ≤ -max_daily_loss. On trip:
  set timestamp, HALT all active strategies on the account, audit, publish
  system.circuit_breaker bus event. Reset requires typed-account-label
  confirmation; does NOT auto-restart HALTED strategies.
- PdtAnalyzer: walks fills last 5 business days, identifies day trades
  via per-symbol position-walk; warns at 3 day trades + equity < \$25K.
  Warning only; no blocking.
- BuyingPowerChecker (LIVE only): calls BrokerAdapter.get_account() for
  fresh buying power; rejects worst-case-notional > buying_power. Sells
  exempt. Fail-open on broker unreachable.
- RiskEngine extended with all three gates. Order matters: circuit
  breaker first (cheap), then per-day cap (one COUNT query), then
  buying power (LIVE only, broker round-trip).
- Endpoints:
    GET    /api/v1/risk-limits
    PUT    /api/v1/risk-limits/{id}
    GET    /api/v1/accounts/{id}/risk-state
    POST   /api/v1/accounts/{id}/risk/reset-circuit-breaker
- Audit actions: CIRCUIT_BREAKER_TRIPPED, CIRCUIT_BREAKER_RESET,
  RISK_LIMITS_UPDATED.
- Frontend: RiskStateBanner (account dashboard) renders trip + PDT
  warnings; reset modal requires typed account label.
- ADR 0004: daily-loss circuit breaker as hard halt.
- 24 backend tests; 8 CI invariants all green.

NOT in this PR:
- Background PnL polling — checks only on order submission.
- Auto-reset of breaker or auto-restart of strategies.
- Margin / day-trading buying power.

Load-bearing: P1-§4 paper smoke produces byte-identical chains
(no breaker trip with default \$2,000 daily loss limit)."

git push -u origin feat/p5-session5-risk-gates

gh pr create \
  --title "feat(p5): live-mode risk gates (P5 §5)" \
  --body "P5 Session 5 — circuit breaker, PDT warning, pre-trade buying power.

Load-bearing assertion: paper smoke from P1-§4 unchanged.

PLEASE: do not merge in flow. The circuit breaker is one of two systems
in P5 that prevents catastrophic loss (the other is the activation
wizard in §7). Re-read the trip/reset logic carefully."

gh pr checks

# Walk away ≥1 hour (Session 4 was merged without this; the cost showed up
# in the Results punch list). Re-read with attention to:
# - trip() is atomic (timestamp + strategies + audit + publish, single commit)
# - reset() requires correct confirmation_text (NOT just authentication)
# - HALTED strategies stay HALTED across reset
# - The daily PnL calc handles "no positions today" correctly (no false trip)
# - ensure_aware coercion applied wherever stored datetimes meet aware ones

# Squash-merge convention (matches Session 4's `b5b37da`)
gh pr merge --squash --subject "feat(p5): live-mode risk gates (P5 §5) (#NN)" --delete-branch
git checkout main && git pull
git tag -a p5-session5-complete -m "P5 §5 risk gates complete"
git push origin p5-session5-complete
```

- [ ] PR opened; CI green incl. all eight invariants + ADR 0002 test.
- [ ] Walked away ≥1 hour; trip/reset logic re-read; `ensure_aware` usage verified.
- [ ] All eight invariants pass.
- [ ] PR merged.
- [ ] Tag pushed.

---

## Verification Checklist (full session)

- [ ] §5.1 Schema columns + StrategyStatus.HALTED + migration round-trips.
- [ ] §5.2 CircuitBreakerService trips atomically, resets with confirmation.
- [ ] §5.3 PdtAnalyzer detects day trades correctly.
- [ ] §5.4 BuyingPowerChecker rejects insufficient with clean error.
- [ ] §5.5 RiskEngine integrates all three gates.
- [ ] §5.6 Risk endpoints work end-to-end.
- [ ] §5.7 Audit actions + WS routing.
- [ ] §5.8 Frontend banner + reset modal with typed confirmation.
- [ ] §5.9 24 backend tests pass; eight CI invariants green.
- [ ] §5.10 ADR 0004 documents the hard-halt decision.
- [ ] §5.11 Manual smoke: trip-and-reset works; paper baseline unchanged.
- [ ] §5.12 Runbook covers all four gates.
- [ ] §5.13 PR merged, tag pushed.

---

## Notes & Gotchas

1. **The breaker's "today" window is fixed -5h UTC offset, not DST-aware.** Gotcha-of-record: from March-November the realized-PnL window shifts by one hour (because EDT is UTC-4, not UTC-5). For MVP this means the breaker's idea of "today's PnL" is off by one hour for ~7 months. Trip threshold isn't affected (it's a comparison against a configured value); just the time-of-day at which the window resets. P5+ polish replaces with `zoneinfo.ZoneInfo("America/New_York")`. Don't mix this with the activation wizard's date handling in §7.

2. **The realized PnL is conservative (over-counts loss on open positions).** Gotcha at §5.2: `_compute_realized_pnl_today` sums signed cash flow today. Open positions opened today appear as cash outflows (potential loss) until they're closed. The companion `_compute_unrealized_pnl` adds positions' unrealized P&L back via the broker. Net `(realized + unrealized)` is the correct quantity. If the broker is unreachable, unrealized=0 and the net biases negative — meaning a stuck breaker trip is more likely than a missed one. Acceptable for a safety-first design; documented.

3. **No background PnL polling.** The breaker checks on order submission only. A position that drifts deep while no orders are being submitted will NOT trip the breaker. The user owns this exposure. P5+ polish: a one-minute APScheduler job that calls `cb.check(account_id)` for every account with active positions.

4. **HALTED strategies do not auto-restart on reset.** Gotcha §5.10 + §5.12 + ADR 0004: this is a deliberate friction. The user is forced to look at each strategy and decide whether it's still appropriate before resuming. Auto-restart would defeat the purpose of the manual reset.

5. **Reset requires typed account label as `confirmation_text`.** Gotcha §5.2's reset: server-side defense in depth. The frontend's modal enforces it client-side, but a direct API call also requires the match. If the user changes the account label between trip and reset, they must type the NEW label. Mention this in the modal copy if it becomes confusing.

6. **`trip()` is atomic but not transactional across services.** Gotcha §5.2: all the DB writes (account row + strategy rows + audit row) commit in one session.commit(). But the bus.publish() happens after the commit — if publish fails, the trip is still durable. This is the right order: better to have a tripped account with no WS notification than a non-tripped account with a stale WS warning.

7. **PDT analyzer uses a position-walk, not order-counting.** Gotcha §5.3: a "day trade" is determined by whether the symbol's position crossed zero both ways within one day. This handles partial fills correctly (5 buys + 1 sell that brings position back to 0 = 1 day trade, not 5). The simpler "count buy-sell pairs" approach would mis-count.

8. **The PDT warning threshold is 3, but FINRA's is 4.** Gotcha §5.3's `PDT_DAY_TRADE_THRESHOLD = 3`: we warn one trade early so users have a chance to back off before triggering the actual FINRA rule. Configurable if a real user finds this annoying.

9. **Pre-trade buying power is LIVE-only.** Gotcha §5.5: paper accounts skip the check. Alpaca paper enforces buying power on its side (with paper money it's generous), and adding a broker round-trip to every paper order would noticeably slow down paper smoke. If you want to test the buying-power check on paper for development, temporarily flip the `if account.mode == AccountMode.live` condition; revert before merging.

10. **The migration creates a LIVE risk_limits row even though no LIVE account exists.** Gotcha §5.1.4: this is intentional. P5 §7's activation wizard reads this row to populate the wizard's risk-limit step. If we created the row only at wizard time, we'd have a chicken-and-egg dependency. Creating it at migration time means it's there and editable from day one of §5.

11. **The `max_orders_per_day=200` backfill for paper changes behavior.** Gotcha §5.1.4: existing paper risk_limits previously had no per-day cap; the migration sets 200. If your paper strategies submit >200 orders/day, they'll start hitting MAX_ORDERS_PER_DAY rejections. Adjust upward if needed (Settings → Risk Limits) before merging. We expect 200/day to be generous enough that no normal strategy hits it.

12. **Walk away before merging.** Gotcha §5.13: this PR adds a hard-halt mechanism that you will rely on. The cost of a bug is high (false trips lock the user out; missed trips let losses run). Re-read the trip and reset logic with the eyes of someone debugging at midnight after a trip happened in production. Particularly: `_get_active_limits`, the order of operations in `trip()`, and the `confirmation_text` check in `reset()`.

13. **Don't bundle P5 §6 (live order safety) into this PR.** Each P5 session is its own tag.

14. **`BuyingPowerChecker` fails open on any adapter error.** §5.4: the design decision is **fail-open** — broker unreachable, credentials revoked, transient network error, all fall through to "no check performed, broker decides on its side." Reasoning: a temporary Alpaca outage shouldn't block all live orders; Alpaca itself does the authoritative buying-power check on its side and will reject if truly insufficient. The platform's pre-trade check is a *helpful early warning*, not the safety mechanism — that's the risk engine's other gates plus Alpaca's own enforcement. Two alternatives were considered and rejected for §5 scope: **fail-closed** (reject the order; safer but unfamiliar UX when Alpaca is briefly down), and **trip-the-breaker** (escalate to the operator; too aggressive for a transient API hiccup). Future hardening could add a "consecutive failures → trip" policy; out of §5 scope.

15. **The shared `ensure_aware()` helper at `app/utils/time.py` is the canonical fix for SQLite's naive datetime return.** §5.0: Session 3 first hit this in `app/auth/stub.py::_aware`; Session 4 hit it again in `app/security/credential_store.py::_ensure_aware`. Session 5 is the third site; extracting once costs ~15 lines and avoids three more copies. New code in §5.2 / §5.3 / §5.5 imports from `app.utils.time`. The two prior copies are refactored to import the shared helper (small mechanical edits to `stub.py` and `credential_store.py`).

16. **ADR 0008 implication (additive schema).** The new `risk_limits.max_orders_per_day` column and the new `accounts.circuit_breaker_tripped_at` column are additive — they don't change any existing column's meaning or shape. This means future risk-related capabilities (per-strategy gross exposure caps, per-symbol limits, time-of-day caps, etc., all listed in v0.1's "Out of scope") can extend the schema with new columns and new RiskEngine gates without rewriting §5 work. The pattern of "one new column per new risk dimension + one new gate in `RiskEngine.check()`" generalizes cleanly.

17. **Circuit-breaker trip/reset does NOT touch `BrokerRegistry`.** Important integration point with Session 4's async broker registry: when the breaker trips, the platform stops *routing orders to* the adapter; the adapter itself remains constructed and connected. When the breaker resets, no `broker_registry.refresh()` call is needed — the adapter was never modified. The `RiskEngine.check()` is the gate; the adapter is the destination. The two are deliberately separate concerns.

18. **`_router_token` discipline preserved.** Session 2's load-bearing invariant: broker mutators (`submit_order` / `cancel_order` / `replace_order`) are `_router_token`-gated, only `OrderRouter` passes it. Session 5's new risk gates call only adapter *read* methods (`adapter.get_account()` in `BuyingPowerChecker` and `PdtAnalyzer._fetch_equity`). No mutator calls; no token needed; `tests/test_adr_0002_invariant.py` stays green without edit.

---

*End of P5 Session 5 v0.2. Updated in-place from v0.1 (2026-05-23) with 13 drift corrections from `TradingWorkbench_P5_Session5_DriftAnalysis_v0.1.md` and the two design decisions captured in Notes & Gotchas #14 and #15.*
