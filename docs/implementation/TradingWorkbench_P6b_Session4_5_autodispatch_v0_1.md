# Trading Workbench — P6b §4.5: Live Strategy Auto-Dispatch

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-06-05 |
| Phase | P6b — §4.5 (live strategy auto-dispatch; prerequisite for §5) |
| Session | §4.5 of P6b (inserted between §4 and §5) |
| Predecessor | `p6b-session4-eval-harness-complete` (`6f970e6`) |
| Successor | `TradingWorkbench_P6b_Session5_optin_v0_1.md` (unblocked once this ships) |
| Governing ADR | **ADR 0015 — Live strategy auto-dispatch** (`Docs/adr/0015-live-strategy-auto-dispatch.md`) |
| Repository | github.com/jayw04/AI-TRADING-APP |
| Scope | Wire the engine to dispatch a `LIVE` strategy's orders to the live account, behind a default-off global master switch, with a coherent activation→registration lifecycle. |
| Estimated wall time | 5–7 hours (touches the live order path; ≥2h walk-away) |
| Tag on completion | `p6b-session4-5-autodispatch-complete` |
| Out of scope | See §"What this session does NOT do" |

---

## Why this session exists

P5 §7 built the live-trading *toggle* (activation ceremony + the OrderRouter live guard) but never wired the engine to *produce* live orders: `engine.register()` hardcodes the paper account for every strategy, and the activation-completion job flips `PENDING_LIVE → LIVE` without registering the strategy for dispatch. So a `LIVE` strategy's automatic orders go to paper (or don't dispatch at all). P6b §5 (LLM-driven live opt-in, ADR 0006 v2) presupposes a real live-dispatch path. §4.5 builds that path — the platform's first capability where software places a real-money order without a human confirming it — behind the safety envelope ADR 0015 establishes.

## What this session ships

1. Engine resolves the dispatch account by **status** (`LIVE` → live, `PAPER`/`PAPER_VARIANT` → paper).
2. A default-off global master switch `LIVE_AUTODISPATCH_ENABLED` (durable in `system_config`, mirroring `app/risk/halt.py`) that gates all live auto-dispatch; a `LIVE` strategy's submit is wrapped so that, while off, its automatic orders are suppressed before the broker.
3. A coherent activation→registration lifecycle: entering `LIVE` (re-)registers against the live account; entering `PENDING_LIVE` / leaving `LIVE` unregisters.
4. A new audit action `LIVE_AUTODISPATCH_ENABLED_CHANGED` (the operator flip).
5. An audited operator endpoint to read/flip the switch + a minimal Settings toggle (zero-dep).
6. A CI invariant/test asserting the engine resolves account by status and the switch defaults off.
7. Paper smoke stays byte-identical (the load-bearing P5 §7 assertion carries forward).

## Prerequisites

- `p6b-session4-eval-harness-complete` (`6f970e6`) merged.
- **ADR 0015 accepted.** This session builds against its envelope; do not start code until it is accepted.
- The user has a live Alpaca account row (`Account.mode == live`) for live dispatch to resolve. (Norton blocks live Alpaca calls locally — live broker submission is verified on a non-Norton stack; the dispatch wiring + suppression are unit-tested with a fake adapter.)

---

## Detailed work

### §4.5.1 — Engine: resolve the dispatch account by status

`app/strategies/engine.py::register()` (currently lines ~189-197 hardcode paper). Branch on `row.status`:

```python
wants_live = row.status == StrategyStatus.LIVE
mode = AccountMode.live if wants_live else AccountMode.paper
account = (
    await session.execute(
        select(Account).where(
            Account.user_id == row.user_id,
            Account.broker == "alpaca",
            Account.mode == mode,
        )
    )
).scalars().first()
if account is None:
    # A LIVE strategy with no live account cannot dispatch → ERROR (not a silent
    # fallback to paper, which would place orders on the wrong account).
    await self._mark_error(session, row, f"no_{mode.value}_account")
    await session.commit()
    raise StrategyLoadError(f"no {mode.value} account for user_id={row.user_id}")
```

`PAPER` and `PAPER_VARIANT` keep the exact current path (paper). This preserves the §4 harness (Mode A = `PAPER_VARIANT` → paper) and the "paper byte-identical" property.

### §4.5.2 — The master switch + the suppression wrap

