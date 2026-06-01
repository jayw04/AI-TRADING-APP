# P5 Session 7 — Activation Wizard & Live Path Open

| Field | Value |
|---|---|
| Document version | **v0.2** (updated in-place from v0.1; 15 drift corrections from Sessions 0–6 Results + candid acknowledgment of execution-surfaced drift) |
| Date | 2026-05-31 |
| Phase | **P5 — Live Trading**, **§7** (entirely) |
| Predecessor | `TradingWorkbench_P5_Session6_v0.2.md` (tag `p5-session6-complete`, PR #44) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Scope | **Open the live order path.** Lift P5 §1's BrokerModeError guard with the gates from §2-§6 now in place. Multi-step activation wizard with prerequisites checklist (credentials, TOTP, backtest within 7 days, risk limits, no breaker). 24-hour activation cooldown between wizard completion and live order flow (ADR 0005). Strategy lifecycle: IDLE → PENDING_LIVE (24h) → LIVE → IDLE (with optional liquidation on deactivation). LIVE account creation permitted via API. Background scheduler completes pending activations. New endpoints for activation/deactivation/cancellation. New `StrategyStatus.PENDING_LIVE`. New `strategies.live_activation_initiated_at`. Single PR. |
| Estimated wall time | 5 hours |
| Stopping point | `git tag p5-session7-complete` |
| Out of scope | Multi-strategy bulk activation. Backtest *quality* requirements (we check that a backtest ran, not that it was profitable — strategy quality is the user's call). Auto-deactivation on drawdown beyond the circuit breaker (the breaker IS that mechanism). Wizard pause / resume across sessions. Account-level activation cooldown (cooldown is per-strategy). Cross-strategy correlation analysis as a prerequisite. Auto-suggestion of risk limits based on backtest stats (P5+ polish). |

---

## Updated in v0.2 (drift corrections + candid acknowledgment of what we can't predict)

This file was updated 2026-05-31 against what Sessions 1–6 actually shipped (v0.1 was drafted 2026-05-23, before any of them executed). Sources: Session Zero Results, Session 2 v1.0 + Results, Session 3 Results, Session 4 Results, Session 5 v0.2 + Results, Session 6 v0.2 + Results.

### Part 1 — Drift corrections applied below (the knowable ones)

1. **`BrokerMode` → `AccountMode`.** Session Zero confirmed; the enum is `AccountMode` (lowercase values `paper` / `live`). Affects §7.3 prerequisite checks, §7.5 guard-lifting block, §7.6 LIVE account creation, §7.10 tests.

2. **`OrderSource` → `OrderSourceType`** (the enum); **`orders.source` → `orders.source_type`** (the column). Session Zero Results. Affects §7.5 guard-lifting (the `request.source == OrderSourceType.STRATEGY` checks).

3. **OrderRouter lives at `app/orders/router.py`**, not `app/orders/router.py`. Session Zero + Session 6 Results.

4. **`AuditLogger` is sync, lives in `app.audit.logger`**, and `write()` does NOT take `await`. Session 5 + 6 Results confirmed. The v0.1 code uses `AuditLogger.write(...)` with import from `app.services.audit_log`. Both wrong throughout §7.3, §7.4, §7.6, §7.7, §7.8.

5. **Audit action enum values use the UPPER convention** (`STRATEGY_ACTIVATION_INITIATED`, not lowercase). Confirmed by Session 6 Results — matches the existing `AuditAction` enum convention. The v0.1 doc's action values are already uppercase, so this is mostly a verification item: don't accidentally use lowercase.

6. **`strategies` has NO `account_id` column.** This is the most consequential drift in Session 7. v0.1 references `strategy.account_id` in **six places** (lines 438, 630, 730, 827, 831, 852). Session 5 Results documented the actual mapping: strategies have `user_id` + `status` (PAPER/LIVE per `StrategyStatus`), and account derivation goes via `user_id` + the desired mode. For Session 7's prerequisite check, "the strategy's account" means **the user's LIVE account** (since activation is about going LIVE). For deactivation's optional liquidation, "the strategy's account" means **the LIVE account the strategy is associated with** (a strategy with `status=LIVE` has at most one LIVE account per user). See the corrected helper `_resolve_strategy_account(strategy, mode)` introduced in §7.3 below.

7. **Existing global daily-loss halt** (`app/risk/halt.py`, RiskEngine step 9) coexists with the account-scoped breaker from §5. §7's "no active circuit breaker" prerequisite checks the account-scoped breaker (Session 5's `accounts.circuit_breaker_tripped_at`). The global halt is orthogonal — when triggered, ALL orders are blocked regardless of strategy status, so it's not a prerequisite to check but rather an environmental condition. Worth flagging in Notes & Gotchas.

8. **`_router_token` discipline preserved.** Session 2's load-bearing invariant: broker mutators (`submit_order`/`cancel_order`/`replace_order`) are `_router_token`-gated; only `OrderRouter` itself passes it. Session 7's **liquidation flow in §7.4 calls `OrderRouter.submit()`** to close positions — this is the right pattern (the OrderRouter is the gate, and liquidation orders go through the same audit/risk path as regular orders). But: this means the liquidation orders carry `OrderSourceType.MANUAL` or a new source (e.g., `OrderSourceType.LIQUIDATION`) — verify the existing enum, don't invent. If a `LIQUIDATION` source doesn't exist, use `MANUAL` with a flag or a special audit tag. The integration test must verify liquidation orders pass through risk gates (including §6 cooldown rules — though MANUAL bypasses cooldown).

9. **Strategy authorization uses `user_id`**, not a join through `account`. Session 6 established the pattern: `if strategy.user_id != current_user_id: raise PermissionError`. v0.1's §7.4 already does this correctly, so this is mostly a verification.

10. **Shared `ensure_aware()` helper at `app/utils/time.py`** (introduced in Session 5 §5.0). Session 7 has heavy datetime work: `live_activation_initiated_at`, `completes_at = initiated_at + 24h`, `account.circuit_breaker_tripped_at` checks, the scheduler's `now - 24h` comparison. Every SQLite-stored datetime needs `ensure_aware()` before comparison against `datetime.now(timezone.utc)`. **At least 5 sites need this.** Without it: silent-correctness bugs where the scheduler appears to never complete a pending activation, or `seconds_remaining` shows nonsense.

11. **Two daily-loss mechanisms now coexist** (inherited from Session 5 / Session 6). Session 7's activation flow doesn't directly touch either, but the prerequisite "no active circuit breaker on the strategy's account" checks the **account-scoped breaker only**. If the **global halt** at `app/risk/halt.py` is active, activations should also be blocked — but that's handled by the RiskEngine when orders flow, not by Session 7's prereq check. Worth a one-paragraph note.

12. **Paths and tooling.** Windows working dir (`C:\LLM-RAG-APP\ai-trading-app`); `uv run` → `.\.venv\Scripts\python.exe`; pytest needs `--cov-branch`. Affects Prerequisites and §7.13.

13. **`check_adr0002.sh` removed from Prerequisites.** Doesn't exist; ADR 0002 is enforced by `tests/test_adr_0002_invariant.py` + the `_router_token` tripwire.

14. **API router wired via `app/api/v1/__init__.py`** with no extra prefix (Session 5/6 deviation). The §7.7 endpoint registration should follow the same pattern.

15. **Frontend uses `apiFetch` + plain `useEffect` polling**, not React Query (Session 6 Results: "the strategy detail page is rendered/tested without a `QueryClientProvider`"). §7.9's `ActivationCountdown` polling should follow the same pattern as §6.7's `CooldownIndicator`.

### Part 2 — Candid acknowledgment of what this drift analysis CANNOT predict

Session 5 surfaced ~6 unknown drift items during execution (Fill schema, SQLEnum stores names, the existing `app/risk/halt.py`, etc.). Session 6 surfaced more (the POST /orders endpoint hardcodes the user's PAPER account; `OrderRequest` is a frozen dataclass; risk engine method is `evaluate()` not `check()`; rejections carry `rejection_reason` string not `reason_code`; no `_reject`/`_record_*` helpers; `strategy_id` derived from `source_id` not a separate field). **Session 7 will almost certainly surface its own list. The categories most likely to bite:**

- **`OrderRouter.submit()` actual signature and helper methods.** Session 6 Results showed the v0.1 sketches were against an imagined order-path shape that didn't match live code. §7.5's guard-lifting block needs to integrate with the *actual* router, including `OrderRequest` (frozen dataclass), `evaluate()` (not `check()`), `rejection_reason` (string), and Session 6's `_confirmation_reject_reason` / `_strategy_id_from_source` / `_ephemeral_rejected_order_with_reason` helpers. **Before pasting any §7.5 code, grep+read `app/orders/router.py` for its current shape — including how Session 6 modified it.**

- **The orders endpoint after Session 6.** Session 6 Results: the endpoint "hardcodes the user's PAPER account; no `account_id` in the body; `extra='forbid'`; source always MANUAL." §7.6 lifts this so LIVE accounts can be selected, but the actual change set depends on the post-§6 endpoint shape. Verify.

- **`OrderRouter.submit()` for liquidation orders.** §7.4 deactivation calls `submit` to close positions. The actual call signature, the way to convey "this is a liquidation," and how the response shape exposes success/failure all depend on Session 6's actual router. The v0.1 code shows `await self._order_router.submit(request, current_user_id=user_id)` — but per Session 6 Results, `submit` has signature `submit(req: OrderRequest) -> Order` (no `current_user_id` keyword, sync-name despite being async, returns Order not OrderSubmissionResult).

- **`Position` / `positions` table shape.** §7.4 liquidation queries open positions to determine what to close. The actual `Position` model fields (`qty`, `side`, `account_id` vs `user_id` vs both), the side determination ("long" vs `side="buy"`), and how to mark positions as "associated with strategy X" all depend on the actual model. v0.1 assumes positions have an `account_id` and a `symbol` filter on the strategy.

- **`Backtest` model shape.** §7.3's "backtest in the last 7 days" prereq queries `backtests` by `strategy_id` and `created_at`. Verify the actual model column names — `created_at` vs `started_at` vs `completed_at`; index considerations.

- **`StrategyStatus.LIVE` enum value.** The v0.1 doc adds `PENDING_LIVE` but assumes `LIVE` exists. Session 5 confirmed `HALTED` already existed; verify `LIVE` exists too (and whether existing values are uppercase like `LIVE` or lowercase like `live` — confirm against the actual `app/db/enums.py`).

- **Scheduler infrastructure.** §7.8 uses APScheduler. Verify the actual scheduler entry point in `app/jobs/` or wherever existing scheduled jobs live (Session 5 mentioned scheduled jobs in the breaker context). The scheduler may already be configured; `activation_completion.py` may just need to register itself.

- **`TOTP verify_code` import location.** §7.4 imports `from app.auth.totp import verify_code`. Verify the function actually lives there and takes `(secret, code)` in that order.

**Process recommendation for implementation:** before writing §7.3 (the prereq lookup that touches strategy/account/backtest/credentials), §7.4 (the write-side with audit logging), §7.5 (the guard-lifting OrderRouter change — the highest-risk part of §7), §7.6 (LIVE account creation), and §7.8 (the scheduler) — do a grep+read pass on each affected file. Adjust the v0.2 code to match the actual shape. Capture deviations in Session 7 Results.

**Session 7 is the most consequential session in P5.** This is the session where real money becomes possible. The walk-away ≥1h discipline (Session 4 skipped, Sessions 5+6 honored) is non-optional here.

---

## ⚠ Real-money posture

This session ships the moment your code can actually lose money. Every gate from §2-§6 is now in the actively-checked path:

- §2's `AlpacaLiveAdapter` becomes a live endpoint, not just a constructed-but-unused object.
- §3's authentication is on every request.
- §4's encrypted broker credentials are actually decrypted and used.
- §5's circuit breaker watches real PnL.
- §6's typed-ticker and cooldown gate the order submit.

The 24-hour activation cooldown is the last friction layer before LIVE orders flow. ADR 0005 (§7.1) is the durable place for that argument; the short version is that algorithms feel "ready" to traders much sooner than they actually are, and a one-day pause lets the gap show.

Load-bearing assertion: **the P1-§6 paper smoke is byte-identical.** §7 only changes behavior on paths where `account.mode == LIVE` was previously rejected; paper paths are untouched.

---

## Session Goal

After this session:
- **ADR 0005** — Activation cooldown as defense against impulse decisions. Committed at `docs/adr/0005-activation-cooldown.md`.
- New `StrategyStatus.PENDING_LIVE` — the 24-hour holding state between wizard completion and live order flow.
- New `strategies.live_activation_initiated_at` column (nullable datetime). Set when the wizard completes; the scheduler reads it to determine when 24h has elapsed.
- New `app/services/activation.py`: `ActivationService` with `check_prerequisites(strategy_id) → list[Prerequisite]`, `initiate(strategy_id, user_id, confirmation_name, totp_code)`, `cancel(strategy_id, user_id)`, `complete_pending(strategy_id)`, `deactivate(strategy_id, user_id, liquidate: bool)`.
- New `Prerequisite` data class with `name`, `satisfied`, `detail`. Five prerequisites:
  1. Live broker credentials (`alpaca_live_key` + `alpaca_live_secret` set in credential store)
  2. TOTP enrolled (`users.totp_verified_at IS NOT NULL`)
  3. Recent backtest (a `backtests` row for this strategy in the last 7 days)
  4. LIVE risk limits configured (`risk_limits` row with `broker_mode=LIVE` for the user)
  5. No active circuit breaker on the strategy's account
- **P5 §1 BrokerModeError guard lifted.** OrderRouter now permits:
  - `source=MANUAL` and `account.mode=LIVE` if the §6 confirmation passes (no strategy lookup needed).
  - `source=STRATEGY` and `account.mode=LIVE` if `strategy.status=LIVE`.
  - Refuses `source=STRATEGY` and `account.mode=LIVE` if `strategy.status=PENDING_LIVE` (with reason `STRATEGY_PENDING_LIVE`).
  - Refuses `source=AGENT` and `account.mode=LIVE` (agent doesn't submit; deferred to P6).
- **`POST /api/v1/accounts` accepts `mode=live`.** Live account creation requires TOTP confirmation in the request body.
- New endpoints:
  - `GET /api/v1/strategies/{id}/activation` — current activation status with prerequisites.
  - `POST /api/v1/strategies/{id}/activate` — initiate activation. Body: `{confirmation_name, totp_code}`. Returns 400 if any prerequisite fails. Sets status=PENDING_LIVE, `live_activation_initiated_at=now`. Audit-logged.
  - `POST /api/v1/strategies/{id}/activate/cancel` — cancel pending activation. Reverts to IDLE. Audit-logged. No TOTP needed (cancellation is always permitted).
  - `POST /api/v1/strategies/{id}/deactivate` — deactivate LIVE strategy. Body: `{liquidate: bool}`. If `liquidate=true`, enqueues closing market orders for all open positions on the account that match the strategy's symbols. Sets status=IDLE. Audit-logged.
- Background scheduler (`apps/backend/app/jobs/activation_completion.py`): runs every 60s, finds strategies with `status=PENDING_LIVE` and `live_activation_initiated_at < now - 24h`, transitions to LIVE. Audit-logged with `STRATEGY_LIVE_ACTIVATED`.
- New audit actions: `STRATEGY_ACTIVATION_INITIATED`, `STRATEGY_ACTIVATION_CANCELED`, `STRATEGY_LIVE_ACTIVATED`, `STRATEGY_DEACTIVATED`, `LIVE_ACCOUNT_CREATED`.
- Frontend: `ActivationWizard.tsx` — 4-step modal (prerequisites → review strategy → review risk → confirm with TOTP). `ActivationCountdown.tsx` — shows time-to-live for PENDING_LIVE strategies. `DeactivationModal.tsx` — confirms deactivation with optional liquidation. `LiveAccountCreationFlow.tsx` — separate path in Settings → Accounts that requires TOTP.
- 28 backend tests covering activation lifecycle + lifted guard + lifecycle audit.
- 8 CI invariants pass; **P1-§6 paper smoke byte-identical.**

What does NOT happen this session:
- **No production deployment.** §7 lifts the guards in code; §8 (production hardening) is the session that adds the monitoring/health/backup infrastructure that makes the system runnable beyond a developer's laptop. Don't activate a live strategy on the §7 build until §8 ships.
- **No backtest-quality gating.** A user can run a 5-minute backtest with bad params just to satisfy the prerequisite. We check that they engaged with the backtest tool, not the results. Quality is the user's call.
- **No multi-strategy activation.** One strategy at a time. Bulk-activation is a UX optimization that can wait.
- **No liquidation on circuit breaker trip.** §5's breaker halts strategies but leaves positions open (covered in §5's ADR 0004). §7's deactivation flow is the place to optionally liquidate.

---

## Prerequisites Check

```powershell
# from repo root; uv is not on PATH — use the venv python
cd C:\LLM-RAG-APP\ai-trading-app
git checkout main; git pull origin main
git describe --tags --abbrev=0           # expect: p5-session6-complete

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

# Verify the §1 BrokerModeError guard is currently active in the live router path
cd apps\backend
.\.venv\Scripts\python.exe -c "from app.orders.router import OrderRouter; import inspect; src = inspect.getsource(OrderRouter); assert 'BrokerModeError' in src or 'AccountMode.live' in src, 'Expected §1 guard'; print('§1 guard present')"

# Verify backtests table from P2 exists
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print([r[1] for r in c.execute('PRAGMA table_info(backtests)').fetchall()])"
# Expect: list of columns including (at least) id, strategy_id, created_at (or equivalent)

# Verify the scheduler infrastructure is wired (existing scheduled jobs from P3/P5.5)
findstr /S /R "AsyncIOScheduler\|APScheduler" app\lifespan.py
# Expect: matches

# Verify shared ensure_aware helper from Session 5 §5.0 exists
findstr /S /R "ensure_aware" app\utils\time.py
# Expect: matches

# Verify strategies table has cooldown_until from Session 6 (sanity)
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); print('cooldown_until' in [r[1] for r in c.execute('PRAGMA table_info(strategies)').fetchall()])"
# Expect: True

cd ..\..
```

Live runtime gates are **deferred** per the standing Norton SSL + no-Docker posture. The in-suite tests in §7.10 stand in for the load-bearing assertions; the live diff runs in WSL/CI before the tag is promoted to a release.

```bash
git checkout -b feat/p5-session7-activation
```

- [ ] On `main`, at `p5-session6-complete`.
- [ ] All eight CI invariants pass; ADR 0002 pytest invariant green.
- [ ] Baseline backend suite green.
- [ ] §1 BrokerModeError guard present and active in `app/orders/router.py`.
- [ ] `backtests` table from P2 exists.
- [ ] APScheduler available in `app/lifespan.py`.
- [ ] `app/utils/time.py::ensure_aware` available for import.
- [ ] `strategies.cooldown_until` present (Session 6 sanity).

---

## §7.1 — ADR 0005

Create `docs/adr/0005-activation-cooldown.md`:

```markdown
# ADR 0005 — 24-Hour Activation Cooldown

| Field | Value |
|---|---|
| Date | 2026-05-23 |
| Status | Accepted |
| Phase | P5 §7 |
| Related | ADR 0004 (circuit breaker hard halt) |

## Context

P5 §7 opens the live order path: a strategy that's been validated in
paper can now submit live orders. The activation gesture has to be
explicit (typed strategy name, TOTP code, prerequisites checklist) — but
the question is whether the LIVE state is effective immediately on
wizard completion or after a delay.

Three candidates:

1. **Immediate** — wizard completes; next bar dispatched can submit live.
2. **Short cooldown** (e.g., 1 hour) — wizard completes; strategy waits
   an hour before live order flow, during which the user can cancel.
3. **Long cooldown** (24 hours) — same as (2), but the window is long
   enough to span a full overnight/next-morning review cycle.

## Decision

**24-hour cooldown.** Strategy transitions PAPER/IDLE → PENDING_LIVE on
wizard completion. A scheduled job 24 hours later transitions
PENDING_LIVE → LIVE. During PENDING_LIVE, no orders flow; the user can
cancel without TOTP at any time.

## Rationale

The choice between immediate and a cooldown turns on what kind of
mistakes the activation gesture is most likely to filter.

- **Cognitive bias of "feeling ready."** Traders complete validation in
  paper and feel ready to go live — but humans systematically underestimate
  how different live execution is from paper. A 24-hour pause means the
  user has a chance to re-encounter the decision in a cooler state. If
  the conviction holds 24 hours later (and the user doesn't cancel), they
  almost certainly meant it.

- **The wizard is fast; the consequences are slow.** The wizard itself
  takes 2-3 minutes. The 24-hour cooldown is ~500x that. The asymmetry
  matches the asymmetry between "easy to start" and "hard to undo a bad
  trading day."

- **The cooldown is not gated by user action.** No "click here to
  activate after 24 hours" — the scheduler flips the bit automatically.
  This avoids the failure mode where the user forgets and the strategy
  sits dormant. The only friction is the wait itself.

- **Cancellation during cooldown is frictionless.** No TOTP, no typed
  confirmation. Reverting to IDLE is always cheap. Activation is the
  expensive action; cancellation is the safe action.

- **Why not 1 hour, why not 7 days.** 1 hour doesn't span the
  overnight/next-morning reset that catches most impulse decisions; the
  user is still in the same "I just completed validation" headspace. 7
  days is too long — by then the market conditions the user validated
  against may have moved enough that they're no longer relevant. 24
  hours is the sweet spot: long enough to cool the impulse, short enough
  to keep the validation context fresh.

## Consequences

**Positive:**
- Filters impulse activations. The user has to want it twice (during
  the wizard AND by not canceling 24 hours later).
- Forces the user to live with the activation decision overnight. Most
  bad calls feel worse the morning after.
- The countdown itself is a useful UX surface — the user can watch
  paper signals during the cooldown and confirm/cancel before live.

**Negative:**
- Genuine "I really want to start now" cases must wait. A trader who
  spotted a tactical opportunity at 9:00 AM and completed the wizard at
  9:15 can't trade it that day. This is the intended friction.
- A bug in the scheduler that fails to transition PENDING_LIVE → LIVE
  leaves the strategy stuck. Defense: structured logs every minute, a
  manual override endpoint is NOT exposed in §7 (P5+ polish if needed).
- 24h is a magic number. A 6-hour cooldown might be enough; 72h might
  be better. We pick 24h because it's the natural unit of trading-day
  context and adjust later if real users demand it.

## Alternatives considered (not chosen)

- **No cooldown, but require TOTP on every live order.** Defeats the
  purpose of activation. The activation gesture IS the explicit step.
- **24-hour cooldown applied per-account, not per-strategy.** Bad UX —
  once one strategy is live, all subsequent strategies on the same
  account skip the cooldown. The cooldown should attach to the
  individual strategy decision.
- **Configurable cooldown duration.** Configurability is a way to defer
  the design call to the user. We make the call: 24h.
- **No cancellation during PENDING_LIVE.** Would force the user to wait
  out a regretted decision. Bad design.

## Implementation notes

- `strategies.live_activation_initiated_at` is the source of truth.
  When set and status=PENDING_LIVE, the strategy is in cooldown.
- The transition PENDING_LIVE → LIVE happens via APScheduler job
  `activation_completion`, running every 60s. The job is idempotent —
  if the backend was down when 24h elapsed, the first run after restart
  completes the transition.
- Cancellation is permitted at any time during PENDING_LIVE. It clears
  `live_activation_initiated_at` and sets status=IDLE. Audit-logged with
  STRATEGY_ACTIVATION_CANCELED.
- After completion (status=LIVE), `live_activation_initiated_at` is
  retained for forensic / "when did this go live" queries.
```

- [ ] ADR 0005 committed.

---

## §7.2 — Schema Changes

Three changes: new `StrategyStatus` enum value, new column on `strategies`, new audit actions.

### 7.2.1 — `StrategyStatus.PENDING_LIVE`

Edit `apps/backend/app/db/enums.py`:

```python
class StrategyStatus(str, Enum):
    IDLE = "idle"
    PAPER = "paper"
    PENDING_LIVE = "pending_live"     # NEW in P5 §7
    LIVE = "live"
    ERROR = "error"
    HALTED = "halted"
```

> **Important**: `ACTIVE_STRATEGY_STATUSES` should NOT include PENDING_LIVE (it can't submit orders). Verify:
> ```python
> ACTIVE_STRATEGY_STATUSES = frozenset([
>     StrategyStatus.PAPER, StrategyStatus.LIVE,
> ])    # PENDING_LIVE, IDLE, HALTED, ERROR all inactive
> ```

### 7.2.2 — `strategies.live_activation_initiated_at`

Edit `apps/backend/app/db/models/strategy.py`:

```python
# When the activation wizard completed (status: IDLE/PAPER → PENDING_LIVE).
# The scheduler watches this column to flip PENDING_LIVE → LIVE after 24h.
# Retained after LIVE transition for forensic queries.
live_activation_initiated_at: Mapped[datetime | None] = mapped_column(
    DateTime(timezone=True), nullable=True,
)
```

### 7.2.3 — Audit Actions

Edit `apps/backend/app/db/enums.py`:

```python
class AuditAction(str, Enum):
    # ... existing ...
    STRATEGY_ACTIVATION_INITIATED = "strategy_activation_initiated"
    STRATEGY_ACTIVATION_CANCELED = "strategy_activation_canceled"
    STRATEGY_LIVE_ACTIVATED = "strategy_live_activated"
    STRATEGY_DEACTIVATED = "strategy_deactivated"
    LIVE_ACCOUNT_CREATED = "live_account_created"
```

### 7.2.4 — Migration

```bash
cd apps/backend
.\.venv\Scripts\python.exe -m alembic revision --autogenerate -m "P5: live_activation_initiated_at + PENDING_LIVE"
```

Verify the migration adds the column. PENDING_LIVE is a string enum value — no DDL needed (the `status` column is a generic String, not a native enum).

```python
def upgrade():
    op.add_column("strategies", sa.Column(
        "live_activation_initiated_at",
        sa.DateTime(timezone=True), nullable=True,
    ))


def downgrade():
    with op.batch_alter_table("strategies") as batch:
        batch.drop_column("live_activation_initiated_at")
```

```powershell
cd apps\backend
.\.venv\Scripts\python.exe -m alembic upgrade head

# Verify the new column exists
.\.venv\Scripts\python.exe -c "import sqlite3; c=sqlite3.connect(r'data\workbench.sqlite'); cols=[r[1] for r in c.execute('PRAGMA table_info(strategies)').fetchall()]; print('live_activation_initiated_at' in cols)"
# Expect: True

# Round-trip
.\.venv\Scripts\python.exe -m alembic downgrade -1
.\.venv\Scripts\python.exe -m alembic upgrade head
cd ..\..
```

- [ ] PENDING_LIVE in enum.
- [ ] Column added; round-trips.
- [ ] Five new audit actions.

---

## §7.3 — `ActivationService` — Prerequisites Check

Create `apps/backend/app/services/activation.py`:

```python
"""ActivationService: orchestrates the paper → live transition.

State machine (see ADR 0005):
  IDLE         ─── initiate ──►  PENDING_LIVE
  PAPER        ─── initiate ──►  PENDING_LIVE
  PENDING_LIVE ─── cancel ────►  IDLE
  PENDING_LIVE ─── (24h) ─────►  LIVE   (via scheduler)
  LIVE         ─── deactivate ►  IDLE   (with optional liquidation)

The five prerequisites for initiate:
  1. Live broker credentials configured
  2. TOTP enrolled
  3. Backtest run in the last 7 days
  4. LIVE risk limits configured
  5. No active circuit breaker on the strategy's account

Initiate requires TOTP code re-entry + typed strategy name. Cancellation
during PENDING_LIVE requires nothing beyond authentication (frictionless
escape hatch).
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any, Optional

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.enums import (
    AuditAction, AuditActorType, AccountMode, OrderSide, OrderSourceType,
    OrderType, RiskScopeType, StrategyStatus, TimeInForce,
)
from app.db.models.account import Account
from app.db.models.backtest import Backtest
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.audit.logger import AuditLogger
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
    initiated_at: Optional[datetime]
    completes_at: Optional[datetime]      # initiated_at + 24h, if PENDING_LIVE
    seconds_remaining: int                 # 0 if not in cooldown


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

    # ============================================================
    # Read-side: prerequisites + status
    # ============================================================

    async def _resolve_strategy_account(
        self, strategy: Strategy, mode: AccountMode,
    ) -> Optional[Account]:
        """Resolve the account this strategy uses for the given mode.

        Session 5 Results documented: `strategies` has no `account_id` FK.
        The mapping is via `strategy.user_id` + the desired mode (a user
        has at most one Alpaca paper account and at most one Alpaca live
        account in the MVP single-broker shape). Returns None if no
        account exists for that mode (e.g., no LIVE account yet).
        """
        result = await self._session.execute(
            select(Account)
            .where(Account.user_id == strategy.user_id)
            .where(Account.mode == mode)
        )
        return result.scalars().first()

    async def check_prerequisites(
        self, strategy_id: int,
    ) -> list[Prerequisite]:
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        # Activation is paper→live. "The strategy's account" for prereq
        # purposes is the user's LIVE account.
        account = await self._resolve_strategy_account(strategy, AccountMode.live)
        # account may be None if the user hasn't created a LIVE account yet;
        # that case is captured in the "live_account_exists" prereq below
        # rather than raising here.

        store = CredentialStore(self._session)
        prereqs: list[Prerequisite] = []

        # 0. LIVE account exists (NEW prereq surfaced by Session 5 mapping)
        prereqs.append(Prerequisite(
            name="live_account_exists",
            satisfied=account is not None,
            detail=(
                "Create a LIVE account via Settings → Accounts before activating."
                if account is None else
                f"LIVE account {account.id} configured."
            ),
        ))

        # 1. Live broker credentials
        live_key = await store.get(strategy.user_id, CredentialKind.ALPACA_LIVE_KEY)
        live_secret = await store.get(strategy.user_id, CredentialKind.ALPACA_LIVE_SECRET)
        prereqs.append(Prerequisite(
            name="live_broker_credentials",
            satisfied=bool(live_key and live_secret),
            detail=(
                "Set via Settings → Credentials → Alpaca Live API Key/Secret"
                if not (live_key and live_secret) else
                "Configured."
            ),
        ))

        # 2. TOTP enrolled
        user = await self._session.get(User, strategy.user_id)
        totp_ok = user is not None and user.totp_verified_at is not None
        prereqs.append(Prerequisite(
            name="totp_enrolled",
            satisfied=totp_ok,
            detail=(
                "TOTP not enrolled. Run scripts/create_user.sh or enroll via /auth/totp/setup."
                if not totp_ok else
                f"Enrolled at {user.totp_verified_at.isoformat()}"
            ),
        ))

        # 3. Recent backtest
        cutoff = datetime.now(timezone.utc) - timedelta(days=RECENT_BACKTEST_WINDOW_DAYS)
        recent_backtest = (await self._session.execute(
            select(Backtest)
            .where(Backtest.strategy_id == strategy_id)
            .where(Backtest.created_at >= cutoff)
            .order_by(Backtest.created_at.desc())
            .limit(1)
        )).scalars().first()
        prereqs.append(Prerequisite(
            name="recent_backtest",
            satisfied=recent_backtest is not None,
            detail=(
                f"Run a backtest on this strategy "
                f"(none in last {RECENT_BACKTEST_WINDOW_DAYS} days)."
                if recent_backtest is None else
                f"Last run: {recent_backtest.created_at.isoformat()}"
            ),
        ))

        # 4. LIVE risk limits
        live_limits = (await self._session.execute(
            select(RiskLimits)
            .where(RiskLimits.user_id == strategy.user_id)
            .where(RiskLimits.broker_mode == AccountMode.live)
            .where(RiskLimits.scope_type == RiskScopeType.GLOBAL)
        )).scalars().first()
        prereqs.append(Prerequisite(
            name="live_risk_limits",
            satisfied=live_limits is not None,
            detail=(
                "Configure via Settings → Risk Limits → LIVE."
                if live_limits is None else
                f"Configured (max_daily_loss=${live_limits.max_daily_loss})."
            ),
        ))

        # 5. Circuit breaker OK on the account
        # If no LIVE account exists yet, the breaker prereq is trivially
        # "OK" — the live_account_exists prereq above already failed and
        # surfaces the real blocker. SQLite naive-datetime coercion via
        # ensure_aware (Session 5 §5.0).
        if account is None:
            breaker_ok = True
            breaker_detail = "Pending LIVE account creation."
        else:
            tripped_at = ensure_aware(account.circuit_breaker_tripped_at)
            breaker_ok = tripped_at is None
            breaker_detail = (
                f"Circuit breaker tripped at {tripped_at.isoformat()}. "
                f"Reset before activating."
                if not breaker_ok else
                "No active trip."
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
        completes_at: Optional[datetime] = None
        seconds_remaining = 0
        # SQLite naive-datetime coercion (Session 5 §5.0)
        initiated_at = ensure_aware(strategy.live_activation_initiated_at)
        if (
            strategy.status == StrategyStatus.PENDING_LIVE
            and initiated_at is not None
        ):
            completes_at = initiated_at + timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
            now = datetime.now(timezone.utc)
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
```

> Five prerequisites is a deliberate ceiling. Each one is something the user can *fix* directly (set credentials, enroll TOTP, run a backtest, configure risk, reset breaker). We deliberately don't gate on "recent paper-trading PnL > 0" or "Sharpe ratio > 1.0" or other quality signals — those are the user's call.

- [ ] `Prerequisite`, `ActivationStatus` dataclasses.
- [ ] `check_prerequisites` returns 5-item list.
- [ ] `status` computes remaining cooldown seconds.

---

## §7.4 — `ActivationService` — Write-Side

Continue `apps/backend/app/services/activation.py`:

```python
    # ============================================================
    # Write-side: initiate / cancel / complete / deactivate
    # ============================================================

    async def initiate(
        self,
        *,
        strategy_id: int,
        user_id: int,
        confirmation_name: str,
        totp_code: str,
    ) -> ActivationStatus:
        """Wizard completion. Verifies all prerequisites + TOTP + name match.
        Sets status=PENDING_LIVE and starts the 24h cooldown."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}",
            )
        if strategy.status not in (StrategyStatus.IDLE, StrategyStatus.PAPER):
            raise ActivationError(
                f"Cannot activate strategy in status {strategy.status.value}. "
                f"Required: IDLE or PAPER."
            )

        # Confirmation name (case-sensitive — names are case-significant)
        if confirmation_name != strategy.name:
            raise ActivationError(
                f"Confirmation name does not match strategy name. "
                f"Expected '{strategy.name}'."
            )

        # TOTP re-verification (defense against session hijack)
        from app.auth.totp import verify_code
        store = CredentialStore(self._session)
        totp_secret = await store.get(user_id, CredentialKind.TOTP_SECRET)
        if totp_secret is None or not verify_code(totp_secret, totp_code):
            raise ActivationError("Invalid TOTP code.")

        # Re-check all prerequisites at the last moment
        prereqs = await self.check_prerequisites(strategy_id)
        unsatisfied = [p for p in prereqs if not p.satisfied]
        if unsatisfied:
            raise ActivationError(
                f"Prerequisites not satisfied: "
                f"{', '.join(p.name for p in unsatisfied)}"
            )

        now = datetime.now(timezone.utc)
        strategy.status = StrategyStatus.PENDING_LIVE
        strategy.live_activation_initiated_at = now

        # Resolve the LIVE account for the audit payload (no strategy.account_id;
        # see drift item #6 in "Updated in v0.2"). The prereq check above
        # already verified the LIVE account exists, so this is safe.
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

    async def cancel(
        self,
        *,
        strategy_id: int,
        user_id: int,
    ) -> None:
        """Cancel pending activation. Always permitted during PENDING_LIVE.
        No TOTP required — cancellation is the safe direction."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}",
            )
        if strategy.status != StrategyStatus.PENDING_LIVE:
            raise ActivationError(
                f"Cannot cancel — strategy is in status {strategy.status.value}, "
                f"not PENDING_LIVE."
            )

        prior_initiated_at = strategy.live_activation_initiated_at
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
                "prior_initiated_at": (
                    prior_initiated_at.isoformat() if prior_initiated_at else None
                ),
            },
            user_id=user_id,
        )
        await self._session.commit()

        logger.info("strategy_activation_canceled",
                    strategy_id=strategy_id, user_id=user_id)

    async def complete_pending(self, strategy_id: int) -> bool:
        """Called by the scheduler. Transitions PENDING_LIVE → LIVE if
        24h has elapsed. Returns True if transition happened.

        Idempotent: if the strategy is no longer PENDING_LIVE (canceled,
        already LIVE), returns False without changes."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            return False
        if strategy.status != StrategyStatus.PENDING_LIVE:
            return False
        if strategy.live_activation_initiated_at is None:
            # Inconsistent state — log and reset
            logger.error(
                "complete_pending_missing_initiated_at",
                strategy_id=strategy_id,
            )
            strategy.status = StrategyStatus.IDLE
            await self._session.commit()
            return False

        now = datetime.now(timezone.utc)
        # SQLite naive-datetime coercion (Session 5 §5.0) — without this,
        # the scheduler can appear to never complete pending activations
        initiated_at = ensure_aware(strategy.live_activation_initiated_at)
        elapsed = now - initiated_at
        if elapsed < timedelta(hours=ACTIVATION_COOLDOWN_HOURS):
            return False

        strategy.status = StrategyStatus.LIVE

        # Resolve the LIVE account for the audit payload (no strategy.account_id)
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
                await self._bus.publish("strategy.live_activated", {
                    "strategy_id": strategy_id,
                    "activated_at": now.isoformat(),
                })
            except Exception:
                logger.exception("strategy_live_activated_publish_failed")

        logger.info("strategy_live_activated",
                    strategy_id=strategy_id, user_id=strategy.user_id)
        return True

    async def deactivate(
        self,
        *,
        strategy_id: int,
        user_id: int,
        liquidate: bool,
    ) -> dict[str, Any]:
        """Deactivate a LIVE strategy. Always immediate (no cooldown — you
        can always stop trading). If liquidate=True, enqueues market-order
        closes for every open position on the strategy's account where
        the symbol matches the strategy's symbols_json.

        Returns a summary dict with the deactivation actions taken."""
        strategy = await self._session.get(Strategy, strategy_id)
        if strategy is None:
            raise ActivationError(f"Strategy {strategy_id} not found")
        if strategy.user_id != user_id:
            raise PermissionError(
                f"Strategy {strategy_id} does not belong to user {user_id}",
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

        logger.info("strategy_deactivated",
                    strategy_id=strategy_id, liquidate=liquidate,
                    liquidation_count=len(liquidation_orders))

        return {
            "strategy_id": strategy_id,
            "new_status": StrategyStatus.IDLE.value,
            "liquidation_orders": liquidation_orders,
        }

    async def _enqueue_liquidation(self, strategy: Strategy) -> list[int]:
        """For each open position on the strategy's account where the
        symbol is in strategy.symbols_json, submit a market sell (for long)
        or market buy (for short) to close at market.

        Notes:
        - Submits via the OrderRouter, which means the orders go through
          the §6 cooldown / §5 risk gates / §6 audit just like any other
          STRATEGY-sourced order. Liquidation is not a special bypass path.
        - If the broker is unreachable, returns the empty list and logs.
          The user must then manually liquidate; we don't retry.
        """
        if self._broker_registry is None or self._order_router is None:
            logger.warning("liquidation_no_broker_or_router",
                           strategy_id=strategy.id)
            return []
        # Resolve the LIVE account (no strategy.account_id; see drift item #6)
        live_account = await self._resolve_strategy_account(strategy, AccountMode.live)
        if live_account is None:
            logger.warning("liquidation_no_live_account",
                           strategy_id=strategy.id, user_id=strategy.user_id)
            return []
        adapter = self._broker_registry.get(live_account.id)
        if adapter is None:
            logger.warning("liquidation_no_adapter",
                           strategy_id=strategy.id,
                           account_id=live_account.id)
            return []
        try:
            # Sync call (Session 2 v1.0: BrokerAdapter is sync); may return
            # dict[str, Any] or list of dicts/objects depending on adapter
            positions = adapter.get_positions()
        except Exception:
            logger.exception("liquidation_position_fetch_failed",
                             strategy_id=strategy.id)
            return []

        strategy_symbols = set(strategy.symbols_json or [])
        order_ids: list[int] = []
        # NOTE: Session 6 Results documented that the actual router signature
        # is submit(req: OrderRequest) -> Order (no current_user_id kwarg;
        # rejections carry rejection_reason as a string, not reason_code).
        # The submission call below assumes the Session 6 shape; verify
        # against current code and adjust as needed during execution.
        from app.api.v1.schemas.orders import OrderRequest
        for pos in positions:
            symbol = pos.get("symbol") if isinstance(pos, dict) else getattr(pos, "symbol", None)
            qty = pos.get("qty") if isinstance(pos, dict) else getattr(pos, "qty", None)
            if symbol is None or qty is None:
                continue
            if symbol not in strategy_symbols:
                continue
            from decimal import Decimal
            qty_dec = Decimal(str(qty))
            if qty_dec == 0:
                continue
            # Long position → sell; short → buy.
            side = OrderSide.SELL if qty_dec > 0 else OrderSide.BUY
            req = OrderRequest(
                account_id=live_account.id,
                symbol=symbol,
                side=side,
                type=OrderType.MARKET,
                qty=abs(qty_dec),
                tif=TimeInForce.DAY,
                source=OrderSourceType.STRATEGY,
                source_id=str(strategy.id),  # Session 6: strategy_id derived from source_id
            )
            try:
                # Session 6 actual signature: submit(req) -> Order
                order = await self._order_router.submit(req)
                if getattr(order, "id", None):
                    order_ids.append(order.id)
            except Exception:
                logger.exception("liquidation_submit_failed",
                                 strategy_id=strategy.id,
                                 symbol=symbol)
        return order_ids
```

> **Liquidation uses the OrderRouter — not a bypass path.** This is intentional. The §5/§6 gates still apply to liquidation orders. If a strategy is HALTED by the circuit breaker, the liquidation orders ALSO go through risk checks. If the breaker has tripped, the user is expected to reset it before deactivation can liquidate (the prerequisites checklist surfaces this).
>
> **Cancellation has no TOTP.** This is the asymmetry from ADR 0005 — activation is the expensive direction, cancellation is the safe direction. We make cancellation cheap on purpose.

- [ ] `initiate` requires confirmation name + TOTP + all prereqs.
- [ ] `cancel` requires only authentication.
- [ ] `complete_pending` is idempotent.
- [ ] `deactivate` optionally liquidates via OrderRouter.

---

## §7.5 — Lifting the §1 BrokerModeError Guard

Edit `apps/backend/app/orders/router.py`. The §1 guard raised `BrokerModeError` for any LIVE order entirely. §7 replaces it with conditional logic that permits some LIVE flows and rejects others with typed reason codes.

> **Critical integration note (Session 6 Results).** Session 6 reshaped the router internals. The actual call signature is `submit(req: OrderRequest) -> Order` (frozen dataclass in, Order out). Rejections produce an `Order` with `status=REJECTED` and a `rejection_reason` string — they do NOT return early via a `self._reject(...)` helper (no such helper exists). The risk method is `evaluate()` not `check()`. The strategy_id for STRATEGY-sourced orders is derived from `source_id` (string) via Session 6's `_strategy_id_from_source()` helper. Typed reason codes live in `ReasonCode` enum (Session 6 added `CONFIRMATION_REQUIRED`, `CONFIRMATION_MISMATCH`, `STRATEGY_COOLDOWN`).
>
> **Before writing this code:** grep+read `app/orders/router.py` to confirm:
> - The exact shape of `submit()` and any helpers Session 6 added (`_confirmation_reject_reason`, `_strategy_id_from_source`, `_ephemeral_rejected_order_with_reason`, `_maybe_set_cooldown`, `_audit_live_submission`)
> - The current location of the §1 `BrokerModeError` raise (Session 6 confirmed the confirmation check runs BEFORE it)
> - The `ReasonCode` enum's current values — add `AGENT_LIVE_DISABLED`, `STRATEGY_ID_REQUIRED`, `STRATEGY_NOT_FOUND`, `STRATEGY_PENDING_LIVE`, `STRATEGY_NOT_LIVE` to this enum in §7.1's schema work if they're not there yet

Find the existing `BrokerModeError` raise block and replace it with a conditional that produces an ephemeral rejected Order for the disallowed cases, and falls through for the allowed cases. The pattern matches Session 6's `_ephemeral_rejected_order_with_reason`:

```python
# ============================================================
# P5 §1 (lifted in §7): the unconditional BrokerModeError raise
# is REPLACED by the conditional logic below.
# ============================================================
# Session 6 ordering recap: by the time execution reaches this block,
# the §6 confirmation_text gate (MANUAL+LIVE) has already passed.
# What we still need to check, in order:
#   (a) Agent-sourced LIVE orders are refused entirely (P6 territory)
#   (b) Strategy-sourced LIVE orders require strategy.status==LIVE
#   (c) Manual+LIVE is permitted (confirmation gate already enforced)

if account.mode == AccountMode.live:
    # (a) AGENT
    if req.source == OrderSourceType.AGENT_PROPOSAL:
        return self._ephemeral_rejected_order_with_reason(
            req,
            reason=ReasonCode.AGENT_LIVE_DISABLED,
            detail="Agent-sourced orders to LIVE accounts are disabled.",
        )

    # (b) STRATEGY
    if req.source == OrderSourceType.STRATEGY:
        # Session 6 helper: strategy_id derived from source_id (string).
        # Returns None if source_id is empty or not parseable.
        strategy_id = self._strategy_id_from_source(req)
        if strategy_id is None:
            return self._ephemeral_rejected_order_with_reason(
                req,
                reason=ReasonCode.STRATEGY_ID_REQUIRED,
                detail="STRATEGY source requires source_id with a valid strategy id.",
            )
        # Fresh session for the strategy lookup (Session 6 pattern;
        # router doesn't hold a long-lived session)
        async with self._session_factory() as session:
            strategy = await session.get(Strategy, strategy_id)
        if strategy is None:
            return self._ephemeral_rejected_order_with_reason(
                req,
                reason=ReasonCode.STRATEGY_NOT_FOUND,
                detail=f"Strategy {strategy_id} not found.",
            )
        if strategy.status == StrategyStatus.PENDING_LIVE:
            # ensure_aware coercion (Session 5 §5.0) for the timestamp shown
            initiated_at = ensure_aware(strategy.live_activation_initiated_at)
            initiated_str = initiated_at.isoformat() if initiated_at else "unknown"
            return self._ephemeral_rejected_order_with_reason(
                req,
                reason=ReasonCode.STRATEGY_PENDING_LIVE,
                detail=(
                    f"Strategy is in 24-hour activation cooldown "
                    f"(initiated {initiated_str})."
                ),
            )
        if strategy.status != StrategyStatus.LIVE:
            return self._ephemeral_rejected_order_with_reason(
                req,
                reason=ReasonCode.STRATEGY_NOT_LIVE,
                detail=(
                    f"Strategy status={strategy.status.value}; "
                    f"must be LIVE to submit live orders."
                ),
            )

    # (c) MANUAL+LIVE: permitted; §6 confirmation gate above already enforced.
    # Fall through to RiskEngine.evaluate() (the existing post-guard path).
```

The previous `raise BrokerModeError(...)` line is removed. The `BrokerModeError` *class* may still be kept in the codebase for backward compatibility but is no longer raised by the router.

> **`_router_token` discipline preserved.** This change adds new pre-flight rejections (which return Orders, not call adapters) and removes a raise. Adapter mutators (`submit_order`/`cancel_order`/`replace_order`) are still only called from inside `OrderRouter.submit()` with the token. `tests/test_adr_0002_invariant.py` stays green; no edit needed.

> **Order of checks recap (now finalized):**
> 1. Pre-flight validation (existing).
> 2. Manual+LIVE confirmation_text check (§6; produces REJECTED Order if absent/wrong).
> 3. Strategy cooldown check (§6; produces REJECTED Order with `STRATEGY_COOLDOWN` if active).
> 4. **§7 conditional guard (this section): AGENT_LIVE_DISABLED / STRATEGY_ID_REQUIRED / STRATEGY_NOT_FOUND / STRATEGY_PENDING_LIVE / STRATEGY_NOT_LIVE → REJECTED Order.**
> 5. Risk engine: `RiskEngine.evaluate()` — circuit breaker + per-day cap + buying power (§5; produces REJECTED Order).
> 6. Broker adapter `submit_order` via `_router_token` (Session 2 + 5 path).
> 7. `_maybe_set_cooldown` (§6).
> 8. `_audit_live_submission` (§6 — LIVE_ORDER_SUBMITTED on every reachable LIVE attempt; some paths are still unreachable in §6 due to the §1 guard; §7's removal opens them).

After the change, the §6 `LIVE_ORDER_SUBMITTED` audit now fires on the post-risk/broker paths too (§7 opens them). Verify in the §7.10 tests that an end-to-end LIVE order produces the audit row.

The §6 LiveOrderConfirmModal frontend component (shipped in §6 but not wired into the Order Ticket because manual LIVE wasn't reachable) is wired into the Order Ticket in §7.9.

- [ ] §1 `BrokerModeError` raise replaced with conditional `_ephemeral_rejected_order_with_reason` returns.
- [ ] `ReasonCode` enum extended with the five new values.
- [ ] `tests/test_adr_0002_invariant.py` still passes (`_router_token` discipline preserved).
- [ ] An end-to-end LIVE order now produces `LIVE_ORDER_SUBMITTED` audit.

---

## §7.6 — `POST /api/v1/accounts` Accepts LIVE

Edit `apps/backend/app/api/v1/accounts.py`. The §1 endpoint refused LIVE creation. Replace with TOTP-gated permit:

```python
class CreateAccountRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    broker: str = Field(default="alpaca")
    mode: BrokerMode
    label: str = Field(min_length=1, max_length=64)
    # NEW in P5 §7: required for mode=live. Re-verified server-side
    # against the user's TOTP secret.
    totp_code: Optional[str] = Field(default=None)


@router.post("", response_model=AccountResponse)
async def create_account(
    body: CreateAccountRequest,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    if body.mode == AccountMode.live:
        if not body.totp_code:
            raise HTTPException(
                status_code=400,
                detail="totp_code is required for LIVE account creation.",
            )
        from app.auth.totp import verify_code
        store = CredentialStore(session)
        totp_secret = await store.get(current_user.id, CredentialKind.TOTP_SECRET)
        if totp_secret is None or not verify_code(totp_secret, body.totp_code):
            raise HTTPException(status_code=401, detail="Invalid TOTP code.")

    account = Account(
        user_id=current_user.id,
        broker=body.broker,
        mode=body.mode,
        label=body.label,
        created_at=datetime.now(timezone.utc),
    )
    session.add(account)
    await session.commit()
    await session.refresh(account)

    if body.mode == AccountMode.live:
        AuditLogger.write(
            session,
            actor_type=AuditActorType.USER,
            actor_id=str(current_user.id),
            action=AuditAction.LIVE_ACCOUNT_CREATED,
            target_type="account",
            target_id=account.id,
            payload={
                "broker": body.broker,
                "label": body.label,
            },
            user_id=current_user.id,
        )
        await session.commit()

    # Refresh BrokerRegistry so the new account is loaded
    # (P5 §2's refresh() method).
    from app.brokers.registry import BrokerRegistry   # via app state
    broker_registry = ...    # injected via Request.app.state
    # ... refresh handled by lifespan startup or explicit call ...

    return AccountResponse.model_validate(account, from_attributes=True)
```

> The TOTP requirement on LIVE account creation is a small cost (the user already has a TOTP code from login) and it materially raises the bar against "someone with the session cookie creates a live account and submits an order before I notice." Layered defense.

- [ ] Endpoint accepts `mode=live` with TOTP.
- [ ] LIVE_ACCOUNT_CREATED audit on success.
- [ ] BrokerRegistry refreshed on create (per §2's `refresh()` method).

---

## §7.7 — Activation Endpoints

Create `apps/backend/app/api/v1/activation.py`:

```python
"""Activation lifecycle endpoints under /api/v1/strategies/{id}/."""
from __future__ import annotations

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.stub import CurrentUser, get_current_user
from app.db.session import get_session
from app.services.activation import (
    ActivationError, ActivationService,
)


router = APIRouter(prefix="/strategies", tags=["activation"])


class PrerequisiteResponse(BaseModel):
    name: str
    satisfied: bool
    detail: str


class ActivationStatusResponse(BaseModel):
    strategy_id: int
    status: str
    prerequisites: list[PrerequisiteResponse]
    all_satisfied: bool
    initiated_at: Optional[datetime]
    completes_at: Optional[datetime]
    seconds_remaining: int


class ActivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    confirmation_name: str = Field(min_length=1, max_length=128)
    totp_code: str = Field(min_length=6, max_length=8)


class DeactivateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    liquidate: bool = False


@router.get("/{strategy_id}/activation", response_model=ActivationStatusResponse)
async def activation_status(
    strategy_id: int,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    from app.db.models.strategy import Strategy
    strategy = await session.get(Strategy, strategy_id)
    if strategy is None or strategy.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Strategy not found")
    svc = ActivationService(session=session)
    status = await svc.status(strategy_id)
    return ActivationStatusResponse(
        strategy_id=status.strategy_id,
        status=status.status.value,
        prerequisites=[
            PrerequisiteResponse(name=p.name, satisfied=p.satisfied, detail=p.detail)
            for p in status.prerequisites
        ],
        all_satisfied=status.all_satisfied,
        initiated_at=status.initiated_at,
        completes_at=status.completes_at,
        seconds_remaining=status.seconds_remaining,
    )


@router.post("/{strategy_id}/activate", response_model=ActivationStatusResponse)
async def activate_strategy(
    strategy_id: int,
    body: ActivateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = ActivationService(session=session)
    try:
        result = await svc.initiate(
            strategy_id=strategy_id,
            user_id=current_user.id,
            confirmation_name=body.confirmation_name,
            totp_code=body.totp_code,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found")
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return ActivationStatusResponse(
        strategy_id=result.strategy_id,
        status=result.status.value,
        prerequisites=[
            PrerequisiteResponse(name=p.name, satisfied=p.satisfied, detail=p.detail)
            for p in result.prerequisites
        ],
        all_satisfied=result.all_satisfied,
        initiated_at=result.initiated_at,
        completes_at=result.completes_at,
        seconds_remaining=result.seconds_remaining,
    )


@router.post("/{strategy_id}/activate/cancel")
async def cancel_activation(
    strategy_id: int,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    svc = ActivationService(session=session)
    try:
        await svc.cancel(strategy_id=strategy_id, user_id=current_user.id)
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found")
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"ok": True, "strategy_id": strategy_id}


@router.post("/{strategy_id}/deactivate")
async def deactivate_strategy(
    strategy_id: int,
    body: DeactivateRequest,
    request: Request,
    current_user: CurrentUser = Depends(get_current_user),
    session: AsyncSession = Depends(get_session),
):
    broker_registry = getattr(request.app.state, "broker_registry", None)
    order_router = getattr(request.app.state, "order_router", None)
    svc = ActivationService(
        session=session,
        broker_registry=broker_registry,
        order_router=order_router,
    )
    try:
        result = await svc.deactivate(
            strategy_id=strategy_id,
            user_id=current_user.id,
            liquidate=body.liquidate,
        )
    except PermissionError:
        raise HTTPException(status_code=404, detail="Strategy not found")
    except ActivationError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return result
```

Mount in `apps/backend/app/main.py`:

```python
from app.api.v1 import activation as activation_router
app.include_router(activation_router.router, prefix="/api/v1")
```

- [ ] GET status, POST activate, POST cancel, POST deactivate.
- [ ] Activate requires confirmation_name + totp_code.
- [ ] Cancel requires only auth.
- [ ] Deactivate accepts liquidate flag.

---

## §7.8 — Background Scheduler Job

Create `apps/backend/app/jobs/activation_completion.py`:

```python
"""Background job: complete PENDING_LIVE → LIVE transitions after 24h.

Runs every 60s. Idempotent: if the backend was down when the 24h mark
elapsed, the first run after restart catches it up.

The job processes ALL eligible strategies in one pass. Even if 100
strategies all transition at the same minute, the work is bounded —
each transition is one row update + one audit row.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

import structlog
from sqlalchemy import select

from app.db.enums import StrategyStatus
from app.db.models.strategy import Strategy
from app.services.activation import (
    ACTIVATION_COOLDOWN_HOURS, ActivationService,
)


logger = structlog.get_logger(__name__)


async def run_activation_completion(session_factory, bus=None) -> int:
    """Find PENDING_LIVE strategies whose 24h has elapsed; transition each.
    Returns the count of transitions performed."""
    cutoff = datetime.now(timezone.utc) - timedelta(hours=ACTIVATION_COOLDOWN_HOURS)
    async with session_factory() as session:
        eligible = (await session.execute(
            select(Strategy.id)
            .where(Strategy.status == StrategyStatus.PENDING_LIVE)
            .where(Strategy.live_activation_initiated_at.isnot(None))
            .where(Strategy.live_activation_initiated_at <= cutoff)
        )).scalars().all()

    transitioned = 0
    for strategy_id in eligible:
        async with session_factory() as session:
            svc = ActivationService(session=session, bus=bus)
            try:
                if await svc.complete_pending(strategy_id):
                    transitioned += 1
            except Exception:
                logger.exception(
                    "activation_completion_failed",
                    strategy_id=strategy_id,
                )

    if transitioned:
        logger.info("activation_completion_pass", transitioned=transitioned)
    return transitioned
```

Wire into the scheduler. Edit `apps/backend/app/lifespan.py`:

```python
from app.jobs.activation_completion import run_activation_completion


# Inside the lifespan startup, after the scheduler is started:
scheduler.add_job(
    lambda: run_activation_completion(
        session_factory=app.state.session_factory,
        bus=app.state.event_bus,
    ),
    trigger="interval", seconds=60,
    id="activation_completion",
    max_instances=1,    # don't pile up if a run takes >60s
    coalesce=True,
)
logger.info("activation_completion_scheduled")
```

> **Why 60-second polling, not event-driven?** The PENDING_LIVE → LIVE transition is naturally batched. A user activating at 09:00 expects to be LIVE at 09:00 the next day, ±1 minute. Event-driven would require a per-strategy timer; polling is simpler and the latency is acceptable.

- [ ] Job created at `app/jobs/activation_completion.py`.
- [ ] Wired into APScheduler in `lifespan.py`.
- [ ] `max_instances=1, coalesce=True` prevents pile-up.

---

## §7.9 — Frontend: Activation Wizard

The wizard is a 4-step modal. For brevity, here's the top-level component skeleton; the four step components are mechanical.

Create `apps/frontend/src/components/activation/ActivationWizard.tsx`:

```tsx
import { useEffect, useState } from "react";
import { activationApi } from "@/api/activation";
import { PrerequisitesStep } from "./steps/PrerequisitesStep";
import { ReviewStrategyStep } from "./steps/ReviewStrategyStep";
import { ReviewRiskStep } from "./steps/ReviewRiskStep";
import { ConfirmStep } from "./steps/ConfirmStep";
import type { ActivationStatus } from "@/api/activation";


interface Props {
  strategyId: number;
  strategyName: string;
  onClose: () => void;
  onActivated: () => void;
}


type Step = "prerequisites" | "review_strategy" | "review_risk" | "confirm";


export function ActivationWizard({ strategyId, strategyName, onClose, onActivated }: Props) {
  const [step, setStep] = useState<Step>("prerequisites");
  const [status, setStatus] = useState<ActivationStatus | null>(null);

  useEffect(() => {
    activationApi.status(strategyId).then(setStatus).catch(() => {});
  }, [strategyId]);

  if (!status) {
    return (
      <ModalShell onClose={onClose}>
        <div className="text-gray-300">Loading prerequisites…</div>
      </ModalShell>
    );
  }

  return (
    <ModalShell onClose={onClose}>
      <Header strategyName={strategyName} step={step} />
      <StepBody>
        {step === "prerequisites" && (
          <PrerequisitesStep
            status={status}
            onNext={() => setStep("review_strategy")}
            onCancel={onClose}
          />
        )}
        {step === "review_strategy" && (
          <ReviewStrategyStep
            strategyId={strategyId}
            onBack={() => setStep("prerequisites")}
            onNext={() => setStep("review_risk")}
          />
        )}
        {step === "review_risk" && (
          <ReviewRiskStep
            strategyId={strategyId}
            onBack={() => setStep("review_strategy")}
            onNext={() => setStep("confirm")}
          />
        )}
        {step === "confirm" && (
          <ConfirmStep
            strategyName={strategyName}
            strategyId={strategyId}
            onBack={() => setStep("review_risk")}
            onActivated={onActivated}
          />
        )}
      </StepBody>
    </ModalShell>
  );
}


function ModalShell({ children, onClose }: { children: any; onClose: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-[36rem] space-y-4 rounded-lg border-2 border-red-700 bg-gray-950 p-6">
        {children}
      </div>
    </div>
  );
}


function Header({ strategyName, step }: { strategyName: string; step: Step }) {
  const stepLabels: Record<Step, string> = {
    prerequisites: "1. Prerequisites",
    review_strategy: "2. Review strategy",
    review_risk: "3. Review risk limits",
    confirm: "4. Confirm activation",
  };
  return (
    <div>
      <div className="flex items-center gap-2">
        <span className="rounded bg-red-700 px-2 py-0.5 text-[10px] font-bold text-white">LIVE</span>
        <h2 className="text-lg font-semibold text-red-100">
          Activate <code className="font-mono">{strategyName}</code> for live trading
        </h2>
      </div>
      <div className="mt-2 text-xs text-gray-400">{stepLabels[step]}</div>
    </div>
  );
}


function StepBody({ children }: { children: any }) {
  return <div className="space-y-3">{children}</div>;
}
```

The four step components (sketched):

- **`PrerequisitesStep`** — renders the `status.prerequisites` array as a checklist. Green check if `satisfied`, red X otherwise. "Next" button disabled until `all_satisfied`. Each unsatisfied row shows the `detail` text and (where applicable) a deep link to fix it (e.g., "Set credentials →" jumps to Settings → Credentials).

- **`ReviewStrategyStep`** — renders the strategy's name, code path (or first 50 lines of code), params, symbols, last backtest summary. Read-only confirmation that "this is the strategy I'm activating." Back / Next buttons.

- **`ReviewRiskStep`** — renders the LIVE-scoped `risk_limits` row. Editable: max_position_qty, max_position_notional, max_gross_exposure, max_daily_loss, max_orders_per_day. Save calls `riskApi.updateLimits`. Back / Next buttons.

- **`ConfirmStep`** — typed strategy-name input + TOTP code input. Submit calls `activationApi.activate(strategyId, { confirmation_name, totp_code })`. On success, calls `onActivated()`. Shows a banner: "Strategy will go LIVE in 24 hours. You can cancel anytime during the cooldown."

Create `apps/frontend/src/api/activation.ts`:

```typescript
import { apiFetch } from "./client";


export interface Prerequisite {
  name: string;
  satisfied: boolean;
  detail: string;
}


export interface ActivationStatus {
  strategy_id: number;
  status: string;
  prerequisites: Prerequisite[];
  all_satisfied: boolean;
  initiated_at: string | null;
  completes_at: string | null;
  seconds_remaining: number;
}


export const activationApi = {
  status: (strategyId: number) =>
    apiFetch<ActivationStatus>(`/api/v1/strategies/${strategyId}/activation`),
  activate: (strategyId: number, body: { confirmation_name: string; totp_code: string }) =>
    apiFetch<ActivationStatus>(`/api/v1/strategies/${strategyId}/activate`, {
      method: "POST", body,
    }),
  cancelActivation: (strategyId: number) =>
    apiFetch<{ ok: boolean }>(`/api/v1/strategies/${strategyId}/activate/cancel`, {
      method: "POST",
    }),
  deactivate: (strategyId: number, liquidate: boolean) =>
    apiFetch<{ strategy_id: number; new_status: string; liquidation_orders: number[] }>(
      `/api/v1/strategies/${strategyId}/deactivate`,
      { method: "POST", body: { liquidate } },
    ),
};
```

Also create `ActivationCountdown.tsx` (shown on the strategy detail page when status=PENDING_LIVE):

```tsx
import { useEffect, useState } from "react";
import { activationApi } from "@/api/activation";


export function ActivationCountdown({ strategyId }: { strategyId: number }) {
  const [status, setStatus] = useState<{
    seconds_remaining: number; completes_at: string | null;
  } | null>(null);
  const [canceling, setCanceling] = useState(false);

  useEffect(() => {
    let cancelled = false;
    async function refresh() {
      try {
        const s = await activationApi.status(strategyId);
        if (!cancelled) setStatus(s);
      } catch { /* silent */ }
    }
    refresh();
    const id = setInterval(refresh, 30_000);    // every 30s — countdown is in hours, not seconds
    return () => { cancelled = true; clearInterval(id); };
  }, [strategyId]);

  async function handleCancel() {
    if (!confirm("Cancel activation? Strategy returns to IDLE.")) return;
    setCanceling(true);
    try {
      await activationApi.cancelActivation(strategyId);
      window.location.reload();
    } finally {
      setCanceling(false);
    }
  }

  if (!status || status.seconds_remaining === 0) return null;

  const hours = Math.floor(status.seconds_remaining / 3600);
  const minutes = Math.floor((status.seconds_remaining % 3600) / 60);

  return (
    <div className="rounded border-2 border-amber-700 bg-amber-950/40 p-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="text-sm font-semibold text-amber-100">
            ⏳ Activation pending — {hours}h {minutes}m remaining
          </div>
          <div className="mt-1 text-[10px] text-amber-300">
            Goes LIVE at {status.completes_at && new Date(status.completes_at).toLocaleString()}.
            Cancel anytime before then.
          </div>
        </div>
        <button
          onClick={handleCancel}
          disabled={canceling}
          className="rounded border border-amber-700 px-3 py-1.5 text-xs text-amber-100 hover:bg-amber-900/30"
        >
          {canceling ? "Canceling…" : "Cancel"}
        </button>
      </div>
    </div>
  );
}
```

Also `DeactivationModal.tsx` for the LIVE → IDLE transition with optional liquidation:

```tsx
export function DeactivationModal({ strategyId, strategyName, onClose, onDeactivated }: {
  strategyId: number; strategyName: string;
  onClose: () => void; onDeactivated: () => void;
}) {
  const [liquidate, setLiquidate] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  async function handleDeactivate() {
    setSubmitting(true);
    try {
      const result = await activationApi.deactivate(strategyId, liquidate);
      onDeactivated();
      if (result.liquidation_orders.length > 0) {
        alert(`Deactivated. ${result.liquidation_orders.length} liquidation orders submitted.`);
      }
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/80">
      <div className="w-96 space-y-3 rounded-lg border-2 border-amber-700 bg-gray-950 p-5">
        <h2 className="text-lg font-semibold text-amber-100">Deactivate strategy</h2>
        <p className="text-sm text-gray-300">
          <code className="font-mono">{strategyName}</code> will transition LIVE → IDLE
          and stop submitting orders.
        </p>
        <label className="flex items-center gap-2 text-sm text-amber-200">
          <input type="checkbox" checked={liquidate}
                 onChange={(e) => setLiquidate(e.target.checked)} />
          Also liquidate open positions in this strategy's symbols
        </label>
        <p className="text-[10px] text-amber-300">
          {liquidate ? (
            "Closing market orders will be submitted for each open position. " +
            "Submissions go through the normal risk gates."
          ) : (
            "Open positions stay open. Close manually if needed."
          )}
        </p>
        <div className="flex justify-end gap-2">
          <button onClick={onClose} className="rounded bg-gray-700 px-3 py-1.5 text-sm text-gray-200">
            Cancel
          </button>
          <button
            onClick={handleDeactivate}
            disabled={submitting}
            className="rounded bg-amber-700 px-3 py-1.5 text-sm font-semibold text-white hover:bg-amber-600 disabled:bg-gray-700"
          >
            {submitting ? "Deactivating…" : "Deactivate"}
          </button>
        </div>
      </div>
    </div>
  );
}
```

Mount the wizard via an "Activate for live" button on the strategy detail page (visible when `account.mode==LIVE` and `strategy.status in (IDLE, PAPER)`). Mount `ActivationCountdown` when `strategy.status==PENDING_LIVE`. Mount the deactivate button when `strategy.status in (LIVE, HALTED)`.

For the LIVE account creation flow: add a Settings → Accounts page (if not present) with a "Create LIVE account" button that opens a small modal asking for label + TOTP code, then calls `POST /api/v1/accounts` with `mode=live`.

- [ ] ActivationWizard.tsx 4-step modal.
- [ ] ActivationCountdown.tsx for PENDING_LIVE state.
- [ ] DeactivationModal.tsx with liquidation toggle.
- [ ] LiveAccountCreationFlow (TOTP + label).

---

## §7.10 — Tests

Create `apps/backend/tests/services/test_p5_activation_service.py`:

```python
"""ActivationService unit tests."""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock

from app.brokers.base import BrokerPosition
from app.db.enums import (
    BrokerMode, RiskScopeType, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.backtest import Backtest
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.security.crypto import _reset_cache_for_tests
from app.services.activation import (
    ActivationError, ActivationService, ACTIVATION_COOLDOWN_HOURS,
)


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def master_key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("WORKBENCH_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


async def _seed_full(session_factory):
    """Seed: user (TOTP'd), live account, strategy, live risk limits,
    recent backtest, live broker credentials. Everything for prereqs OK."""
    async with session_factory() as session:
        session.add(User(
            id=1, email="t@local", display_name="T",
            totp_verified_at=_now(),
        ))
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
            label="MyLive", created_at=_now(),
        ))
        session.add(RiskLimits(
            user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=10, user_id=1, account_id=1, name="momentum_v1",
            version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="x.py",
            params_json={}, symbols_json=["AAPL", "MSFT"],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        session.add(Backtest(
            strategy_id=10, user_id=1,
            start_date=_now().date() - timedelta(days=30),
            end_date=_now().date(),
            created_at=_now() - timedelta(days=1),
            status="completed",
        ))
        await session.commit()
        store = CredentialStore(session)
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "PKLIVE...")
        await store.set(1, CredentialKind.ALPACA_LIVE_SECRET, "secret...")
        # Set a TOTP secret too (for initiate's verification)
        # Use a known-good generator
        import pyotp
        secret = pyotp.random_base32()
        await store.set(1, CredentialKind.TOTP_SECRET, secret)
        await session.commit()
        return secret


@pytest.mark.asyncio
async def test_all_prereqs_satisfied(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        svc = ActivationService(session=session)
        prereqs = await svc.check_prerequisites(10)
    assert all(p.satisfied for p in prereqs)
    names = {p.name for p in prereqs}
    assert names == {
        "live_broker_credentials", "totp_enrolled",
        "recent_backtest", "live_risk_limits", "circuit_breaker_clear",
    }


@pytest.mark.asyncio
async def test_missing_broker_credentials(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        store = CredentialStore(session)
        await store.revoke(1, CredentialKind.ALPACA_LIVE_KEY)
    async with session_factory() as session:
        svc = ActivationService(session=session)
        prereqs = await svc.check_prerequisites(10)
    by_name = {p.name: p for p in prereqs}
    assert by_name["live_broker_credentials"].satisfied is False


@pytest.mark.asyncio
async def test_missing_totp(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        user = await session.get(User, 1)
        user.totp_verified_at = None
        await session.commit()
    async with session_factory() as session:
        svc = ActivationService(session=session)
        prereqs = await svc.check_prerequisites(10)
    by_name = {p.name: p for p in prereqs}
    assert by_name["totp_enrolled"].satisfied is False


@pytest.mark.asyncio
async def test_old_backtest_not_recent(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        from sqlalchemy import update
        await session.execute(
            update(Backtest)
            .where(Backtest.strategy_id == 10)
            .values(created_at=_now() - timedelta(days=10))
        )
        await session.commit()
    async with session_factory() as session:
        svc = ActivationService(session=session)
        prereqs = await svc.check_prerequisites(10)
    by_name = {p.name: p for p in prereqs}
    assert by_name["recent_backtest"].satisfied is False


@pytest.mark.asyncio
async def test_circuit_breaker_tripped(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        account = await session.get(Account, 1)
        account.circuit_breaker_tripped_at = _now()
        await session.commit()
    async with session_factory() as session:
        svc = ActivationService(session=session)
        prereqs = await svc.check_prerequisites(10)
    by_name = {p.name: p for p in prereqs}
    assert by_name["circuit_breaker_clear"].satisfied is False


@pytest.mark.asyncio
async def test_initiate_success_sets_pending_live(session_factory):
    secret = await _seed_full(session_factory)
    import pyotp
    code = pyotp.TOTP(secret).now()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        result = await svc.initiate(
            strategy_id=10, user_id=1,
            confirmation_name="momentum_v1",
            totp_code=code,
        )
    assert result.status == StrategyStatus.PENDING_LIVE
    assert result.initiated_at is not None
    assert result.seconds_remaining > 23 * 3600
    assert result.seconds_remaining <= ACTIVATION_COOLDOWN_HOURS * 3600


@pytest.mark.asyncio
async def test_initiate_wrong_confirmation_name(session_factory):
    secret = await _seed_full(session_factory)
    import pyotp
    code = pyotp.TOTP(secret).now()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        with pytest.raises(ActivationError) as exc:
            await svc.initiate(
                strategy_id=10, user_id=1,
                confirmation_name="WRONG_NAME",
                totp_code=code,
            )
        assert "Confirmation name" in str(exc.value)


@pytest.mark.asyncio
async def test_initiate_wrong_totp(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        svc = ActivationService(session=session)
        with pytest.raises(ActivationError) as exc:
            await svc.initiate(
                strategy_id=10, user_id=1,
                confirmation_name="momentum_v1",
                totp_code="000000",
            )
        assert "TOTP" in str(exc.value)


@pytest.mark.asyncio
async def test_initiate_unsatisfied_prereqs_rejected(session_factory):
    secret = await _seed_full(session_factory)
    import pyotp
    code = pyotp.TOTP(secret).now()
    # Trip the breaker so prereq fails
    async with session_factory() as session:
        account = await session.get(Account, 1)
        account.circuit_breaker_tripped_at = _now()
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        with pytest.raises(ActivationError) as exc:
            await svc.initiate(
                strategy_id=10, user_id=1,
                confirmation_name="momentum_v1",
                totp_code=code,
            )
        assert "circuit_breaker_clear" in str(exc.value)


@pytest.mark.asyncio
async def test_cancel_reverts_to_idle(session_factory):
    secret = await _seed_full(session_factory)
    import pyotp
    code = pyotp.TOTP(secret).now()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        await svc.initiate(strategy_id=10, user_id=1,
                           confirmation_name="momentum_v1", totp_code=code)

    async with session_factory() as session:
        svc = ActivationService(session=session)
        await svc.cancel(strategy_id=10, user_id=1)

    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.status == StrategyStatus.IDLE
    assert strat.live_activation_initiated_at is None


@pytest.mark.asyncio
async def test_cancel_when_not_pending_raises(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        svc = ActivationService(session=session)
        with pytest.raises(ActivationError) as exc:
            await svc.cancel(strategy_id=10, user_id=1)
        assert "PENDING_LIVE" in str(exc.value)


@pytest.mark.asyncio
async def test_cancel_other_user_raises_permission(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        session.add(User(id=2, email="other@local"))
        await session.commit()
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.PENDING_LIVE
        strat.live_activation_initiated_at = _now()
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        with pytest.raises(PermissionError):
            await svc.cancel(strategy_id=10, user_id=2)


@pytest.mark.asyncio
async def test_complete_pending_before_24h_no_transition(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.PENDING_LIVE
        strat.live_activation_initiated_at = _now() - timedelta(hours=23)
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        transitioned = await svc.complete_pending(10)
    assert transitioned is False

    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.status == StrategyStatus.PENDING_LIVE


@pytest.mark.asyncio
async def test_complete_pending_after_24h_transitions(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.PENDING_LIVE
        strat.live_activation_initiated_at = _now() - timedelta(hours=25)
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        transitioned = await svc.complete_pending(10)
    assert transitioned is True

    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
    assert strat.status == StrategyStatus.LIVE


@pytest.mark.asyncio
async def test_complete_pending_idempotent(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.LIVE
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        transitioned = await svc.complete_pending(10)
    assert transitioned is False    # already LIVE


@pytest.mark.asyncio
async def test_deactivate_without_liquidation(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.LIVE
        await session.commit()

    async with session_factory() as session:
        svc = ActivationService(session=session)
        result = await svc.deactivate(
            strategy_id=10, user_id=1, liquidate=False,
        )

    assert result["new_status"] == "idle"
    assert result["liquidation_orders"] == []


@pytest.mark.asyncio
async def test_deactivate_with_liquidation_submits_orders(session_factory):
    await _seed_full(session_factory)
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.LIVE
        await session.commit()

    # Mock broker registry + order router
    broker_reg = MagicMock()
    adapter = MagicMock()
    adapter.get_positions = AsyncMock(return_value=[
        BrokerPosition(symbol="AAPL", qty=Decimal("10"), avg_entry_price=Decimal("150"),
                       market_value=Decimal("1500"), unrealized_pl=Decimal("0")),
        BrokerPosition(symbol="NVDA", qty=Decimal("5"), avg_entry_price=Decimal("400"),
                       market_value=Decimal("2000"), unrealized_pl=Decimal("0")),
    ])
    broker_reg.get.return_value = adapter

    order_router = MagicMock()
    submitted_results = []
    async def fake_submit(req, **kwargs):
        from app.orders.router import OrderSubmissionResult
        from app.db.enums import OrderStatus
        result = OrderSubmissionResult(
            order_id=len(submitted_results) + 100,
            status=OrderStatus.ACCEPTED,
            reason_code=None,
        )
        submitted_results.append((req, result))
        return result
    order_router.submit = fake_submit

    async with session_factory() as session:
        svc = ActivationService(
            session=session,
            broker_registry=broker_reg,
            order_router=order_router,
        )
        result = await svc.deactivate(
            strategy_id=10, user_id=1, liquidate=True,
        )

    # NVDA is not in strategy.symbols_json (["AAPL", "MSFT"]) — only AAPL closes
    assert len(result["liquidation_orders"]) == 1
    assert len(submitted_results) == 1
    submitted_req = submitted_results[0][0]
    assert submitted_req.symbol == "AAPL"
    assert submitted_req.side.value == "sell"
    assert submitted_req.qty == Decimal("10")
```

Create `apps/backend/tests/api/test_p5_activation_endpoints.py`:

```python
"""Activation endpoint tests."""
import pytest
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from app.db.enums import (
    BrokerMode, RiskScopeType, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.backtest import Backtest
from app.db.models.risk_limits import RiskLimits
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User
from app.security.credential_store import CredentialKind, CredentialStore
from app.security.crypto import _reset_cache_for_tests


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture(autouse=True)
def master_key(monkeypatch):
    from cryptography.fernet import Fernet
    monkeypatch.setenv("WORKBENCH_MASTER_KEY", Fernet.generate_key().decode("ascii"))
    _reset_cache_for_tests()
    yield
    _reset_cache_for_tests()


@pytest.fixture
async def live_strategy_setup(session_factory):
    import pyotp
    async with session_factory() as session:
        user = await session.get(User, 1)
        user.totp_verified_at = _now()
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
            label="MyLive", created_at=_now(),
        ))
        session.add(RiskLimits(
            user_id=1, broker_mode=AccountMode.live,
            scope_type=RiskScopeType.GLOBAL,
            max_daily_loss=Decimal("500"),
            created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=10, user_id=1, account_id=1, name="my_strategy",
            version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.IDLE, code_path="x.py",
            params_json={}, symbols_json=["AAPL"],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        session.add(Backtest(
            strategy_id=10, user_id=1,
            start_date=_now().date() - timedelta(days=30),
            end_date=_now().date(),
            created_at=_now() - timedelta(days=1),
            status="completed",
        ))
        await session.commit()
        store = CredentialStore(session)
        await store.set(1, CredentialKind.ALPACA_LIVE_KEY, "PK...")
        await store.set(1, CredentialKind.ALPACA_LIVE_SECRET, "...")
        secret = pyotp.random_base32()
        await store.set(1, CredentialKind.TOTP_SECRET, secret)
        await session.commit()
        return secret


@pytest.mark.asyncio
async def test_activation_status_returns_prerequisites(auth_client, live_strategy_setup):
    r = await auth_client.get("/api/v1/strategies/10/activation")
    assert r.status_code == 200
    body = r.json()
    assert body["strategy_id"] == 10
    assert body["status"] == "idle"
    assert len(body["prerequisites"]) == 5
    assert body["all_satisfied"] is True


@pytest.mark.asyncio
async def test_activate_success_transitions_to_pending_live(
    auth_client, live_strategy_setup, session_factory,
):
    import pyotp
    code = pyotp.TOTP(live_strategy_setup).now()
    r = await auth_client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy",
        "totp_code": code,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["status"] == "pending_live"
    assert body["seconds_remaining"] > 23 * 3600


@pytest.mark.asyncio
async def test_activate_bad_totp_400(auth_client, live_strategy_setup):
    r = await auth_client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy",
        "totp_code": "000000",
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_activate_bad_name_400(auth_client, live_strategy_setup):
    import pyotp
    code = pyotp.TOTP(live_strategy_setup).now()
    r = await auth_client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "WRONG",
        "totp_code": code,
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_cancel_returns_to_idle(auth_client, live_strategy_setup, session_factory):
    import pyotp
    code = pyotp.TOTP(live_strategy_setup).now()
    await auth_client.post("/api/v1/strategies/10/activate", json={
        "confirmation_name": "my_strategy",
        "totp_code": code,
    })
    r = await auth_client.post("/api/v1/strategies/10/activate/cancel")
    assert r.status_code == 200

    r = await auth_client.get("/api/v1/strategies/10/activation")
    assert r.json()["status"] == "idle"


@pytest.mark.asyncio
async def test_cancel_not_pending_returns_400(auth_client, live_strategy_setup):
    r = await auth_client.post("/api/v1/strategies/10/activate/cancel")
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_deactivate_idle_strategy_returns_400(
    auth_client, live_strategy_setup,
):
    r = await auth_client.post("/api/v1/strategies/10/deactivate", json={
        "liquidate": False,
    })
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_deactivate_live_strategy(auth_client, live_strategy_setup, session_factory):
    async with session_factory() as session:
        strat = await session.get(StrategyRow, 10)
        strat.status = StrategyStatus.LIVE
        await session.commit()

    r = await auth_client.post("/api/v1/strategies/10/deactivate", json={
        "liquidate": False,
    })
    assert r.status_code == 200
    body = r.json()
    assert body["new_status"] == "idle"
```

Create `apps/backend/tests/services/test_p5_order_router_live_path.py`:

```python
"""Verify the lifted §1 guard accepts and rejects correctly."""
import pytest
from datetime import datetime, timezone
from decimal import Decimal

from app.db.enums import (
    AccountMode, OrderSourceType, OrderStatus, StrategyStatus, StrategyType,
)
from app.db.models.account import Account
from app.db.models.strategy import Strategy as StrategyRow
from app.db.models.user import User


def _now():
    return datetime.now(timezone.utc)


@pytest.fixture
async def live_account_and_strategies(session_factory):
    async with session_factory() as session:
        session.add(Account(
            id=1, user_id=1, broker="alpaca", mode=AccountMode.live,
            label="MyLive", created_at=_now(),
        ))
        session.add(StrategyRow(
            id=10, user_id=1, account_id=1, name="pending",
            version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.PENDING_LIVE,
            live_activation_initiated_at=_now(),
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        session.add(StrategyRow(
            id=11, user_id=1, account_id=1, name="live",
            version="0.1.0", type=StrategyType.PYTHON,
            status=StrategyStatus.LIVE,
            code_path="x.py", params_json={}, symbols_json=[],
            schedule="event", created_at=_now(), updated_at=_now(),
        ))
        await session.commit()


@pytest.mark.asyncio
async def test_strategy_pending_live_rejected(
    auth_client, live_account_and_strategies,
):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": 1,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day",
        "source": "strategy", "strategy_id": 10,
    })
    body = r.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "STRATEGY_PENDING_LIVE"


@pytest.mark.asyncio
async def test_strategy_live_passes_live_guard(
    auth_client, live_account_and_strategies,
):
    """Order may still be rejected by downstream gates (no broker setup,
    no credentials, etc.) but it should NOT be rejected with STRATEGY_*
    reject codes."""
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": 1,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day",
        "source": "strategy", "strategy_id": 11,
    })
    body = r.json()
    assert body.get("reason_code") not in (
        "STRATEGY_PENDING_LIVE", "STRATEGY_NOT_LIVE", "STRATEGY_ID_REQUIRED",
    )


@pytest.mark.asyncio
async def test_agent_live_rejected(auth_client, live_account_and_strategies):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": 1,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day",
        "source": "agent",
    })
    body = r.json()
    assert body["status"] == "rejected"
    assert body["reason_code"] == "AGENT_LIVE_DISABLED"


@pytest.mark.asyncio
async def test_strategy_id_required_for_strategy_source(
    auth_client, live_account_and_strategies,
):
    r = await auth_client.post("/api/v1/orders", json={
        "account_id": 1,
        "symbol": "AAPL", "side": "buy", "type": "market",
        "qty": "1", "tif": "day",
        "source": "strategy",
    })
    body = r.json()
    assert body["reason_code"] == "STRATEGY_ID_REQUIRED"
```

Run:

```bash
cd apps\backend
.\.venv\Scripts\python.exe -m pytest tests/services/test_p5_activation_service.py tests/api/test_p5_activation_endpoints.py tests/services/test_p5_order_router_live_path.py -v
.\.venv\Scripts\python.exe -m pytest -q --cov-branch

# All eight CI invariants (no check_adr0002.sh — see drift item #13)
.\.venv\Scripts\python.exe -m pytest tests/test_adr_0002_invariant.py -q
bash scripts/check_strategy_isolation.sh
bash scripts/check_mcp_readonly.sh
bash scripts/check_no_llm_in_order_path.sh
bash scripts/check_broker_isolation.sh
bash scripts/check_no_env_credentials.sh
.\.venv\Scripts\python.exe scripts\check_risk_coverage.py
.\.venv\Scripts\python.exe scripts\check_p2_coverage.py
.\.venv\Scripts\python.exe scripts\check_p3_coverage.py
cd ../..
```

- [ ] 17 activation service tests pass.
- [ ] 7 endpoint tests pass.
- [ ] 4 OrderRouter live-path tests pass.
- [ ] Full suite green; eight invariants green.

---

## §7.11 — Manual Smoke

```bash
./scripts/dev.sh &
sleep 30
./scripts/login_helper.sh

# 1. Paper baseline — byte-identical
PAPER_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[] | select(.mode=="paper") | .id')
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, reason_code}'
# Expect: status=accepted

# 2. Try creating a LIVE account WITHOUT TOTP — rejected
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d '{"broker": "alpaca", "mode": "live", "label": "TestLive"}' | jq
# Expect: 400 detail mentions totp_code

# 3. Create LIVE account WITH TOTP
TOTP_CODE=$(python3 -c "
import pyotp, sys
# In real flow you have the user's TOTP secret via the authenticator app.
# For testing: read it from the DB.
import sqlite3
import os
# (the test script knows where the DB is)
" 2>/dev/null || echo "ENTER_TOTP_HERE")

# (Use your authenticator app's current code)
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/accounts \
  -H "Content-Type: application/json" \
  -d "{
    \"broker\": \"alpaca\", \"mode\": \"live\",
    \"label\": \"TestLive\", \"totp_code\": \"${TOTP_CODE}\"
  }" | jq

LIVE_ACC_ID=$(curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/accounts | jq -r '.items[] | select(.mode=="live") | .id')
echo "LIVE_ACC_ID=${LIVE_ACC_ID}"

# 4. Set LIVE broker credentials (use Alpaca paper keys for safety —
#    Alpaca paper keys against the LIVE adapter will get rejected by
#    Alpaca but we're testing the workbench path, not Alpaca's auth)
curl -s -b /tmp/cookies.txt -X PUT http://127.0.0.1:8000/api/v1/users/me/credentials/alpaca_live_key \
  -H "Content-Type: application/json" \
  -d '{"value": "PKtest..."}'
curl -s -b /tmp/cookies.txt -X PUT http://127.0.0.1:8000/api/v1/users/me/credentials/alpaca_live_secret \
  -H "Content-Type: application/json" \
  -d '{"value": "secret..."}'

# 5. Create a strategy attached to the LIVE account
STRATEGY_ID=$(curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/strategies \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${LIVE_ACC_ID},
    \"name\": \"smoke_test\",
    \"version\": \"0.1.0\",
    \"type\": \"python\",
    \"code\": \"def on_bar(ctx, bar): return None\",
    \"params\": {},
    \"symbols\": [\"AAPL\"],
    \"schedule\": \"event\"
  }" | jq -r '.id')
echo "STRATEGY_ID=${STRATEGY_ID}"

# 6. Check activation status — expect some prereqs unsatisfied
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activation | jq

# 7. Run a backtest to satisfy the recent_backtest prereq
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/backtests \
  -H "Content-Type: application/json" \
  -d "{
    \"strategy_id\": ${STRATEGY_ID},
    \"start_date\": \"2026-01-01\",
    \"end_date\": \"2026-01-31\"
  }"
sleep 5

# 8. Check status again — all prereqs satisfied?
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activation | jq '.all_satisfied'
# Expect: true

# 9. Try activate with WRONG name → 400
TOTP_CODE_2=$(python3 -c "...")  # fresh code
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activate \
  -H "Content-Type: application/json" \
  -d "{\"confirmation_name\": \"WRONG\", \"totp_code\": \"${TOTP_CODE_2}\"}" | jq
# Expect: 400

# 10. Try activate with correct name + TOTP → success
TOTP_CODE_3=$(python3 -c "...")
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activate \
  -H "Content-Type: application/json" \
  -d "{\"confirmation_name\": \"smoke_test\", \"totp_code\": \"${TOTP_CODE_3}\"}" | jq
# Expect: status=pending_live, seconds_remaining ≈ 86400

# 11. Try to submit a strategy LIVE order RIGHT NOW — rejected
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${LIVE_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\", \"tif\": \"day\",
    \"source\": \"strategy\", \"strategy_id\": ${STRATEGY_ID}
  }" | jq '{status, reason_code}'
# Expect: status=rejected, reason_code=STRATEGY_PENDING_LIVE

# 12. Manually backdate live_activation_initiated_at to simulate 24h elapsed
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE strategies SET live_activation_initiated_at = datetime('now', '-25 hours') WHERE id=${STRATEGY_ID};"

# 13. Run the activation completion job manually (or wait 60s for the scheduler)
docker compose exec backend uv run python -c "
import asyncio
from app.db.session import async_session_factory
from app.jobs.activation_completion import run_activation_completion
asyncio.run(run_activation_completion(async_session_factory))
"
# OR sleep 70 for the scheduler

# 14. Verify status = LIVE
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activation | jq '.status'
# Expect: "live"

# 15. Cancel a fresh activation
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE strategies SET status='pending_live', live_activation_initiated_at=datetime('now') WHERE id=${STRATEGY_ID};"
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activate/cancel | jq

# 16. Verify status = IDLE
curl -s -b /tmp/cookies.txt http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/activation | jq '.status'

# 17. Deactivate flow — set LIVE then deactivate WITHOUT liquidation
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite \
  "UPDATE strategies SET status='live' WHERE id=${STRATEGY_ID};"
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/strategies/${STRATEGY_ID}/deactivate \
  -H "Content-Type: application/json" \
  -d '{"liquidate": false}' | jq

# 18. LOAD-BEARING: paper order still works
curl -s -b /tmp/cookies.txt -X POST http://127.0.0.1:8000/api/v1/orders \
  -H "Content-Type: application/json" \
  -d "{
    \"account_id\": ${PAPER_ACC_ID},
    \"symbol\": \"AAPL\", \"side\": \"buy\",
    \"type\": \"market\", \"qty\": \"1\",
    \"tif\": \"day\", \"source\": \"manual\"
  }" | jq '{status, reason_code, broker_order_id}'
# Expect: status=accepted, broker_order_id from Alpaca

# 19. UI smoke (manual): strategy detail page shows "Activate for live" button
#     when on a LIVE account and IDLE/PAPER status. Wizard renders 4 steps.
#     Prerequisites step shows green checks (since we set them up).
#     Confirm step requires typed name + TOTP.
#     After activation: ActivationCountdown badge shows on detail page.
#     LIVE strategies show Deactivate button; modal asks about liquidation.

docker compose down
```

- [ ] Paper baseline byte-identical.
- [ ] LIVE account creation requires TOTP.
- [ ] Strategy with all prereqs activates successfully.
- [ ] PENDING_LIVE strategy rejects orders with STRATEGY_PENDING_LIVE.
- [ ] After 24h (backdated), scheduler transitions to LIVE.
- [ ] Cancel during PENDING_LIVE returns to IDLE.
- [ ] Deactivation works (with and without liquidation).
- [ ] **Paper smoke unchanged.**

---

## §7.12 — Runbook

Create `docs/runbook/activation.md`:

```markdown
# Strategy Activation

## Overview

A strategy can be in one of these statuses:

| Status | Can submit orders? | How to enter | How to exit |
|---|---|---|---|
| IDLE | No | Default; from cancellation; from deactivation | Activation wizard → PENDING_LIVE; start in paper → PAPER |
| PAPER | Yes (paper only) | Start strategy on paper account | Stop → IDLE |
| PENDING_LIVE | No | Activation wizard from IDLE/PAPER | 24h elapses → LIVE; cancel → IDLE |
| LIVE | Yes (live only) | Scheduler after 24h cooldown | Deactivate → IDLE; circuit breaker → HALTED |
| HALTED | No | Circuit breaker trip | Reset breaker; restart → PAPER/LIVE |
| ERROR | No | Strategy engine crash | Fix code + restart → PAPER/LIVE |

## Activation flow

### Prerequisites

Five things must be true before the wizard accepts initiation:

1. **Live broker credentials configured** — Alpaca Live API Key + Secret
   set via Settings → Credentials.
2. **TOTP enrolled** — `users.totp_verified_at` is not NULL.
3. **Recent backtest** — a `backtests` row for this strategy in the
   last 7 days. The workbench doesn't grade the backtest; it just
   confirms you engaged with the tool.
4. **LIVE risk limits configured** — a `risk_limits` row with
   `broker_mode=LIVE` exists for the user. The migration in §5 creates
   one with conservative defaults.
5. **No active circuit breaker** — the strategy's account is not
   currently tripped.

The wizard surfaces each prereq as a green check / red X with a "fix
this" link. Don't proceed until all green.

### Initiation

The wizard's final step asks for:
- The strategy name, typed exactly (case-sensitive).
- A TOTP code from your authenticator app.

Server-side: both are re-verified. Mismatched name → 400. Wrong TOTP →
400. Both checks block initiation.

On success: status transitions to PENDING_LIVE; the 24-hour cooldown
begins; an audit log entry is written.

### Cooldown (24 hours)

During PENDING_LIVE:
- Orders from this strategy are rejected with `STRATEGY_PENDING_LIVE`.
- The ActivationCountdown banner shows on the strategy detail page.
- The user can cancel at any time. No friction (no typed name, no TOTP).
  Cancellation is the safe direction.

The cooldown is per-strategy. A user with multiple strategies activates
each one independently, each with its own 24h.

### Completion

When 24 hours has elapsed since `live_activation_initiated_at`:
- The `activation_completion` scheduler job (runs every 60s) flips
  status PENDING_LIVE → LIVE.
- Audit log entry: `STRATEGY_LIVE_ACTIVATED`.
- The strategy can now submit live orders.

The job is idempotent. If the backend was down when 24h elapsed, the
first run after restart completes the transition.

## Deactivation

To stop a LIVE strategy:
1. Go to the strategy detail page.
2. Click Deactivate.
3. Decide whether to liquidate open positions (checkbox).
4. Click Deactivate.

The strategy transitions LIVE → IDLE. If liquidate=true, market orders
are submitted to close all open positions in the strategy's symbols.
Liquidation orders go through the normal risk gates (cooldown, risk
engine, audit).

There is no cooldown on deactivation. You can always stop trading.

## LIVE account creation

LIVE accounts are created via `POST /api/v1/accounts` with `mode=live`.
The request requires `totp_code`. Audit log: `LIVE_ACCOUNT_CREATED`.

The BrokerRegistry refreshes after creation so the new account's adapter
is loaded.

## Inspecting

### Strategies currently in PENDING_LIVE

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT id, name, account_id, live_activation_initiated_at,
       datetime(live_activation_initiated_at, '+24 hours') AS goes_live_at
FROM strategies
WHERE status='pending_live'
ORDER BY live_activation_initiated_at;
"
```

### Recent activation audit trail

```bash
docker compose exec backend uv run sqlite3 /app/data/workbench.sqlite "
SELECT created_at, action, target_id, payload
FROM audit_log
WHERE action IN (
  'strategy_activation_initiated', 'strategy_activation_canceled',
  'strategy_live_activated', 'strategy_deactivated',
  'live_account_created'
)
ORDER BY id DESC LIMIT 20;
"
```

### Scheduler health

```bash
grep activation_completion /var/log/workbench/backend.log | tail -20
```

If you don't see periodic `activation_completion_pass` messages every 60s,
the scheduler may be wedged. Restart the backend.

## Failure modes

### Strategy stuck in PENDING_LIVE

Check:
1. Is the scheduler running? (See "Scheduler health" above.)
2. Is `live_activation_initiated_at` set correctly? Query the strategy row.
3. Is 24h actually elapsed?

If all yes but the strategy is still PENDING_LIVE, run the completion
job manually:

```python
asyncio.run(run_activation_completion(async_session_factory))
```

### Activation refused with "Prerequisites not satisfied"

The error includes the failing prerequisite names. Most common:
- `recent_backtest` — run a backtest in the last 7 days.
- `live_broker_credentials` — set via Settings → Credentials.
- `circuit_breaker_clear` — reset the breaker first.

### Liquidation failed mid-deactivation

If liquidate=true but some closing orders fail, the strategy is still
transitioned to IDLE (the API returns the list of orders that DID
submit). Re-deactivate is a no-op. To liquidate the remaining
positions, manually submit closing orders.
```

- [ ] Runbook committed at `docs/runbook/activation.md`.

---

## §7.13 — Commit and PR

```bash
git add apps/backend/app/db/enums.py
git add apps/backend/app/db/models/strategy.py
git add apps/backend/alembic/versions/
git add apps/backend/app/services/activation.py
git add apps/backend/app/orders/router.py
git add apps/backend/app/api/v1/accounts.py
git add apps/backend/app/api/v1/activation.py
git add apps/backend/app/api/v1/strategies.py
git add apps/backend/app/main.py
git add apps/backend/app/jobs/activation_completion.py
git add apps/backend/app/lifespan.py
git add apps/backend/tests/services/test_p5_activation_service.py
git add apps/backend/tests/services/test_p5_order_router_live_path.py
git add apps/backend/tests/api/test_p5_activation_endpoints.py
git add apps/frontend/src/api/activation.ts
git add apps/frontend/src/components/activation/
git add apps/frontend/src/pages/Strategies/StrategyDetail.tsx    # wire in wizard + countdown + deactivate
git add apps/frontend/src/pages/Settings/Accounts.tsx            # LIVE account creation
git add docs/adr/0005-activation-cooldown.md
git add docs/runbook/activation.md

git commit -m "feat(p5): activation wizard + live path open (P5 §7)

The session that opens the live order path.

- ADR 0005 — 24-hour activation cooldown as defense against impulse
  decisions. Cancellation during cooldown is frictionless (no TOTP, no
  typed confirmation).
- New StrategyStatus.PENDING_LIVE. Lifecycle: IDLE/PAPER → PENDING_LIVE
  (via wizard) → LIVE (via 60s-polling scheduler after 24h). Cancel:
  PENDING_LIVE → IDLE.
- New strategies.live_activation_initiated_at (datetime, nullable).
- ActivationService: check_prerequisites (5 prereqs), initiate
  (TOTP + typed strategy name + all prereqs satisfied), cancel
  (auth only), complete_pending (idempotent), deactivate (with optional
  OrderRouter-mediated liquidation).
- P5 §1 BrokerModeError guard REPLACED in OrderRouter with conditional
  logic: MANUAL+LIVE permitted (§6 confirm), STRATEGY+LIVE permitted if
  strategy.status==LIVE (rejects PENDING_LIVE with STRATEGY_PENDING_LIVE,
  IDLE with STRATEGY_NOT_LIVE), AGENT+LIVE rejected with
  AGENT_LIVE_DISABLED.
- POST /api/v1/accounts accepts mode=live with totp_code required.
  LIVE_ACCOUNT_CREATED audit.
- New endpoints:
    GET    /api/v1/strategies/{id}/activation
    POST   /api/v1/strategies/{id}/activate
    POST   /api/v1/strategies/{id}/activate/cancel
    POST   /api/v1/strategies/{id}/deactivate
- Background job activation_completion runs every 60s; flips
  PENDING_LIVE → LIVE after 24h. Idempotent across backend restarts.
- New audit actions: STRATEGY_ACTIVATION_INITIATED,
  STRATEGY_ACTIVATION_CANCELED, STRATEGY_LIVE_ACTIVATED,
  STRATEGY_DEACTIVATED, LIVE_ACCOUNT_CREATED.
- Frontend: ActivationWizard (4-step modal), ActivationCountdown
  (PENDING_LIVE banner with cancel), DeactivationModal (with
  liquidation toggle), LiveAccountCreationFlow (TOTP-gated).
- 28 backend tests covering the lifecycle, lifted guard, and edge cases.

NOT in this PR:
- Production deployment infra — that's §8.
- Backtest quality gating — we check engagement, not results.
- Multi-strategy bulk activation.

Load-bearing: P1-§6 paper smoke produces byte-identical chains.
LIVE paths only fire on LIVE accounts; paper untouched."

git push -u origin feat/p5-session7-activation

gh pr create \
  --title "feat(p5): activation wizard + live path open (P5 §7)" \
  --body "P5 Session 7 — the session that opens the live order path.

ADR 0005 (24h activation cooldown) is the central decision. Read it
first if reviewing.

Load-bearing: P1-§6 paper smoke byte-identical.

PLEASE: do not merge in flow. This is the second-most consequential PR
in P5 (after §5). Walk away ≥2 hours. Re-read with attention to:
- The lifted §1 guard — are all four (MANUAL, STRATEGY+LIVE,
  STRATEGY+PENDING_LIVE, AGENT) paths covered?
- The activation_completion scheduler — idempotent across restarts?
- TOTP re-verification in initiate (defense against session hijack).
- Cancel-without-friction (the asymmetry from ADR 0005)."

gh pr checks

# Walk away ≥2 hours. Re-read with attention to:
# - OrderRouter's lifted guard correctly handles every (source, mode) pair.
# - ActivationService.initiate re-checks all prereqs at the last moment
#   (not just on the wizard's first step — they may have changed).
# - The scheduler job is idempotent on restart (uses < cutoff, not == cutoff).
# - Liquidation submits through the OrderRouter, not a bypass path.
# - All five prereqs return the right .satisfied for negative cases.

# Squash-merge convention (matches Sessions 4 + 5 + 6)
gh pr merge --squash --subject "feat(p5): activation wizard + live path open (P5 §7) (#NN)" --delete-branch
git checkout main && git pull
git tag -a p5-session7-complete -m "P5 §7 activation wizard complete; live path open"
git push origin p5-session7-complete
```

- [ ] PR opened; CI green incl. all eight invariants + ADR 0002 test.
- [ ] **Walked away ≥2 hours** (Session 7 is the most consequential — real money becomes possible).
- [ ] Eight CI invariants pass.
- [ ] PR merged.
- [ ] Tag pushed.

---

## Verification Checklist (full session)

- [ ] §7.1 ADR 0005 explains the 24h cooldown.
- [ ] §7.2 PENDING_LIVE + live_activation_initiated_at + audit actions.
- [ ] §7.3 check_prerequisites returns 5 items, each with correct .satisfied.
- [ ] §7.4 initiate / cancel / complete_pending / deactivate semantics.
- [ ] §7.5 §1 BrokerModeError replaced; AGENT_LIVE_DISABLED, STRATEGY_PENDING_LIVE,
       STRATEGY_NOT_LIVE, STRATEGY_ID_REQUIRED reject codes covered.
- [ ] §7.6 POST /accounts accepts mode=live with TOTP.
- [ ] §7.7 4 activation endpoints.
- [ ] §7.8 60s scheduler job; idempotent.
- [ ] §7.9 Wizard + countdown + deactivation modal.
- [ ] §7.10 28 backend tests pass.
- [ ] §7.11 Manual smoke: full lifecycle + paper baseline unchanged.
- [ ] §7.12 Runbook covers prereqs, lifecycle, failure modes.
- [ ] §7.13 PR merged, tag pushed.

---

## Notes & Gotchas

1. **The session that actually lets you lose money.** Gotcha-of-record: every gate from §2-§6 is now in the live path. If you find yourself testing on a LIVE account with real credentials, do it during after-hours (no fills) and with `max_position_qty=1`. The smoke procedure in §7.11 explicitly uses Alpaca paper keys against the LIVE adapter so that even if the workbench-side gates fail, Alpaca rejects.

2. **Cancellation is frictionless on purpose.** Gotcha §7.4 + ADR 0005: no TOTP, no typed confirmation. The asymmetry is intentional. Activation is the expensive action; cancellation is always safe. If you find yourself adding friction to cancellation "for symmetry," step back — that's not the right reason.

3. **Re-check prereqs at initiate time, not just at status time.** Gotcha §7.4: `initiate` calls `check_prerequisites` again. A user could:
   - Open the wizard at step 1 (all green).
   - Have their breaker trip while they're filling in step 4.
   - Submit → the prereq is re-checked and refuses cleanly.

4. **TOTP re-verification in initiate is defense against session hijack.** Gotcha §7.4: even though the user is authenticated (cookie + TOTP at login), the activation gesture re-verifies TOTP. The reasoning: the cookie is long-lived (14 days); the TOTP code is 30 seconds. An attacker with the cookie but not the TOTP secret can't activate.

5. **The 5 prerequisites are deliberately a ceiling.** Gotcha §7.3: tempting to add "minimum backtest Sharpe ratio," "minimum paper P&L over 30 days," etc. Don't. The workbench gates *process* (you engaged with the backtest, you have credentials, you have TOTP) but not *quality*. Quality is the user's call. A user who wants to activate a bad strategy should be allowed to — once.

6. **The scheduler uses a 60s interval, not event-driven.** Gotcha §7.8: a strategy activated at 09:00:30 goes LIVE somewhere in 09:00:30+24h → 09:01:30+24h next day, ±60s. Acceptable for the use case (24h ± 60s is the same trading-day boundary). Event-driven (e.g., `asyncio.sleep(86400)`) would require per-strategy timers and isn't worth it.

7. **Idempotency of complete_pending.** Gotcha §7.4: the function early-returns if `strategy.status != PENDING_LIVE`. This handles:
   - The user canceled between scheduler ticks (status=IDLE → return False).
   - A previous scheduler tick already completed it (status=LIVE → return False).
   - A different worker raced and completed it (same as above).
   The scheduler can safely retry on any error; the worst case is a duplicate log line.

8. **Liquidation goes through the OrderRouter, not a bypass.** Gotcha §7.4: `_enqueue_liquidation` calls `self._order_router.submit` for each position. This means liquidation orders are subject to §5's risk gates and §6's cooldown. If the circuit breaker is tripped, liquidation orders are also rejected. The user is expected to handle this case (reset the breaker first). It's also why the prerequisites checklist includes `circuit_breaker_clear` — symmetric exit and entry.

9. **AGENT_LIVE_DISABLED is in §7, not earlier.** Gotcha §7.5: the §1 BrokerModeError refused every LIVE request including agent. The §7 replacement reintroduces the agent refuse explicitly as `AGENT_LIVE_DISABLED`. P6 (agent autonomy) is where the agent gets its own activation flow and this reject code gets retired.

10. **The wizard's "review risk limits" step (§7.9) edits in-place.** Gotcha: the wizard surfaces the LIVE-scoped risk_limits row and lets the user edit it. Saving uses the §5 `PUT /api/v1/risk-limits/{id}` endpoint, which audit-logs the change. The wizard itself doesn't create new risk limits — it edits the row the §5 migration created.

11. **LIVE account creation requires BrokerRegistry refresh.** Gotcha §7.6: after creating a LIVE account, the BrokerRegistry needs to load the adapter for it. The §2 `refresh()` method handles this; call it from the create endpoint via `request.app.state.broker_registry.refresh()`. If you forget, the new account works for everything except actual order submission (no adapter loaded yet) — confusing.

12. **The migration only adds a column. PENDING_LIVE is a string enum value.** Gotcha §7.2.4: because the `status` column is a generic String (per P1 convention), adding the new enum value requires no DDL. Don't add an `ALTER TABLE` to the migration; you'll cause grief on rollback.

13. **Activation triggers no broker call.** Gotcha §7.4: `initiate` does DB writes only. The broker isn't contacted until the first live order actually flows (after the 24h cooldown completes). This means initiation succeeds even if Alpaca is down — which is the right behavior. The credentials are validated when an order is actually attempted.

14. **The §7.11 smoke uses a `python3 -c "..."` placeholder for TOTP.** Gotcha: actual TOTP codes have to come from your authenticator app (or computed locally from the seed if you saved it during enrollment). The smoke script can't auto-fill this without breaking the security model. For automated CI, use the test fixtures (which write TOTP secrets to the credential store and compute codes via pyotp).

15. **Walk away before merging.** Gotcha §7.13: this is the second-most consequential PR in P5 (after §5). The §1 guard being lifted is the moment the code can lose money. Re-read the OrderRouter integration with the eyes of someone debugging at midnight after a live order went through that shouldn't have. Verify every (source, mode) combination is explicitly handled.

16. **Don't bundle §8 (production hardening) into this PR.** §8 is the production-deploy session; until §8 ships, treat §7 as "the live path works on a developer laptop." Don't actually activate a real strategy until §8.

17. **`strategies` has no `account_id` FK** (drift item #6). Every "the strategy's account" lookup goes through `_resolve_strategy_account(strategy, mode)`, which queries `Account.user_id == strategy.user_id AND Account.mode == mode`. A user has at most one paper and one live account in the MVP shape, so this is a 1:1 mapping. If future work introduces multiple accounts per (user, mode), the resolution needs to disambiguate — but that's not §7 scope. The new `live_account_exists` prerequisite surfaces the "no live account yet" case to the user.

18. **Shared `ensure_aware()` is applied in five places in this session.** Inherits Session 5 §5.0's helper. The sites: (a) `check_prerequisites` for the breaker's `tripped_at`; (b) `status()` for `initiated_at`; (c) `complete_pending` for the elapsed computation; (d) `cancel` if it reads the timestamp (verify); (e) any frontend-derived `seconds_remaining` payload. Without these coercions, the scheduler can silently fail to advance PENDING_LIVE → LIVE because the elapsed check compares aware `now` against naive `initiated_at` and raises TypeError — but our code may catch and log it, making the bug appear as "scheduler not running." Silent-correctness risk.

19. **Liquidation submits through the OrderRouter, preserving `_router_token` discipline.** Session 2's invariant: only OrderRouter passes `_router_token` to broker mutators. Session 7's liquidation calls `self._order_router.submit(req)` — the router internally adds the token. The liquidation orders go through the §5 risk gates and §6 confirmation/cooldown rules (cooldown doesn't fire on MANUAL, which liquidation isn't — see drift item #8 about source). If a strategy is HALTED by the circuit breaker, liquidation orders ALSO go through risk checks; the user must reset the breaker before deactivation can liquidate.

20. **Two daily-loss mechanisms inherited from Session 5.** The existing global daily-loss halt at `app/risk/halt.py` (RiskEngine step 9) coexists with the account-scoped breaker. The "no active circuit breaker" prereq only checks the account-scoped breaker (Session 5's `accounts.circuit_breaker_tripped_at`). The global halt is orthogonal and not a prereq to check — when it's tripped, ALL orders are blocked regardless of strategy status. A future ADR may consolidate them.

21. **Liquidation order shape uses `OrderRequest` (Session 6's actual schema), not `OrderSubmitRequest`.** Session 6 Results confirmed the request type is `OrderRequest` (frozen dataclass) and `strategy_id` is derived from `source_id` (string). The v0.2 code reflects this; verify against current code before relying.

22. **Expect execution-surfaced drift.** This v0.2 catches the knowable drift from Sessions 0–6 Results. It cannot catch unknown drift in the actual codebase. Session 5 found ~6 unknown items during execution; Session 6 found another ~7 (including the orders endpoint hardcoding the PAPER account, `OrderRequest` being a frozen dataclass, `evaluate()` vs `check()`, `rejection_reason` string vs `reason_code`, etc.). Session 7 has the largest surface area (§7.3 prereqs, §7.4 write-side, §7.5 guard-lifting, §7.6 LIVE account creation, §7.8 scheduler, §7.10 tests) and is the most consequential session in P5. Before pasting any §7.5 OrderRouter code, grep+read `app/orders/router.py` for its Session-6-modified shape. Before pasting §7.4 deactivation/liquidation code, verify the Position model, the OrderRouter.submit signature, and the `evaluate` method. Capture deviations in Session 7 Results.

---

*End of P5 Session 7 v0.2. Updated in-place from v0.1 (2026-05-23) with 15 drift corrections from Sessions 0–6 Results — including the consequential `strategy.account_id` absence (resolved via the new `_resolve_strategy_account` helper) — the shared `ensure_aware()` integration from Session 5 §5.0, and a candid acknowledgment that this is the most consequential session in P5 (real money becomes possible). Walk away ≥2 hours before merging.*
