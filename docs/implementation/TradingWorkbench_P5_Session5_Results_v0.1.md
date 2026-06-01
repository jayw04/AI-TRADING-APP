# P5 Session 5 — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-31 |
| Phase | P5 §5 — Live-Mode Risk Gates (companion to `TradingWorkbench_P5_Session5_v0.2.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#43** — branch `feat/p5-session5-risk-gates`; tag **`p5-session5-complete`** |
| Built against | `main` at `p5-session4-complete` (`00f0b5e`) |
| Verdict | **GO.** All §5 sections implemented and **executed** locally: schema + migration, circuit breaker, PDT analyzer, buying-power checker, RiskEngine integration, endpoints, audit + WS routing, frontend, ADR 0004, runbook. Full backend suite green; risk-engine branch gate passes; mypy/ruff clean; frontend tsc + ESLint clean. Live-runtime smoke (§5.11 trip/reset + paper baseline) deferred to WSL/CI per the standing Norton + no-Docker posture. |
| Method | **Executed** (not static): pytest with `--cov-branch`, the migration upgrade/downgrade/upgrade round-trip against a copy of the dev DB (incl. ORM verification the seeded LIVE row is found), the risk/p2/p3 coverage gates, the 5 shell invariants + ADR 0002 test, mypy, and the frontend typecheck/lint were all run on the dev box. |

> **Decisions confirmed with the developer before implementation** (the v0.2 doc's
> code sketches conflicted with the live schema in several places): (A) map
> strategies→account via `user_id` + status↔mode (strategies have no
> `account_id`); (B) keep both the existing global daily-loss halt and the new
> account-scoped breaker (compose, per the risk-engine skill); (C) implement and
> document deviations here (the Session 4 pattern).

---

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 5.0 | Shared `ensure_aware` helper | ✅ `app/utils/time.py`; `stub.py::_aware` + `credential_store.py::_ensure_aware` refactored to import it |
| 5.1 | Schema + migration | ✅ `accounts.circuit_breaker_tripped_at`, `risk_limits.max_orders_per_day`; `StrategyStatus.HALTED` already existed; migration `c4d8e2f1a6b9` seeds a LIVE GLOBAL risk_limits row + backfills PAPER `max_orders_per_day=200`. Upgrade/downgrade/upgrade round-trip verified on a DB copy; **ORM-verified the seeded LIVE row is found by the engine** |
| 5.2 | CircuitBreakerService | ✅ status/check/trip/reset; atomic trip (timestamp + HALT account's active strategies + audit + publish, single commit); typed-label reset; idempotent |
| 5.3 | PdtAnalyzer | ✅ position-walk day-trade detection (joins Symbol for ticker), broker equity, warn-at-3 |
| 5.4 | BuyingPowerChecker | ✅ LIVE-only, worst-case notional per order type, sells exempt, fail-open |
| 5.5 | RiskEngine integration | ✅ per-day cap + buying-power (LIVE) + circuit-breaker (last) added to `evaluate()`; constructor gains optional `broker_registry`/`bar_cache`/`bus`; lifespan reorders to inject; **existing global daily-loss halt left intact** |
| 5.6 | Endpoints | ✅ `GET/PUT /risk-limits`, `GET /accounts/{id}/risk-state`, `POST /accounts/{id}/risk/reset-circuit-breaker`; wired via `app/api/v1/__init__.py` (no double prefix) |
| 5.7 | Audit actions + WS | ✅ `CIRCUIT_BREAKER_TRIPPED/RESET`, `RISK_LIMITS_UPDATED` in `app/audit/logger.py`; `system.circuit_breaker` added to `_BUS_TOPICS` |
| 5.8 | Frontend | ✅ `api/risk.ts`, `RiskStateBanner.tsx` (breaker + PDT, typed-label reset modal), `Settings/RiskLimits.tsx`, routes + Settings links |
| 5.9 | Tests | ✅ **38 new tests** (12 breaker + 6 PDT + 7 buying-power + 6 endpoint + 7 engine-gate + edge-coverage); full suite green; risk gate `engine.py` branch-rate ≥0.85; new risk modules ≥0.96 branch / ≥0.99 line |
| 5.10 | ADR 0004 | ✅ `docs/adr/0004-circuit-breaker-hard-halt.md` (hard-halt decision + the compose-with-global-halt note) |
| 5.12 | Runbook | ✅ `docs/runbook/risk-gates.md` (four gates + new audit actions + operator response) |
| — | `_router_token` discipline | ✅ new gates call only adapter *read* methods; `tests/test_adr_0002_invariant.py` green without edit |

---

## Deliberate deviations (as-built vs the v0.2 plan)

The v0.2 "13 drift corrections" missed several schema mismatches; corrected to
live code and **executed**:

- **Strategy→account mapping.** `strategies` has no `account_id` (deferred to
  §7). The breaker HALTs strategies via `user_id` + status↔mode (PAPER-status →
  paper account, LIVE → live). Verified by a test that a LIVE-status strategy and
  another user's strategy are NOT halted when a paper account trips.
- **Realized PnL.** `Fill` has no `signed_direction`; realized PnL joins
  `Fill→Order` and signs by `Order.side` (BUY = cash out, SELL = cash in).
- **Unrealized PnL.** Read from the local `positions` table (`sum(unrealized_pl)`),
  not a broker call — keeps the engine DB-bound (its docstring promise).
- **Enum storage.** `SQLEnum` persists the enum **name** (`'GLOBAL'`, `'PAPER'`,
  `'BUY'`), not the value. The migration's raw-SQL seed uses `scope_type='GLOBAL'`
  (the doc's lowercase `'global'` would have made the seeded LIVE row invisible to
  the engine — caught by ORM verification). All ORM comparisons use enum members,
  never `.value`.
- **AuditLogger.** Lives in `app.audit` (not `app.db.enums`/`app.services`) and
  `write()` is **sync** (caller commits) — the doc's `await AuditLogger.write` and
  import paths were wrong.
- **`StrategyStatus.HALTED`** already existed (StrEnum) — §5.1.3 was a no-op.
- **Existing global daily-loss halt** (`app/risk/halt.py`, RiskEngine step 9) —
  the doc was unaware of it. Kept (compose); documented in ADR 0004.
- **Endpoint wiring** via `app/api/v1/__init__.py` with no extra prefix (the doc's
  `prefix="/api/v1"` would double it).
- **Buying-power gate is dormant in §5** — the router's `BrokerModeError`
  short-circuits LIVE orders before the engine; the gate is implemented + tested
  for §7. `bar_cache` is wired in §7 (passed `None` now).

---

## Findings / punch list

- [ ] **§5.11 live-runtime smoke — deferred (no committed evidence).** The
  trip-and-reset flow and the load-bearing paper-baseline (byte-identical chains
  at the default $2,000 paper daily-loss limit) have **in-suite** coverage but no
  live curl/diff (Norton + no Docker). **Action:** run §5.11 in WSL/CI.
- [ ] **PAPER `max_orders_per_day=200` backfill changes behavior.** Existing paper
  limits were unlimited; the migration sets 200. Paper strategies submitting >200
  orders/day will start hitting `MAX_ORDERS_PER_DAY`. Raise via Settings → Risk
  Limits if needed.
- [ ] **Two daily-loss mechanisms now coexist** (global `system_config` halt +
  account breaker). Defense in depth for §5; a future ADR may consolidate them.
- [ ] **DST:** the "today" window is a fixed -5h UTC offset; off by one hour ~7
  months/year (Notes & Gotchas #1). P5+ uses `zoneinfo`.

---

## Deferred gates — require a live stack (run in a working / non-Norton env)

- [ ] **§5.11** trip → reject → reset → strategies-stay-HALTED → paper-baseline.
- [ ] **Migration on the real prod DB** with the master key exported (verified
  here only on a copy).
- [ ] **Eight CI invariants green on CI** for the merge commit.
- [ ] **Frontend `vite build`** — `tsc --noEmit` + ESLint pass locally.

---

## To close Session 5 cleanly (Jay, in a working env)

1. Run §5.11; note the results (trip on a tightened limit, reject, reset with
   typed label, strategies stay HALTED, paper baseline unchanged).
2. Run the migration against the real DB; confirm the LIVE risk_limits row + the
   PAPER `max_orders_per_day=200` backfill.
3. Confirm the post-merge CI run is green.

Next up per the P5 plan: **§6 — live order safety** (the session doc is
`TradingWorkbench_P5_Session6_v0.1.md`; expect v0.1 drift — verify against live
code first).

---

*P5 Session 5 results v0.1 — recorded 2026-05-31.*
