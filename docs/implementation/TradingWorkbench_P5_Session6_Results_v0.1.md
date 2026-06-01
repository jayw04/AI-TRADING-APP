# P5 Session 6 — Results (go / no-go record)

| Field | Value |
|---|---|
| Document version | v0.1 |
| Date | 2026-05-31 |
| Phase | P5 §6 — Live Order Safety (companion to `TradingWorkbench_P5_Session6_v0.2.md`) |
| Repository | `github.com/jayw04/AI-TRADING-APP` |
| Shipped as | PR **#NN** — branch `feat/p5-session6-live-safety`; tag **`p5-session6-complete`** |
| Built against | `main` at `p5-session5-complete` (`49e7ab7`) |
| Verdict | **GO.** Both friction layers (typed-ticker confirmation + per-strategy cooldown) + the LIVE_ORDER_SUBMITTED audit are implemented and **executed**: schema + migration, cooldown service, OrderRouter integration, endpoints, frontend components, runbook. Full backend suite green; risk gate + p2/p3 + mypy + ruff + 8 invariants + ADR 0002 all green; frontend tsc + ESLint + 77 vitest green. Live trip/reset runtime smoke (§6.9) deferred to WSL/CI per Norton + no-Docker. |
| Method | **Executed** (not static): pytest with `--cov-branch`, the migration round-trip on a copy of the dev DB, the coverage gates, the 5 shell invariants + ADR 0002 test, mypy, ruff, and the frontend typecheck/lint/vitest were all run on the dev box. |