**Flag** (`app/services/live_autodispatch.py`, new — mirrors `app/risk/halt.py`, reuses `system_config`, **no migration**):

```python
LIVE_AUTODISPATCH_KEY = "trading.live_autodispatch_enabled"

async def is_live_autodispatch_enabled(session) -> bool:
    row = (await session.execute(
        select(SystemConfig).where(SystemConfig.key == LIVE_AUTODISPATCH_KEY)
    )).scalars().first()
    return _truthy(row.value if row else None)   # absent → False (default OFF)

async def set_live_autodispatch_enabled(session, enabled: bool, *, actor_user_id: int) -> None:
    # upsert "1"/"0"; audit LIVE_AUTODISPATCH_ENABLED_CHANGED; caller commits.
```

**Suppression wrap** (same module). For a `LIVE` strategy, the engine binds `submit_order_fn` to:

```python
def make_live_autodispatch_submit_fn(*, strategy_id, real_submit, session_factory) -> SubmitFn:
    async def _submit(order_request):
        async with session_factory() as session:
            if not await is_live_autodispatch_enabled(session):
                logger.warning("live_autodispatch_suppressed", strategy_id=strategy_id,
                               symbol=order_request.symbol_ticker)
                return _ephemeral_suppressed_order(order_request)  # not sent to broker
        return await real_submit(order_request)
    return _submit
```

Checked **per order** (not at register time) so flipping the switch off halts dispatch on the very next order without re-registering. Manual live orders (`OrderSourceType.MANUAL`, Trade page) never pass through this wrap — they go straight to `OrderRouter.submit` with a human-confirmed live `account_id`, and are unaffected by the switch (ADR 0015 decision 3).

In `engine.register()`, after resolving the account:

```python
submit_order_fn: Any = self._order_router.submit
if row.status == StrategyStatus.LIVE:
    submit_order_fn = make_live_autodispatch_submit_fn(
        strategy_id=row.id, real_submit=self._order_router.submit,
        session_factory=self._session_factory,
    )
# (the §4 mode_a harness wrap and the future §5 LLM gate compose around this)
```

> **Composition note for §5:** the §5 LLM gate wraps *inside* this (master-switch check outermost, so an off switch skips the LLM call entirely — no cost, no live order). The §5 doc's §5.4 threads `make_live_llm_submit_fn(real_submit=make_live_autodispatch_submit_fn(...))`.

### §4.5.3 — Activation → registration lifecycle

- **`ActivationService.complete_pending`** (`PENDING_LIVE → LIVE`, the cron path): after setting `LIVE` and committing, the **completion job** (`app/jobs/activation_completion.py`) calls `engine.register(strategy_id)` so the strategy binds the live account and begins dispatching. (The service stays engine-agnostic; the job owns the engine handle, mirroring the §2/§4 endpoint-owns-engine pattern.)
- **`ActivationService.initiate`** (`PAPER → PENDING_LIVE`): if the strategy was running on paper, `engine.unregister(strategy_id)` so it stops paper-dispatching during the 24h cooldown (`PENDING_LIVE ∉ ENGINE_RUNNABLE_STATUSES`). The endpoint owns the engine handle.
- **Boot resume** (`lifespan.py:439`): already resumes `ENGINE_RUNNABLE_STATUSES` (incl. `LIVE`); with §4.5.1 those now correctly bind the live account.
- **Deactivate/halt** (already unregister): unchanged, now also drops the live binding.

### §4.5.4 — Audit

Add `LIVE_AUTODISPATCH_ENABLED_CHANGED` to `AuditAction`. Payload `{enabled, actor_user_id}`. **Runbook scenario** added to `docs/runbook/agent.md` (the new-AuditAction-needs-a-runbook convention). Suppressed live orders (switch off) are **logged, not audited** (a spinning live strategy would flood the chain — same reasoning as the per-strategy cooldown rejection in `router.py`).

### §4.5.5 — Operator endpoint + minimal Settings toggle

