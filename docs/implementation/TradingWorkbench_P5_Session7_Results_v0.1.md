# P5 Session 7 — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-01 |
| Phase | P5 §7 — Activation Wizard & Live Path Open (companion to `TradingWorkbench_P5_Session7_v0.2.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#45** — branch `feat/p5-session7-activation`; tag **`p5-session7-complete`** |
| Built against | `main` at `p5-session6-complete` (`9f589e5`) |
| Verdict | **GO.** The live order path is open. The §1 blanket `BrokerModeError` is lifted and replaced by a per-source conditional guard; the activation lifecycle (IDLE/PAPER → PENDING_LIVE → 24h → LIVE → IDLE), six prerequisites, TOTP-gated initiation + LIVE account creation, the 24h completion scheduler, and the deactivate/liquidate path are all implemented and **executed**. Full backend suite green (548 passed / 9 skipped); risk gate + p2/p3 + mypy + ruff + 5 shell invariants + ADR 0002 + audit-immutability all green; frontend tsc + ESLint + 77 vitest green. **Live runtime smoke (real money) deferred to WSL/CI** per Norton + no-Docker — and per the standing rule that §8 hardening lands before any real strategy is activated. |
| Method | **Executed** (not static): pytest with `--cov-branch`, the migration round-trip on a copy of the dev DB, the three coverage gates, the 5 shell invariants + ADR 0002 + audit-immutability tests, mypy, ruff, and the frontend typecheck/lint/vitest were all run on the dev box. |

> **The v0.2 doc was candid that §7 was written against an imagined schema**
> (a `backtests` table, `OrderSubmissionResult`, `BrokerPosition`, strategies
> with an `account_id`). It reconciled to live code. The deviations below are
> that adjustment, executed.

---

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 7.1 | `StrategyStatus.PENDING_LIVE` + `live_activation_initiated_at` + audit actions | ✅ `PENDING_LIVE = "pending_live"` added between PAPER and LIVE; **excluded** from `ACTIVE_STRATEGY_STATUSES`. Column `live_activation_initiated_at` added. Five UPPER audit actions added (INITIATED / CANCELED / LIVE_ACTIVATED / DEACTIVATED / `LIVE_ACCOUNT_CREATED`). |
| 7.2 | Migration | ✅ `e1f6b4c9a8d3` (down-revision `d5a9b3e7c2f1`); `batch_alter_table` for SQLite; round-trips on a DB copy. |
| 7.3 | Reason codes | ✅ `AGENT_LIVE_DISABLED`, `STRATEGY_ID_REQUIRED`, `STRATEGY_NOT_FOUND`, `STRATEGY_PENDING_LIVE`, `STRATEGY_NOT_LIVE` added to `app/risk/reason_codes.py`. |
| 7.4 | `ActivationService` | ✅ `check_prerequisites` (6 prereqs), `status`, `initiate` (typed name + TOTP + all prereqs re-checked), `cancel` (frictionless), `complete_pending` (idempotent, 24h), `deactivate` (optional liquidation via MANUAL closing orders). `ACTIVATION_COOLDOWN_HOURS=24`, `RECENT_BACKTEST_WINDOW_DAYS=7`. |
| 7.5 | OrderRouter live guard lifted | ✅ §1 `BrokerModeError` raise **removed**; replaced by `_live_guard_reject_reason(req)` → MANUAL allowed; STRATEGY allowed only if status LIVE; AGENT → `AGENT_LIVE_DISABLED`; returns a typed `REJECTED` Order (no raise). `LIVE_ORDER_SUBMITTED` audit on every reachable live path (ephemeral-reject, risk-reject, broker-reject, success). `_router_token` discipline untouched; **paper byte-identical** (existing order/risk suite green). |
| 7.6 | LIVE account creation TOTP-gated | ✅ `POST /api/v1/accounts` mode=live now requires `totp_code` (400 if absent, 401 if invalid via `verify_code`); `LIVE_ACCOUNT_CREATED` audit on success. |
| 7.7 | POST /orders extended for live | ✅ optional `account_id` (ownership-checked → 404), `source`, `strategy_id` added to `OrderCreateRequest`; threaded as `source_type` / `source_id`. Defaults to the paper account + MANUAL (back-compatible). |
| 7.8 | Activation endpoints | ✅ `GET /strategies/{id}/activation`, `POST .../activate`, `POST .../activate/cancel`, `POST .../deactivate`. |
| 7.9 | Frontend | ✅ `ActivationWizard` (3-step: prerequisites → review → confirm+TOTP), `ActivationCountdown`, `DeactivationModal`, `Settings/Accounts` LIVE-creation flow; `pending_live` added to the status union + `StatusBadge`; wired into the strategy detail page. |
| 7.10 | Tests | ✅ **36 new tests** (19 service + 9 endpoint + 8 router-level live-path) + repurposed §1/§2/§6 BrokerModeError tests to the new reject-not-raise behavior. |
| 7.11 | Scheduler completion job | ✅ `run_activation_completion` wired via `scheduler.add_job(..., interval 60s, id="activation_completion", max_instances=1, coalesce=True)`; idempotent (`< cutoff`). |
| 7.12 | Runbook | ✅ `docs/runbook/activation.md`. |
| — | 5 shell invariants + ADR 0002 + audit-immutability | ✅ all green. |
| — | ADR 0005 (24h cooldown) | ✅ recorded at `docs/adr/0005-activation-cooldown.md`. |

---

## Deliberate deviations (as-built vs the v0.2 plan)

The v0.2 §7 was written against an imagined schema; reconciled to live code and
**executed**:

- **No `backtests` table** — the "recent backtest" prerequisite checks for a
  `BacktestResult` row in the last 7 days. (A result row means a backtest ran;
  the workbench gates on engagement, not on quality — that's the user's call.)
- **Strategies have no `account_id`** — the strategy's live account is resolved
  by `user_id` + mode (`_resolve_strategy_account`), not read off the strategy.
- **`OrderStatus` has no `ACCEPTED`; no `OrderSubmissionResult` / `BrokerPosition`
  types** — the router returns `Order`; the guard returns an ephemeral `REJECTED`
  Order via the existing `_ephemeral_rejected_order_with_reason` helper.
- **The lifted guard REJECTS, it does not raise.** §1/§6 tests that asserted a
  raised `BrokerModeError` were repurposed: AGENT_PROPOSAL+LIVE now returns
  `REJECTED` / `AGENT_LIVE_DISABLED` (still "refused before risk/registry");
  STRATEGY+PAPER-status returns `STRATEGY_NOT_LIVE`; the confirmation path falls
  through to risk.
- **Liquidation uses MANUAL source + auto `confirmation_text = symbol`** (not
  STRATEGY) — so closing orders work for both LIVE and HALTED strategies and are
  not blocked by the §7 strategy-status guard or the §6 cooldown, while still
  passing the full risk engine and being audited.
- **Live-path tests are router-level.** `app.state.order_router` is `None` under
  the `client` fixture (`WORKBENCH_ALPACA_STARTUP_ENABLED=0`), so the lifted
  guard is tested by constructing an `OrderRouter` with a non-paper stub adapter
  — same pattern as the §6 live-safety tests. One API-level test covers the
  LIVE-account-TOTP path.
- **Audit action + reason-code conventions** follow the existing UPPER
  `AuditAction` enum and the typed `ReasonCode` enum, not the doc's lowercase.
- **TOTP re-verification on initiate** (the doc only mentioned the typed name):
  the 14-day session cookie vastly outlives a 30s code, so initiating live
  activation re-checks the code as a session-hijack defense.

---

## Findings / punch list

- [ ] **Live runtime smoke — deferred (real money).** The full lifecycle has
  **in-suite** coverage (service + endpoint + router level), but the live
  end-to-end (create LIVE account → run backtest → initiate → wait 24h → submit a
  real live order → deactivate+liquidate) was **not** run: Norton blocks
  `data.alpaca.markets`, there's no local Docker stack, and — most importantly —
  **§8 production hardening lands before any real strategy is activated.** The
  runbook says so explicitly. **Action:** run in WSL/CI against paper-as-live,
  and do the real-money walkthrough only post-§8.
- [ ] **Scheduler completion job not exercised against a running scheduler in
  tests** — `run_activation_completion` is unit-tested directly (idempotent, 24h
  boundary); the APScheduler wiring is verified by lifespan import + the job
  registering. The 60s tick itself is observed only at runtime.
- [ ] **`Settings/Accounts` LIVE-creation page has no vitest** — it compiles
  (tsc) and lints clean; the creation path is covered by the backend
  TOTP-gated-account test. A component test can follow.

---

## Deferred gates — require a live stack (run in a working / non-Norton env)

- [ ] Live order submission against a real (or paper-as-live) Alpaca account.
- [ ] The 24h → LIVE scheduler transition observed end-to-end.
- [ ] Migration on the real prod DB (verified here on a copy).
- [ ] 5 CI invariants + ADR 0002 + audit-immutability green on CI for the merge commit.
- [ ] Frontend `vite build` — `tsc` + ESLint + vitest pass locally.

---

## To close Session 7 cleanly (Jay, in a working env)

1. Run the live (or paper-as-live) submission + the 24h scheduler transition.
2. Run the migration against the real DB.
3. Confirm the post-merge CI run is green.
4. **Do not activate a real strategy until §8 ships.**

Next up per the P5 plan: **§8 — production hardening** (the immutable
hash-chained audit log triggers, health/monitoring, backups — the infra that
makes activating a real strategy safe).

---

*P5 Session 7 results v0.1 — recorded 2026-06-01.*