> **The v0.2 doc explicitly anticipated execution-surfaced drift** ("before
> pasting any §6.4 OrderRouter code, grep+read the actual shape... adjust the
> integration to match"). It did. The deviations below are that adjustment.

---

## Gates — PASS (executed)

| § | Gate | Result |
|---|---|---|
| 6.1 | `strategies.cooldown_until` + audit actions | ✅ column added; `LIVE_ORDER_SUBMITTED` + `STRATEGY_COOLDOWN_CLEARED` in `app/audit/logger.py` (UPPER convention, not the doc's lowercase); migration `d5a9b3e7c2f1` round-trips on a DB copy |
| 6.2 | `confirmation_text` on request | ✅ added to `OrderRequest` (frozen dataclass) + `OrderCreateRequest`; threaded through the orders endpoint |
| 6.3 | `StrategyCooldownService` | ✅ status / is_in_cooldown / set_cooldown / clear_cooldown; `ensure_aware` coercion; each-failure-resets-window; clear is permission-checked + audit-logged |
| 6.4 | OrderRouter integration | ✅ confirmation gate (MANUAL+LIVE, before the §1 guard) → cooldown gate (STRATEGY) → §1 BrokerModeError; cooldown-set on STRATEGY rejections; `LIVE_ORDER_SUBMITTED` audit on every reachable live attempt; **paper byte-identical** (existing order/risk suite green); `_router_token` untouched |
| 6.5 | Cooldown endpoints | ✅ `GET /strategies/{id}/cooldown` + `POST /strategies/{id}/cooldown/clear` (ownership-checked) |
| 6.6 | LiveOrderConfirmModal | ✅ component ships ready (typed-ticker match, ESC/Enter); **not wired into the Order Ticket** — the ticket disables live submit today, so wiring is §7 |
| 6.7 | CooldownIndicator | ✅ countdown badge + Clear button on the strategy detail page; plain useEffect polling (matches the page; no QueryClientProvider) |
| 6.8 | Tests | ✅ **34 new tests** (14 cooldown service + 14 router-level safety + 6 endpoint); full suite green; new code mypy/ruff clean |
| 6.10 | Runbook | ✅ `docs/runbook/live-order-safety.md` |
| — | Eight invariants + ADR 0002 | ✅ all green |

---

## Deliberate deviations (as-built vs the v0.2 plan)

The v0.2 doc's §6.4/§6.8 were sketches against an imagined order-path shape;
reconciled to live code and **executed**:

- **The POST /orders endpoint hardcodes the user's PAPER account** (no
  `account_id` in the body; `extra="forbid"`; source always MANUAL). So manual
  LIVE orders are **not reachable via the HTTP API** yet (that's §7). The §6
  confirmation/cooldown/audit logic lives in the **OrderRouter** (the ADR-0002
  choke point for both manual and strategy orders) and is tested at the **router
  level** — the doc's §6.8 HTTP tests (POST with `account_id=live`, `reason_code`
  in the body) are impossible against the real API.
- **Real router shape:** `submit(req: OrderRequest) -> Order` (not
  `submit(request, *, current_user_id) -> OrderSubmissionResult`); rejections
  carry `rejection_reason` (string), not `reason_code`; risk is `evaluate()` not
  `check()`; there are no `_reject`/`_record_*` helpers. New helpers added:
  `_confirmation_reject_reason`, `_strategy_id_from_source`,
  `_ephemeral_rejected_order_with_reason`, `_maybe_set_cooldown`,
  `_audit_live_submission`.
- **Confirmation runs BEFORE the §1 `BrokerModeError`** (which RAISES → HTTP 400).
  A MANUAL+LIVE order with no/wrong confirmation now returns a `REJECTED` Order
  (CONFIRMATION_*); with correct confirmation it falls through to the (raised)
  BrokerModeError. The two existing §1 live-refusal tests were updated to pass a
  matching `confirmation_text` so they still reach the BrokerModeError path.
- **`strategy_id` is derived from `source_id`** (strategy orders carry
  `source_id=str(strategy_id)`), not a new request field.
- **Audit action values use the UPPER convention** (`LIVE_ORDER_SUBMITTED`,
  `STRATEGY_COOLDOWN_CLEARED`) to match the existing `AuditAction` enum, not the
  doc's lowercase. `AuditLogger` is sync, in `app.audit`.
- **§6 rejection codes are typed** (`ReasonCode.CONFIRMATION_REQUIRED` /
  `CONFIRMATION_MISMATCH` / `STRATEGY_COOLDOWN`).
- **`LiveOrderConfirmModal` not wired into the Order Ticket** — the ticket
  disables the live submit button today (§1); §7 lifts that and gates the submit
  through the modal. The component ships ready.
- **`CooldownIndicator` uses plain `useEffect` polling**, not React Query — the
  strategy detail page is rendered/tested without a `QueryClientProvider`.

---

## Findings / punch list

- [ ] **§6.9 live runtime smoke — deferred.** Trip-and-reject (confirmation),
  cooldown set/clear, and the LIVE audit stream have **in-suite** coverage at the
  router/endpoint level, but the live curl/diff against a running stack was not
  run (Norton + no Docker). The doc's §6.9 also assumes a LIVE account is
  reachable via the API, which it is not until §7. **Action:** run the
  router-level equivalents in WSL/CI; the full manual-LIVE smoke waits for §7.
- [ ] **Manual LIVE orders are not reachable via the API in §6** (paper-only
  endpoint). The confirmation gate is dormant via the HTTP path until §7 adds
  account selection + lifts BrokerModeError. The logic is in place and tested at
  the router level.
- [ ] **No LIVE_ORDER_SUBMITTED audit on the post-risk/broker paths** — those are
  unreachable for live in §6 (BrokerModeError short-circuits). §7 adds the audit
  there when the guard lifts and the paths become live-reachable.

---

## Deferred gates — require a live stack (run in a working / non-Norton env)

- [ ] **§6.9** the manual-LIVE confirmation flow end-to-end (needs §7's account
  selection) and the cooldown GET/clear smoke.
- [ ] **Migration on the real prod DB** (verified here on a copy).
- [ ] **Eight CI invariants green on CI** for the merge commit.
- [ ] **Frontend `vite build`** — `tsc` + ESLint + vitest pass locally.

---

## To close Session 6 cleanly (Jay, in a working env)

1. Run the cooldown GET/clear smoke + (once §7 lands) the manual-LIVE
   confirmation flow.
2. Run the migration against the real DB.
3. Confirm the post-merge CI run is green.

Next up per the P5 plan: **§7 — activation wizard** (the session that finally
lifts `BrokerModeError`, adds LIVE account selection to the order path, and
wires the LiveOrderConfirmModal). Expect v0.1 drift — verify against live code
first.

---

*P5 Session 6 results v0.1 — recorded 2026-05-31.*