- `app/api/v1/live_autodispatch.py` (new, off the P2 gate): `GET /system/live-autodispatch` → `{enabled}`; `POST /system/live-autodispatch` body `{enabled, totp_code}` → flips it (TOTP-gated — it is an account-level safety control), audits, returns `{enabled}`. Register in `app/api/v1/__init__.py`.
- Frontend: a single toggle in the Settings page ("Enable live strategy auto-dispatch") with the risk copy + TOTP entry; zero-dep, react-query. Off by default; flipping shows a confirmation. (This is the only UI — the per-strategy activation UI already exists.)
- MCP: optional read `workbench_live_autodispatch_status` (defer if it widens scope; not required for §5).

### §4.5.6 — Tests + invariant

- Unit (engine): a `LIVE` strategy binds the **live** account; `PAPER`/`PAPER_VARIANT` bind paper; a `LIVE` strategy with no live account → `ERROR`.
- Unit (suppression): switch off → a `LIVE` strategy's order is suppressed (never reaches the fake adapter); switch on → it reaches `OrderRouter.submit`. Manual live order is unaffected by the switch.
- Unit (flag): default absent → `False`; set/clear round-trips; the flip audits.
- Unit (lifecycle): `complete_pending` → strategy registered; `initiate` → paper instance unregistered.
- Invariant/test `check_engine_account_by_status` (a pytest is sufficient; a shell invariant if we want CI-level enforcement): asserts the engine's account resolution is status-branched and the master switch default is off. *Implementer's call whether this rises to a shell invariant or a high-visibility test; default = a clearly-named test in `tests/strategies/`.*
- Full battery: pytest, ruff, mypy, 3 coverage gates, all shell invariants, vitest.

---

## Manual smoke

1. Master switch defaults off: `GET /system/live-autodispatch` → `{enabled: false}`.
2. With a `LIVE` strategy registered, trigger a signal → order is **suppressed** (logged `live_autodispatch_suppressed`, not sent); paper smoke for a `PAPER` strategy is byte-identical.
3. `POST /system/live-autodispatch {enabled: true, totp_code}` → audited `LIVE_AUTODISPATCH_ENABLED_CHANGED`.
4. Trigger the `LIVE` strategy's signal → order now routes to the **live** account (verified against a fake/paper adapter locally; real Alpaca live on a non-Norton stack), through the risk engine + circuit breaker.
5. Flip the switch back off → the next order is suppressed immediately (no re-register).
6. **Load-bearing assertion:** a `PAPER` strategy's path is byte-identical to today; a `LIVE` strategy never reaches the live broker while the switch is off; manual live orders (Trade page) work regardless of the switch.

## Walk-away discipline

**≥ 2 hours** (live order path). Honor it even though paper is byte-identical — the change is live-money behavior.

## What this session does NOT do

- **No LLM anywhere** — that's §5. §4.5 is purely about *where deterministic live orders go*.
- **No per-strategy auto-dispatch flag** — `LIVE` status is the authorization (ADR 0015 decision 2).
- **No live-scoped risk limits** — the existing risk engine + circuit breaker bound every order; live-scoped caps are a possible future (ADR 0015 re-eval trigger), not §4.5.
- **No change to manual live trading** (Trade page) — untouched; the switch doesn't gate it.
- **No new account model** — one live account per user (the existing `user_id + mode` resolution).
- **No multi-account / account-selection UI.**

## Notes & gotchas

1. **Default OFF is load-bearing.** Merging §4.5 must change *nothing* in production until an operator flips the switch. The flag absent → `False` (mirror `halt.py`'s `_truthy(None)`); paper byte-identical; manual live untouched.
2. **Check the switch per order, not per register** — so an off-flip halts instantly without re-registering every live strategy.
3. **A `LIVE` strategy with no live account is `ERROR`, not a paper fallback.** Silently dispatching a "live" strategy to paper would be a worse failure than refusing.
4. **The suppression wrap composes with §5's LLM gate** (master switch outermost). Build the wrap as a standalone factory so §5 nests cleanly.
5. **Reuse `system_config` + the `halt.py` pattern** — do not invent a new flags table.
6. **Endpoint flip is TOTP-gated** — it's an account-level safety control; treat it like activation.
7. **Norton:** real live Alpaca submission can't be exercised locally; unit-test the dispatch + suppression with a fake adapter and verify the live broker leg on a non-Norton stack (carry the standing blocker).
8. **The §4 harness is unaffected** — Mode A (`PAPER_VARIANT`) and Mode B (`IDLE` bucket) resolve paper; invariant #12 untouched.
