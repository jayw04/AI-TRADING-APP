# P6b Session 4.5 — Live strategy auto-dispatch — Results

| Field | Value |
|---|---|
| Document version | v0.1 (execution results) |
| Date | 2026-06-05 |
| Phase | P6b — §4.5 (live strategy auto-dispatch; prerequisite for §5) |
| Governing ADR | **ADR 0015 — Live strategy auto-dispatch** (Accepted 2026-06-05) |
| Plan doc | `TradingWorkbench_P6b_Session4_5_autodispatch_v0_1.md` |
| Predecessor | `p6b-session4-eval-harness-complete` (`6f970e6`) |
| Tag | **`p6b-session4-5-autodispatch-complete`** (`d446778` squash merge → moved to the §4.5 todo commit) |
| Shipped as | PR **#64** — branch `feat/p6b-session4-5-autodispatch`; squash-merged `d446778` |
| Verdict | **GO.** The engine now dispatches LIVE strategies to the live account behind a default-off master switch. Full backend (949/9 skip/0 fail) + frontend (vitest 125) suites + mypy + ruff + tsc + eslint + 3 coverage gates + all 9 shell invariants green. No migration. |

## Why this session existed (a §5 blocker)

Implementing §5 (LLM-driven live opt-in, ADR 0006 v2) surfaced that the live path it presupposes did not exist: `engine.register()` resolved the **paper** account for every strategy and **forced `status` to `PAPER`**, so a `LIVE` strategy's automatic orders went to paper (or didn't dispatch at all). The OrderRouter's STRATEGY-on-LIVE guard was dead code for engine-dispatched orders. Surfaced as a stop-the-PR finding; the owner chose to build the real live path first (ADR 0015), then resume §5 on top.

## What shipped

- **Engine account-by-status** (`engine.py`): `LIVE` → live account, `PAPER`/`PAPER_VARIANT` → paper. `register()` now **preserves `LIVE`** (the `run_status` block forced `PAPER` pre-§4.5 — the root cause). A `LIVE` strategy with no live account → `ERROR` (not a silent paper fallback). The `strategy.status_changed` event publishes `run_status`, not a hardcoded `PAPER`.
- **Master switch** (`app/services/live_autodispatch.py`, new): `LIVE_AUTODISPATCH_ENABLED` durable in `system_config` (key `trading.live_autodispatch_enabled`), default **OFF** — mirrors `app/risk/halt.py`, **no new table/migration**. `make_live_autodispatch_submit_fn` wraps a LIVE strategy's submit and **suppresses automatic orders while off** (returns a non-persisted `REJECTED` order, reason `LIVE_AUTODISPATCH_DISABLED`), checked **per order** so an off-flip halts instantly. Manual live orders bypass the wrap. Built as a standalone factory so **§5's LLM gate nests inside** (master switch outermost).
- **Activation lifecycle** coherent: `run_activation_completion` takes the engine and `register()`s a now-`LIVE` strategy (binds the live account); the `activate` endpoint `unregister()`s the paper instance during the 24h cooldown. `lifespan.py` threads `strategy_engine` into the completion cron.
- **Audit + safety**: new `AuditAction.LIVE_AUTODISPATCH_ENABLED_CHANGED` (operator flip; payload `enabled` + `actor_user_id`) + an on-call runbook scenario ("My LIVE strategy isn't placing any orders"); `ReasonCode.LIVE_AUTODISPATCH_DISABLED`. Suppressed orders are logged, not audited (volume).
- **Endpoint + UI**: TOTP-gated `GET`/`POST /api/v1/system/live-autodispatch`; a zero-dep Settings → Live Trading toggle (`LiveTrading.tsx`, `liveAutodispatch.ts`) with the risk copy + TOTP modal.
- **ADR 0015** (Accepted): `LIVE` status is the authorization (reuse the activation ceremony); global master switch default-off; full Rationale / Consequences / Alternatives / Re-evaluation triggers.

## Key implementation findings (vs the v0.1 plan)

1. **`register()` forced `PAPER`** — the plan named the account-resolution hardcode but not the `run_status` overwrite (lines 299–314). Both had to change; without preserving `LIVE`, a live strategy would flip to `PAPER` on registration. (The `status_changed` event's hardcoded `PAPER` was a third spot.)
2. **The suppression wrap reuses the OrderRouter's `_ephemeral_rejected_order_with_reason`** (imported lazily to avoid a module cycle) rather than inventing a new ephemeral-order shape.
3. **The engine test asserts via `running.instance.ctx.account_id`** (the `Strategy.ctx` is public) — LIVE→live(2), PAPER→paper(1), LIVE-without-live-account→`ERROR`.

## Safety posture

**Default-off is load-bearing**: merging §4.5 changes nothing in production until an operator flips the switch (TOTP-gated, audited). Paper behavior is byte-identical. The switch is the staged-rollout gate and a single instant halt for all live auto-dispatch, distinct from the per-account loss-triggered circuit breaker. `LIVE` status is the only authorization — no per-strategy flag.

## Verification

- **Backend**: `pytest` full suite **949 passed / 9 skipped / 0 failed** (incl. 14 new §4.5 tests: flag/wrap [6], engine account-by-status [3], endpoint [4], completion-registers [2]... net +14). ruff + mypy(174) clean. **No migration** (reuses `system_config`). The one full-suite blip was the documented `test_user_exception_marks_error_and_unregisters` async-ordering flake (passed on re-run + isolated + `test_engine.py` together).
- **Coverage gates**: risk 0.904 / P2 / P3 — pass.
- **Shell invariants**: all 9 green (no new shell invariant — §4.5 uses a clearly-named engine test instead, per the plan).
- **Frontend**: vitest **125 passed** (+3 new), tsc + eslint clean.
- **PR CI**: all 10 jobs green (Python-backend 4m35s). Merged on the owner's "merge on green."

## Deferred (live, non-Norton + creds)

Real live Alpaca submission can't be exercised locally (Norton SSL); the dispatch + suppression are unit-tested with a fake adapter. Verify the live broker leg + the end-to-end `LIVE` strategy placing a real order on a non-Norton stack with the switch on.

## Next

**P6b §5 — LLM-driven live opt-in resumes**, now on a real live path. Its v0.1 doc stands; only §5.4 (engine integration) changes — the §5 LLM gate nests **inside** the §4.5 live-auto-dispatch wrap (master switch outermost → an off switch skips the LLM call entirely). The opt-in lifecycle, gate, invariant #13, audit, budget, cooldown, and UI are unaffected.
